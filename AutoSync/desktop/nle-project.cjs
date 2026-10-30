'use strict';
// Clip-based, non-ripple NLE timeline for AutoSync's audio alignment plans.
// Timeline clips are independent objects until flattened for the existing engine.
// FilmCraft was studied as a UX reference; this is original JS code, not a port.
const {validateSegments}=require('./alignment-model.cjs');
const EPS=0.00001,MIN=.04,MIN_SOURCE=0.00001;
const copy=x=>JSON.parse(JSON.stringify(x));
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const finite=n=>typeof n==='number'&&Number.isFinite(n);
const trackIds=['A1','A2','A3'];
function nextId(project){return 'c'+(project.nextId++);}
function newProject(plan){
 const segments=validateSegments(plan.segments,plan.duration);
 const project={duration:Number(plan.duration),nextId:1,tracks:[
  {id:'A1',name:'Source audio',type:'audio',priority:2,mute:false,solo:false,locked:false,clips:[]},
  {id:'A2',name:'Target audio',type:'audio',priority:1,mute:false,solo:false,locked:false,clips:[]},
  {id:'A3',name:'Extra audio',type:'audio',priority:3,mute:false,solo:false,locked:false,clips:[]}
 ]};
 const a1=project.tracks[0],a2=project.tracks[1];
 for(const s of segments){
  if(s.kind==='audio'){
   a1.clips.push({id:nextId(project),kind:'audio',start:s.target_start,end:s.target_end,
    sourceStart:s.source_start,speed:s.speed});
  }
  const previous=a2.clips.at(-1),kind=s.kind==='audio'?'reference':s.kind;
  if(previous&&previous.kind===kind&&Math.abs(previous.end-s.target_start)<EPS)
   previous.end=s.target_end;
  else a2.clips.push({id:nextId(project),kind,start:s.target_start,end:s.target_end});
 }
 return validateProject(project);
}
function validateProject(project){
 if(!project||!finite(project.duration)||project.duration<=0||!Array.isArray(project.tracks)||
  project.tracks.length!==3||project.tracks.some((t,i)=>t.id!==trackIds[i]))
  throw Error('Invalid multitrack timeline.');
 for(const track of project.tracks){
  if(!Array.isArray(track.clips)||track.clips.length>2500)throw Error('Invalid track clips.');
  let previous=0;
  for(const c of track.clips){
   if(!c||typeof c.id!=='string'||!['audio','reference','target_outer','verified_gap'].includes(c.kind)||
    !finite(c.start)||!finite(c.end)||c.start<-EPS||c.end>project.duration+EPS||
    c.end-c.start<MIN_SOURCE-EPS||c.start<previous-EPS)
    throw Error('Overlapping or invalid clips on '+track.id);
   if(c.kind==='audio'&&(!finite(c.sourceStart)||c.sourceStart<0||!finite(c.speed)||c.speed<.5||c.speed>2))
    throw Error('Invalid source audio clip.');
   previous=c.end;
  }
 }
 return project;
}
function findClip(project,id){
 for(const track of project.tracks){const index=track.clips.findIndex(c=>c.id===id);
  if(index>=0)return {track,clip:track.clips[index],index};}
 throw Error('Select an audio clip.');
}
function normalizeClips(track){track.clips.sort((a,b)=>a.start-b.start);}
function checkCollision(track,clip,id){
 return track.clips.some(c=>c.id!==id&&c.start<clip.end-EPS&&c.end>clip.start+EPS);
}
function split(project,id,at){
 const p=copy(project),{track,clip,index}=findClip(p,id);
 if(track.locked)throw Error('Unlock this track before editing.');
 if(!finite(at)||at<=clip.start+MIN||at>=clip.end-MIN)throw Error('Put the razor inside the clip.');
 const right={...clip,id:nextId(p),start:at};
 if(clip.kind==='audio')right.sourceStart=clip.sourceStart+(at-clip.start)*clip.speed;
 clip.end=at;track.clips.splice(index+1,0,right);
 return validateProject(p);
}
function trim(project,id,edge,at){
 const p=copy(project),{track,clip}=findClip(p,id);
 if(track.locked)throw Error('Unlock this track before editing.');
 const lo=edge==='in'?0:clip.start+MIN,hi=edge==='out'?p.duration:clip.end-MIN;
 if(!['in','out'].includes(edge)||!finite(at)||at<lo-EPS||at>hi+EPS)throw Error('Invalid trim position.');
 const oldStart=clip.start,oldEnd=clip.end;
 if(edge==='in'){clip.start=at;if(clip.kind==='audio')clip.sourceStart+=(at-oldStart)*clip.speed;}
 else clip.end=at;
 if(clip.end-clip.start<MIN||clip.kind==='audio'&&clip.sourceStart<-EPS||checkCollision(track,clip,id)){
  throw Error('Trim overlaps another clip or extends before available source audio.');
 }
 if(oldEnd===clip.end&&oldStart===clip.start)return p;
 return validateProject(p);
}
function move(project,id,trackId,at){
 const p=copy(project),found=findClip(p,id),destination=p.tracks.find(t=>t.id===trackId);
 if(!destination)throw Error('Choose an audio track.');
 if(found.track.locked||destination.locked)throw Error('Unlock the affected tracks before moving clips.');
 const length=found.clip.end-found.clip.start;
 if(!finite(at)||at<-EPS||at+length>p.duration+EPS)throw Error('Clip falls outside the sequence.');
 const transferred={...found.clip,start:clamp(at,0,p.duration-length),end:clamp(at,0,p.duration-length)+length};
 if(checkCollision(destination,transferred,id))throw Error('This clip overlaps another clip on '+trackId+'.');
 found.track.clips.splice(found.index,1);
 destination.clips.push(transferred);normalizeClips(destination);
 return validateProject(p);
}
function remove(project,id){
 const p=copy(project),{track,index}=findClip(p,id);
 if(track.locked)throw Error('Unlock this track before deleting clips.');
 track.clips.splice(index,1);
 return validateProject(p);
}
function copyClip(project,id,inPoint=null,outPoint=null){
 const {clip}=findClip(project,id);
 const start=inPoint==null?clip.start:Number(inPoint),end=outPoint==null?clip.end:Number(outPoint);
 if(!finite(start)||!finite(end)||start<clip.start-EPS||end>clip.end+EPS||end-start<MIN)
  throw Error('Set In/Out inside the clip.');
 return {kind:clip.kind,duration:end-start,
  ...(clip.kind==='audio'?{sourceStart:clip.sourceStart+(start-clip.start)*clip.speed,speed:clip.speed}:{})};
}
function paste(project,clipboard,trackId,at,{overwrite=false}={}){
 const p=copy(project),destination=p.tracks.find(t=>t.id===trackId);
 if(!destination||destination.locked)throw Error('Choose an unlocked destination track.');
 if(!clipboard||!finite(clipboard.duration)||clipboard.duration<MIN||!finite(at)||at<0||
   at+clipboard.duration>p.duration+EPS)throw Error('Copied clip does not fit the destination.');
 const clip={id:nextId(p),kind:clipboard.kind,start:at,end:at+clipboard.duration};
 if(clip.kind==='audio'){clip.sourceStart=clipboard.sourceStart;clip.speed=clipboard.speed;}
 if(overwrite){
  // NLE overwrite: trim/split underlying clip portions, never ripple other tracks.
  const survivors=[];
  for(const c of destination.clips){
   if(c.end<=clip.start+EPS||c.start>=clip.end-EPS){survivors.push(c);continue;}
   if(c.start<clip.start-EPS)survivors.push({...c,end:clip.start});
   if(c.end>clip.end+EPS){
    const right={...c,id:nextId(p),start:clip.end};
    if(c.kind==='audio')right.sourceStart=c.sourceStart+(clip.end-c.start)*c.speed;
    survivors.push(right);
   }
  }
  destination.clips=survivors;
 }else if(checkCollision(destination,clip)){throw Error('Clip overlaps this track. Use Overwrite or choose an empty space.');}
 destination.clips.push(clip);normalizeClips(destination);
 return validateProject(p);
}
function setTrack(project,trackId,property,value){
 const p=copy(project),track=p.tracks.find(t=>t.id===trackId);
 if(!track||!['mute','solo','locked'].includes(property)||typeof value!=='boolean')throw Error('Invalid track action.');
 track[property]=value;return p;
}
function flatSegments(project){
 validateProject(project);
 const audible=project.tracks.filter(t=>!t.mute);
 const solo=audible.filter(t=>t.solo);
 const active=(solo.length?solo:audible).slice().sort((a,b)=>b.priority-a.priority);
 const points=[0,project.duration];
 for(const track of active)for(const c of track.clips)points.push(c.start,c.end);
 points.sort((a,b)=>a-b);
 const bounds=points.filter((x,i)=>i===0||x-points[i-1]>EPS),rows=[];
 for(let i=0;i<bounds.length-1;i++){
  const start=bounds[i],end=bounds[i+1];
  if(end-start<EPS)continue;
  let chosen;
  for(const t of active){chosen=t.clips.find(c=>c.start<=start+EPS&&c.end>=end-EPS);if(chosen)break;}
  const row={kind:chosen?.kind||'verified_gap',target_start:start,target_end:end};
  if(row.kind==='audio'){row.source_start=chosen.sourceStart+(start-chosen.start)*chosen.speed;row.speed=chosen.speed;}
  const prev=rows.at(-1);
  const same=prev&&prev.kind===row.kind&&Math.abs(prev.target_end-start)<EPS&&
   (row.kind!=='audio'||Math.abs(prev.source_start+(prev.target_end-prev.target_start)*prev.speed-row.source_start)<.0001&&Math.abs(prev.speed-row.speed)<EPS);
  if(same)prev.target_end=end;
  else rows.push(row);
 }
 return validateSegments(rows,project.duration);
}
function snap(project,time,{threshold=.15,playhead,exclude=null}={}){
 const candidates=[0,project.duration,...(finite(playhead)?[playhead]:[])];
 for(const t of project.tracks)for(const c of t.clips)if(c.id!==exclude)candidates.push(c.start,c.end);
 let nearest=time,delta=threshold;
 for(const edge of candidates)if(Math.abs(edge-time)<delta){nearest=edge;delta=Math.abs(edge-time);}
 return clamp(nearest,0,project.duration);
}
module.exports={newProject,validateProject,flatSegments,split,trim,move,remove,copyClip,paste,setTrack,snap,findClip};
