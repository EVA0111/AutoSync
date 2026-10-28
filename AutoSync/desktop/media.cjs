const fs=require('node:fs');const path=require('node:path');const {execFile}=require('node:child_process');
function probe(file,root){
 if(typeof file!=='string'||!path.isAbsolute(file)||!fs.existsSync(file)||!fs.statSync(file).isFile())return Promise.reject(Error('Choose an existing local media file.'));
 const binary=[path.join(root,'ffprobe.exe'),'C:/ffmpeg/bin/ffprobe.exe'].find(p=>fs.existsSync(p))||'ffprobe';
 return new Promise((resolve,reject)=>execFile(binary,['-v','error','-show_streams','-of','json',file],{windowsHide:true,timeout:30000,maxBuffer:4*1024*1024},(err,stdout,stderr)=>{
  if(err)return reject(Error(err.code==='ENOENT'?'FFprobe was not found. Install FFmpeg or put ffprobe.exe beside AutoSync.':(stderr||err.message).slice(-1200)));
  try{const counts={};resolve(JSON.parse(stdout).streams.filter(s=>['audio','subtitle'].includes(s.codec_type)).map(s=>{const type=s.codec_type,index=counts[type]||0;counts[type]=index+1;return {type,index,streamIndex:s.index,language:s.tags?.language||'und',title:s.tags?.title||'',codec:s.codec_name||'unknown',channels:s.channels||0,layout:s.channel_layout||'',default:!!s.disposition?.default,forced:!!s.disposition?.forced};}));}catch(e){reject(Error('Invalid FFprobe response: '+e.message));}
 }));
}
module.exports={probe};
