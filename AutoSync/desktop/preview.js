const manualMarks={source:new Map(),target:new Map()};
function previewTime(t){if(t==null)return 'Not set';const ms=Math.round(t*1000);return [Math.floor(ms/3600000),Math.floor(ms/60000)%60,Math.floor(ms/1000)%60].map(n=>String(n).padStart(2,'0')).join(':')+'.'+String(ms%1000).padStart(3,'0');}
function manualPairValues(source,target){
 const result={};
 for(const [side,file] of [['source',source],['target',target]]){
  const mark=manualMarks[side].get(file);if(!mark)continue;
  if(!Number.isFinite(mark.start)||!Number.isFinite(mark.end)||mark.start<0||mark.end<=mark.start)throw Error('Choose a valid '+side+' trim range.');
  result[side+'_trim_start']=String(mark.start);result[side+'_trim_end']=String(mark.end);
 }
 return result;
}
function addPreviewButton(row,name,side,file){
 name.classList.add('preview-filename');
 const b=document.createElement('button');b.className='preview-icon';b.type='button';
 b.title='Preview video and trim before syncing';b.setAttribute('aria-label',`Preview ${side}: ${name.textContent}`);
 b.innerHTML='<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="3" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="m10 8 6 4-6 4Z" fill="currentColor"/></svg>';
 b.onclick=e=>{e.stopPropagation();if(!running)openVideoPreview(side,file);};b.onkeydown=e=>e.stopPropagation();row.append(b);
 const mark=manualMarks[side].get(file);
 if(mark){b.classList.add('marked');b.title=`Trim range: ${previewTime(mark.start)} – ${previewTime(mark.end)}. Click to edit.`;const tag=document.createElement('small');tag.className='preview-range';tag.textContent='Trim '+previewTime(mark.start)+' – '+previewTime(mark.end);name.append(document.createElement('br'),tag);}
}
const previewDialog=document.createElement('dialog');previewDialog.className='video-preview';previewDialog.setAttribute('aria-labelledby','preview-title');
previewDialog.innerHTML=`<div class="preview-heading"><div><h2 id="preview-title">Trim before syncing</h2><p id="preview-file"></p></div><button id="preview-x" aria-label="Close preview">×</button></div>
<div class="preview-picture"><img id="preview-image" alt="Selected video frame"><span id="preview-loading" role="status">Reading video timestamps…</span></div>
<div class="preview-position"><output id="preview-position">00:00:00.000</output><span id="preview-frame-label"></span><span id="preview-length"></span></div>
<input id="preview-seek" type="range" min="0" max="0" step="1" value="0" aria-label="Seek video">
<div class="preview-transport"><button id="preview-first" title="First frame">|←</button><button id="preview-prev" title="Previous frame (Left arrow)">← Frame</button><button id="preview-next" title="Next frame (Right arrow)">Frame →</button><button id="preview-last" title="Last frame">→|</button><label for="preview-jump">Time</label><input id="preview-jump" placeholder="00:00:00.000" aria-label="Go to timestamp"><button id="preview-go">Go</button><label for="preview-frame-jump">Frame</label><input id="preview-frame-jump" type="number" min="1" step="1" placeholder="1" aria-label="Go to frame number"><button id="preview-frame-go">Go</button></div>
<div class="preview-marks"><div><button id="preview-mark-start">Trim start</button><output id="preview-start">Not set</output><button id="preview-goto-start" class="link">Go to start</button></div><div><button id="preview-mark-end">Trim end</button><output id="preview-end">Not set</output><button id="preview-goto-end" class="link">Go to end</button></div></div>
<p class="hint">Keep only the marked range before syncing. Video and audio are trimmed together; original files stay unchanged. Start is included; end is excluded. Use “Video end” to include the last frame. Source and target trims are independent. Frames start at 1. Preview is silent.</p>
<div class="preview-actions"><button id="preview-end-video">Video end</button><button id="preview-clear">Clear marks</button><span id="preview-error" role="alert"></span><button id="preview-cancel">Cancel</button><button id="preview-save" class="primary">Save trim</button></div>`;
document.body.append(previewDialog);
let previewState=null,previewTimer=null,previewGeneration=0;
function previewControls(enabled){previewDialog.querySelectorAll('input,button').forEach(el=>{if(!['preview-x','preview-cancel'].includes(el.id))el.disabled=!enabled;});}
function showPreviewMarks(){const s=previewState;if(!s)return;$('preview-start').textContent=previewTime(s.start);$('preview-end').textContent=previewTime(s.end);$('preview-goto-start').disabled=s.start==null;$('preview-goto-end').disabled=s.end==null;}
async function openVideoPreview(side,file){
 const generation=++previewGeneration;const saved=manualMarks[side].get(file);
 previewState={side,file,start:saved?.start??null,end:saved?.end??null,times:[],index:0,shown:null};
 $('preview-file').textContent=(side==='source'?'Source · ':'Target · ')+file.split(/[\\/]/).pop();$('preview-error').textContent='';$('preview-image').removeAttribute('src');$('preview-image').hidden=true;$('preview-loading').textContent='Reading video timestamps…';$('preview-loading').hidden=false;
 $('preview-position').textContent='00:00:00.000';$('preview-frame-label').textContent='';$('preview-length').textContent='';$('preview-jump').value='';$('preview-seek').value=0;showPreviewMarks();previewControls(false);previewDialog.showModal();
 try{const info=await window.autosync.previewOpen(file);if(generation!==previewGeneration)return;Object.assign(previewState,info);$('preview-seek').max=info.times.length-1;$('preview-frame-jump').max=info.times.length;$('preview-length').textContent='Duration '+previewTime(info.duration);previewControls(true);showPreviewMarks();await seekPreview(saved?nearestPreviewFrame(saved.start):0);}catch(e){if(generation===previewGeneration){$('preview-loading').textContent='Preview unavailable';$('preview-error').textContent=e.message;}}
}
function nearestPreviewFrame(t){const a=previewState.times;let lo=0,hi=a.length-1;while(lo<hi){const m=Math.floor((lo+hi)/2);if(a[m]<t)lo=m+1;else hi=m;}return lo>0&&Math.abs(a[lo-1]-t)<Math.abs(a[lo]-t)?lo-1:lo;}
async function seekPreview(index){
 if(!previewState?.times.length)return;clearTimeout(previewTimer);const s=previewState;index=Math.max(0,Math.min(s.times.length-1,Number(index)));s.index=index;s.shown=null;const generation=++previewGeneration;
 $('preview-frame-jump').value=index+1;$('preview-seek').value=index;$('preview-position').textContent=previewTime(s.times[index]);$('preview-frame-label').textContent=`Frame ${index+1} / ${s.times.length}`;$('preview-mark-start').disabled=true;$('preview-mark-end').disabled=true;$('preview-loading').hidden=false;$('preview-loading').textContent='Loading frame…';$('preview-error').textContent='';
 try{const frame=await window.autosync.previewFrame(index);if(generation!==previewGeneration)return;$('preview-image').src=frame.image;$('preview-image').hidden=false;$('preview-loading').hidden=true;s.shown=frame.time;$('preview-mark-start').disabled=false;$('preview-mark-end').disabled=false;}catch(e){if(generation===previewGeneration){$('preview-loading').textContent='Frame unavailable';$('preview-error').textContent=e.message;}}
}
function closePreview(){++previewGeneration;clearTimeout(previewTimer);previewState=null;window.autosync.previewClose().catch(()=>{});if(previewDialog.open)previewDialog.close();}
for(const id of ['preview-x','preview-cancel'])$(id).onclick=closePreview;
previewDialog.addEventListener('cancel',e=>{e.preventDefault();closePreview();});
$('preview-seek').oninput=()=>{++previewGeneration;clearTimeout(previewTimer);previewState.shown=null;$('preview-mark-start').disabled=true;$('preview-mark-end').disabled=true;const index=Number($('preview-seek').value);$('preview-position').textContent=previewTime(previewState.times[index]);previewTimer=setTimeout(()=>seekPreview(index),100);};
$('preview-seek').onchange=()=>seekPreview($('preview-seek').value);
$('preview-prev').onclick=()=>seekPreview(previewState.index-1);$('preview-next').onclick=()=>seekPreview(previewState.index+1);$('preview-first').onclick=()=>seekPreview(0);$('preview-last').onclick=()=>seekPreview(previewState.times.length-1);
$('preview-go').onclick=()=>{const parts=$('preview-jump').value.trim().split(':');const valid=parts.length<=3&&parts.every(x=>/^\d+(\.\d+)?$/.test(x));const t=parts.reduce((a,x)=>a*60+Number(x),0);if(!valid||!Number.isFinite(t)||t<0||t>previewState.duration){$('preview-error').textContent='Enter seconds or HH:MM:SS.mmm within this video.';return;}seekPreview(nearestPreviewFrame(t));};
$('preview-jump').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();$('preview-go').click();}};
for(const side of ['start','end']){$('preview-mark-'+side).onclick=()=>{if(previewState.shown!=null){previewState[side]=previewState.shown;showPreviewMarks();}};$('preview-goto-'+side).onclick=()=>seekPreview(nearestPreviewFrame(previewState[side]));}
$('preview-end-video').onclick=()=>{previewState.end=previewState.duration;showPreviewMarks();};
$('preview-clear').onclick=()=>{previewState.start=null;previewState.end=null;showPreviewMarks();$('preview-error').textContent='Press Save trim to remove these marks.';};
$('preview-save').onclick=()=>{const s=previewState;if(s.start==null&&s.end==null)manualMarks[s.side].delete(s.file);else{if(s.start==null||s.end==null||s.end<=s.start){$('preview-error').textContent='Mark both points, with the end after the start.';return;}manualMarks[s.side].set(s.file,{start:s.start,end:s.end});}closePreview();renderBatch();};
previewDialog.addEventListener('keydown',e=>{if(e.target.matches('input')||!previewState?.times.length)return;if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();seekPreview(previewState.index+(e.key==='ArrowRight'?1:-1));}});

$('preview-frame-go').onclick=()=>{
 const value=$('preview-frame-jump').value.trim(),n=Number(value),count=previewState?.times.length||0;
 if(!/^\d+$/.test(value)||!Number.isSafeInteger(n)||n<1||n>count){$('preview-error').textContent='Enter a whole frame number from 1 to '+count+'.';return;}
 seekPreview(n-1);
};
$('preview-frame-jump').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();$('preview-frame-go').click();}};
