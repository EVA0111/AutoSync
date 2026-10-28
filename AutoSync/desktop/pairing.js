(function(root){
function episode(file){const name=file.split(/[\\/]/).pop().replace(/\.[^.]+$/,'');let m=name.match(/s(\d{1,2})[ ._-]*e(\d{1,4})/i);if(m)return `${+m[1]}:${+m[2]}`;m=name.match(/(?:episode|ep|第)[ ._-]*(\d{1,4})(?:話)?/i);if(m)return `1:${+m[1]}`;const clean=name.replace(/\[[^\]]*\]|\([^)]*\)/g,' ').replace(/\b(?:480|576|720|1080|2160)p?\b|\b(?:19|20)\d{2}\b|\b(?:264|265)\b/g,' ');const numbers=[...clean.matchAll(/(?:^|\D)(\d{1,3})(?=\D|$)/g)];return numbers.length===1?`1:${+numbers[0][1]}`:null;}
function match(sources,targets){const ids=sources.map(episode),other=targets.map(episode);if(ids.some(x=>!x)||other.some(x=>!x)||new Set(ids).size!==ids.length||new Set(other).size!==other.length)return null;const by=new Map(other.map((id,i)=>[id,targets[i]]));if(ids.length!==other.length||ids.some(id=>!by.has(id)))return null;return ids.map(id=>by.get(id));}
const api={episode,match};if(typeof module!=='undefined')module.exports=api;else root.pairing=api;
})(globalThis);
