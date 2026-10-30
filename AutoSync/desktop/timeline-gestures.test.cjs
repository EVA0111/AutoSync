'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {sourceTime,validateSegments}=require('./alignment-model.cjs');
const {hitClip,snapTime,placeClip,slipClip,trimClip,splitClip,visibleClips}=require('./timeline-gestures.cjs');
const rows=[
 {kind:'audio',target_start:0,target_end:5,source_start:8,speed:1.1},
 {kind:'reference',target_start:5,target_end:8},
 {kind:'audio',target_start:8,target_end:14,source_start:24,speed:1}
];
test('source and target lanes only display their own clips',()=>{
 assert.deepEqual(visibleClips(rows,'source').map(x=>x.index),[0,2]);
 assert.deepEqual(visibleClips(rows,'target').map(x=>x.index),[1]);
 assert.deepEqual(visibleClips(rows,'mix').map(x=>x.index),[0,1,2]);
});
test('hit-testing detects trim handles in output mix but not guide lanes',()=>{
 assert.deepEqual(hitClip(rows,5.03,'mix',0.09),{index:1,edge:'start'});
 assert.deepEqual(hitClip(rows,4.96,'source',0.09),{index:0,edge:null});
 assert.equal(hitClip(rows,6,'source',0.09),null);
});
test('snapping respects 8px threshold and excluded original edge',()=>{
 assert.equal(snapTime(4.93,[0,5,8],100,8),5);
 assert.equal(snapTime(4.9,[0,5,8],100,8),4.9);
 assert.equal(snapTime(4.99,[5],100,8,[5]),4.99);
});
test('moving a clip lifts its original region to target and places exact mapping',()=>{
 const moved=placeClip(rows,14,0,5,{copy:false});
 assert.equal(moved[0].kind,'reference');
 assert.equal(sourceTime(moved,5),8);
 assert.ok(Math.abs(sourceTime(moved,6)-9.1)<1e-7);
 assert.equal(sourceTime(moved,12),28);
 assert.equal(moved.at(-1).target_end,14);
 validateSegments(moved,14);
 assert.equal(rows[0].kind,'audio');
});
test('alt-copy keeps original and overwrites only destination',()=>{
 const pasted=placeClip(rows,14,0,5,{copy:true});
 assert.equal(sourceTime(pasted,1),9.1);
 assert.equal(sourceTime(pasted,5),8);
 assert.equal(sourceTime(pasted,11),27);
});
test('slip changes source in-point without moving output clip',()=>{
 const slipped=slipClip(rows,14,0,1.25);
 assert.equal(slipped[0].target_start,0);
 assert.equal(slipped[0].target_end,5);
 assert.equal(slipped[0].source_start,9.25);
 assert.equal(rows[0].source_start,8);
});
test('dragging an edge trims only that edge, fills with target audio',()=>{
 const a=trimClip(rows,14,0,'start',2);
 assert.equal(a[0].kind,'reference');
 assert.ok(Math.abs(sourceTime(a,2)-10.2)<1e-7);
 const b=trimClip(rows,14,2,'end',12);
 assert.equal(b.at(-1).kind,'reference');
 assert.equal(b.at(-1).target_end,14);
});
test('razor split preserves sample mapping and duration',()=>{
 const cut=splitClip(rows,14,0,2.5);
 assert.equal(cut.length,4);
 assert.ok(Math.abs(cut[1].source_start-10.75)<1e-7);
 assert.equal(sourceTime(cut,4),12.4);
});
test('invalid drags do not create gaps or mutate original',()=>{
 assert.throws(()=>splitClip(rows,14,0,-1),/inside/);
 assert.throws(()=>slipClip(rows,14,1,1),/source-audio/);
 assert.deepEqual(rows[0],{kind:'audio',target_start:0,target_end:5,source_start:8,speed:1.1});
});
