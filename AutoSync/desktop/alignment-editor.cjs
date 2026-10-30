'use strict';
const {BrowserWindow, dialog, ipcMain, shell}=require('electron');
const fs=require('node:fs');
const path=require('node:path');
const {execFile,spawn}=require('node:child_process');
const {pathToFileURL}=require('node:url');
const {randomUUID}=require('node:crypto');
const {validateSegments}=require('./alignment-model.cjs');

function createAlignmentEditor(root,python){
 let editor=null,project=null,exportChild=null;
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
 async function open(parent){
  if(editor&&!editor.isDestroyed()){editor.focus();return true;}
  const picked=await dialog.showOpenDialog(parent,{title:'Open an AutoSync plan.json',properties:['openFile'],filters:[{name:'AutoSync alignment plan',extensions:['json']}]});
  if(picked.canceled)return false;
  const file=picked.filePaths[0];
  const value=JSON.parse(await fs.promises.readFile(file,'utf8'));
  if(!value||!Array.isArray(value.segments)||!Number.isFinite(Number(value.duration))||!value.audio)throw Error('Select a valid AutoSync plan.json file.');
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
   exportChild=null;editor=null;project=null;
  });
  return true;
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
  const b=await run('ffmpeg',['-v','error','-nostdin','-ss',String(time),'-t',String(len*rate),'-i',file,'-map','0:a:'+stream,'-af','atempo='+rate,'-ar','24000','-ac','2','-c:a','pcm_s16le','-f','wav','pipe:1'],10*1024*1024);
  if(b.length<64)throw Error('No audio at this timestamp.');
  return 'data:audio/wav;base64,'+b.toString('base64');
 });
 ipcMain.handle('align-save',async(e,segments)=>{
  trusted(e);
  if(project.exporting)throw Error('Cannot save while export is running.');
  const revised=validateSegments(segments,project.plan.duration);
  // Never overwrite the original, unedited alignment or FLAC.
  if(!project.outputPlan||project.exported){
   const pick=await dialog.showOpenDialog(editor,{title:'Choose where to save the corrected sync',properties:['openDirectory','createDirectory']});
   if(pick.canceled)return null;
   const folder=path.join(pick.filePaths[0],'AutoSync_Edited_'+new Date().toISOString().replace(/[:.]/g,'-')+'_'+randomUUID().slice(0,6));
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
 return {open,close(){if(editor&&!editor.isDestroyed())editor.close();}};
}
module.exports={createAlignmentEditor};
