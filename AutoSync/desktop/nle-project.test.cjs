'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const n=require('./nle-project.cjs');
const plan={duration:20,segments:[
 {kind:'reference',target_start:0,target_end:2},
 {kind:'audio',target_start:2,target_end:8,source_start:10,speed:1},
 {kind:'reference',target_start:8,target_end:12},
 {kind:'audio',target_start:12,target_end:20,source_start:20,speed:1.1}
]};
const example=()=>n.newProject(plan);
test('NLE imports one clip per source region over a target soundtrack bed',()=>{
 const p=example();assert.equal(p.tracks[0].clips.length,2);assert.equal(p.tracks[1].clips.length,1);
 assert.deepEqual(n.flatSegments(p),plan.segments);
});
test('razor splits source mapping at the edit point without changing timing',()=>{
 const p=example(),id=p.tracks[0].clips[0].id;
 const cut=n.split(p,id,5);
 assert.equal(cut.tracks[0].clips[1].sourceStart,13);
 assert.deepEqual(n.flatSegments(cut),plan.segments);
 assert.equal(p.tracks[0].clips.length,2);
});
test('trim handles drag source in-point and preserve other clips',()=>{
 const p=example(),id=p.tracks[0].clips[0].id;
 const trimmed=n.trim(p,id,'in',3);
 assert.equal(trimmed.tracks[0].clips[0].sourceStart,11);
 assert.equal(n.flatSegments(trimmed)[1].target_start,3);
 const shortened=n.trim(p,id,'out',6);
 assert.equal(shortened.tracks[0].clips[0].end,6);
 assert.equal(n.flatSegments(shortened)[2].target_end,12);
 assert.throws(()=>n.trim(p,id,'in',7.99));
});
test('drag clips into empty gaps and across audio lanes; reject collisions',()=>{
 const p=example(),id=p.tracks[0].clips[0].id;
 assert.throws(()=>n.move(p,id,'A1',13),/overlaps/);
 const shifted=n.move(p,id,'A3',8);
 assert.equal(shifted.tracks[2].clips[0].start,8);
 assert.equal(n.flatSegments(shifted).find(r=>r.target_start===8).source_start,10);
 assert.deepEqual(n.flatSegments(p),plan.segments);
});
test('paste insert rejects overlap; overwrite splits displaced clip',()=>{
 const p=example(),original=p.tracks[0].clips[0].id;
 const piece=n.copyClip(p,original,3,5);
 const inserted=n.paste(p,piece,'A3',9);
 assert.equal(n.flatSegments(inserted).find(r=>r.target_start===9).source_start,11);
 assert.throws(()=>n.paste(p,piece,'A1',7),/overlaps/);
 const over=n.paste(p,piece,'A1',4,{overwrite:true});
 assert.equal(over.tracks[0].clips.length,4);
 assert.equal(n.flatSegments(over).find(r=>r.target_start===4).source_start,11);
});
test('track mute and solo affect actual flattened export',()=>{
 const p=example(),muted=n.setTrack(p,'A1','mute',true);
 assert.deepEqual(n.flatSegments(muted),[{kind:'reference',target_start:0,target_end:20}]);
 const solo=n.setTrack(p,'A1','solo',true);
 assert.equal(n.flatSegments(solo)[0].kind,'verified_gap');
 assert.throws(()=>n.move(n.setTrack(p,'A1','locked',true),p.tracks[0].clips[0].id,'A3',3),/Unlock/);
});
test('snap toward nearby clip boundaries and playhead',()=>{
 const p=example();
 assert.equal(n.snap(p,7.92,{threshold:.12}),8);
 assert.equal(n.snap(p,6.11,{threshold:.12}),6.11);
 assert.equal(n.snap(p,7.92,{threshold:.12,exclude:p.tracks[0].clips[0].id}),7.92);
 assert.equal(n.snap(p,14.95,{threshold:.1,playhead:15}),15);
});
test('delete an audio clip exposes the target bed without rippling',()=>{
 const p=example(),cut=n.remove(p,p.tracks[0].clips[0].id);
 assert.equal(n.flatSegments(cut)[0].kind,'reference');
 assert.equal(n.flatSegments(cut)[0].target_end,12);
 assert.equal(n.flatSegments(cut).at(-1).target_end,20);
});
test('video timing is never shortened when clips are moved or deleted',()=>{
 let p=example();
 p=n.remove(p,p.tracks[0].clips[0].id);
 p=n.move(p,p.tracks[0].clips[0].id,'A3',8);
 assert.equal(n.flatSegments(p).at(-1).target_end,20);
});
