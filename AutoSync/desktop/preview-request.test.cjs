'use strict';

const test=require('node:test');
const assert=require('node:assert/strict');
const {PREVIEW_MODE,preparePreviewValues,reusablePreviewPlan}=require('./preview-request.cjs');

test('preview ignores boundary-dependent export mode; never cuts or removes video',()=>{
 for(const mode of ['Main episode only','Keep target opening / ending','Sync full target audio']){
  const original={mode,main_start:'4.2',main_end:'1400',
   source_main_start:'1.1',source_main_end:'1300',
   remove_unmatched_video:true,reference_fallback:false,
   allow_uncertain_cuts:true,analyze_only:false,source:'C:\\media\\source.mkv',
   target:'C:\\media\\target.mkv',audio_stream:'2',reference_stream:'0',cut_times:''};
  const result=preparePreviewValues(original);
  assert.equal(result.mode,PREVIEW_MODE);
  assert.equal(result.analyze_only,true);
  assert.equal(result.remove_unmatched_video,false);
  assert.equal(result.allow_uncertain_cuts,false);
  assert.equal(result.main_start,'');
  assert.equal(result.main_end,'');
  assert.equal(result.source_main_start,'');
  assert.equal(result.source_main_end,'');
  assert.equal(result.audio_stream,'2');
  assert.equal(result.reference_stream,'0');
  assert.equal(original.mode,mode);
  assert.equal(original.remove_unmatched_video,true);
 }
});

test('reject reusing a trimmed or altered plan in full-timeline Preview & Edit',()=>{
 const values={source:'C:\\m\\src.mkv',target:'C:\\m\\tgt.mkv',audio:'C:\\m\\src.mkv',reference:'C:\\m\\tgt.mkv'};
 const plan={duration:1200,source_video:values.source,target_video:values.target,
  audio:values.audio,reference:values.reference,
  segments:[{kind:'audio',target_start:0,target_end:1200,source_start:0,speed:1}]};
 assert.equal(reusablePreviewPlan(plan,values),true);
 for(const key of ['main_trim','keep_target_op_ed','video_edits']){
  const p={...plan,[key]:{}};
  assert.equal(reusablePreviewPlan(p,values),false,key);
 }
 assert.equal(reusablePreviewPlan({...plan,input_trims:{target:{start:0,end:20}}},values),false);
 assert.equal(reusablePreviewPlan(plan,{...values,target:'C:\\m\\different.mkv'}),false);
 assert.equal(reusablePreviewPlan(plan,{...values,reference:'C:\\m\\other.mkv'}),false);
 assert.equal(reusablePreviewPlan({...plan,audio_stream:2},values),false);
 assert.equal(reusablePreviewPlan({...plan,reference_stream:1},values),false);
 assert.equal(reusablePreviewPlan({...plan,audio_stream:2},{...values,audio_stream:'2'}),true);
});
