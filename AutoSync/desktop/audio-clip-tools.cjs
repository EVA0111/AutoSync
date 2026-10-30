'use strict';
// Non-ripple editing: the output/video timeline never changes duration.
// Copy and paste overwrite audio mappings only, so existing video stays in sync.
const {validateSegments}=require('./alignment-model.cjs');
const EPS=1e-6;
const clone=x=>JSON.parse(JSON.stringify(x));
function boundary(rows,at){
 const result=clone(rows);
 if(!Number.isFinite(at)||at<=EPS||at>=result[result.length-1].target_end-EPS)return result;
 const index=result.findIndex(s=>s.target_start+EPS<at&&at<s.target_end-EPS);
 if(index<0)return result;
 const left=result[index],right={...left,target_start:at};
 if(right.kind==='audio')right.source_start=left.source_start+(at-left.target_start)*left.speed;
 left.target_end=at;result.splice(index+1,0,right);return result;
}
function overwrite(segments,total,at,length,clip){
 if(!Number.isFinite(at)||at<0||at>=total||!Number.isFinite(length)||length<=.001)throw Error('Invalid placement.');
 const duration=Math.min(length,total-at);
 const to=at+duration;
 let rows=boundary(boundary(segments,at),to);
 rows=rows.filter(x=>x.target_end<=at+EPS||x.target_start>=to-EPS);
 const region={kind:clip.kind,target_start:at,target_end:to};
 if(clip.kind==='audio'){
  if(!Number.isFinite(clip.source_start)||clip.source_start<0||!Number.isFinite(clip.speed)||clip.speed<=0)
   throw Error('Copied audio mapping is invalid.');
  region.source_start=clip.source_start;
  region.speed=clip.speed;
 }else if(clip.kind!=='reference'&&clip.kind!=='target_outer'){
  throw Error('Unsupported audio clip.');
 }
 rows.push(region);rows.sort((a,b)=>a.target_start-b.target_start);
 return validateSegments(rows,total);
}
function copyClip(segments,index,inPoint=null,outPoint=null){
 const s=segments[index];if(!s)throw Error('Choose an audio clip first.');
 const from=inPoint===null?s.target_start:Number(inPoint);
 const to=outPoint===null?s.target_end:Number(outPoint);
 if(!Number.isFinite(from)||!Number.isFinite(to)||from<s.target_start-EPS||to>s.target_end+EPS||to-from<.05)
  throw Error('Set an In and Out point inside the selected region.');
 const copied={kind:s.kind,duration:to-from};
 if(s.kind==='audio'){
  copied.source_start=s.source_start+(from-s.target_start)*s.speed;
  copied.speed=s.speed;
 }
 return copied;
}
function trimTo(segments,total,index,position,which){
 const s=segments[index];if(!s)throw Error('Select a clip.');
 if(!Number.isFinite(position)||position<=s.target_start+.05||position>=s.target_end-.05)
  throw Error('Put the playhead inside the selected clip.');
 const start=which==='left'?s.target_start:position;
 const end=which==='left'?position:s.target_end;
 if(which!=='left'&&which!=='right')throw Error('Invalid trim edge.');
 return overwrite(segments,total,start,end-start,{kind:'reference'});
}
function pasteClip(segments,total,at,clip){
 if(!clip||!Number.isFinite(clip.duration)||clip.duration<.05)throw Error('Copy a clip before pasting.');
 return overwrite(segments,total,at,clip.duration,clip);
}
module.exports={copyClip,pasteClip,trimTo,overwrite,boundary};
