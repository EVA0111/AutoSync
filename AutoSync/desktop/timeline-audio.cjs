'use strict';
// Audio and video previews for manual alignment review. FFmpeg is invoked directly,
// with argv arrays (never a shell). The source media are never modified.
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {execFile}=require('node:child_process');
function createTimeline(root){
  const cache=new Map();
  function bin(name){
    for(const p of [path.join(root,name+'.exe'),'C:/ffmpeg/bin/'+name+'.exe'])if(fs.existsSync(p))return p;
    return name;
  }
  function run(name,args,maxBuffer=64*1024*1024,timeout=180000){
    return new Promise((resolve,reject)=>execFile(bin(name),args,
      {windowsHide:true,encoding:'buffer',maxBuffer,timeout},
      (err,out,stderr)=>err?reject(Error((stderr||Buffer.from(err.message)).toString().slice(-1800))):resolve(out)));
  }
  function absoluteFile(file){
    if(typeof file!=='string'||!path.isAbsolute(file)||!fs.existsSync(file)||!fs.statSync(file).isFile())
      throw Error('The source file is missing: '+String(file));
    return file;
  }
  function number(x,name,min=0,max=1e7){
    const v=Number(x);if(!Number.isFinite(v)||v<min||v>max)throw Error('Invalid '+name);return v;
  }
  function validate(p){
    if(!p||typeof p!=='object'||!Array.isArray(p.segments)||!p.segments.length||p.segments.length>5000)
      throw Error('Not a usable AutoSync plan.');
    number(p.duration,'output duration',.1,86400);
    absoluteFile(p.audio);absoluteFile(p.target_video);
    if(p.source_video)absoluteFile(p.source_video);
    if(p.reference)absoluteFile(p.reference);
    let cursor=0;
    for(let i=0;i<p.segments.length;i++){
      const s=p.segments[i],a=number(s.target_start,'region start'),
        b=number(s.target_end,'region end');
      if(Math.abs(a-cursor)>.0002||b<=a+.00001)throw Error('Regions must be contiguous and ordered (region '+(i+1)+').');
      if(!['audio','reference','verified_gap','target_outer'].includes(s.kind))throw Error('Unsupported region type.');
      if(s.kind==='audio'){
        number(s.source_start,'source position');
        number(s.speed,'speed',.5,2);
      }
      cursor=b;
    }
    if(Math.abs(cursor-p.duration)>.0002)throw Error('The region durations must match the output duration.');
    return p;
  }
  async function load(file){
    absoluteFile(file);
    if(fs.statSync(file).size>8*1024*1024)throw Error('Plan file is too large.');
    const p=validate(JSON.parse(await fs.promises.readFile(file,'utf8')));
    return {plan:p,path:file};
  }
  function audioLocation(p,which){
    if(which==='source')return {file:absoluteFile(p.audio),stream:number(p.audio_stream||0,'source audio stream',0,100)};
    return {file:absoluteFile(p.reference||p.target_video),
      stream:number(p.reference?p.reference_stream||0:p.outer_stream||0,'target audio stream',0,100)};
  }
  function waveKey(q){const st=fs.statSync(q.file);return q.file+'|'+q.stream+'|'+st.size+'|'+st.mtimeMs;}
  async function wave(p,which){
    validate(p);
    if(!['source','target'].includes(which))throw Error('Unknown waveform track.');
    const q=audioLocation(p,which),key=waveKey(q);
    if(cache.has(key))return cache.get(key);
    const raw=await run('ffmpeg',['-v','error','-nostdin','-i',q.file,
      '-map','0:a:'+q.stream,'-vn','-ac','1','-ar','1000','-f','s16le','pipe:1'],72*1024*1024);
    if(raw.length<2)throw Error('Empty audio waveform.');
    const samples=Math.floor(raw.length/2),size=Math.max(1,Math.ceil(samples/3000));
    const peak=[];
    for(let start=0;start<samples;start+=size){
      let top=0;
      for(let i=start;i<Math.min(samples,start+size);i++){
        const a=Math.abs(raw.readInt16LE(i*2));if(a>top)top=a;
      }
      peak.push(Math.round(1000*Math.sqrt(top/32768)));
    }
    const result={peaks:peak,duration:samples/1000};
    cache.set(key,result);if(cache.size>5)cache.delete(cache.keys().next().value);
    return result;
  }
  function part(p,s,start,end){
    const duration=end-start;
    if(s.kind==='audio')return {file:p.audio,track:p.audio_stream||0,
      pos:s.source_start+(start-s.target_start)*s.speed,speed:s.speed,duration};
    if(s.kind==='target_outer')return {file:p.target_video,track:p.outer_stream||0,
      pos:(s.reference_target_start??s.target_start)+(start-s.target_start)-(p.outer_shift||0),speed:1,duration};
    const ref=p.reference||p.target_video;
    return {file:ref,track:p.reference?p.reference_stream||0:p.outer_stream||0,
      pos:(s.reference_target_start??s.target_start)+(start-s.target_start)-(p.reference_shift||0),speed:1,duration};
  }
  async function audio(p,which,t){
    validate(p);t=number(t,'playhead');
    let args=['-hide_banner','-v','error','-nostdin'],filters=[],parts=[];
    const end=Math.min(p.duration,t+9);
    if(which==='source'||which==='target'){
      const q=audioLocation(p,which);
      args.push('-ss',String(t),'-t','9','-i',q.file,
        '-map','0:a:'+q.stream,'-ac','2','-ar','48000');
    }else if(which==='output'){
      if(t>=p.duration)throw Error('Playhead is beyond the output.');
      for(const s of p.segments){
        const a=Math.max(t,s.target_start),b=Math.min(end,s.target_end);
        if(b-a<.0001)continue;
        parts.push(part(p,s,a,b));
      }
      if(!parts.length||parts.length>24)throw Error('Too many tiny regions for an audio preview.');
      for(let i=0;i<parts.length;i++){
        const q=parts[i];absoluteFile(q.file);number(q.pos,'source time');
        args.push('-ss',String(q.pos),'-t',String(q.duration*q.speed+.08),'-i',q.file);
        filters.push('['+i+':a:'+q.track+']atrim=start=0:duration='+
          (q.duration*q.speed).toFixed(6)+',asetpts=PTS-STARTPTS,aresample=48000,atempo='+
          Number(q.speed).toFixed(8)+',atrim=duration='+q.duration.toFixed(6)+
          ',aformat=sample_rates=48000:channel_layouts=stereo[a'+i+']');
      }
      if(parts.length===1){
        args.push('-filter_complex',filters.join(';'),'-map','[a0]');
      }else{
        const names=parts.map((_,i)=>'[a'+i+']').join('');
        args.push('-filter_complex',filters.join(';')+';'+names+
          'concat=n='+parts.length+':v=0:a=1[out]','-map','[out]');
      }
    }else throw Error('Unknown preview track.');
    args.push('-c:a','libmp3lame','-q:a','5','-f','mp3','pipe:1');
    const data=await run('ffmpeg',args,20*1024*1024,120000);
    if(!data.length)throw Error('Preview produced no audio.');
    return 'data:audio/mpeg;base64,'+data.toString('base64');
  }
  async function thumb(p,which,t){
    validate(p);t=number(t,'thumbnail timestamp');
    let file=which==='source'?p.source_video:p.target_video;
    if(!file)throw Error('A source video is required for picture preview.');
    absoluteFile(file);
    const data=await run('ffmpeg',['-v','error','-nostdin','-ss',String(t),'-i',file,
      '-map','0:v:0','-frames:v','1','-vf',
      'scale=480:270:force_original_aspect_ratio=decrease',
      '-f','image2pipe','-c:v','mjpeg','pipe:1'],3*1024*1024,45000);
    return 'data:image/jpeg;base64,'+data.toString('base64');
  }
  async function save(p,originalFile){
    validate(p);absoluteFile(originalFile);
    const parent=path.dirname(originalFile);
    let output=null;
    for(let k=0;k<100;k++){
      const name='manual-edit-'+new Date().toISOString().replace(/[-:TZ.]/g,'').slice(0,14)+(k?'-'+k:'');
      const f=path.join(parent,name);
      if(!fs.existsSync(f)){output=f;break;}
    }
    if(!output)throw Error('Could not create a unique edited output folder.');
    fs.mkdirSync(output,{recursive:false});
    // Revalidated copy, with declared manual cut approvals for new source-only joins.
    const clean=JSON.parse(JSON.stringify(p));
    clean.review=Array.isArray(clean.review)?clean.review:[];
    for(let i=1;i<clean.segments.length;i++){
      const left=clean.segments[i-1],right=clean.segments[i];
      if(left.kind!=='audio'||right.kind!=='audio')continue;
      const jump=right.source_start-(left.source_start+(left.target_end-left.target_start)*left.speed);
      if(jump>.25)clean.review.push({start:Math.max(0,right.target_start-.15),
        end:Math.min(clean.duration,right.target_start+.15),splice:right.target_start,
        confidence:'manual',reason:'Join manually accepted in Preview + Edit; check the rendered audio.'});
    }
    const dest=path.join(output,'plan.json');
    try{await fs.promises.writeFile(dest,JSON.stringify(clean,null,2)+'\n',{flag:'wx'});
      await fs.promises.writeFile(path.join(output,'README.txt'),
        'This folder contains your manual alignment plan. Render it from AutoSync > Saved plan.\r\n'+
        'Original: '+originalFile+'\r\nMedia were not changed when saving.\r\n');}
    catch(e){await fs.promises.rm(output,{recursive:true,force:true});throw e;}
    return dest;
  }
  return {load,wave,audio,thumb,save};
}
module.exports={createTimeline};
