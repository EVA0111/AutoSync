'use strict';

/**
 * Picture edits in Preview & Edit: the output video as a list of pieces.
 *
 * A timeline is {segments, duration, kept}. `segments` is the audio plan in
 * output time (as before). `kept` lists the output video in order: a target
 * piece {start,end,output_start,original_start,original_end} (start/end in
 * the plan's own target time, as video_edits.py writes them) or an imported
 * clip {start,end,output_start,media,media_start} (start/end only give its
 * length), or a motion fill {..., fill:'motion', hold} that shows target
 * picture `hold` kept moving (built at export; video_edits.py). `overlays` is the
 * V2 track: imported clips {at,length,media,media_start,label} that cover V1's
 * picture where they sit (flatten() merges them into `kept` for export). Edits ripple: later picture AND audio move together, so the
 * source audio stays on the picture it was synced to.
 *
 * Pure functions: no Electron, FFmpeg or DOM. Every result is a new object.
 */
const EPS=1e-6;
const len=k=>Number(k.end)-Number(k.start);
const copy=x=>JSON.parse(JSON.stringify(x));
const TARGET_KINDS=['reference','target_outer','verified_gap'];

function baseKept(plan){
 if(plan.video_edits?.kept?.length)return copy(plan.video_edits.kept);
 const shift=Number(plan.main_trim?.target_start||0)+Number(plan.input_trims?.target?.start||0);
 const d=Number(plan.duration);
 return [{start:0,end:d,output_start:0,original_start:shift,original_end:d+shift}];
}

function fromPlan(plan,segments){
 return {segments:copy(segments||plan.segments),duration:Number(plan.duration),kept:baseKept(plan),overlays:copy(plan.video_overlays||[])};
}
const oEnd=o=>Number(o.at)+Number(o.length);
// Parts of V2 clips outside [a,b) (a clip spanning the range becomes two).
function cutOverlays(overlays,a,b){
 const out=[];
 for(const o of overlays||[]){
  const s=Number(o.at),e=oEnd(o);
  if(e<=a+EPS||s>=b-EPS){out.push({...o});continue;}
  if(s<a-EPS)out.push({...o,length:a-s});
  if(e>b+EPS)out.push({...o,at:b,length:e-b,media_start:Number(o.media_start||0)+(b-s)});
 }
 return out.sort((x,y)=>x.at-y.at);
}

/** What the output shows at time t: {media,time} for an imported clip, else {target:time}. */
function pictureAt(kept,t){
 for(const k of kept){
  const a=Number(k.output_start),b=a+len(k);
  if(t>=a-1e-3&&t<b-1e-9||k===kept[kept.length-1]&&t<=b+1e-3){
   if(k.media)return {media:k.media,time:Number(k.media_start||0)+t-a,piece:k};
   if(k.fill)return {target:Number(k.hold),piece:k};          // previewed as the held frame
   return {target:Number(k.original_start)+t-a,piece:k};
  }
 }
 return null;
}

// Target-audio clips keep pointing at the target audio they played before
// anything moved (render() reads reference_target_start).
function pin(segments){
 return segments.map(s=>TARGET_KINDS.includes(s.kind)&&s.reference_target_start===undefined?{...s,reference_target_start:s.target_start}:{...s});
}

function splitSegments(segments,t){
 const out=[];
 for(const s of segments){
  if(!(s.target_start<t-EPS&&t<s.target_end-EPS)){out.push(s);continue;}
  const d=t-s.target_start,b={...s,target_start:t};
  if(s.kind==='audio')b.source_start=Number(s.source_start)+d*Number(s.speed);
  else if(s.kind==='media')b.media_start=Number(s.media_start||0)+d;
  else b.reference_target_start=Number(s.reference_target_start??s.target_start)+d;
  out.push({...s,target_end:t},b);
 }
 return out;
}

function splitKept(kept,t){
 const out=[];
 for(const k of kept){
  const a=Number(k.output_start),b=a+len(k);
  if(!(a<t-EPS&&t<b-EPS)){out.push(k);continue;}
  const d=t-a,first={...k,end:Number(k.start)+d},second={...k,start:Number(k.start)+d,output_start:t};
  if(k.media)second.media_start=Number(k.media_start||0)+d;
  else if(k.fill){first.original_end=Number(k.original_start)+d;second.original_end=Number(k.original_start)+len(second);}
  else{first.original_end=Number(k.original_start)+d;second.original_start=Number(k.original_start)+d;}
  out.push(first,second);
 }
 return out;
}

function shiftFrom(tl,at,delta){
 for(const s of tl.segments)if(s.target_start>=at-EPS){s.target_start+=delta;s.target_end+=delta;}
 for(const o of tl.overlays||[])if(Number(o.at)>=at-EPS)o.at=Number(o.at)+delta;
 for(const k of tl.kept)if(Number(k.output_start)>=at-EPS){
  k.output_start=Number(k.output_start)+delta;
  if(k.media){k.start=Number(k.start)+delta;k.end=Number(k.end)+delta;}
 }
}

/** Remove output [a,b): picture and audio; everything after moves earlier. */
function rippleDelete(tl,a,b){
 a=Math.max(0,a);b=Math.min(tl.duration,b);
 if(!(b-a>EPS))throw Error('Mark a range (In and Out) or select a clip to delete.');
 if(b-a>=tl.duration-1e-3)throw Error('The whole output cannot be deleted.');
 let segments=splitSegments(splitSegments(pin(tl.segments),a),b);
 let kept=splitKept(splitKept(copy(tl.kept),a),b);
 segments=segments.filter(s=>!(s.target_start>=a-EPS&&s.target_end<=b+EPS));
 kept=kept.filter(k=>!(Number(k.output_start)>=a-EPS&&Number(k.output_start)+len(k)<=b+EPS));
 const out={segments,kept,overlays:cutOverlays(tl.overlays,a,b),duration:tl.duration-(b-a)};
 shiftFrom(out,b,-(b-a));
 return check(out);
}

/** Insert an imported clip at t: its picture (and audio, or silence) push the rest later. */
function insertClip(tl,t,item,inPoint=0,length=null){
 if(!item?.path||!item.hasVideo)throw Error('Only clips with a picture can be inserted into the video.');
 const L=clipLength(item,inPoint,length);
 t=Math.max(0,Math.min(tl.duration,t));
 let segments=splitSegments(pin(tl.segments),t),kept=splitKept(copy(tl.kept),t);
 const out={segments,kept,overlays:cutOverlays(tl.overlays,t,t),duration:tl.duration+L};
 // A V2 clip spanning t splits there: its later part moves with everything after t.
 out.overlays=out.overlays.flatMap(o=>Number(o.at)<t-EPS&&oEnd(o)>t+EPS?[{...o,length:t-o.at},{...o,at:t,length:oEnd(o)-t,media_start:Number(o.media_start||0)+(t-o.at)}]:[o]);
 shiftFrom(out,t,L);
 out.segments.push({kind:'media',target_start:t,target_end:t+L,media:item.path,media_start:inPoint,
  media_stream:item.hasAudio?Number(item.audioStream||0):null,label:item.name||''});
 out.kept.push({start:t,end:t+L,output_start:t,media:item.path,media_start:inPoint,label:item.name||''});
 out.segments.sort((x,y)=>x.target_start-y.target_start);
 out.kept.sort((x,y)=>Number(x.output_start)-Number(y.output_start));
 return check(out);
}

/** Play an imported file's audio over output [a,b); the picture does not change. */
function replaceAudio(tl,a,b,item,inPoint=0){
 if(!item?.path||!item.hasAudio)throw Error('This file has no audio.');
 a=Math.max(0,a);b=Math.min(tl.duration,b,a+clipLength(item,inPoint,null));
 if(!(b-a>EPS))throw Error('Mark a range (In and Out) or select a clip for the new audio.');
 let segments=splitSegments(splitSegments(pin(tl.segments),a),b);
 segments=segments.filter(s=>!(s.target_start>=a-EPS&&s.target_end<=b+EPS));
 segments.push({kind:'media',target_start:a,target_end:b,media:item.path,media_start:inPoint,
  media_stream:Number(item.audioStream||0),label:item.name||''});
 segments.sort((x,y)=>x.target_start-y.target_start);
 return check({segments,kept:copy(tl.kept),overlays:copy(tl.overlays||[]),duration:tl.duration});
}

/** Fill output [a,b) with the target picture shown at a, kept moving ('motion'), or black; the audio does not change. */
function fillRange(tl,a,b,kind='motion'){
 a=Math.max(0,a);b=Math.min(tl.duration,b);
 if(!(b-a>EPS))throw Error('Mark a range (In and Out) or select a clip to fill.');
 if(!['motion','black'].includes(kind))throw Error('Unknown fill.');
 const at=pictureAt(tl.kept,a);
 if(kind==='motion'&&(!at||at.target===undefined))throw Error('The picture at In is an imported clip; fill needs target footage there.');
 const hold=at&&at.target!==undefined?at.target:0;
 let kept=splitKept(splitKept(copy(tl.kept),a),b);
 kept=kept.filter(k=>!(Number(k.output_start)>=a-EPS&&Number(k.output_start)+len(k)<=b+EPS));
 kept.push({start:a,end:b,output_start:a,original_start:hold,original_end:hold+(b-a),fill:kind,hold});
 kept.sort((x,y)=>Number(x.output_start)-Number(y.output_start));
 return check({segments:copy(tl.segments),kept,overlays:copy(tl.overlays||[]),duration:tl.duration});
}

/** Put an imported clip (picture) on V2 at `at`: it covers V1 there and overwrites V2 clips under it. */
function placeOverlay(tl,at,item,inPoint=0,length=null){
 if(!item?.path||!item.hasVideo)throw Error('Only pictures and videos can go on a video track.');
 at=Math.max(0,Math.min(tl.duration-.04,at));
 const L=Math.min(clipLength(item,inPoint,length),tl.duration-at);
 const overlays=cutOverlays(tl.overlays,at,at+L);
 overlays.push({at,length:L,media:item.path,media_start:inPoint,label:item.name||'',image:!!item.image});
 return check({segments:copy(tl.segments),kept:copy(tl.kept),overlays:overlays.sort((x,y)=>x.at-y.at),duration:tl.duration});
}
/** Move V2 clip i to start at `at` (it overwrites what it lands on). */
function moveOverlay(tl,i,at){
 const o=tl.overlays?.[i];if(!o)throw Error('No clip on V2 there.');
 at=Math.max(0,Math.min(tl.duration-Number(o.length),at));
 const rest=copy(tl.overlays);rest.splice(i,1);
 const overlays=cutOverlays(rest,at,at+Number(o.length));overlays.push({...o,at});
 return check({segments:copy(tl.segments),kept:copy(tl.kept),overlays:overlays.sort((x,y)=>x.at-y.at),duration:tl.duration});
}
/** Trim V2 clip i: edge 'start' or 'end' moves to `time` (inside the clip's media). */
function trimOverlay(tl,i,edge,time){
 const o={...tl.overlays?.[i]};if(!o.media)throw Error('No clip on V2 there.');
 const s=Number(o.at),e=oEnd(o);
 if(edge==='start'){const t=Math.max(Math.max(0,s-Number(o.media_start||0)*(o.image?Infinity:1)),Math.min(e-.04,time));o.media_start=Math.max(0,Number(o.media_start||0)+(t-s));o.at=t;o.length=e-t;}
 else{o.length=Math.max(.04,Math.min(tl.duration,time)-s);}
 const rest=copy(tl.overlays);rest.splice(i,1);
 const overlays=cutOverlays(rest,o.at,oEnd(o));overlays.push(o);
 return check({segments:copy(tl.segments),kept:copy(tl.kept),overlays:overlays.sort((x,y)=>x.at-y.at),duration:tl.duration});
}
function removeOverlay(tl,i){
 const overlays=copy(tl.overlays||[]);overlays.splice(i,1);
 return check({segments:copy(tl.segments),kept:copy(tl.kept),overlays,duration:tl.duration});
}
/** The output picture as one sequence: V2 clips laid over V1 (what export renders). */
function flatten(kept,overlays){
 let out=copy(kept);
 for(const o of overlays||[]){
  const a=Number(o.at),b=oEnd(o);
  out=splitKept(splitKept(out,a),b).filter(k=>!(Number(k.output_start)>=a-EPS&&Number(k.output_start)+len(k)<=b+EPS));
  out.push({start:a,end:b,output_start:a,media:o.media,media_start:Number(o.media_start||0),label:o.label||''});
  out.sort((x,y)=>Number(x.output_start)-Number(y.output_start));
 }
 return out;
}
/** V2 clip showing at output time t, or null. */
function overlayAt(overlays,t){
 for(const o of overlays||[])if(t>=Number(o.at)-1e-6&&t<oEnd(o))return {media:o.media,time:Number(o.media_start||0)+t-Number(o.at),overlay:o};
 return null;
}

function clipLength(item,inPoint,length){
 const available=item.image?Infinity:Number(item.duration)-inPoint;
 const L=length??(item.image?Number(item.stillSeconds||5):available);
 if(!(L>0.04)||!(available>=L-1e-3))throw Error('The chosen part of the clip is empty or longer than the file.');
 return L;
}

/** Contiguous, ordered, covering pieces; throws on anything else. */
function check(tl){
 const {segments,kept,duration}=tl;
 let at=0;
 for(const s of segments){
  if(Math.abs(s.target_start-at)>1e-3||s.target_end<=s.target_start)throw Error('Edit produced a gap or overlap in the audio.');
  at=s.target_end;
 }
 if(Math.abs(at-duration)>1e-3)throw Error('Audio does not cover the edited video.');
 at=0;
 for(const k of kept){
  if(Math.abs(Number(k.output_start)-at)>1e-3||len(k)<=0)throw Error('Edit produced a gap or overlap in the video.');
  at=Number(k.output_start)+len(k);
 }
 if(Math.abs(at-duration)>1e-3)throw Error('Video does not cover the output.');
 let end=0;
 for(const o of tl.overlays||[]){
  if(!(Number(o.length)>0)||Number(o.at)<end-1e-3||oEnd(o)>duration+1e-3)throw Error('Edit produced overlapping or out-of-range clips on V2.');
  end=oEnd(o);
 }
 return tl;
}

/** Whether the timeline changes the picture (so a video export is needed). */
function editsPicture(plan,kept){
 const base=baseKept({...plan,video_edits:undefined});
 if(plan.video_edits?.kept?.length)return true;
 return kept.length!==1||!!kept[0].media||Math.abs(len(kept[0])-len(base[0]))>1e-3||
  Math.abs(Number(kept[0].original_start)-Number(base[0].original_start))>1e-3;
}

const api={fromPlan,baseKept,pictureAt,rippleDelete,insertClip,replaceAudio,fillRange,check,editsPicture,splitSegments,splitKept,
 placeOverlay,moveOverlay,trimOverlay,removeOverlay,flatten,overlayAt,cutOverlays};
// Node (tests) and the editor page (plain script) share this file.
if(typeof module!=='undefined'&&module.exports)module.exports=api;else globalThis.VideoTimeline=api;
