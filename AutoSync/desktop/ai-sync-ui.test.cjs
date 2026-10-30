'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {preparePreviewValues,reusablePreviewPlan}=require('./preview-request.cjs');

test('standard is default; AI-assisted is a separate method, not an output mode',()=>{
 const ui=fs.readFileSync(path.join(__dirname,'remodel.js'),'utf8');
 const engine=fs.readFileSync(path.join(__dirname,'renderer.js'),'utf8');
 const setup=fs.readFileSync(path.join(__dirname,'index.html'),'utf8');
 assert.match(ui,/id=\\?["']sync_method/);
 assert.match(ui,/value=\\?["']standard/);
 assert.match(ui,/value=\\?["']ai_assisted/);
 assert.match(engine,/'sync_method'/);
 assert.match(setup,/id="setup-sync-ai"/);
});

test('Preview & Edit retains the chosen syncing method even if export mode differs',()=>{
 const input={mode:'Keep target opening / ending',sync_method:'ai_assisted',source:'C:\\a.mkv',
              target:'C:\\b.mkv',remove_unmatched_video:true};
 const p=preparePreviewValues(input);
 assert.equal(p.mode,'Sync full target audio');
 assert.equal(p.sync_method,'ai_assisted');
 assert.equal(p.remove_unmatched_video,false);
 assert.equal(input.mode,'Keep target opening / ending');
});

test('cannot reuse a standard plan as an AI-assisted alignment',()=>{
 const v={source:'C:\\a.mkv',target:'C:\\b.mkv',audio:'C:\\a.mkv',reference:'C:\\b.mkv'};
 const p={source_video:v.source,target_video:v.target,audio:v.audio,reference:v.reference,
          duration:100,segments:[{kind:'audio',target_start:0,target_end:100,source_start:0,speed:1}]};
 assert.equal(reusablePreviewPlan(p,{...v,sync_method:'standard'}),true);
 assert.equal(reusablePreviewPlan(p,{...v,sync_method:'ai_assisted'}),false);
 assert.equal(reusablePreviewPlan({...p,sync_method:'ai_assisted'},{...v,sync_method:'ai_assisted'}),true);
});
