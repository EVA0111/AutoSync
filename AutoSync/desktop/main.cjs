const {probe}=require('./media.cjs');
const {createPreview}=require('./video-preview.cjs');
const {createAlignmentEditor}=require('./alignment-editor.cjs');
const {collect,prepareBatch}=require('./batch.cjs');
const {app,BrowserWindow,ipcMain,dialog,shell}=require('electron');
const {spawn}=require('node:child_process');
const fs=require('node:fs');const path=require('node:path');const {pathToFileURL}=require('node:url');
let win,child=null,lastOutput=null,lastReport=null,lastPlan=null,stopping=false,quitting=false;
const root=app.isPackaged?path.join(process.resourcesPath,'engine'):path.resolve(__dirname,'..');
const preview=createPreview(root);
const alignmentEditor=createAlignmentEditor(root,python);
const page=pathToFileURL(path.join(__dirname,'index.html')).href;
function python(){if(app.isPackaged)return [path.join(process.resourcesPath,'python','python.exe'),[]];const local=path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');return fs.existsSync(local)?[local,[]]:process.platform==='win32'?['py',['-3']]:['python3',[]];}
function send(type,data){if(win&&!win.isDestroyed())win.webContents.send('job-event',{type,data});}
function stop(){if(!child)return;stopping=true;send('status','Stopping…');try{if(process.platform==='win32')spawn('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true});else process.kill(-child.pid,'SIGTERM');}catch(e){send('log',e.message+'\n');}}
function trusted(event){if(event.sender!==win.webContents||event.senderFrame?.url!==page)throw Error('Untrusted caller');}
app.whenReady().then(()=>{
 win=new BrowserWindow({width:1240,height:900,minWidth:880,minHeight:660,backgroundColor:'#11151d',title:'AutoSync v1.1',webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true}});
 win.removeMenu();win.loadFile(path.join(__dirname,'index.html'));win.webContents.setWindowOpenHandler(()=>({action:'deny'}));win.webContents.on('will-navigate',e=>e.preventDefault());
 win.on('close',e=>{if(child&&!quitting){e.preventDefault();dialog.showMessageBox(win,{type:'question',message:'Stop the running job and close?',detail:'Partial output and temporary files may remain.',buttons:['Keep running','Stop and close'],defaultId:0,cancelId:0}).then(r=>{if(r.response===1){quitting=true;stop();}});}});
 ipcMain.handle('open-github-profile',async e=>{trusted(e);await shell.openExternal('https://github.com/EVA0111');});
 ipcMain.handle('browse',async(e,kind)=>{trusted(e);if(!['media','subtitle','csv','plan','output'].includes(kind))throw Error('Unknown file type');const dir=kind==='output';const result=await dialog.showOpenDialog(win,{properties:[dir?'openDirectory':'openFile'],filters:dir?undefined:kind==='subtitle'?[{name:'Subtitles or container',extensions:['ass','ssa','srt','vtt','sbv','sub','mpl2','smi','sami','ttml','dfxp','xml','sup','mkv','mp4']},{name:'All files',extensions:['*']}]:kind==='csv'?[{name:'Batch CSV',extensions:['csv']}]:kind==='plan'?[{name:'Saved plan',extensions:['json']}]:[{name:'Media',extensions:['mkv','mp4','avi','wmv','mov','m2ts','wav','flac','mp3','aac','ac3','wma']},{name:'All files',extensions:['*']}]});if(result.canceled)return '';const p=result.filePaths[0];return p;});
 win.on('closed',()=>{preview.cancel();alignmentEditor.close();});
 ipcMain.handle('alignment-editor-open',async(e,request={})=>{
  trusted(e);
  if(child)throw Error('Finish the running sync job before opening Preview & Edit.');
  if(!request||typeof request!=='object'||JSON.stringify(request).length>100000)throw Error('Invalid Preview & Edit request.');
  if(request.plan)return alignmentEditor.open(win,request.plan);
  if(!request.job&&lastPlan&&fs.existsSync(lastPlan))return alignmentEditor.open(win,lastPlan);
  // Reuse an already-completed analysis for this media pair.
  if(request.job&&lastPlan&&fs.existsSync(lastPlan)){
   try{
    const previous=JSON.parse(await fs.promises.readFile(lastPlan,'utf8'));
    const values=request.job.values||{};
    const same=(a,b)=>typeof a==='string'&&typeof b==='string'&&path.resolve(a)===path.resolve(b);
    if(same(previous.source_video,values.source)&&same(previous.target_video,values.target)&&
       same(previous.audio,values.audio)&&same(previous.reference,values.reference)){
     return alignmentEditor.open(win,lastPlan);
    }
   }catch(err){send('log','Could not reuse alignment: '+err.message+'\n');}
  }
  if(request.job)return alignmentEditor.analyzeAndOpen(win,request.job,request.outputDirectory,message=>send('alignment-log',message));
  return alignmentEditor.open(win);
 });
 ipcMain.handle('preview-open',async(e,file)=>{trusted(e);return preview.open(file);});
 ipcMain.handle('preview-frame',async(e,index)=>{trusted(e);return preview.frame(index);});
 ipcMain.handle('preview-close',e=>{trusted(e);preview.cancel();});
 ipcMain.handle('probe',async(e,file)=>{trusted(e);return probe(file,root);});
 ipcMain.handle('subtitle-collect',async(e,paths)=>{trusted(e);return collect(paths,'subtitle-target');});
 ipcMain.handle('subtitle-pick',async(e,folder)=>{trusted(e);const r=await dialog.showOpenDialog(win,{properties:folder?['openDirectory']:['openFile','multiSelections']});return r.canceled?[]:collect(r.filePaths,'subtitle-target');});
 ipcMain.handle('collect',async(e,paths,videoOnly)=>{trusted(e);return collect(paths,videoOnly!==false);});
 ipcMain.handle('pick-batch',async(e,folder)=>{trusted(e);const r=await dialog.showOpenDialog(win,{properties:folder?['openDirectory']:['openFile','multiSelections']});return r.canceled?[]:collect(r.filePaths);});
 ipcMain.handle('start',async(e,job)=>{trusted(e);if(child||alignmentEditor.isBusy())throw Error('A sync or Preview & Edit analysis is already running.');if(!job||typeof job!=='object'||JSON.stringify(job).length>100000)throw Error('Invalid job.');const queued=job.task==='Queue'?job.jobs:[job];if(!Array.isArray(queued)||!queued.length||queued.length>2)throw Error('Invalid queue.');for(const entry of queued){if(entry.task==='Folder batch'){entry.values.batch=await prepareBatch(entry.pairs,entry.values);entry.task='Batch CSV';}}if(job.task==='Setup'&&!['engine','ai'].includes(job.kind))throw Error('Invalid setup option.');const [bin,prefix]=python();stopping=false;lastOutput=job.task==='Managed queue'?job.output_dir:null;lastReport=null;lastPlan=null;const managed=job.task==='Managed queue';let workRoot=null;if(managed){workRoot=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'autosync-work-'));job.work_root=workRoot;}
 const setup=job.task==='Setup';
 child=spawn(bin,[...prefix,'-u',path.join(root,setup?'runtime_setup.py':'desktop_bridge.py'),...(setup&&job.kind==='ai'?['--ai']:[])],{cwd:root,env:{...process.env,PYTHONIOENCODING:'utf-8',PYTHONUNBUFFERED:'1'},windowsHide:true,detached:process.platform!=='win32',stdio:['pipe','pipe','pipe']});
 const running=child;let pending='';
 running.stdout.setEncoding('utf8');running.stderr.setEncoding('utf8');
 running.stdout.on('data',chunk=>{pending+=chunk;let i;while((i=pending.indexOf('\n'))!==-1){let line=pending.slice(0,i);pending=pending.slice(i+1);if(line.startsWith('AUTOSYNC_REPORTS=')){try{lastReport=JSON.parse(line.slice(17));}catch{}}else if(line.startsWith('AUTOSYNC_RESULT=')){try{send('result',JSON.parse(line.slice(16)));}catch{}}else if(line.startsWith('AUTOSYNC_PLAN=')){try{lastPlan=JSON.parse(line.slice('AUTOSYNC_PLAN='.length));send('plan',lastPlan);}catch{send('log',line+'\n');}}else if(line.startsWith('AUTOSYNC_PROGRESS=')){try{send('progress',JSON.parse(line.slice(18)));}catch{send('log',line+'\n');}}else if(line.startsWith('AUTOSYNC_OUTPUT=')){try{if(!managed)lastOutput=JSON.parse(line.slice(16));send('output',lastOutput);}catch{send('log',line+'\n');}}else send('log',line+'\n');}});
 running.stderr.on('data',s=>send('log',s));running.on('error',err=>send('log','Unable to launch the sync engine: '+err.message+'\n'));
 running.stdin.on('error',()=>{});running.stdin.end(JSON.stringify(job));
 running.on('close',code=>{if(pending)send('log',pending);child=null;if(workRoot)fs.promises.rm(workRoot,{recursive:true,force:true,maxRetries:5,retryDelay:200}).catch(e=>send('log','Could not remove temporary work files: '+e.message+'\n'));send('done',{code,cancelled:stopping});if(quitting)app.quit();});return true;});
 ipcMain.handle('stop',e=>{trusted(e);stop();});
 ipcMain.handle('open-output',async(e,report)=>{trusted(e);if(!lastOutput)throw Error('No output folder is available yet.');const p=report?lastReport:lastOutput;if(!p)throw Error('Reports were not saved. Enable Save reports in Settings for future runs.');if(!fs.existsSync(p))throw Error('This file or folder has not been created yet.');const error=await shell.openPath(p);if(error)throw Error(error);});
 ipcMain.handle('example',e=>{trusted(e);return shell.openPath(path.join(root,'jobs_example.csv'));});
});
app.on('window-all-closed',()=>app.quit());
