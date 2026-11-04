'use strict';

/**
 * Picture edits in Preview & Edit: the output video as a list of pieces.
 *
 * A timeline is {segments, duration, kept, tracks}. `segments` is the audio plan
 * in output time. `kept` is V1, the main picture, in order: a target piece
 * {start,end,output_start,original_start,original_end} (start/end in the
 * plan's own target time, as video_edits.py writes them), an imported clip
 * {start,end,output_start,media,media_start} (start/end only give its
 * length), or a fill {..., fill:'motion'|'black', hold} (the target picture
 * `hold` kept moving, or black; built at export).
 *
 * `tracks` are the video tracks above V1 (V2, V3 ... bottom to top), each
 * {clips, locked, hidden}. A clip sits at output time [at, at+length) and
 * shows target footage from `target`, an imported file from `media_start`, or
 * a fill. The topmost visible clip covers everything below it; flatten()
 * merges the tracks into one picture sequence for export. Ripple edits move
 * picture (every track) AND audio together, so synced audio stays on its picture.
 *
 * Pure functions: no Electron, FFmpeg or DOM. Every result is a new object.
 */
const EPS=1e-6;
const len=k=>Number(k.end)-Number(k.start);
const copy=x=>JSON.parse(JSON.stringify(x));
const TARGET_KINDS=['reference','target_outer','verified_gap'];
const cEnd=c=>Number(c.at)+Number(c.length);

function baseKept(plan){
 if(plan.video_edits?.kept?.length)return copy(plan.video_edits.kept);
 const shift=Number(plan.main_trim?.target_start||0)+Number(plan.input_trims?.target?.start||0);
 const d=Number(plan.duration);
 return [{start:0,end:d,output_start:0,original_start:shift,original_end:d+shift}];
}
// Video tracks of a saved plan (an older plan's V2 overlay list becomes one track).
function planTracks(plan){
 if(Array.isArray(plan.video_tracks))return copy(plan.video_tracks).map(t=>({clips:t.clips||[],locked:!!t.locked,hidden:!!t.hidden}));
 if(Array.isArray(plan.video_overlays)&&plan.video_overlays.length)return [{clips:copy(plan.video_overlays),locked:false,hidden:false}];
 return [];
}
function fromPlan(plan,segments){
 return {segments:copy(segments||plan.segments),duration:Number(plan.duration),kept:baseKept(plan),tracks:planTracks(plan)};
}
const timeline=(tl,over)=>check({segments:copy(tl.segments),kept:copy(tl.kept),tracks:copy(tl.tracks||[]),duration:tl.duration,...over});

/** What a picture piece shows at time t: {media,time} for an imported clip, else {target:time}. */
function pictureAt(kept,t){
 for(const k of kept){
  const a=Number(k.output_start),b=a+len(k);
  if(t>=a-1e-3&&t<b-1e-9||k===kept[kept.length-1]&&t<=b+1e-3){
   if(k.media)return {media:k.media,time:Number(k.media_start||0)+t-a,piece:k};
   if(k.fill)return {target:Number(k.hold),piece:k};          // previewed as the held frame (or black)
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

// ---- track clips ----
// A clip's content from d seconds into it: footage and media advance, a fill holds.
function advance(c,d){
 const out={...c};
 if(c.media!==undefined)out.media_start=Number(c.media_start||0)+d;
 else if(c.target!==undefined)out.target=Number(c.target)+d;
 return out;
}
// Parts of clips outside [a,b) (a clip spanning the range becomes two).
function cutClips(clips,a,b){
 const out=[];
 for(const c of clips||[]){
  const s=Number(c.at),e=cEnd(c);
  if(e<=a+EPS||s>=b-EPS){out.push({...c});continue;}
  if(s<a-EPS)out.push({...c,length:a-s});
  if(e>b+EPS)out.push({...advance(c,b-s),at:b,length:e-b});
 }
 return out.sort((x,y)=>x.at-y.at);
}
function splitClipsAt(clips,t){
 return (clips||[]).flatMap(c=>Number(c.at)<t-EPS&&cEnd(c)>t+EPS?[{...c,length:t-c.at},{...advance(c,t-c.at),at:t,length:cEnd(c)-t}]:[{...c}]);
}
function withClips(tl,k,clips){
 if(!tl.tracks?.[k])throw Error('No such video track.');
 const tracks=copy(tl.tracks);tracks[k]={...tracks[k],clips:clips.sort((x,y)=>x.at-y.at)};
 return timeline(tl,{tracks});
}
const clipOf=(tl,k,i)=>{const c=tl.tracks?.[k]?.clips?.[i];if(!c)throw Error('No clip on that track there.');return c;};
// The picture piece a clip shows over [at, at+length).
function clipPiece(c){
 const a=Number(c.at),b=cEnd(c),base={start:a,end:b,output_start:a};
 if(c.media!==undefined)return {...base,media:c.media,media_start:Number(c.media_start||0),label:c.label||''};
 if(c.fill)return {...base,original_start:Number(c.hold),original_end:Number(c.hold)+(b-a),fill:c.fill,hold:Number(c.hold)};
 return {...base,original_start:Number(c.target),original_end:Number(c.target)+(b-a)};
}
// A V1 piece as a track clip (duplicating a track keeps every cut and fill).
function pieceClip(k){
 const at=Number(k.output_start),length=len(k);
 if(k.media)return {at,length,media:k.media,media_start:Number(k.media_start||0),label:k.label||'',image:!!k.image};
 if(k.fill)return {at,length,fill:k.fill,hold:Number(k.hold)};
 return {at,length,target:Number(k.original_start)};
}

/** The output picture as one sequence: visible tracks laid over V1, bottom to top (what export renders). */
function flatten(kept,tracks){
 let out=copy(kept);
 for(const t of tracks||[]){
  if(t.hidden)continue;
  for(const c of t.clips){
   const a=Number(c.at),b=cEnd(c);
   out=splitKept(splitKept(out,a),b).filter(k=>!(Number(k.output_start)>=a-EPS&&Number(k.output_start)+len(k)<=b+EPS));
   out.push(clipPiece(c));
   out.sort((x,y)=>Number(x.output_start)-Number(y.output_start));
  }
 }
 return out;
}
/** Clip index on track k at output time t, or -1. */
function clipAt(tl,k,t){return (tl.tracks?.[k]?.clips||[]).findIndex(c=>t>=Number(c.at)-1e-6&&t<cEnd(c));}

/** Copy V1 (k=-1) or track k into a new track directly above it. */
function duplicateTrack(tl,k=-1){
 const clips=k<0?tl.kept.map(pieceClip):copy(clipsOf(tl,k));
 const tracks=copy(tl.tracks||[]);tracks.splice(k+1,0,{clips,locked:false,hidden:false});
 return timeline(tl,{tracks});
}
function addTrack(tl){return timeline(tl,{tracks:[...copy(tl.tracks||[]),{clips:[],locked:false,hidden:false}]});}
function deleteTrack(tl,k){
 if(!tl.tracks?.[k])throw Error('No such video track.');
 const tracks=copy(tl.tracks);tracks.splice(k,1);return timeline(tl,{tracks});
}
/** Put an imported clip (picture) on track k at `at`; it overwrites what is under it on that track. */
function placeMedia(tl,k,at,item,inPoint=0,length=null){
 if(!item?.path||!item.hasVideo)throw Error('Only pictures and videos can go on a video track.');
 at=Math.max(0,Math.min(tl.duration-.04,at));
 const L=Math.min(clipLength(item,inPoint,length),tl.duration-at);
 const clips=cutClips(clipsOf(tl,k),at,at+L);
 clips.push({at,length:L,media:item.path,media_start:inPoint,label:item.name||'',image:!!item.image});
 return withClips(tl,k,clips);
}
const clipsOf=(tl,k)=>{if(!tl.tracks?.[k])throw Error('No such video track.');return tl.tracks[k].clips;};
/** Move clip i of track k to start at `at` (it overwrites what it lands on). */
function moveClip(tl,k,i,at){
 const c=clipOf(tl,k,i);
 at=Math.max(0,Math.min(tl.duration-Number(c.length),at));
 const rest=copy(clipsOf(tl,k));rest.splice(i,1);
 const clips=cutClips(rest,at,at+Number(c.length));clips.push({...c,at});
 return withClips(tl,k,clips);
}
/** Trim clip i of track k: edge 'start' or 'end' moves to `time`. Footage and media stay in place. */
function trimClip(tl,k,i,edge,time){
 const c={...clipOf(tl,k,i)},s=Number(c.at),e=cEnd(c);
 if(edge==='start'){
  let t=Math.min(e-.04,Math.max(0,time));
  if(c.media!==undefined&&!c.image)t=Math.max(t,s-Number(c.media_start||0));   // not before the file starts
  if(c.target!==undefined)t=Math.max(t,s-Number(c.target));
  Object.assign(c,advance(c,t-s),{at:t,length:e-t});
 }else c.length=Math.max(.04,Math.min(tl.duration,time)-s);
 const rest=copy(clipsOf(tl,k));rest.splice(i,1);
 const clips=cutClips(rest,c.at,cEnd(c));clips.push(c);
 return withClips(tl,k,clips);
}
/** Split clip i of track k at time t into two clips. */
function splitClip(tl,k,i,t){
 const c=clipOf(tl,k,i);
 if(!(t>Number(c.at)+.02&&t<cEnd(c)-.02))throw Error('Put the playhead inside the clip to split it.');
 const clips=copy(clipsOf(tl,k));clips.splice(i,1,{...c,length:t-c.at},{...advance(c,t-c.at),at:t,length:cEnd(c)-t});
 return withClips(tl,k,clips);
}
/** Slip clip i of track k: same place and length, footage/media `delta` seconds later. */
function slipClip(tl,k,i,delta){
 const c={...clipOf(tl,k,i)};
 if(c.fill)throw Error('A fill has no footage to slip.');
 if(c.media!==undefined){if(c.image)throw Error('A still image has nothing to slip.');c.media_start=Number(c.media_start||0)+delta;if(c.media_start<0)throw Error('The clip would start before its file.');}
 else{c.target=Number(c.target)+delta;if(c.target<0)throw Error('The clip would start before the target video.');}
 const clips=copy(clipsOf(tl,k));clips[i]=c;
 return withClips(tl,k,clips);
}
function removeClip(tl,k,i){
 clipOf(tl,k,i);const clips=copy(clipsOf(tl,k));clips.splice(i,1);return withClips(tl,k,clips);
}
/** Fill [a,b) on track k with the picture shown at a (kept moving) or black. */
function fillTrack(tl,k,a,b,kind='motion'){
 a=Math.max(0,a);b=Math.min(tl.duration,b);
 if(!(b-a>EPS))throw Error('Mark a range (In and Out) or select a clip to fill.');
 if(!['motion','black'].includes(kind))throw Error('Unknown fill.');
 const below=pictureAt(flatten(tl.kept,(tl.tracks||[]).slice(0,k+1)),a);
 if(kind==='motion'&&(!below||below.target===undefined))throw Error('The picture at In is an imported clip; fill needs target footage there.');
 const clips=cutClips(clipsOf(tl,k),a,b);
 clips.push({at:a,length:b-a,fill:kind,hold:below&&below.target!==undefined?below.target:0});
 return withClips(tl,k,clips);
}

function shiftFrom(tl,at,delta){
 for(const s of tl.segments)if(s.target_start>=at-EPS){s.target_start+=delta;s.target_end+=delta;}
 for(const t of tl.tracks||[])for(const c of t.clips)if(Number(c.at)>=at-EPS)c.at=Number(c.at)+delta;
 for(const k of tl.kept)if(Number(k.output_start)>=at-EPS){
  k.output_start=Number(k.output_start)+delta;
  if(k.media){k.start=Number(k.start)+delta;k.end=Number(k.end)+delta;}
 }
}

/** Remove output [a,b): picture (every track) and audio; everything after moves earlier. */
function rippleDelete(tl,a,b){
 a=Math.max(0,a);b=Math.min(tl.duration,b);
 if(!(b-a>EPS))throw Error('Mark a range (In and Out) or select a clip to delete.');
 if(b-a>=tl.duration-1e-3)throw Error('The whole output cannot be deleted.');
 let segments=splitSegments(splitSegments(pin(tl.segments),a),b);
 let kept=splitKept(splitKept(copy(tl.kept),a),b);
 segments=segments.filter(s=>!(s.target_start>=a-EPS&&s.target_end<=b+EPS));
 kept=kept.filter(k=>!(Number(k.output_start)>=a-EPS&&Number(k.output_start)+len(k)<=b+EPS));
 const tracks=(tl.tracks||[]).map(t=>({...t,clips:cutClips(t.clips,a,b)}));
 const out={segments,kept,tracks,duration:tl.duration-(b-a)};
 shiftFrom(out,b,-(b-a));
 return check(out);
}

/** Insert an imported clip on V1 at t: its picture (and audio, or silence) push the rest later. */
function insertClip(tl,t,item,inPoint=0,length=null){
 if(!item?.path||!item.hasVideo)throw Error('Only clips with a picture can be inserted into the video.');
 const L=clipLength(item,inPoint,length);
 t=Math.max(0,Math.min(tl.duration,t));
 let segments=splitSegments(pin(tl.segments),t),kept=splitKept(copy(tl.kept),t);
 // A track clip spanning t splits there: its later part moves with everything after t.
 const tracks=(tl.tracks||[]).map(x=>({...x,clips:splitClipsAt(x.clips,t)}));
 const out={segments,kept,tracks,duration:tl.duration+L};
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
 return timeline(tl,{segments});
}

/** Fill V1 output [a,b) with the target picture shown at a, kept moving ('motion'), or black; the audio does not change. */
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
 return timeline(tl,{kept});
}

function clipLength(item,inPoint,length){
 const available=item.image?Infinity:Number(item.duration)-inPoint;
 const L=length??(item.image?Number(item.stillSeconds||5):available);
 if(!(L>0.04)||!(available>=L-1e-3))throw Error('The chosen part of the clip is empty or longer than the file.');
 return L;
}

/** Contiguous, ordered, covering pieces; ordered non-overlapping track clips; throws on anything else. */
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
 (tl.tracks||[]).forEach((t,i)=>{
  let end=0;
  for(const c of t.clips){
   if(!(Number(c.length)>0)||Number(c.at)<end-1e-3||cEnd(c)>duration+1e-3)throw Error('Edit produced overlapping or out-of-range clips on V'+(i+2)+'.');
   end=cEnd(c);
  }
 });
 return tl;
}

/** Whether the timeline changes the picture (so a video export is needed). */
function editsPicture(plan,kept){
 const base=baseKept({...plan,video_edits:undefined});
 if(plan.video_edits?.kept?.length)return true;
 return kept.length!==1||!!kept[0].media||Math.abs(len(kept[0])-len(base[0]))>1e-3||
  Math.abs(Number(kept[0].original_start)-Number(base[0].original_start))>1e-3;
}

const api={fromPlan,baseKept,planTracks,pictureAt,rippleDelete,insertClip,replaceAudio,fillRange,check,editsPicture,splitSegments,splitKept,
 flatten,clipAt,clipPiece,duplicateTrack,addTrack,deleteTrack,placeMedia,moveClip,trimClip,splitClip,slipClip,removeClip,fillTrack,cutClips};
// Node (tests) and the editor page (plain script) share this file.
if(typeof module!=='undefined'&&module.exports)module.exports=api;else globalThis.VideoTimeline=api;
