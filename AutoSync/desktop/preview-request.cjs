'use strict';

const path=require('node:path');

// Preview & Edit always opens the *uncut target timeline*. Export options such
// as Main only and Keep target OP/ED require verified video boundaries and
// must not prevent examining the alignment in a non-destructive editor.
const PREVIEW_MODE='Sync full target audio';

function preparePreviewValues(input){
 if(!input||typeof input!=='object'||Array.isArray(input))throw Error('Invalid preview settings.');
 return {
  ...input,
  mode:PREVIEW_MODE,
  main_start:'',
  main_end:'',
  source_main_start:'',
  source_main_end:'',
  // A non-destructive preview never drops picture or asks for uncertain
  // destructive cuts. The user explicitly chooses export behavior later.
  remove_unmatched_video:false,
  reference_fallback:false,
  allow_uncertain_cuts:false,
  analyze_only:true
 };
}
function sameFile(a,b){
 return typeof a==='string'&&a.trim()!==''&&typeof b==='string'&&b.trim()!==''&&
  path.resolve(a)===path.resolve(b);
}
function reusablePreviewPlan(plan,values){
 if(!plan||!values||!Array.isArray(plan.segments)||!Number.isFinite(plan.duration)||plan.duration<=0)
  return false;
 // Full-timeline plans can be reused, but not plans previously trimmed or
 // constructed using keep-target-outer / destructive video-edit operations.
 if((plan.sync_method||'standard')!==(values.sync_method||'standard'))return false;
 if(plan.main_trim||plan.keep_target_op_ed||plan.video_edits||plan.input_trims?.target)
  return false;
 // Track selection must also match, or the previously produced mapping
 // can silently refer to a different dub or target soundtrack.
 const stream=(v)=>v===undefined||v===null||v===''?0:Number(v);
 if(!Number.isInteger(stream(values.audio_stream))||!Number.isInteger(stream(values.reference_stream)))
  return false;
 if(stream(plan.audio_stream)!==stream(values.audio_stream)||
    stream(plan.reference_stream)!==stream(values.reference_stream))return false;
 return sameFile(plan.source_video,values.source)&&
  sameFile(plan.target_video,values.target)&&
  sameFile(plan.audio,values.audio||values.source)&&
  sameFile(plan.reference,values.reference||values.target);
}
module.exports={PREVIEW_MODE,preparePreviewValues,reusablePreviewPlan};
