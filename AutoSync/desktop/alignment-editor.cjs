'use strict';
const {BrowserWindow, dialog, ipcMain, shell, app}=require('electron');
const fs=require('node:fs');
const path=require('node:path');
const {execFile,spawn}=require('node:child_process');
const {pathToFileURL}=require('node:url');
const {randomUUID,createHash}=require('node:crypto');
const {validateSegments,validateTimeline,validateOverlays}=require('./alignment-model.cjs');
const clips=require('./audio-clip-tools.cjs');
const timelineGestures=require('./timeline-gestures.cjs');
const {preparePreviewValues}=require('./preview-request.cjs');

const IMAGE_EXT=['.png','.jpg','.jpeg','.bmp','.webp','.tif','.tiff'];
// FFmpeg f32le output viewed as floats without per-sample reads (copied when unaligned).
const floats=buf=>buf.byteOffset%4===0?new Float32Array(buf.buffer,buf.byteOffset,Math.floor(buf.length/4)):new Float32Array(Uint8Array.from(buf).buffer,0,Math.floor(buf.length/4));
const PROXY_KEEP=12;   // preview proxies kept on disk, newest first
// atempo accepts 0.5-2 per stage; chain stages for 0.25-4x previews.
function tempo(rate){
 const out=[];let r=Number(rate);
 while(r>2){out.push('atempo=2');r/=2;}
 while(r<.5){out.push('atempo=0.5');r/=.5;}
 out.push('atempo='+r.toFixed(6));return out.join(',');
}
function createAlignmentEditor(root,python){
 let editor=null,project=null,exportChild=null,prepareChild=null,lastPrepared=null;
 let proxyChildren=new Set();
 const html=path.join(__dirname,'alignment-editor.html');
 const page=pathToFileURL(html).href;
 const ff=name=>[path.join(root,name+'.exe'),'C:/ffmpeg/bin/'+name+'.exe'].find(p=>fs.existsSync(p))||name;
 const run=(name,args,limit=48*1024*1024)=>new Promise((resolve,reject)=>{
  execFile(ff(name),args,{windowsHide:true,encoding:'buffer',maxBuffer:limit,timeout:180000},(err,out,stderr)=>{
   if(err)reject(Error((stderr||Buffer.from(err.message)).toString().slice(-1300)));
   else resolve(out);
  });
 });
 function trusted(e){
  if(!editor||editor.isDestroyed()||e.sender!==editor.webContents||e.senderFrame?.url!==page)throw Error('Untrusted editor request.');
  if(!project)throw Error('No plan is loaded.');
 }
 const assertTime=x=>{
  x=Number(x);
  if(!Number.isFinite(x)||x<0||x>24*3600)throw Error('Invalid playback time.');
  return x;
 };
 function trackInfo(track){
  if(track==='source')return {file:project.plan.audio,stream:project.plan.audio_stream||0};
  if(track==='target')return {file:project.plan.reference||project.plan.target_video,stream:project.plan.reference_stream||0};
  throw Error('Unknown audio track.');
 }
 function mediaInfo(){
  const p=project.plan;
  const source=p.source_video||p.audio;
  const target=p.target_video||p.reference;
  return {source:source&&fs.existsSync(source)?pathToFileURL(source).href:null,target:target&&fs.existsSync(target)?pathToFileURL(target).href:null};
 }
 // Media imported in Preview & Edit (or already in the plan): probed once; the
 // renderer can only name these files, never arbitrary paths.
 async function probeMedia(file){
  const out=JSON.parse((await run('ffprobe',['-v','error','-show_entries','format=duration:stream=index,codec_type,width,height,disposition','-of','json',file],1024*1024)).toString());
  const streams=out.streams||[];
  const image=IMAGE_EXT.includes(path.extname(file).toLowerCase());
  const video=streams.find(s=>s.codec_type==='video'&&!(s.disposition?.attached_pic));
  const audio=streams.filter(s=>s.codec_type==='audio');
  const duration=image?null:Number(out.format?.duration);
  if(!image&&!(duration>0))throw Error('Cannot read the length of '+path.basename(file));
  if(!video&&!audio.length)throw Error(path.basename(file)+' has no picture or sound.');
  let thumb=null;
  if(video)try{
   const at=image?0:Math.min(Math.max(0,duration*.1),Math.max(0,duration-.1));
   const jpg=await run('ffmpeg',['-v','error','-nostdin',...(at?['-ss',String(at)]:[]),'-i',file,'-map','0:'+video.index,'-frames:v','1','-vf','scale=160:90:force_original_aspect_ratio=decrease','-c:v','mjpeg','-f','image2pipe','pipe:1'],2*1024*1024);
   if(jpg.length)thumb='data:image/jpeg;base64,'+jpg.toString('base64');
  }catch{}
  return {path:file,name:path.basename(file),url:pathToFileURL(file).href,image,duration,hasVideo:!!video,
   hasAudio:audio.length>0,audioStream:0,width:Number(video?.width)||null,height:Number(video?.height)||null,stillSeconds:5,thumb};
 }
 async function registerPlanMedia(){
  project.imports=new Map();
  const files=new Set([...(project.plan.segments||[]),...(project.plan.video_edits?.kept||[]),...(project.plan.video_edits?.v1||[]),...(project.plan.video_overlays||[])].filter(x=>x.media).map(x=>String(x.media)));
  for(const file of files){
   if(!fs.existsSync(file))continue;
   try{project.imports.set(file,await probeMedia(file));}catch{}
  }
 }
 function importedFile(file){
  const info=project.imports?.get(String(file));
  if(!info)throw Error('Unknown imported media.');
  return info;
 }
 function send(kind,payload){
  if(editor&&!editor.isDestroyed())editor.webContents.send('alignment-event',{kind,payload});
 }
 async function open(parent,knownPlan=null){
  if(editor&&!editor.isDestroyed()){editor.focus();return true;}
  let file=knownPlan;
  if(!file){
   const picked=await dialog.showOpenDialog(parent,{title:'Open a previously saved AutoSync alignment plan',properties:['openFile'],filters:[{name:'AutoSync alignment plan',extensions:['json']}]});
   if(picked.canceled)return false;
   file=picked.filePaths[0];
  }
  if(typeof file!=='string'||!path.isAbsolute(file)||!fs.existsSync(file))throw Error('Alignment plan does not exist: '+String(file));
  const value=JSON.parse(await fs.promises.readFile(file,'utf8'));
  if(!value||!Array.isArray(value.segments)||!Number.isFinite(Number(value.duration))||!value.audio)throw Error('The selected file does not contain an AutoSync alignment.');
  validateSegments(value.segments,value.duration);
  if(!fs.existsSync(value.audio))throw Error('The original source audio file is missing: '+value.audio);
  if(!fs.existsSync(value.reference||value.target_video))throw Error('The original target file is missing. Open a plan with valid media paths.');
  project={file,plan:value,outputPlan:null,exporting:false,exported:false};
  editor=new BrowserWindow({parent,width:1450,height:920,minWidth:950,minHeight:690,backgroundColor:'#11151d',title:'AutoSync · Preview & Edit',show:false,webPreferences:{preload:path.join(__dirname,'alignment-editor-preload.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true}});
  editor.removeMenu();
  editor.loadFile(html);
  editor.once('ready-to-show',()=>editor?.show());
  editor.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  editor.webContents.on('will-navigate',e=>e.preventDefault());
  editor.on('closed',()=>{
   if(exportChild)try{exportChild.kill();}catch{}
   for(const child of proxyChildren)try{child.kill();}catch{}
   proxyChildren.clear();exportChild=null;editor=null;project=null;
  });
  return true;
 }

 // Generate an alignment from the selected pair without requiring a saved plan.
 // Uses the existing portable engine via desktop_bridge.py in analyze-only mode.
 async function analyzeAndOpen(parent,job,preferredDirectory,notify=()=>{}){
  if(editor&&!editor.isDestroyed()){editor.focus();return true;}
  if(prepareChild)throw Error('Preview analysis is already running.');
  if(!job||job.task!=='Single episode'||!job.values||typeof job.values!=='object')throw Error('Choose a source and target pair before previewing.');
  if(JSON.stringify(job).length>100000)throw Error('Preview request is too large.');
  const values=preparePreviewValues(job.values);
  for(const field of ['source','target']){
   if(typeof values[field]!=='string'||!path.isAbsolute(values[field])||!fs.existsSync(values[field]))throw Error('Choose a valid '+field+' video.');
  }
  const key=JSON.stringify(values);
  if(lastPrepared?.key===key&&fs.existsSync(lastPrepared.file))return open(parent,lastPrepared.file);
  const location=typeof preferredDirectory==='string'&&path.isAbsolute(preferredDirectory)&&fs.existsSync(preferredDirectory)?preferredDirectory:path.dirname(values.target);
  const selected=await dialog.showOpenDialog(parent,{
   title:'Where should AutoSync save the alignment and edited output?',
   defaultPath:location,
   properties:['openDirectory','createDirectory']
  });
  if(selected.canceled)return false;
  const outputRoot=selected.filePaths[0];
  if(!path.isAbsolute(outputRoot)||!fs.statSync(outputRoot).isDirectory())throw Error('Choose an existing output directory.');
  const output=await fs.promises.mkdtemp(path.join(outputRoot,'AutoSync_Alignment_'));
  values.out=output;
  const request={task:'Single episode',values};
  const [bin,prefix]=python();
  let tail='';
  notify('Preview & Edit analyzes the entire target without automatically trimming the opening/ending or removing video.\n');
  notify('Alignment will be saved in '+output+'\n');
  await new Promise((resolve,reject)=>{
   let done=false;
   function finish(err){
    if(done)return;
    done=true;
    prepareChild=null;
    if(err)reject(err);else resolve();
   }
   const child=spawn(bin,[...prefix,'-u',path.join(root,'desktop_bridge.py')],{
    cwd:root,env:{...process.env,PYTHONIOENCODING:'utf-8',PYTHONUNBUFFERED:'1'},windowsHide:true,stdio:['pipe','pipe','pipe']
   });
   prepareChild=child;
   for(const stream of [child.stdout,child.stderr]){
    stream.setEncoding('utf8');
    stream.on('data',chunk=>{
     const message=String(chunk);
     tail=(tail+message).slice(-5000);
     notify(message);
    });
   }
   child.on('error',err=>finish(Error('Could not start the AutoSync analyzer: '+err.message)));
   child.on('close',code=>finish(code===0?null:Error('Alignment analysis failed (exit '+code+'). Review the log in AutoSync.\n'+tail.slice(-1500))));
   child.stdin.on('error',()=>{});
   child.stdin.end(JSON.stringify(request));
  });
  const file=path.join(output,'plan.json');
  if(!fs.existsSync(file))throw Error('The analyzer finished without saving plan.json to '+output);
  lastPrepared={key,file};
  notify('Alignment saved to '+file+'\n');
  return open(parent,file);
 }
 // Frame rate of the target picture, so frame-step and nudge controls move by
 // exactly one frame (23.976, 25, 29.97 ...). Falls back to 25 fps.
 // Native size (for the plan's crop rectangles) and frame rate of a video.
 async function videoInfo(video){
  if(!video||!fs.existsSync(video))return null;
  try{
   const out=(await run('ffprobe',['-v','error','-select_streams','v:0','-show_entries','stream=width,height,r_frame_rate,avg_frame_rate','-of','json',video],1024*1024)).toString();
   const s=JSON.parse(out).streams?.[0]||{};
   let fps=null;
   for(const key of ['r_frame_rate','avg_frame_rate']){
    const [a,b]=String(s[key]||'').split('/').map(Number);
    if(!fps&&a>0&&b>0&&a/b>5&&a/b<121)fps=a/b;
   }
   return {width:Number(s.width)||null,height:Number(s.height)||null,fps};
  }catch{return null;}
 }
 ipcMain.handle('align-get-plan',async e=>{
  trusted(e);
  const [source,target]=await Promise.all([videoInfo(project.plan.source_video),videoInfo(project.plan.target_video)]);
  if(!project.imports)await registerPlanMedia();
  return {file:project.file,plan:project.plan,media:mediaInfo(),fps:target?.fps||25,videos:{source,target},imports:[...project.imports.values()]};
 });
 ipcMain.handle('align-waveform',async(e,track)=>{
  trusted(e);
  const {file,stream}=trackInfo(track);
  const data=await run('ffmpeg',['-v','error','-nostdin','-i',file,'-map','0:a:'+stream,'-ac','1','-ar','200','-f','f32le','pipe:1'],80*1024*1024);
  const samples=floats(data),count=samples.length;
  // Up to 60000 peaks: fine enough for every zoom the coarse view is used at.
  const step=Math.max(1,Math.ceil(count/60000));
  const peaks=new Float32Array(Math.ceil(count/step));
  let max=.0001;
  for(let i=0,k=0;i<count;i+=step,k++){
   let sum=0,p=0,n=0;
   for(let j=i,e=Math.min(count,i+step);j<e;j++){const v=samples[j];if(v!==v)continue;sum+=v*v;const a=v<0?-v:v;if(a>p)p=a;n++;}
   const x=Math.max(Math.sqrt(sum/Math.max(1,n)),p*.5);peaks[k]=x;if(x>max)max=x;
  }
  for(let k=0;k<peaks.length;k++)peaks[k]=Math.min(1,peaks[k]/max);
  return {peaks,duration:count/200};
 });

 ipcMain.handle('align-waveform-range',async(e,track,start,end)=>{
  trusted(e);
  const {file,stream}=trackInfo(track);
  const from=assertTime(start),to=assertTime(end);
  if(to<=from||to-from>120)throw Error('Waveform range must be between 0 and 120 seconds.');
  const data=await run('ffmpeg',['-v','error','-nostdin','-ss',String(from),'-t',String(to-from),'-i',file,'-map','0:a:'+stream,'-ac','1','-ar','2000','-f','f32le','pipe:1'],8*1024*1024);
  const samples=floats(data),count=samples.length,step=Math.max(1,Math.ceil(count/6000));
  const peaks=new Float32Array(Math.ceil(count/step));
  for(let i=0,k=0;i<count;i+=step,k++){
   let max=0;
   for(let j=i,e=Math.min(count,i+step);j<e;j++){const x=samples[j];const a=x<0?-x:x;if(a>max)max=a;}
   peaks[k]=Math.min(1,max);
  }
  return {start:from,duration:count/2000,peaks};
 });

 // Use the original local video with Chromium's hardware-accelerated player.
 // For unsupported video formats, generate an MP4 proxy once rather than
 // spawning FFmpeg to extract individual frames during playback.
 ipcMain.handle('align-video-proxy',async(e,track)=>{
  trusted(e);
  if(!['source','target'].includes(track))throw Error('Invalid video track.');
  const file=track==='source'?(project.plan.source_video||project.plan.audio):(project.plan.target_video||project.plan.reference);
  if(!file||!fs.existsSync(file))throw Error('Original video is missing.');
  const stat=await fs.promises.stat(file);
  const key=createHash('sha256').update(file+'\0'+stat.size+'\0'+stat.mtimeMs).digest('hex').slice(0,24);
  const dir=path.join(app.getPath('userData'),'AutoSync preview cache');
  await fs.promises.mkdir(dir,{recursive:true});
  const output=path.join(dir,key+'.mp4');
  if(fs.existsSync(output)&&(await fs.promises.stat(output)).size>16384){fs.promises.utimes(output,new Date(),new Date()).catch(()=>{});return pathToFileURL(output).href;}
  await pruneProxies(dir).catch(()=>{});
  const partial=path.join(dir,key+'.'+randomUUID().slice(0,8)+'.part.mp4');
  send('preview-progress',{track,message:'Generating playable proxy for '+track+' (only once per file)…'});
  const args=['-hide_banner','-loglevel','error','-nostdin','-y','-i',file,
   '-map','0:v:0','-vf','scale=640:360:force_original_aspect_ratio=decrease,fps=24',
   '-c:v','libx264','-preset','ultrafast','-threads','2','-crf','33','-pix_fmt','yuv420p',
   '-an','-sn','-dn','-movflags','+faststart',partial];
  await new Promise((resolve,reject)=>{
   let finished=false,errors='';
   const child=spawn(ff('ffmpeg'),args,{windowsHide:true,stdio:['ignore','ignore','pipe']});
   proxyChildren.add(child);
   child.stderr.on('data',chunk=>{errors=(errors+chunk.toString()).slice(-1800);});
   child.on('error',err=>{if(!finished){finished=true;proxyChildren.delete(child);reject(err);}});
   child.on('close',code=>{proxyChildren.delete(child);if(finished)return;finished=true;
     if(code===0)resolve();else reject(Error('Video proxy failed: '+(errors||'FFmpeg exit '+code)));});
  }).catch(async err=>{await fs.promises.rm(partial,{force:true});throw err;});
  await fs.promises.rename(partial,output).catch(async err=>{
   if(fs.existsSync(output))await fs.promises.rm(partial,{force:true});else throw err;
  });
  return pathToFileURL(output).href;
 });
 // Keep the preview cache bounded: the newest PROXY_KEEP proxies; stale partial files go.
 async function pruneProxies(dir){
  const rows=[];
  for(const name of await fs.promises.readdir(dir)){
   const file=path.join(dir,name);
   try{rows.push({file,name,t:(await fs.promises.stat(file)).mtimeMs});}catch{}
  }
  const now=Date.now();
  for(const r of rows)if(r.name.endsWith('.part.mp4')&&now-r.t>24*3600*1000)await fs.promises.rm(r.file,{force:true});
  const done=rows.filter(r=>r.name.endsWith('.mp4')&&!r.name.endsWith('.part.mp4')).sort((a,b)=>b.t-a.t);
  for(const r of done.slice(PROXY_KEEP))await fs.promises.rm(r.file,{force:true});
 }
 // Save the picture at the playhead as a PNG (target, source or imported clip frame).
 ipcMain.handle('align-snapshot',async(e,track,time,media)=>{
  trusted(e);
  if(!['source','target','media'].includes(track))throw Error('Invalid snapshot track.');
  const file=track==='media'?importedFile(media).path:track==='source'?(project.plan.source_video||project.plan.audio):(project.plan.target_video||project.plan.reference);
  if(!file||!fs.existsSync(file))throw Error('The video file is missing.');
  const t=track==='media'&&importedFile(media).image?0:assertTime(time);
  const pick=await dialog.showSaveDialog(editor,{title:'Save frame as image',
   defaultPath:path.join(path.dirname(project.outputPlan||project.file),'frame_'+t.toFixed(3).replace('.','_')+'.png'),filters:[{name:'PNG image',extensions:['png']}]});
  if(pick.canceled||!pick.filePath)return null;
  await run('ffmpeg',['-v','error','-nostdin','-y',...(t?['-ss',String(t)]:[]),'-i',file,'-map','0:v:0','-frames:v','1',path.resolve(pick.filePath)],1024*1024);
  return path.resolve(pick.filePath);
 });
 ipcMain.handle('align-clip-op',(e,op,payload)=>{
  trusted(e);
  if(!payload||JSON.stringify(payload).length>250000)throw Error('Invalid clip edit.');
  // Picture edits change the output length; the renderer sends the current one.
  const duration=payload.duration===undefined?project.plan.duration:Number(payload.duration);
  if(!Number.isFinite(duration)||duration<=0||duration>24*3600)throw Error('Invalid output duration.');
  const rows=validateSegments(payload.segments,duration);
  if(op==='copy')return clips.copyClip(rows,payload.index,payload.inPoint??null,payload.outPoint??null);
  if(op==='paste')return clips.pasteClip(rows,duration,payload.at,payload.clip);
  if(op==='move')return timelineGestures.placeClip(rows,duration,payload.index,payload.at,{copy:!!payload.copy});
  if(op==='slip')return timelineGestures.slipClip(rows,duration,payload.index,payload.delta);
  if(op==='edge')return timelineGestures.trimClip(rows,duration,payload.index,payload.edge,payload.at);
  if(op==='razor')return timelineGestures.splitClip(rows,duration,payload.index,payload.at);
  if(op==='trim-left'||op==='trim-right')
   return clips.trimTo(rows,duration,payload.index,payload.at,op==='trim-left'?'left':'right');
  throw Error('Unknown clip operation.');
 });

 ipcMain.handle('align-frame',async(e,track,time,media)=>{
  trusted(e);
  if(!['source','target','media'].includes(track))throw Error('Invalid preview track.');
  const file=track==='media'?importedFile(media).path:track==='source'?(project.plan.source_video||project.plan.audio):(project.plan.target_video||project.plan.reference);
  if(!file||!fs.existsSync(file))return null;
  const t=track==='media'&&importedFile(media).image?0:assertTime(time);
  const b=await run('ffmpeg',['-v','error','-nostdin',...(t?['-ss',String(t)]:[]),'-i',file,'-map','0:v:0','-frames:v','1','-vf','scale=600:360:force_original_aspect_ratio=decrease','-an','-c:v','mjpeg','-f','image2pipe','pipe:1'],8*1024*1024);
  return b.length?'data:image/jpeg;base64,'+b.toString('base64'):null;
 });
 ipcMain.handle('align-audio',async(e,track,start,duration,speed,media)=>{
  trusted(e);
  const time=assertTime(start),len=Number(duration),rate=Number(speed);
  if(!Number.isFinite(len)||len<=0||len>30||!Number.isFinite(rate)||rate<.25||rate>4)throw Error('Invalid preview duration or playback rate.');
  // Raw 48 kHz stereo s16 PCM, sent as binary (no WAV, no base64): the editor
  // schedules chunks back to back in Web Audio, so playback has no gaps.
  // `len` is output (playback) seconds; `rate` folds in clip speed and preview speed,
  // so len x rate source seconds are read and time-stretched into len seconds.
  if(track==='silence')return new Uint8Array(Math.max(1,Math.round(len*48000))*4);
  const {file,stream}=track==='media'?{file:importedFile(media).path,stream:importedFile(media).audioStream}:trackInfo(track);
  const b=await run('ffmpeg',['-v','error','-nostdin','-ss',String(time),'-t',String(len*rate),'-i',file,'-map','0:a:'+stream,'-af',tempo(rate),'-ar','48000','-ac','2','-f','s16le','pipe:1'],24*1024*1024);
  if(b.length<64)throw Error('No audio at this timestamp.');
  return new Uint8Array(b.buffer,b.byteOffset,b.length-b.length%4);
 });
 ipcMain.handle('align-import',async e=>{
  trusted(e);
  const picked=await dialog.showOpenDialog(editor,{title:'Import media into Preview & Edit',properties:['openFile','multiSelections'],
   filters:[{name:'Video, audio and images',extensions:['mp4','mkv','mov','m4v','avi','webm','ts','m2ts','wmv','mpg','mpeg','mp3','wav','flac','m4a','aac','ogg','opus','wma','ac3','png','jpg','jpeg','bmp','webp','tif','tiff']},{name:'All files',extensions:['*']}]});
  if(picked.canceled)return [];
  if(!project.imports)await registerPlanMedia();
  const added=[],failed=[];
  for(const file of picked.filePaths.slice(0,50)){
   try{const info=await probeMedia(path.resolve(file));project.imports.set(info.path,info);added.push(info);}
   catch(err){failed.push(path.basename(file)+': '+err.message);}
  }
  if(failed.length&&!added.length)throw Error(failed.join('; '));
  return added;
 });
 // Unsaved edits restored from the editor's autosave name files imported in an
 // earlier session: probe them again (existing local media only).
 ipcMain.handle('align-register-media',async(e,paths)=>{
  trusted(e);
  if(!Array.isArray(paths)||paths.length>50)throw Error('Invalid media list.');
  if(!project.imports)await registerPlanMedia();
  const found=[];
  for(const file of paths){
   if(typeof file!=='string'||!path.isAbsolute(file)||!fs.existsSync(file))continue;
   try{const info=await probeMedia(path.resolve(file));project.imports.set(info.path,info);found.push(info);}catch{}
  }
  return found;
 });
 ipcMain.handle('align-save',async(e,segments,timeline,extras)=>{
  trusted(e);
  if(project.exporting)throw Error('Cannot save while export is running.');
  // Picture edits (ripple deletes, imported clips) change length and video pieces.
  const edit=timeline?validateTimeline(timeline,project.plan,file=>importedFile(file)):null;
  const revised=validateSegments(segments,edit?edit.duration:project.plan.duration);
  for(const s of revised)if(s.kind==='media')importedFile(s.media);
  // Save As can choose any drive, directory and name. Its filename stem becomes
  // the new output folder, so rendered media never overwrites another episode.
  if(!project.outputPlan||project.exported){
   const defaultDirectory=path.dirname(project.outputPlan||project.file);
   const suggested='AutoSync_Edited_'+new Date().toISOString().replace(/[:.]/g,'-')+'.json';
   const pick=await dialog.showSaveDialog(editor,{
    title:'Choose edited output name and location (any drive or folder)',
    defaultPath:path.join(defaultDirectory,suggested),
    filters:[{name:'AutoSync output project',extensions:['json']}],
    properties:['createDirectory','showOverwriteConfirmation']
   });
   if(pick.canceled||!pick.filePath)return null;
   const selected=path.resolve(pick.filePath);
   const name=path.parse(selected).name;
   if(!name||name==='.'||name==='..')throw Error('Choose a valid output folder name.');
   const folder=path.join(path.dirname(selected),name);
   if(fs.existsSync(folder))throw Error('An output folder already exists here. Choose another name: '+folder);
   await fs.promises.mkdir(folder,{recursive:false});
   project.outputPlan=path.join(folder,'plan.json');
   project.exported=false;
  }
  const value={...project.plan,segments:revised,source_cuts:[],editor_revision:1,editor_origin_plan:project.file};
  // Markers (output seconds) and review notes travel with the edited plan.
  const marks=Array.isArray(extras?.markers)?extras.markers.map(Number).filter(t=>Number.isFinite(t)&&t>=0&&t<=(edit?edit.duration:project.plan.duration)).slice(0,2000):[];
  if(marks.length)value.markers=marks;else delete value.markers;
  if(extras?.notes&&typeof extras.notes==='object'&&JSON.stringify(extras.notes).length<200000)value.review_notes=extras.notes;
  if(edit){
   value.duration=edit.duration;
   value.video_edits={original_target_duration:project.plan.video_edits?.original_target_duration??project.plan.duration,
    kept:edit.kept,removed:project.plan.video_edits?.removed||[],edited_in_preview:true};
   // Tracks as edited (V1 sequence and V2 clips), so the editor reopens them; export
   // renders `kept`, the flattened picture.
   if(Array.isArray(timeline.v1))value.video_edits.v1=validateTimeline({duration:edit.duration,kept:timeline.v1},project.plan,file=>importedFile(file)).kept;
  }
  const overlays=validateOverlays(extras?.overlays,value.duration,file=>importedFile(file));
  if(overlays.length)value.video_overlays=overlays;else delete value.video_overlays;
  const tracks=extras?.tracks;
  if(tracks&&typeof tracks==='object')value.editor_tracks={locks:Object.fromEntries(['V2','V1','MIX'].map(k=>[k,!!tracks.locks?.[k]])),hidden:{V2:!!tracks.hidden?.V2}};
  // The previous cut-review annotations describe old boundaries, not the edited timeline.
  value.review=[{start:0,end:Math.min(1,value.duration),confidence:'manual',reason:'User-edited sync plan. Verify output joins.'}];
  await fs.promises.writeFile(project.outputPlan,JSON.stringify(value,null,2)+'\n','utf8');
  return project.outputPlan;
 });
 ipcMain.handle('align-export',async(e)=>{
  trusted(e);
  if(project.exporting||exportChild)throw Error('Export already running.');
  if(!project.outputPlan||!fs.existsSync(project.outputPlan))throw Error('Save your edited alignment first.');
  project.exporting=true;
  const [bin,prefix]=python();
  return new Promise((resolve)=>{
   let tail='';
   exportChild=spawn(bin,[...prefix,'-u',path.join(root,'autosync.py'),'--render-plan',project.outputPlan,'--reference-fallback','--allow-uncertain-cuts'],{cwd:root,env:{...process.env,PYTHONIOENCODING:'utf-8',PYTHONUNBUFFERED:'1'},windowsHide:true});
   const child=exportChild;
   child.stdout.on('data',x=>{const s=x.toString();tail=(tail+s).slice(-2000);send('export-log',s);});
   child.stderr.on('data',x=>{const s=x.toString();tail=(tail+s).slice(-2000);send('export-log',s);});
   child.on('error',e=>{tail+='\n'+e.message;});
   child.on('close',code=>{exportChild=null;if(project){project.exporting=false;if(code===0)project.exported=true;}send('export-done',{code,folder:path.dirname(project?.outputPlan||''),log:tail});resolve({code,folder:path.dirname(project?.outputPlan||'')});});
  });
 });
 ipcMain.handle('align-open-folder',async e=>{
  trusted(e);
  if(!project.outputPlan)throw Error('Save the edited plan first.');
  const error=await shell.openPath(path.dirname(project.outputPlan));
  if(error)throw Error(error);
 });
 return {open,analyzeAndOpen,isBusy:()=>Boolean(prepareChild),close(){if(prepareChild)try{prepareChild.kill();}catch{};if(editor&&!editor.isDestroyed())editor.close();}};
}
module.exports={createAlignmentEditor};
