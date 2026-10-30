'use strict';

/** Pure plan validation, independent of Electron, FFmpeg and the GUI. */
function validateSegments(rows,duration){
 const limit=Number(duration);
 if(!Number.isFinite(limit)||limit<=0||!Array.isArray(rows)||!rows.length||rows.length>5000)
  throw Error('Invalid audio segments or output duration.');
 let previous=0;
 const result=[];
 rows.forEach((row,i)=>{
  if(!row||typeof row!=='object')throw Error('Invalid region '+(i+1));
  const start=Number(row.target_start),end=Number(row.target_end);
  if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end<=start+1e-5||
    Math.abs(previous-start)>1e-3||end>limit+.001)
   throw Error('Regions must be contiguous, ordered, nonempty and inside the output timeline (region '+(i+1)+').');
  previous=end;
  const kind=row.kind;
  if(!['audio','reference','target_outer','verified_gap'].includes(kind))
   throw Error('Invalid region kind '+kind);
  if(kind==='audio'){
   const ss=Number(row.source_start),speed=Number(row.speed);
   if(!Number.isFinite(ss)||ss<0||!Number.isFinite(speed)||speed<.5||speed>2)
    throw Error('Invalid source time or speed in region '+(i+1));
   result.push({...row,kind,target_start:start,target_end:end,source_start:ss,speed});
  }else result.push({...row,kind,target_start:start,target_end:end});
 });
 if(Math.abs(previous-limit)>.001)throw Error('Regions must cover the complete output timeline.');
 return result;
}
function findRegion(segments,time){
 if(!Number.isFinite(time)||time<0)return null;
 for(let i=0;i<segments.length;i++){
  const s=segments[i];
  if(s.target_start<=time&&(time<s.target_end||i===segments.length-1&&time<=s.target_end))
   return {index:i,region:s};
 }
 return null;
}
function sourceTime(segments,time){
 const found=findRegion(segments,time);
 if(!found||found.region.kind!=='audio')return null;
 const r=found.region;
 return r.source_start+(time-r.target_start)*r.speed;
}
function originalTargetTime(plan,time){
 for(const k of plan.video_edits?.kept||[]){
  const end=Number(k.output_start)+Number(k.end)-Number(k.start);
  if(time>=Number(k.output_start)-.001&&time<=end+.001)
   return Number(k.original_start)+time-Number(k.output_start);
 }
 if(plan.main_trim)return time+Number(plan.main_trim.target_start||0);
 return time;
}
module.exports={validateSegments,findRegion,sourceTime,originalTargetTime};
