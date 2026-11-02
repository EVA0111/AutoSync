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

test('reuse an earlier analysis only with the same censored-dub setting and marked ranges',()=>{
 const values={source:'C:\m\src.mkv',target:'C:\m\tgt.mkv',audio:'C:\m\src.mkv',reference:'C:\m\tgt.mkv'};
 const plan={duration:1200,source_video:values.source,target_video:values.target,
  audio:values.audio,reference:values.reference,
  segments:[{kind:'audio',target_start:0,target_end:1200,source_start:0,speed:1}]};
 // Censored dub: the plan's labels depend on the option.
 const censored={...plan,censorship:{default_action:'cut',smooth:true}};
 assert.equal(reusablePreviewPlan(censored,values),false);
 assert.equal(reusablePreviewPlan(plan,{...values,censored_dub:'restore'}),false);
 assert.equal(reusablePreviewPlan(censored,{...values,censored_dub:'restore'}),false);
 assert.equal(reusablePreviewPlan(censored,{...values,censored_dub:'cut'}),true);
 // Marked ranges (file-row preview): same ranges reuse, any difference re-analyses.
 const trimmed={...plan,input_trims:{source:{start:12,end:900}}};
 const same={...values,source_trim_start:'12',source_trim_end:'900'};
 assert.equal(reusablePreviewPlan(trimmed,same),true);
 assert.equal(reusablePreviewPlan(trimmed,{...same,source_trim_end:'901'}),false);
 assert.equal(reusablePreviewPlan(trimmed,values),false);
 assert.equal(reusablePreviewPlan(plan,same),false);
 assert.equal(reusablePreviewPlan({...plan,input_trims:{target:{start:5,end:60}}},
  {...values,target_trim_start:'5',target_trim_end:'60'}),true);
});

test('preview keeps marked ranges in its analysis request',()=>{
 const p=preparePreviewValues({mode:'Main episode only',source:'C:\a.mkv',target:'C:\b.mkv',
  source_trim_start:'12',source_trim_end:'900',target_trim_start:'5',target_trim_end:'60'});
 assert.equal(p.source_trim_start,'12');assert.equal(p.target_trim_end,'60');
});
