'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const vt=require('./video-timeline.js');

const plan={duration:100,segments:[
 {kind:'audio',target_start:0,target_end:40,source_start:10,speed:1},
 {kind:'reference',target_start:40,target_end:50},
 {kind:'audio',target_start:50,target_end:100,source_start:60,speed:1.04}]};
const clip={path:'C:/media/clip.mp4',name:'clip.mp4',duration:12,hasVideo:true,hasAudio:true,audioStream:0};
const near=(a,b,msg)=>assert.ok(Math.abs(a-b)<1e-6,msg+': '+a+' vs '+b);

test('ripple delete removes picture and audio together',()=>{
 const tl=vt.rippleDelete(vt.fromPlan(plan),30,45);
 near(tl.duration,85,'duration');
 // Output 30 now shows target 45 with its own (target) audio from target time 45.
 const pic=vt.pictureAt(tl.kept,30);near(pic.target,45,'picture');
 const ref=tl.segments.find(s=>s.target_start<=30.5&&30.5<s.target_end);
 assert.equal(ref.kind,'reference');near(ref.reference_target_start+(30.5-ref.target_start),45.5,'target audio');
 // Later source audio still sits on the picture it was synced to.
 const a=tl.segments.find(s=>s.kind==='audio'&&s.target_start>=35);
 near(a.target_start,35,'shifted start');near(a.source_start,60,'source unchanged');
 near(vt.pictureAt(tl.kept,35).target,50,'picture under shifted audio');
});

test('insert clip ripples later picture and audio',()=>{
 const tl=vt.insertClip(vt.fromPlan(plan),20,clip,2,5);
 near(tl.duration,105,'duration');
 const m=vt.pictureAt(tl.kept,22);assert.equal(m.media,clip.path);near(m.time,4,'media time');
 const seg=tl.segments.find(s=>s.kind==='media');near(seg.target_start,20,'audio at');near(seg.media_start,2,'audio in');
 // Source audio that played at 20 now plays at 25, over the same picture.
 const after=tl.segments.find(s=>s.kind==='audio'&&s.target_start>=25-1e-9);
 near(after.target_start,25,'audio moved');near(after.source_start,30,'audio source time');
 near(vt.pictureAt(tl.kept,25).target,20,'picture moved');
});

test('replace audio keeps picture and length',()=>{
 const tl=vt.replaceAudio(vt.fromPlan(plan),5,8,clip,1);
 near(tl.duration,100,'duration');
 assert.equal(tl.kept.length,1);
 assert.deepEqual(tl.segments.map(s=>s.kind),['audio','media','audio','reference','audio']);
 near(tl.segments[2].source_start,18,'continues after');
});

test('edits compose and stay contiguous',()=>{
 let tl=vt.fromPlan(plan);
 tl=vt.insertClip(tl,50,clip,0,3);
 tl=vt.rippleDelete(tl,10,12);
 tl=vt.rippleDelete(tl,47,49);  // part of the inserted clip
 vt.check(tl);
 const m=vt.pictureAt(tl.kept,47.5);assert.equal(m.media,clip.path);near(m.time,1.5,'trimmed clip head (1 s removed)');
 assert.ok(vt.editsPicture(plan,tl.kept));
 assert.ok(!vt.editsPicture(plan,vt.fromPlan(plan).kept));
});

test('main-episode plans keep their target offset',()=>{
 const p={...plan,main_trim:{target_start:90}};
 near(vt.pictureAt(vt.rippleDelete(vt.fromPlan(p),0,10).kept,0).target,100,'trimmed target');
});

test('refuses bad edits',()=>{
 assert.throws(()=>vt.rippleDelete(vt.fromPlan(plan),0,100),/whole output/);
 assert.throws(()=>vt.insertClip(vt.fromPlan(plan),5,{...clip,hasVideo:false}),/picture/);
 assert.throws(()=>vt.insertClip(vt.fromPlan(plan),5,clip,10,5),/longer than the file/);
 assert.throws(()=>vt.replaceAudio(vt.fromPlan(plan),5,8,{...clip,hasAudio:false}),/no audio/);
});

test('motion fill replaces only the picture in the range, holding the frame at In',()=>{
 const tl=vt.fillRange(vt.fromPlan(plan),20,24);
 assert.equal(tl.duration,plan.duration);
 assert.deepEqual(JSON.parse(JSON.stringify(tl.segments)),JSON.parse(JSON.stringify(vt.fromPlan(plan).segments)));   // sound unchanged
 const fill=tl.kept.find(k=>k.fill);
 near(fill.hold,20,'held frame');near(vt.pictureAt(tl.kept,23).target,20,'previewed as the held frame');
 near(vt.pictureAt(tl.kept,25).target,25,'after the fill');
 const split=vt.splitKept(tl.kept,22).filter(k=>k.fill);
 assert.equal(split.length,2);assert.ok(split.every(k=>Math.abs(k.hold-20)<1e-9));
 assert.throws(()=>vt.fillRange(vt.fromPlan(plan),5,5),/Mark a range/);
});

test('black fill needs no target picture and keeps the sound',()=>{
 const tl=vt.fillRange(vt.fromPlan(plan),10,12,'black');
 assert.equal(tl.kept.find(k=>k.fill).fill,'black');
 assert.throws(()=>vt.fillRange(vt.fromPlan(plan),10,12,'blur'),/Unknown fill/);
});

test('V2 clips cover V1 where they sit and ripple with the timeline',()=>{
 const pic={path:'C:/media/logo.png',name:'logo.png',image:true,hasVideo:true,hasAudio:false,stillSeconds:5};
 let tl=vt.placeOverlay(vt.fromPlan(plan),10,pic,0,4);
 assert.equal(tl.overlays.length,1);near(vt.overlayAt(tl.overlays,12).time,2,'clip time');
 const flat=vt.flatten(tl.kept,tl.overlays);
 assert.equal(flat.filter(k=>k.media).length,1);near(vt.pictureAt(flat,11).time,1,'covers V1');near(vt.pictureAt(flat,15).target,15,'V1 after');
 tl=vt.placeOverlay(tl,12,clip,0,3);                       // overwrites the end of the first one
 assert.deepEqual(tl.overlays.map(o=>[o.at,o.length]),[[10,2],[12,3]]);
 tl=vt.rippleDelete(tl,0,5);                                // everything after 5 s moves 5 s earlier
 assert.deepEqual(tl.overlays.map(o=>[o.at,o.length]),[[5,2],[7,3]]);
 tl=vt.moveOverlay(tl,1,20);near(tl.overlays[1].at,20,'moved');
 tl=vt.trimOverlay(tl,1,'end',21);near(tl.overlays[1].length,1,'trimmed');
 tl=vt.removeOverlay(tl,0);assert.equal(tl.overlays.length,1);
 const ins=vt.insertClip(vt.placeOverlay(vt.fromPlan(plan),10,pic,0,4),12,clip,0,2);
 assert.deepEqual(ins.overlays.map(o=>[o.at,o.length]),[[10,2],[14,2]]);   // split at the insert point
});
