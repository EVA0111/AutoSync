'use strict';
const {BrowserWindow, dialog, ipcMain, shell, app}=require('electron');
const fs=require('node:fs');
const path=require('node:path');
const {execFile,spawn}=require('node:child_process');
const {pathToFileURL}=require('node:url');
const {randomUUID,createHash}=require('node:crypto');
const {validateSegments}=require('./alignment-model.cjs');
const clips=require('./audio-clip-tools.cjs');
const nle=require('./nle-project.cjs');

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
  const values={...job.values};
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
  values.analyze_only=true;
  const request={task:'Single episode',values};
  const [bin,prefix]=python();
  let tail='';
  notify('Analyzing source and target for Preview & Edit. Alignment will be saved in '+output+'\n');
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
 ipcMain.handle('align-get-plan',e=>{
  trusted(e);
  return {file:project.file,plan:project.plan,media:mediaInfo()};
 });
 ipcMain.handle('align-waveform',async(e,track)=>{
  trusted(e);
  const {file,stream}=trackInfo(track);
  const data=await run('ffmpeg',['-v','error','-nostdin','-i',file,'-map','0:a:'+stream,'-ac','1','-ar','200','-f','f32le','pipe:1'],80*1024*1024);
  const count=Math.floor(data.length/4);
  const bins=Math.max(1,Math.min(3200,count));
  const step=Math.max(1,Math.ceil(count/bins));
  const peaks=[];
  for(let i=0;i<count;i+=step){
   let sum=0,p=0,n=0;
   for(let j=i;j<Math.min(count,i+step);j++){const v=data.readFloatLE(j*4);if(!Number.isFinite(v))continue;sum+=v*v;p=Math.max(p,Math.abs(v));n++;}
   peaks.push(Math.max(Math.sqrt(sum/Math.max(1,n)),p*.5));
  }
  const max=Math.max(.0001,...peaks);
  return {peaks:peaks.map(x=>Math.min(1,x/max)),duration:count/200};
 });

 ipcMain.handle('align-waveform-range',async(e,track,start,end)=>{
  trusted(e);
  const {file,stream}=trackInfo(track);
  const from=assertTime(start),to=assertTime(end);
  if(to<=from||to-from>120)throw Error('Waveform range must be between 0 and 120 seconds.');
  const data=await run('ffmpeg',['-v','error','-nostdin','-ss',String(from),'-t',String(to-from),'-i',file,'-map','0:a:'+stream,'-ac','1','-ar','2000','-f','f32le','pipe:1'],8*1024*1024);
  const count=Math.floor(data.length/4),step=Math.max(1,Math.ceil(count/6000)),peaks=[];
  for(let i=0;i<count;i+=step){
   let max=0;
   for(let j=i;j<Math.min(count,i+step);j++){
    const x=data.readFloatLE(j*4);
    if(Number.isFinite(x))max=Math.max(max,Math.abs(x));
   }
   peaks.push(Math.min(1,max));
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
  if(fs.existsSync(output)&&(await fs.promises.stat(output)).size>16384)return pathToFileURL(output).href;
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
 ipcMain.handle('align-clip-op',(e,op,payload)=>{
  trusted(e);
  if(!payload||JSON.stringify(payload).length>250000)throw Error('Invalid clip edit.');
  const rows=validateSegments(payload.segments,project.plan.duration);
  if(op==='copy')return clips.copyClip(rows,payload.index,payload.inPoint??null,payload.outPoint??null);
  if(op==='paste')return clips.pasteClip(rows,project.plan.duration,payload.at,payload.clip);
  if(op==='trim-left'||op==='trim-right')
   return clips.trimTo(rows,project.plan.duration,payload.index,payload.at,op==='trim-left'?'left':'right');
  throw Error('Unknown clip operation.');
 });

 ipcMain.handle('align-frame',async(e,track,time)=>{
  trusted(e);
  if(!['source','target'].includes(track))throw Error('Invalid preview track.');
  const file=track==='source'?(project.plan.source_video||project.plan.audio):(project.plan.target_video||project.plan.reference);
  if(!file||!fs.existsSync(file))return null;
  const t=assertTime(time);
  const b=await run('ffmpeg',['-v','error','-nostdin','-ss',String(t),'-i',file,'-map','0:v:0','-frames:v','1','-vf','scale=600:360:force_original_aspect_ratio=decrease','-an','-c:v','mjpeg','-f','image2pipe','pipe:1'],8*1024*1024);
  return b.length?'data:image/jpeg;base64,'+b.toString('base64'):null;
 });
 ipcMain.handle('align-audio',async(e,track,start,duration,speed)=>{
  trusted(e);
  const {file,stream}=trackInfo(track);
  const time=assertTime(start),len=Number(duration),rate=Number(speed);
  if(!Number.isFinite(len)||len<=0||len>12||!Number.isFinite(rate)||rate<.5||rate>2)throw Error('Invalid preview duration or playback rate.');
  const b=await run('ffmpeg',['-v','error','-nostdin','-ss',String(time),'-t',String(len*rate),'-i',file,'-map','0:a:'+stream,'-af','atempo='+rate,'-ar','48000','-ac','2','-c:a','pcm_s16le','-f','wav','pipe:1'],10*1024*1024);
  if(b.length<64)throw Error('No audio at this timestamp.');
  return 'data:audio/wav;base64,'+b.toString('base64');
 });
 ipcMain.handle('align-save',async(e,segments,timeline=null)=>{
  trusted(e);
  if(project.exporting)throw Error('Cannot save while export is running.');
  const revised=validateSegments(segments,project.plan.duration);
  if(timeline!==null){
   nle.validateProject(timeline);
   if(Math.abs(timeline.duration-project.plan.duration)>.001)throw Error('Clip timeline duration differs from the source plan.');
   const fromTracks=nle.flatSegments(timeline);
   const core=rows=>rows.map(s=>[s.kind,s.target_start,s.target_end,s.source_start??null,s.speed??null]);
   if(JSON.stringify(core(fromTracks))!==JSON.stringify(core(revised)))
    throw Error('Audio tracks and rendered alignment disagree. Save again after refreshing the timeline.');
  }
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
