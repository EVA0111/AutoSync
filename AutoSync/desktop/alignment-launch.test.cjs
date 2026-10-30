'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {EventEmitter}=require('node:events');
const {PassThrough}=require('node:stream');
const Module=require('node:module');
const {pathToFileURL}=require('node:url');

test('Preview & Edit auto-analyzes selected source/target and saves edits in an arbitrary output folder',async()=>{
 const temp=fs.mkdtempSync(path.join(os.tmpdir(),'autosync-editor-test-'));
 const source=path.join(temp,'source.mp4'),target=path.join(temp,'target.mp4');
 fs.writeFileSync(source,'source file remains unchanged');
 fs.writeFileSync(target,'target file remains unchanged');
 const editorHandlers=new Map();
 const windows=[];
 let filePickerCount=0,folderPickerCount=0;
 class FakeWindow extends EventEmitter {
  constructor(){
   super();
   this.webContents=new EventEmitter();
   this.webContents.setWindowOpenHandler=()=>{};
   this.webContents.send=()=>{};
   windows.push(this);
  }
  removeMenu(){}
  loadFile(){}
  show(){}
  focus(){}
  isDestroyed(){return false;}
  close(){this.emit('closed');}
 }
 const electron={
  BrowserWindow:FakeWindow,
  dialog:{
   showOpenDialog:async (_parent,opts)=>{
    if(opts.properties.includes('openFile')){filePickerCount++;throw Error('Editor requested a plan file despite a selected pair');}
    folderPickerCount++;
    return {canceled:false,filePaths:[temp]};
   },
   showSaveDialog:async()=>({canceled:false,filePath:path.join(temp,'My Corrected Audio.json')})
  },
  ipcMain:{handle:(name,handler)=>{editorHandlers.set(name,handler);}},
  shell:{openPath:async()=>''}
 };
 const originalLoad=Module._load;
 Module._load=function(name,parent,isMain){
  if(name==='electron')return electron;
  if(name==='node:child_process'){
   const original=originalLoad.apply(this,arguments);
   return {...original,spawn:()=>{
    const child=new EventEmitter();
    child.stdout=new PassThrough();child.stderr=new PassThrough();
    child.stdin={on:()=>{},end:raw=>{
     const request=JSON.parse(raw);
     assert.equal(request.task,'Single episode');
     assert.equal(request.values.analyze_only,true);
     assert.equal(request.values.source,source);
     assert.equal(request.values.target,target);
     fs.writeFileSync(path.join(request.values.out,'plan.json'),JSON.stringify({
      duration:2,audio:source,audio_stream:0,reference:target,reference_stream:0,
      source_video:source,target_video:target,
      segments:[{kind:'audio',target_start:0,target_end:2,source_start:0,speed:1}]
     }));
     process.nextTick(()=>child.emit('close',0));
    }};
    return child;
   }};
  }
  return originalLoad.apply(this,arguments);
 };
 let create;
 try{
  delete require.cache[require.resolve('./alignment-editor.cjs')];
  create=require('./alignment-editor.cjs').createAlignmentEditor;
 }finally{Module._load=originalLoad;}
 try{
  const instance=create(temp,()=>['python',[]]);
  const result=await instance.analyzeAndOpen({},{
   task:'Single episode',values:{source,target,audio:source,reference:target}
  },temp,()=>{});
  assert.equal(result,true);
  assert.equal(filePickerCount,0,'No plan chooser should appear');
  assert.equal(folderPickerCount,1,'One output directory chooser expected');
  assert.equal(windows.length,1);
  const savedPlans=fs.readdirSync(temp,{withFileTypes:true}).filter(x=>x.isDirectory()&&x.name.startsWith('AutoSync_Alignment_'));
  assert.equal(savedPlans.length,1);
  assert.ok(fs.existsSync(path.join(temp,savedPlans[0].name,'plan.json')));
  const event={sender:windows[0].webContents,senderFrame:{url:pathToFileURL(path.join(__dirname,'alignment-editor.html')).href}};
  const save=editorHandlers.get('align-save');
  const saveResult=await save(event,[{kind:'audio',target_start:0,target_end:2,source_start:.12,speed:1}]);
  assert.equal(saveResult,path.join(temp,'My Corrected Audio','plan.json'));
  assert.equal(JSON.parse(fs.readFileSync(saveResult,'utf8')).segments[0].source_start,.12);
  assert.equal(fs.readFileSync(source,'utf8'),'source file remains unchanged');
  assert.equal(fs.readFileSync(target,'utf8'),'target file remains unchanged');
  instance.close();
 }finally{
  delete require.cache[require.resolve('./alignment-editor.cjs')];
  fs.rmSync(temp,{recursive:true,force:true});
 }
});
