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
