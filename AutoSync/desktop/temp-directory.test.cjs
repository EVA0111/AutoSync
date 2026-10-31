'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {temporaryRoot,prepareTemporaryRoot}=require('./temp-directory.cjs');

test('default temporary folder lives beside the target, not on the system drive',()=>{
 const target=path.join('D:','anime','episode.mkv');
 assert.equal(temporaryRoot({jobs:[{task:'Single episode',values:{target}}]}),
              path.join(path.dirname(path.resolve(target)),'AutoSync Temp'));
});
test('custom directory overrides target-local default',()=>{
 const chosen=path.join(os.tmpdir(),'custom-autosync-temp');
 assert.equal(temporaryRoot({temp_dir:chosen,jobs:[{values:{target:'/example.mkv'}}]}),path.resolve(chosen));
});
test('reject a relative custom directory',()=>{
 assert.throws(()=>temporaryRoot({temp_dir:'relative-temp',jobs:[]}),/absolute/);
});
test('creates target-local temporary root and permits isolated scratch subfolder',()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'autosync-temp-test-'));
 try{
  const target=path.join(root,'episode.mkv');
  const location=prepareTemporaryRoot({jobs:[{values:{target}}]});
  assert.equal(location,path.join(root,'AutoSync Temp'));
  assert.equal(fs.statSync(location).isDirectory(),true);
  const work=fs.mkdtempSync(path.join(location,'autosync-work-'));
  fs.rmSync(work,{recursive:true});
  assert.equal(fs.existsSync(work),false);
 }finally{fs.rmSync(root,{recursive:true,force:true});}
});
test('batch defaults to first target folder',()=>{
 const t=path.join(os.tmpdir(),'anime','test.mkv');
 assert.equal(temporaryRoot({jobs:[{task:'Folder batch',values:{},pairs:[{target:t}]}]}),path.join(path.dirname(t),'AutoSync Temp'));
});
