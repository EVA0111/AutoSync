'use strict';
// Pure editing gestures. No Electron/DOM or FFmpeg: one validated, non-ripple
// output track backed by separate source/target audio lanes.
const {validateSegments}=require('./alignment-model.cjs');
const {copyClip,pasteClip,trimTo}=require('./audio-clip-tools.cjs');
const clone=x=>JSON.parse(JSON.stringify(x));
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const MIN=0.05;
function visibleClips(segments,row){
 if(row==='video')return [];
 if(row==='source')return segments.map((s,index)=>({s,index})).filter(x=>x.s.kind==='audio');
 if(row==='target')return segments.map((s,index)=>({s,index})).filter(x=>x.s.kind!=='audio');
 return segments.map((s,index)=>({s,index}));
}
function hitClip(segments,time,track='mix',edgeSeconds=0){
 const collection=visibleClips(segments,track);
 const candidates=collection.filter(({s})=>time>=s.target_start-1e-5&&time<=s.target_end+1e-5);
 if(!candidates.length)return null;
 // A cut at the edge belongs to the clip being trimmed, not its neighbor.
 const found=candidates.find(({s})=>time>=s.target_start&&time<s.target_end)||candidates.at(-1);
 const {index,s}=found;
 if(track==='mix'&&edgeSeconds>0){
  if(time-s.target_start<=edgeSeconds&&s.target_start>0)return {index,edge:'start'};
  if(s.target_end-time<=edgeSeconds&&s.target_end<segments.at(-1).target_end)return {index,edge:'end'};
 }
 return {index,edge:null};
}
function snapTime(value,candidates,scale,thresholdPx=8,exclude=[]){
 if(!Number.isFinite(value)||!Number.isFinite(scale)||scale<=0)return value;
 let best=value,dist=thresholdPx;
 for(const t of candidates){
  if(!Number.isFinite(t)||exclude.some(x=>Math.abs(x-t)<1e-4))continue;
  const d=Math.abs(value-t)*scale;
  if(d<dist){best=t;dist=d;}
 }
 return best;
}
function candidateTimes(segments,playhead,duration){
 return [0,duration,playhead,...segments.flatMap(s=>[s.target_start,s.target_end])];
}
function placeClip(segments,duration,index,newStart,{copy=false}={}){
 const original=segments[index];if(!original)throw Error('Select an audio clip first.');
 if(original.kind!=='audio'&&original.kind!=='reference'&&original.kind!=='target_outer')
  throw Error('This clip cannot be dragged.');
 const copied=copyClip(segments,index);
 const at=clamp(newStart,0,Math.max(0,duration-copied.duration));
 if(Math.abs(at-original.target_start)<1e-5&&!copy)return validateSegments(clone(segments),duration);
 let rows=clone(segments);
 if(!copy){
  // Lift to the existing target soundtrack before overwriting the new range.
  rows=pasteClip(rows,duration,original.target_start,{kind:'reference',duration:copied.duration});
 }
 return pasteClip(rows,duration,at,copied);
}
function slipClip(segments,duration,index,delta){
 const rows=clone(segments),s=rows[index];
 if(!s||s.kind!=='audio')throw Error('Slip is available for source-audio clips.');
 if(!Number.isFinite(delta))throw Error('Invalid source offset.');
 s.source_start=clamp(s.source_start+delta,0,1e9);
 return validateSegments(rows,duration);
}
function trimClip(segments,duration,index,edge,newTime){
 const s=segments[index];if(!s)throw Error('Select a clip to trim.');
 if(edge!=='start'&&edge!=='end')throw Error('Choose a clip edge.');
 const position=clamp(newTime,edge==='start'?0:s.target_start+MIN,
  edge==='end'?duration:s.target_end-MIN);
 if(edge==='start'){
  if(position<s.target_start-MIN){
   const extra=s.target_start-position;
   const sourceStart=s.kind==='audio'?s.source_start-extra*s.speed:null;
   if(s.kind==='audio'&&sourceStart<0)throw Error('No earlier source audio is available.');
   return pasteClip(segments,duration,position,
    {kind:s.kind,duration:extra,source_start:sourceStart,speed:s.speed});
  }
  return trimTo(segments,duration,index,position,'left');
 }
 if(position>s.target_end+MIN){
  const extra=position-s.target_end;
  const sourceStart=s.kind==='audio'?s.source_start+(s.target_end-s.target_start)*s.speed:null;
  return pasteClip(segments,duration,s.target_end,
   {kind:s.kind,duration:extra,source_start:sourceStart,speed:s.speed});
 }
 return trimTo(segments,duration,index,position,'right');
}
function splitClip(segments,duration,index,time){
 const rows=clone(segments),s=rows[index];
 if(!s||!Number.isFinite(time)||time<s.target_start+MIN||time>s.target_end-MIN)
  throw Error('Click inside a clip to cut.');
 const second={...s,target_start:time};
 if(second.kind==='audio')second.source_start=s.source_start+(time-s.target_start)*s.speed;
 s.target_end=time;rows.splice(index+1,0,second);
 return validateSegments(rows,duration);
}
module.exports={visibleClips,hitClip,snapTime,candidateTimes,placeClip,slipClip,trimClip,splitClip};
