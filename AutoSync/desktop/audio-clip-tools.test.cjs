'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {copyClip,pasteClip,trimTo}=require('./audio-clip-tools.cjs');
const {validateSegments,sourceTime}=require('./alignment-model.cjs');
const rows=[
 {kind:'audio',target_start:0,target_end:4,source_start:10,speed:1.04},
 {kind:'reference',target_start:4,target_end:7},
 {kind:'audio',target_start:7,target_end:12,source_start:20,speed:1.}
];
test('copy part of a clip and overwrite another section without ripple',()=>{
 const clip=copyClip(rows,0,1,3);
 assert.equal(clip.duration,2);
 assert.equal(clip.source_start,11.04);
 const pasted=pasteClip(rows,12,5,clip);
 assert.equal(pasted[pasted.length-1].target_end,12);
 assert.equal(sourceTime(pasted,5),11.04);
 assert.equal(sourceTime(pasted,6),12.08);
 assert.equal(sourceTime(pasted,7),20);
 assert.equal(pasted[0].target_end,4);
});
test('paste in middle of source clip preserves mapping after pasted section',()=>{
 const clip=copyClip(rows,2,8,10);
 const out=pasteClip(rows,12,1,clip);
 assert.equal(sourceTime(out,1),21);
 assert.equal(sourceTime(out,3),13.12);
 assert.equal(out.at(-1).target_end,12);
});
test('trim left and right replaces unused audio with target but does not shorten video',()=>{
 const left=trimTo(rows,12,0,1,'left');
 assert.equal(left[0].kind,'reference');
 assert.equal(sourceTime(left,1),11.04);
 const right=trimTo(rows,12,2,10,'right');
 assert.equal(sourceTime(right,9),22);
 assert.equal(right.at(-1).kind,'reference');
 validateSegments(left,12);validateSegments(right,12);
});
test('pasting near end shortens copied audio and never changes output duration',()=>{
 const out=pasteClip(rows,12,11,copyClip(rows,0));
 assert.equal(out.at(-1).target_end,12);
 assert.equal(sourceTime(out,11),10);
});
test('cut to target soundtrack and paste restored audio',()=>{
 const clip=copyClip(rows,0);
 const cut=trimTo(rows,12,0,2,'left');
 const restored=pasteClip(cut,12,0,clip);
 assert.equal(restored[0].kind,'audio');
});
test('invalid edits reject unsafe boundaries and missing clipboard',()=>{
 assert.throws(()=>copyClip(rows,0,3.9,4.5));
 assert.throws(()=>pasteClip(rows,12,4,null));
 assert.throws(()=>trimTo(rows,12,0,0,'left'));
});
