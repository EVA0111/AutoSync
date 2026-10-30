const $=id=>document.getElementById(id);let task='Single episode',running=false;const batchFiles={source:[],target:[]};let importing=0;let selectedSide=null,selectedIndex=-1;
const paths=[['source','Source video','media','Original edition'],['target','Target video','media','Video to match'],['audio','Source audio','media','Optional · use source video audio'],['reference','Reference audio','media','Optional · use target video audio'],['out','New output folder','output','Choose a parent folder for a new run']];
function fileField(parent,[id,label,kind,placeholder]){const row=document.createElement('div');row.className='field';const l=document.createElement('label');l.htmlFor=id;l.textContent=label;const i=document.createElement('input');i.id=id;i.placeholder=placeholder;const b=document.createElement('button');b.textContent='Browse';b.addEventListener('click',async()=>{try{const p=await window.autosync.browse(kind);if(p){i.value=p;i.dispatchEvent(new Event('change'));}}catch(e){error(e);}});row.addEventListener('dragover',e=>{e.preventDefault();if(!running)row.classList.add('drag-over');});row.addEventListener('dragleave',()=>row.classList.remove('drag-over'));row.append(l,i,b);$(parent).append(row);}
paths.forEach(p=>fileField('file-fields',p));const externalAudio=document.createElement('details');const externalSummary=document.createElement('summary');externalSummary.textContent='Use separate audio files (optional)';externalAudio.append(externalSummary,$('audio').closest('.field'),$('reference').closest('.field'));$('file-fields').append(externalAudio);fileField('batch-field',['batch','Batch CSV','csv','Select jobs.csv']);fileField('plan-field',['plan','Saved plan','plan','Select plan.json']);
fileField('batch-output-field',['batch_out','Batch output folder','output','Choose a parent folder for this batch']);
const advanced=[['audio_delay','Source audio delay (s)','0'],['reference_delay','Reference delay (s)','0'],['cut_times','Manual cut times (comma-separated)',''],['source_crop','Source matching crop (w:h:x:y)',''],['target_crop','Target matching crop (w:h:x:y)',''],['scene_threshold','Scene threshold','0.15'],['video_codec','Trimmed video codec',['h264','ffv1']],['video_preset','H.264 preset',['veryfast','ultrafast','medium']]];
for(const [id,label,value] of advanced){const box=document.createElement('div');box.className='option';const l=document.createElement('label');l.htmlFor=id;l.textContent=label;const i=document.createElement(Array.isArray(value)?'select':'input');i.id=id;if(Array.isArray(value))value.forEach(x=>{const o=document.createElement('option');o.value=x;o.textContent=x;i.append(o);});else i.value=value;box.append(l,i);$('advanced').append(box);}
function log(text){const el=$('log');el.textContent=(el.textContent+text).slice(-180000);el.scrollTop=el.scrollHeight;}
function error(e){$('status').textContent=e.message||String(e);log('\n'+(e.message||String(e))+'\n');}
function busy(value){if(value&&typeof resetProgress==='function')resetProgress();running=value;document.querySelectorAll('input,select,.nav,.field button,#example,#setup-engine,#setup-ai,.drop-zone button,.batch-actions button,.list-controls button').forEach(el=>el.disabled=value);$('start').disabled=value;$('stop').disabled=!value;$('pulse').classList.toggle('busy',value);updateSelection();if(typeof refreshReadiness==='function')refreshReadiness();if(typeof syncRemodelBusy==='function')syncRemodelBusy();}

document.querySelectorAll('[name=mode]').forEach(r=>r.addEventListener('change',()=>{document.querySelectorAll('.mode').forEach(l=>l.classList.toggle('selected',l.querySelector('input').checked));refreshTracks();}));
function audioJob(){const values={};for(const id of [...paths.map(x=>x[0]),...advanced.map(x=>x[0]),'batch','plan','audio_stream','reference_stream','outer_stream','audio_only','reference_fallback','remove_unmatched_video','allow_uncertain_cuts','analyze_only']){const i=$(id);values[id]=i.type==='checkbox'?i.checked:i.value.trim();}values.mode=document.querySelector('[name=mode]:checked').value;values.main_start='';values.main_end='';let job={task,values};if(task==='Batch CSV'&&!$('use_csv').checked){if(!batchFiles.source.length||batchFiles.source.length!==batchFiles.target.length)(()=>{throw Error('Both audio columns need the same number of videos.');})();if(!$('pairs_reviewed').checked)(()=>{throw Error('Check the audio episode pairs, then tick the confirmation box.');})();values.out=$('batch_out').value.trim();job={task:'Folder batch',values,reviewed:true,pairs:batchFiles.source.map((source,i)=>({source,target:batchFiles.target[i],...batchTrackValues(source,batchFiles.target[i]),...manualPairValues(source,batchFiles.target[i],values.mode)}))};}audioDefaultsWhenDisabled(job.values);return job;}
$('stop').onclick=()=>window.autosync.stop().catch(error);$('output').onclick=()=>window.autosync.openOutput(false).catch(error);$('report').onclick=()=>window.autosync.openOutput(true).catch(error);$('example').onclick=()=>window.autosync.example().catch(error);
window.autosync.onEvent(({type,data})=>{if(type==='log')log(data);else if(type==='output'){$('status').textContent='Processing…';log('Output: '+data+'\n');}else if(type==='status')$('status').textContent=data;else if(type==='done'){busy(false);if(setupRunning){setupRunning=false;$('status').textContent=data.cancelled?'Setup stopped':data.code===0?'Setup complete':'Setup failed · see activity';return;}$('status').textContent=data.cancelled?'Stopped · partial files may remain':data.code===0?'Finished':'Failed · see activity log';}});

// Prevent Electron from navigating to dropped files, including outside a drop zone.
document.addEventListener('dragover',e=>e.preventDefault());document.addEventListener('drop',e=>e.preventDefault());
function updateSelection(){
 const length=selectedSide?batchFiles[selectedSide].length:0;const valid=selectedIndex>=0&&selectedIndex<length;
 for(const side of ['source','target']){const list=$(side+'-list');$(side+'-drop').classList.toggle('active-list',side===selectedSide);Array.from(list.children).forEach((row,i)=>{const selected=valid&&side===selectedSide&&i===selectedIndex;row.setAttribute('aria-selected',String(selected));row.classList.toggle('selected-row',selected);row.classList.toggle('paired-row',valid&&side!==selectedSide&&i===selectedIndex);row.tabIndex=selected?0:-1;});}
 $('selection-label').textContent=valid?(selectedSide==='source'?'Source':'Target')+' · row '+(selectedIndex+1):'Select a file';
 for(const id of ['move-up','move-top'])$(id).disabled=running||!valid||selectedIndex===0;
 for(const id of ['move-down','move-bottom'])$(id).disabled=running||!valid||selectedIndex===length-1;
 $('remove-selected').disabled=running||!valid;$('move-to').disabled=running||!valid;$('move-position').disabled=running||!valid;$('move-position').max=String(length);
}
function selectRow(side,i,focus=false){if(running)return;selectedSide=side;selectedIndex=i;$('move-position').value=String(i+1);updateSelection();refreshTracks();if(focus)$(side+'-list').children[i]?.focus({preventScroll:true});}
function moveSelected(destination){if(running||!selectedSide||selectedIndex<0)return;const list=batchFiles[selectedSide];if(!Number.isInteger(destination)||destination<0||destination>=list.length)return error(Error('Enter a row between 1 and '+list.length+'.'));if(destination===selectedIndex)return;const [file]=list.splice(selectedIndex,1);list.splice(destination,0,file);selectedIndex=destination;renderBatch();$('move-position').value=String(destination+1);const row=$(selectedSide+'-list').children[destination];row?.focus({preventScroll:true});row?.scrollIntoView({block:'nearest'});}
function removeSelected(){if(running||!selectedSide||selectedIndex<0)return;manualMarks[selectedSide].delete(batchFiles[selectedSide][selectedIndex]);batchFiles[selectedSide].splice(selectedIndex,1);selectedIndex=Math.min(selectedIndex,batchFiles[selectedSide].length-1);renderBatch();if(selectedIndex>=0)selectRow(selectedSide,selectedIndex,true);}
function renderBatch(){
 $('pairs_reviewed').checked=false;
 for(const side of ['source','target']){const list=$(side+'-list');list.replaceChildren();list.style.minHeight='0px';$(side+'-count').textContent=batchFiles[side].length+' files';$(side+'-empty').classList.toggle('hidden',batchFiles[side].length>0);batchFiles[side].forEach((file,i)=>{const row=document.createElement('li');row.setAttribute('role','option');row.title=file;const number=document.createElement('span');number.className='row-number';number.textContent=String(i+1);const name=document.createElement('span');name.textContent=file.split(/[\\/]/).pop();row.append(number,name);if(typeof addPreviewButton==='function')addPreviewButton(row,name,side,file);row.onclick=()=>selectRow(side,i,true);row.onkeydown=e=>{if(running)return;if(e.key==='Delete'){e.preventDefault();selectRow(side,i);removeSelected();}else if(['ArrowUp','ArrowDown','Home','End'].includes(e.key)){e.preventDefault();selectRow(side,i);const last=batchFiles[side].length-1;const next=e.key==='Home'?0:e.key==='End'?last:Math.max(0,Math.min(last,i+(e.key==='ArrowUp'?-1:1)));if(e.altKey)moveSelected(next);else{selectRow(side,next,true);list.children[next]?.scrollIntoView({block:'nearest'});}}};list.append(row);if(typeof addInlineTrack==='function')addInlineTrack(row,side,file);});}
 updateSelection();refreshTracks();
 const a=batchFiles.source,b=batchFiles.target;const known=a.length===b.length&&a.length&&a.every((p,i)=>pairing.episode(p)&&pairing.episode(p)===pairing.episode(b[i]));
 $('pair-status').textContent=`${a.length} source · ${b.length} target — `+(a.length!==b.length?'Counts differ. Add or remove videos before starting.':!a.length?'Drop your folders to begin.':known?'Episode numbers match. Review the pairs below each heading.':'Pairing is based on row order. Check every pair before starting.');
}
async function addBatch(side,paths,alreadyCollected=false){if(running)return;importing++;$('pair-status').textContent='Reading videos from folders…';try{const files=alreadyCollected?paths:await window.autosync.collect(paths);batchFiles[side]=[...new Set([...batchFiles[side],...files])].sort((a,b)=>a.localeCompare(b,undefined,{numeric:true,sensitivity:'base'}));const matched=pairing.match(batchFiles.source,batchFiles.target);if(matched)batchFiles.target=matched;selectedSide=null;selectedIndex=-1;renderBatch();if(!files.length)$('pair-status').textContent='No supported video files found in that selection.';}catch(e){error(e);}finally{importing--;if(typeof refreshReadiness==='function')refreshReadiness();}}
for(const side of ['source','target']){const zone=$(side+'-drop');zone.addEventListener('dragover',e=>{e.preventDefault();if(!running)zone.classList.add('drag-over');});zone.addEventListener('dragleave',()=>zone.classList.remove('drag-over'));}
document.querySelectorAll('[data-pick]').forEach(b=>b.onclick=async()=>{try{await addBatch(b.dataset.pick,await window.autosync.pickBatch(b.dataset.folder==='1'),true);}catch(e){error(e);}});
$('pair-episodes').onclick=()=>{const matched=pairing.match(batchFiles.source,batchFiles.target);if(matched){batchFiles.target=matched;selectedSide=null;selectedIndex=-1;renderBatch();}else error(Error('Episode numbers are missing, duplicated, or different. Pair the files manually using the arrows.'));};
$('clear-batch').onclick=()=>{manualMarks.source.clear();manualMarks.target.clear();batchFiles.source=[];batchFiles.target=[];selectedSide=null;selectedIndex=-1;renderBatch();};

$('move-up').onclick=()=>moveSelected(selectedIndex-1);$('move-down').onclick=()=>moveSelected(selectedIndex+1);
$('move-top').onclick=()=>moveSelected(0);$('move-bottom').onclick=()=>moveSelected(batchFiles[selectedSide].length-1);
$('move-to').onclick=()=>moveSelected(Number($('move-position').value)-1);$('remove-selected').onclick=removeSelected;
$('move-position').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();$('move-to').click();}};
for(const side of ['source','target']){$(side+'-scroll').addEventListener('scroll',()=>{const other=side==='source'?'target':'source';if($(other+'-scroll').scrollTop!==$(side+'-scroll').scrollTop)$(other+'-scroll').scrollTop=$(side+'-scroll').scrollTop;});$(side+'-drop').addEventListener('keydown',e=>{if(e.target===$(side+'-drop')&&e.key==='Enter'&&batchFiles[side].length){e.preventDefault();selectRow(side,0,true);}});}
updateSelection();

window.autosync.onDrop(({target,paths,error:dropError})=>{
 document.querySelectorAll('.drag-over').forEach(el=>el.classList.remove('drag-over'));
 if(running)return;
 if(dropError||!paths.length)return error(Error(dropError||'Could not read the dropped file paths. Try Add files or Choose folder.'));
 if(target.startsWith('sb-drop-'))return;
 if(target==='source-drop'||target==='target-drop'){addBatch(target.split('-')[0],paths);return;}
 if(paths.length!==1)return error(Error('Drop one file here, or use Batch jobs for multiple files.'));
 const field=$(target);if(!field)return;
 field.value=['out','batch_out','sub_out'].includes(target)?paths[0]+'/AutoSync_'+Date.now():paths[0];field.dispatchEvent(new Event('change'));
});

const subFiles=[['sub_subtitle','Subtitle to sync','subtitle','Subtitle file or MKV containing the track'],['sub_reference_subtitle','Synced reference subtitle','subtitle','Subtitle already matching the target'],['sub_source_video','Source encode','media','Video matching the original subtitle timing'],['sub_target_media','Target video / audio','media','Video or audio to match'],['sub_timing_map','Saved timing map','plan','subtitle_map.json or an AutoSync plan'],['sub_out','New output folder','output','Choose a parent folder']];
subFiles.forEach(field=>fileField('sub-files',field));
for(const [id,label,value] of [['encoding','Text encoding','utf-8-sig'],['source_fps','Source FPS (MicroDVD)',''],['target_fps','Target FPS (MicroDVD)',''],['source_crop','Source crop (optional w:h:x:y)',''],['target_crop','Target crop (optional w:h:x:y)',''],['sushi_window','Sushi search window (seconds)','10'],['sushi_max_window','Sushi maximum window (seconds)','30'],['whisper_model','Whisper model','small'],['language','Target speech language (optional, e.g. en)','']]){const box=document.createElement('div');box.className='option';const l=document.createElement('label');l.htmlFor='sub_'+id;l.textContent=label;const i=document.createElement('input');i.id='sub_'+id;i.value=value;box.append(l,i);$('sub-options').append(box);}
function subtitleMode(){const mode=$('sub_mode').value;$('sushi-hint').classList.toggle('hidden',mode!=='sushi');for(const id of ['reference_subtitle','source_video','target_media','timing_map']){$('sub_'+id).closest('.field').classList.toggle('hidden',!({reference_subtitle:['reference'],source_video:['encodes','sushi'],target_media:['encodes','audio','sushi'],timing_map:['map']}[id].includes(mode)));}for(const id of ['source_crop','target_crop'])$('sub_'+id).closest('.option').classList.toggle('hidden',mode!=='encodes');for(const id of ['whisper_model','language'])$('sub_'+id).closest('.option').classList.toggle('hidden',mode!=='audio');for(const id of ['sushi_window','sushi_max_window'])$('sub_'+id).closest('.option').classList.toggle('hidden',mode!=='sushi');$('sub_semantic').parentElement.classList.toggle('hidden',!['reference','audio'].includes(mode));}
$('sub_mode').onchange=()=>{if($('subtitle-reviewed'))$('subtitle-reviewed').checked=false;subtitleMode();if(typeof applyWorkspace==='function')applyWorkspace();else refreshTracks();};subtitleMode();


// One selector per track role; numbers remain type-relative for FFmpeg -map 0:a:N / 0:s:N.
let setupRunning=false;let trackLoading=0;const trackGeneration={};const trackChoices=new Map();
const trackSpecs=[['audio_stream','Source audio','audio-track-options'],['reference_stream','Target reference audio','audio-track-options'],['outer_stream','Target opening / ending','audio-track-options'],['sub_subtitle_track','Subtitle track','sub_subtitle'],['sub_reference_track','Reference subtitle track','sub_reference_subtitle'],['sub_audio_track','Target audio track','sub_target_media'],['sub_source_audio_track','Source audio track','sub_source_video']];
for(const [id,label,parent] of trackSpecs){const box=document.createElement('div');box.className='option track-option';box.dataset.track=id;const l=document.createElement('label');l.htmlFor=id;l.textContent=label;const select=document.createElement('select');select.id=id;select.add(new Option('Choose a file first','0'));box.append(l,select);if(parent.endsWith('options'))$(parent).append(box);else $(parent).closest('.field').after(box);select.onchange=()=>{trackChoices.set(select.dataset.key,select.value);if(task==='Batch CSV')$('pairs_reviewed').checked=false;};}
function batchTrackValues(source,target){return {audio_stream:trackChoices.get('audio_stream|'+source)||'0',reference_stream:trackChoices.get('reference_stream|'+target)||'0',outer_stream:trackChoices.get('outer_stream|'+target)||'0'};}
const mediaCache=new Map();
function mediaTracks(file){if(!mediaCache.has(file)){const pending=window.autosync.probe(file).catch(e=>{mediaCache.delete(file);throw e;});mediaCache.set(file,pending);}return mediaCache.get(file);}
async function loadTrack(id,file,type,visible=true){const el=$(id),box=el.closest('.track-option');box.classList.toggle('hidden',!visible);const generation=(trackGeneration[id]||0)+1;trackGeneration[id]=generation;if(!visible)return;const key=id+'|'+file;el.dataset.key=key;el.replaceChildren(new Option(file?'Detecting tracks…':'Choose a file first','0'));el.disabled=true;if(!file)return;trackLoading++;
 try{const tracks=(await mediaTracks(file)).filter(t=>t.type===type);if(trackGeneration[id]!==generation)return;if(!tracks.length){el.replaceChildren(new Option('No '+type+' tracks found','0'));return;}el.replaceChildren();for(const t of tracks){const parts=[`Track ${t.index+1}`,t.language,t.title,t.codec.toUpperCase(),t.layout||(t.channels?t.channels+' channels':''),t.default?'default':'',t.forced?'forced':''].filter(Boolean);el.add(new Option(parts.join(' · '),String(t.index)));}const saved=trackChoices.get(key);el.value=tracks.some(t=>String(t.index)===saved)?saved:'0';trackChoices.set(key,el.value);el.disabled=running;
 }catch(e){if(trackGeneration[id]===generation){el.replaceChildren(new Option('Cannot detect tracks — see activity','0'));error(e);}}finally{trackLoading--;if(typeof refreshReadiness==='function')refreshReadiness();}}
function subtitlePath(key){return typeof subtitleBatchActive==='function'&&subtitleBatchActive()?subtitleBatchPath(key):$('sub_'+key).value.trim();}
function refreshTracks(){
 for(const id of ['audio_delay','reference_delay','cut_times','source_crop','target_crop','scene_threshold'])$(id).closest('.option').classList.toggle('hidden',task==='Saved plan'||(['main_start','main_end'].includes(id)&&document.querySelector('[name=mode]:checked').value==='Sync full target audio'));
 const sub=typeof subtitlesEnabled==='function'?subtitlesEnabled():task==='Subtitles',mode=$('sub_mode').value,batch=task==='Batch CSV',index=selectedIndex>=0?selectedIndex:0;const source=batch?batchFiles.source[index]||'':$('audio').value.trim()||$('source').value.trim();const target=batch?batchFiles.target[index]||'':$('reference').value.trim()||$('target').value.trim();const outer=batch?batchFiles.target[index]||'':$('target').value.trim();const audioVisible=(!$('enable-audio')||$('enable-audio').checked)&&['Single episode','Batch CSV'].includes(task)&&!(batch&&$('use_csv').checked);
 $('audio-tracks').classList.toggle('hidden',!audioVisible);$('track-context').textContent=batch?'Tracks for pair '+(index+1)+'. Select a row to edit another pair. Unchanged pairs use their first audio track.':'';
 loadTrack('audio_stream',source,'audio',audioVisible);loadTrack('reference_stream',target,'audio',audioVisible);loadTrack('outer_stream',outer,'audio',audioVisible&&document.querySelector('[name=mode]:checked').value==='Keep target opening / ending');
 const container=p=>/\.(mkv|mp4|m4v|mov|avi|wmv|m2ts|ts|webm)$/i.test(p);
 loadTrack('sub_subtitle_track',subtitlePath('subtitle'),'subtitle',sub&&container(subtitlePath('subtitle')));loadTrack('sub_reference_track',subtitlePath('reference_subtitle'),'subtitle',sub&&mode==='reference'&&container(subtitlePath('reference_subtitle')));loadTrack('sub_audio_track',subtitlePath('target_media'),'audio',sub&&['audio','sushi'].includes(mode));loadTrack('sub_source_audio_track',subtitlePath('source_video'),'audio',sub&&mode==='sushi');
}
for(const id of ['source','target','audio','reference','sub_subtitle','sub_reference_subtitle','sub_target_media','use_csv'])$(id).addEventListener('change',refreshTracks);
for(const kind of ['engine','ai'])$('setup-'+kind).onclick=async()=>{setupRunning=true;busy(true);$('status').textContent='Installing dependencies…';try{await window.autosync.start({task:'Setup',kind});}catch(e){setupRunning=false;busy(false);error(e);}};
refreshTracks();

// Preview & Edit works with the currently selected source and target, too.
// When no plan is supplied, the engine creates one (analyze-only) on the chosen drive.
let editorOpening=false;
$('alignment-editor-open').onclick=async()=>{
 if(editorOpening||running)return;
 const button=$('alignment-editor-open'),caption=button.textContent;
 editorOpening=true;button.disabled=true;button.textContent='Preparing Preview…';
 try{
  let request={};
  if(workspace==='Saved plan'&&$('plan').value.trim()){
   request={plan:$('plan').value.trim()};
  }else{
   const index=selectedIndex>=0?selectedIndex:0;
   const source=batchFiles.source[index]||$('source').value.trim();
   const target=batchFiles.target[index]||$('target').value.trim();
   if(source&&target){
    const values={};
    for(const id of [...paths.map(x=>x[0]),...advanced.map(x=>x[0]),
      'audio_stream','reference_stream','outer_stream','audio_only',
      'reference_fallback','remove_unmatched_video','allow_uncertain_cuts','analyze_only']){
     const element=$(id);
     values[id]=element?.type==='checkbox'?element.checked:element?.value?.trim()||'';
    }
    values.mode=document.querySelector('[name=mode]:checked').value;
    values.main_start='';values.main_end='';
    values.source=source;values.target=target;
    const selectedPair=batchTrackValues(source,target);
    values.audio_stream=selectedPair.audio_stream;
    values.reference_stream=selectedPair.reference_stream;
    values.outer_stream=selectedPair.outer_stream;
    values.audio=$('audio').value.trim()||source;
    values.reference=$('reference').value.trim()||target;
    audioDefaultsWhenDisabled(values);
    values.analyze_only=true;
    request={job:{task:'Single episode',values},
      outputDirectory:$('output-destination').value.trim()};
   }
   // When nothing is selected, show the standard existing-plan picker.
  }
  $('status').textContent=request.job?'Analyzing the selected pair for Preview & Edit…':'Opening Preview & Edit…';
  await window.autosync.openAlignmentEditor(request);
 }catch(e){error(e);}
 finally{editorOpening=false;button.textContent=caption;button.disabled=false;}
};
window.autosync.onEvent(({type,data})=>{
 if(type==='alignment-log')log(data);
});
