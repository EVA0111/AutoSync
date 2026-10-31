'use strict';
const fs=require('node:fs');
const path=require('node:path');

function targetPath(request){
 for(const job of request.jobs||[]){
  const v=job.values||{};
  const target=v.target||job.pairs?.[0]?.target||v.target_media||v.plan;
  if(typeof target==='string'&&target.trim())return target;
 }
 return '';
}
function temporaryRoot(request){
 const chosen=request.temp_dir;
 if(chosen!==undefined&&chosen!==null&&typeof chosen!=='string')
  throw Error('Temporary directory must be a folder path.');
 if(typeof chosen==='string'&&chosen.trim()){
  if(!path.isAbsolute(chosen.trim()))throw Error('Choose an absolute temporary folder path.');
  return path.resolve(chosen.trim());
 }
 const target=targetPath(request);
 if(!target||!path.isAbsolute(target))throw Error('Choose a target file or a custom temporary folder.');
 return path.join(path.dirname(path.resolve(target)),'AutoSync Temp');
}
function prepareTemporaryRoot(request){
 const dir=temporaryRoot(request);
 fs.mkdirSync(dir,{recursive:true});
 if(!fs.statSync(dir).isDirectory())throw Error('Temporary location is not a directory.');
 return dir;
}
module.exports={temporaryRoot,prepareTemporaryRoot};
