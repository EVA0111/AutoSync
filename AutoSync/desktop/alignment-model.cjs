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
  if(!['audio','reference','target_outer','verified_gap','media'].includes(kind))
   throw Error('Invalid region kind '+kind);
  if(kind==='media'){
   const ms=Number(row.media_start||0);
   if(typeof row.media!=='string'||!row.media||!Number.isFinite(ms)||ms<0)throw Error('Invalid imported media in region '+(i+1));
   if(row.media_stream!==null&&row.media_stream!==undefined&&!(Number.isInteger(Number(row.media_stream))&&Number(row.media_stream)>=0))
    throw Error('Invalid imported audio stream in region '+(i+1));
  }
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
 // Video edits already carry original times (input trims included); main-episode
 // trims and input trims (a marked range on the target) are offsets. Imported
 // clips have no target time.
 for(const k of plan.video_edits?.kept||[]){
  const end=Number(k.output_start)+Number(k.end)-Number(k.start);
  if(time>=Number(k.output_start)-.001&&time<=end+.001)
   return k.media?null:Number(k.original_start)+time-Number(k.output_start);
 }
 const trimmed=Number(plan.input_trims?.target?.start||0);
 if(plan.main_trim)return time+Number(plan.main_trim.target_start||0)+trimmed;
 return time+trimmed;
}
/** Output video pieces from Preview & Edit: contiguous, inside the target, imports known. */
function validateTimeline(timeline,plan,knownMedia){
 const duration=Number(timeline?.duration),kept=timeline?.kept;
 if(!Number.isFinite(duration)||duration<=0||duration>24*3600||!Array.isArray(kept)||!kept.length||kept.length>5000)
  throw Error('Invalid edited video timeline.');
 const shift=Number(plan.main_trim?.target_start||0)+Number(plan.input_trims?.target?.start||0);
 const limit=Number(plan.video_edits?.original_target_duration??plan.duration)+shift+.05;
 let at=0;
 const result=kept.map((k,i)=>{
  const start=Number(k.start),end=Number(k.end),out=Number(k.output_start);
  if(![start,end,out].every(Number.isFinite)||end<=start+1e-5||Math.abs(out-at)>1e-3)
   throw Error('Video pieces must be contiguous and nonempty (piece '+(i+1)+').');
  at=out+end-start;
  if(k.media){
   knownMedia(k.media);
   const ms=Number(k.media_start||0);
   if(!Number.isFinite(ms)||ms<0)throw Error('Invalid imported clip position (piece '+(i+1)+').');
   return {start,end,output_start:out,media:String(k.media),media_start:ms,label:String(k.label||'').slice(0,200)};
  }
  const a=Number(k.original_start),b=Number(k.original_end);
  if(k.fill){                      // motion fill: one target picture, kept moving at export
   if(k.fill!=='motion'||!Number.isFinite(Number(k.hold))||Number(k.hold)<-.05||Number(k.hold)>limit)
    throw Error('Invalid motion fill (piece '+(i+1)+').');
   const h=Number(k.hold);
   return {start,end,output_start:out,original_start:h,original_end:h+end-start,fill:'motion',hold:h};
  }
  if(!Number.isFinite(a)||!Number.isFinite(b)||a<-.05||b>limit||Math.abs(b-a-(end-start))>1e-3)
   throw Error('Video piece '+(i+1)+' is outside the target video.');
  return {start,end,output_start:out,original_start:a,original_end:b};
 });
 if(Math.abs(at-duration)>1e-3)throw Error('Video pieces must cover the edited output.');
 return {duration,kept:result};
}
module.exports={validateSegments,validateTimeline,findRegion,sourceTime,originalTargetTime};
