const fs=require('node:fs');
const path=require('node:path');
const {execFile}=require('node:child_process');
function createPreview(root){
 let current=null,session=0,cache=new Map();
 const binary=name=>[path.join(root,name+'.exe'),'C:/ffmpeg/bin/'+name+'.exe'].find(p=>fs.existsSync(p))||name;
 function cancel(){session++;if(current){current.kill();current=null;}}
 function run(name,args,token,maxBuffer=16*1024*1024){return new Promise((resolve,reject)=>{
  if(token!==session)return reject(Error('Preview cancelled.'));
  const child=execFile(binary(name),args,{windowsHide:true,timeout:120000,maxBuffer,encoding:'buffer'},(err,out,stderr)=>{if(current===child)current=null;if(token!==session)return reject(Error('Preview cancelled.'));if(err)return reject(Error((stderr?.toString()||err.message).slice(-1000)));resolve(out);});current=child;
 });}
 async function open(file){
  cancel();const token=session;
  if(typeof file!=='string'||!path.isAbsolute(file))throw Error('Choose a local video file.');
  const stat=await fs.promises.stat(file);if(!stat.isFile())throw Error('Choose a video file.');
  const key=file+'|'+stat.size+'|'+stat.mtimeMs;
  let info=cache.get(key);
  if(!info){
   const data=JSON.parse((await run('ffprobe',['-v','error','-select_streams','v:0','-show_packets','-show_streams','-show_entries','packet=pts_time,duration_time:stream=avg_frame_rate:format=start_time','-of','json',file],token,64*1024*1024)).toString());
   const packets=(data.packets||[]).map(p=>({t:Number(p.pts_time),d:Number(p.duration_time)})).filter(p=>Number.isFinite(p.t)).sort((a,b)=>a.t-b.t);
   if(!packets.length)throw Error('No usable video timestamps found.');
   const origin=packets[0].t;const ratio=(data.streams?.[0]?.avg_frame_rate||'25/1').split('/').map(Number);const step=ratio[0]>0&&ratio[1]>0?ratio[1]/ratio[0]:.04;
   const times=[...new Set(packets.map(p=>p.t-origin))];const last=packets.at(-1);const duration=last.t-origin+(last.d>0?last.d:step);
   info={file,times,duration,origin,formatStart:Number(data.format?.start_time)||0};cache.set(key,info);if(cache.size>8)cache.delete(cache.keys().next().value);
  }
  if(token!==session)throw Error('Preview cancelled.');
  active=info;return {times:info.times,duration:info.duration};
 }
 let active=null;
 async function frame(index){
  if(!active||!Number.isInteger(index)||index<0||index>=active.times.length)throw Error('Invalid preview frame.');
  cancel();const token=session,info=active;
  // -ss is relative to the demuxer start. Decode forward to the selected presentation timestamp.
  const seek=Math.max(0,info.times[index]+info.origin-info.formatStart-.00001);
  const png=await run('ffmpeg',['-v','error','-nostdin','-ss',String(seek),'-i',info.file,'-map','0:v:0','-frames:v','1','-vf','scale=960:540:force_original_aspect_ratio=decrease','-f','image2pipe','-c:v','png','pipe:1'],token);
  if(!png.length)throw Error('This frame could not be decoded. Try a nearby frame.');
  return {index,time:info.times[index],image:'data:image/png;base64,'+png.toString('base64')};
 }
 return {open,frame,cancel:()=>{cancel();active=null;}};
}
module.exports={createPreview};
