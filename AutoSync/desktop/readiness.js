// Explain the next required step before a run can start.
const setupCheck=document.createElement('div');setupCheck.className='panel setup-check';setupCheck.id='setup-check';
setupCheck.innerHTML='<span id="setup-message" role="status"></span><button id="setup-focus">Show me</button>';
$('destination-panel').after(setupCheck);
const rangeNote=document.createElement('p');rangeNote.id='range-status';rangeNote.className='hint';$('pair-status').after(rangeNote);
let setupFocus=null;
function readinessIssue(){
 if(importing||subtitleImporting||trackLoading)return ['Reading files and tracks…',null];
 if(!$('output-destination').value.trim())return ['Choose an output folder before starting.','output-destination'];
 if(prefs.reports&&!$('reports-destination').value.trim())return ['Choose a reports folder in Settings, or disable reports.','reports-destination'];
 if(prefs.reports){
  const clean=s=>s.trim().replace(/\\/g,'/').replace(/\/+$/,'').toLowerCase();
  const a=clean($('output-destination').value),b=clean($('reports-destination').value);
  if(a===b||a.startsWith(b+'/')||b.startsWith(a+'/'))return ['Choose separate, non-nested output and report folders.','reports-destination'];
 }
 if(workspace==='Saved plan')return $('plan').value.trim()?null:['Choose a saved timing plan.','plan'];
 if(!$('enable-audio').checked&&!subtitlesEnabled())return ['Enable Audio, Subtitles, or both.','enable-audio'];
 if($('enable-audio').checked){
  const mode=document.querySelector('[name=mode]:checked').value;
  if(prefs.audioAdvanced&&$('audio_only').checked&&mode!=='Sync full target audio')return ['Audio-only matching requires full-target mode.','audio_only'];
  if(prefs.audioAdvanced&&$('analyze_only').checked&&!prefs.reports)return ['Enable Save reports in Settings for Analyze only.','pref-reports'];
  if(prefs.csv&&$('use_csv').checked){if(!$('batch').value.trim())return ['Choose the job CSV.','batch'];}
  else{
   if(!batchFiles.source.length)return ['Add source videos to the left column.','source-drop'];
   if(batchFiles.source.length!==batchFiles.target.length)return ['Both audio columns need the same number of videos.','target-drop'];
   try{batchFiles.source.forEach((s,i)=>manualPairValues(s,batchFiles.target[i],mode));}catch(e){return [e.message,'source-drop'];}
   if(!$('pairs_reviewed').checked)return ['Check the audio pairs, then tick the confirmation box.','pairs_reviewed'];
  }
 }
 if(subtitlesEnabled()){
  const keys=activeSubtitleColumns(),count=subtitleLists.subtitle.length;
  if(!count||keys.some(k=>subtitleLists[k].length!==count))return ['Add matching files to every subtitle column.','sb-drop-subtitle'];
  if($('sub_mode').value==='map'&&count!==1)return ['Use one subtitle file with a saved timing map.','sb-drop-subtitle'];
  if($('sub_mode').value==='map'&&!$('sub_timing_map').value.trim())return ['Choose the saved timing map.','sub_timing_map'];
  if(!$('subtitle-reviewed').checked)return ['Check the subtitle pairs and track choices.','subtitle-reviewed'];
 }
 return null;
}
function refreshReadiness(){
 if(!document.getElementById('setup-check'))return;
 setupCheck.classList.toggle('hidden',workspace==='Settings');
 const issue=readinessIssue();setupFocus=issue?.[1]||null;
 $('setup-message').textContent=running?'Processing the selected jobs…':issue?.[0]||'Ready to sync the selected jobs.';
 setupCheck.classList.toggle('ready',!issue&&!running);$('setup-focus').hidden=!setupFocus||running;
 $('start').disabled=running||!!issue;
 const count=manualMarks.source.size+manualMarks.target.size;
 rangeNote.textContent=count?`${count} video(s) will be trimmed before syncing. Video and audio use the same exact range. Sync modes apply within that range.`:'';
 const mode=document.querySelector('[name=mode][value="Sync full target audio"]').closest('.mode');
 const hint=mode.querySelector('span');if(hint){if(!hint.dataset.original)hint.dataset.original=hint.textContent;hint.textContent=prefs.audioAdvanced&&$('remove_unmatched_video').checked?'Export edited video + matching FLAC. Target-only sections are removed.':hint.dataset.original;}
}
$('setup-focus').onclick=()=>{if(!setupFocus)return;if(['reports-destination','pref-reports'].includes(setupFocus)){workspace='Settings';applyWorkspace();}const el=$(setupFocus);el?.scrollIntoView({block:'center',behavior:'smooth'});el?.focus();};
for(const [a,b] of [['remove_unmatched_video','reference_fallback'],['reference_fallback','remove_unmatched_video']])$(a).addEventListener('change',()=>{if($(a).checked)$(b).checked=false;});
for(const event of ['input','change','click'])document.addEventListener(event,()=>queueMicrotask(refreshReadiness));
window.autosync.onDrop(()=>setTimeout(refreshReadiness,0));
