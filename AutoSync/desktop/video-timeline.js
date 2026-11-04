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
 * picture `hold` kept moving (built at export; video_edits.py). Edits ripple: later picture AND audio move together, so the
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
 return {segments:copy(segments||plan.segments),duration:Number(plan.duration),kept:baseKept(plan)};
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
 const out={segments,kept,duration:tl.duration-(b-a)};
 shiftFrom(out,b,-(b-a));
 return check(out);
}

/** Insert an imported clip at t: its picture (and audio, or silence) push the rest later. */
function insertClip(tl,t,item,inPoint=0,length=null){
 if(!item?.path||!item.hasVideo)throw Error('Only clips with a picture can be inserted into the video.');
 const L=clipLength(item,inPoint,length);
 t=Math.max(0,Math.min(tl.duration,t));
 let segments=splitSegments(pin(tl.segments),t),kept=splitKept(copy(tl.kept),t);
 const out={segments,kept,duration:tl.duration+L};
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
 return check({segments,kept:copy(tl.kept),duration:tl.duration});
}

/** Fill output [a,b) with the target picture shown at a, kept moving; the audio does not change. */
function fillRange(tl,a,b){
 a=Math.max(0,a);b=Math.min(tl.duration,b);
 if(!(b-a>EPS))throw Error('Mark a range (In and Out) or select a clip to fill.');
 const at=pictureAt(tl.kept,a);
 if(!at||at.target===undefined)throw Error('The picture at In is an imported clip; fill needs target footage there.');
 const hold=at.target;
 let kept=splitKept(splitKept(copy(tl.kept),a),b);
 kept=kept.filter(k=>!(Number(k.output_start)>=a-EPS&&Number(k.output_start)+len(k)<=b+EPS));
 kept.push({start:a,end:b,output_start:a,original_start:hold,original_end:hold+(b-a),fill:'motion',hold});
 kept.sort((x,y)=>Number(x.output_start)-Number(y.output_start));
 return check({segments:copy(tl.segments),kept,duration:tl.duration});
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
 return tl;
}

/** Whether the timeline changes the picture (so a video export is needed). */
function editsPicture(plan,kept){
 const base=baseKept({...plan,video_edits:undefined});
 if(plan.video_edits?.kept?.length)return true;
 return kept.length!==1||!!kept[0].media||Math.abs(len(kept[0])-len(base[0]))>1e-3||
  Math.abs(Number(kept[0].original_start)-Number(base[0].original_start))>1e-3;
}

const api={fromPlan,baseKept,pictureAt,rippleDelete,insertClip,replaceAudio,fillRange,check,editsPicture,splitSegments,splitKept};
// Node (tests) and the editor page (plain script) share this file.
if(typeof module!=='undefined'&&module.exports)module.exports=api;else globalThis.VideoTimeline=api;
