const fs=require('node:fs/promises');
const path=require('node:path');
const VIDEO=new Set(['.mkv','.mp4','.avi','.wmv','.mov','.m2ts','.mts','.webm','.mpg','.mpeg','.vob','.ts','.m4v']);
const SUBS=['.ass','.ssa','.srt','.vtt','.sbv','.sub','.mpl2','.smi','.sami','.ttml','.dfxp','.xml','.sup'];
const MEDIA=new Set([...VIDEO,'.wav','.flac','.mp3','.aac','.ac3','.wma','.m4a','.ogg','.opus','.dts']);
async function collect(paths,videoOnly=true){
 if(!Array.isArray(paths)||paths.length>10000||paths.some(p=>typeof p!=='string'||!path.isAbsolute(p)))throw Error('Drop local files or folders.');
 const found=new Set();let visited=0;const allowed=videoOnly==='subtitles'?new Set([...SUBS,...VIDEO]):videoOnly==='subtitle-target'?new Set([...SUBS,...MEDIA]):videoOnly?VIDEO:MEDIA;
 async function visit(p){if(++visited>50000)throw Error('Folder is too large. Choose an episode folder.');const s=await fs.lstat(p);if(s.isSymbolicLink())return;if(s.isDirectory()){for(const name of await fs.readdir(p))await visit(path.join(p,name));}else if(s.isFile()&&allowed.has(path.extname(p).toLowerCase()))found.add(path.resolve(p));}
 for(const p of paths)await visit(p);
 return [...found].sort((a,b)=>a.localeCompare(b,undefined,{numeric:true,sensitivity:'base'}));
}
function csvCell(v){return '"'+String(v??'').replaceAll('"','""')+'"';}
async function prepareBatch(pairs,values){
 if(!Array.isArray(pairs)||!pairs.length||pairs.length>10000)throw Error('Add at least one episode pair.');
 for(const side of ['source','target']){const seen=new Set();for(const row of pairs){const p=row?.[side];if(typeof p!=='string'||!path.isAbsolute(p)||!VIDEO.has(path.extname(p).toLowerCase())||!(await fs.stat(p)).isFile())throw Error('Every row needs an existing source and target video.');const key=process.platform==='win32'?p.toLowerCase():p;if(seen.has(key))throw Error('A video is used more than once. Remove duplicate rows.');seen.add(key);}}
 if(typeof values.out!=='string'||!path.isAbsolute(values.out))throw Error('Choose a new batch output folder.');
 const root=path.resolve(values.out);await fs.mkdir(root); // exclusive: never reuse or overwrite a prior batch
 const keys=['source','target','audio','reference','out','audio_stream','reference_stream','audio_delay','reference_delay','outer_stream'];
 const rows=pairs.map((r,i)=>[r.source,r.target,r.source,r.target,path.join(root,String(i+1).padStart(3,'0')+'_'+path.parse(r.target).name),r.audio_stream??values.audio_stream,r.reference_stream??values.reference_stream,values.audio_delay,values.reference_delay,r.outer_stream??values.outer_stream]);
 const csv=path.join(root,'jobs.csv');await fs.writeFile(csv,[keys,...rows].map(r=>r.map(csvCell).join(',')).join('\r\n')+'\r\n',{flag:'wx'});return csv;
}
module.exports={collect,prepareBatch};
