'use strict';
const assert=require('node:assert/strict');
const test=require('node:test');
const {validateSegments,findRegion,sourceTime,originalTargetTime}=require('./alignment-model.cjs');

const case1=[
 {kind:'audio',target_start:0,target_end:582.84,source_start:102.5816458333,speed:1.0427083333},
 {kind:'audio',target_start:582.84,target_end:924.44,source_start:717.40393725,speed:1.0434034722},
 {kind:'audio',target_start:924.44,target_end:1211.16,source_start:1074.0521458333,speed:1.0427083333}
];
test('Case 1: editor preserves source positions around both cut boundaries',()=>{
 const checked=validateSegments(case1,1211.16);
 assert.equal(checked.length,3);
 assert.ok(Math.abs(sourceTime(checked,0)-102.5816458333)<.00001);
 assert.ok(Math.abs(sourceTime(checked,582.84)-717.40393725)<.00001);
 assert.ok(Math.abs(sourceTime(checked,924.44)-1074.0521458333)<.00001);
});
test('Case 1: map edited video start back to untrimmed target start',()=>{
 const plan={video_edits:{kept:[
  {start:5.8,end:588.64,output_start:0,original_start:5.8,original_end:588.64},
  {start:588.64,end:930.24,output_start:582.84,original_start:588.64,original_end:930.24},
  {start:930.24,end:1216.96,output_start:924.44,original_start:930.24,original_end:1216.96}
 ]}};
 assert.ok(Math.abs(originalTargetTime(plan,0)-5.8)<1e-9);
 assert.ok(Math.abs(originalTargetTime(plan,582.84)-588.64)<1e-9);
 assert.ok(Math.abs(originalTargetTime(plan,924.44)-930.24)<1e-9);
});
test('Reject gaps, overlaps, reversed times and missing final coverage',()=>{
 assert.throws(()=>validateSegments([{...case1[0],target_start:1},case1[1],case1[2]],1211.16));
 assert.throws(()=>validateSegments([case1[0],{...case1[1],target_start:582.90},case1[2]],1211.16));
 assert.throws(()=>validateSegments([case1[0],case1[1]],1211.16));
 assert.throws(()=>validateSegments([{...case1[0],target_end:-1},case1[1],case1[2]],1211.16));
});
test('Reject invalid audio positions or speed',()=>{
 assert.throws(()=>validateSegments([{...case1[0],source_start:-.2},case1[1],case1[2]],1211.16));
 assert.throws(()=>validateSegments([{...case1[0],speed:0},case1[1],case1[2]],1211.16));
 assert.throws(()=>validateSegments([{...case1[0],speed:Infinity},case1[1],case1[2]],1211.16));
});
test('Target reference region has no mapped source time',()=>{
 const rows=validateSegments([{kind:'reference',target_start:0,target_end:1},{kind:'audio',target_start:1,target_end:2,source_start:4,speed:1}],2);
 assert.equal(sourceTime(rows,.5),null);
 assert.equal(sourceTime(rows,1),4);
 assert.equal(findRegion(rows,2).index,1);
});

test('Target trims: editor target time maps back to the original target file',()=>{
 // A range marked on the target (input trim) keeps output times zero-based.
 assert.equal(originalTargetTime({input_trims:{target:{start:30,end:900}}},10),40);
 // With a main-episode trim inside the trimmed target, both offsets apply.
 assert.equal(originalTargetTime({input_trims:{target:{start:30,end:900}},main_trim:{target_start:90}},10),130);
 // Video edits already carry original times (trim included by the engine).
 const edited={input_trims:{target:{start:30}},video_edits:{kept:[{start:0,end:50,output_start:0,original_start:30}]}};
 assert.equal(originalTargetTime(edited,10),40);
 assert.equal(originalTargetTime({},10),10);
});

test('edited video timeline is validated before saving',()=>{
 const {validateTimeline}=require('./alignment-model.cjs');
 const plan={duration:100,segments:[]};
 const known=new Set(['C:/m/clip.mp4']);
 const media=p=>{if(!known.has(p))throw Error('Unknown imported media.');};
 const ok=validateTimeline({duration:103,kept:[
  {start:0,end:50,output_start:0,original_start:0,original_end:50},
  {start:50,end:53,output_start:50,media:'C:/m/clip.mp4',media_start:1},
  {start:50,end:100,output_start:53,original_start:50,original_end:100}]},plan,media);
 assert.equal(ok.kept.length,3);assert.equal(ok.duration,103);
 assert.throws(()=>validateTimeline({duration:103,kept:[{start:0,end:103,output_start:0,original_start:0,original_end:103}]},plan,media),/outside the target/);
 assert.throws(()=>validateTimeline({duration:10,kept:[{start:0,end:10,output_start:0,media:'C:/other.mp4'}]},plan,media),/Unknown imported/);
 assert.throws(()=>validateTimeline({duration:20,kept:[{start:0,end:10,output_start:0,original_start:0,original_end:10},{start:10,end:20,output_start:11,original_start:10,original_end:20}]},plan,media),/contiguous/);
});

test('motion fills pass validation with their held frame',()=>{
 const {validateTimeline}=require('./alignment-model.cjs');
 const plan={duration:100,segments:[]},media=()=>{};
 const ok=validateTimeline({duration:100,kept:[{start:0,end:20,output_start:0,original_start:0,original_end:20},
  {start:20,end:24,output_start:20,original_start:20,original_end:24,fill:'motion',hold:20},
  {start:24,end:100,output_start:24,original_start:24,original_end:100}]},plan,media);
 assert.equal(ok.kept[1].fill,'motion');assert.equal(ok.kept[1].hold,20);
 assert.throws(()=>validateTimeline({duration:100,kept:[{start:0,end:100,output_start:0,original_start:0,original_end:100,fill:'blur',hold:3}]},plan,media),/motion fill/);
});

test('clip gain and fades are validated',()=>{
 const {validateSegments}=require('./alignment-model.cjs');
 const row={kind:'reference',target_start:0,target_end:2};
 assert.equal(validateSegments([{...row,gain_db:-6,fade_in_ms:500,fade_out_ms:500}],2)[0].gain_db,-6);
 assert.throws(()=>validateSegments([{...row,gain_db:40}],2),/gain or fades/);
 assert.throws(()=>validateSegments([{...row,fade_in_ms:1500,fade_out_ms:1000}],2),/gain or fades/);
});
