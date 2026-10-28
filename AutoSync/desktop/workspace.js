let workspace='Sync jobs';
let activeTab='audio';
const audioSection=document.createElement('section');audioSection.id='audio-section';
const audioHeader=document.createElement('div');audioHeader.className='section-heading';audioHeader.innerHTML='<h2><label><input id="enable-audio" type="checkbox" checked> Audio</label></h2>';
audioSection.append(audioHeader);$('mode-section').before(audioSection);for(const id of ['mode-section','single','batch-panel','audio-tracks','audio-advanced'])audioSection.append($(id));
const subSection=document.createElement('section');subSection.id='subtitle-section';const subHeader=document.createElement('div');subHeader.className='section-heading';subHeader.innerHTML='<h2><label><input id="enable-subtitles" type="checkbox"> Subtitles</label></h2>';
audioSection.after(subSection);subSection.append(subHeader,$('subtitles-panel'));
function subtitlesEnabled(){return workspace==='Sync jobs'&&$('enable-subtitles').checked;}
function subtitleBatchActive(){return subtitlesEnabled();}
function subtitleValues(){const values={};document.querySelectorAll('[id^="sub_"]').forEach(i=>{if(i.tagName==='INPUT'||i.tagName==='SELECT')values[i.id.slice(4)]=i.type==='checkbox'?i.checked:i.value.trim();});subtitleDefaultsWhenDisabled(values);return values;}
function applyWorkspace(){
 const settings=workspace==='Settings',saved=workspace==='Saved plan',audio=!saved&&!settings&&$('enable-audio').checked,sub=subtitlesEnabled();task=saved?'Saved plan':'Batch CSV';
 $('heading').textContent=settings?'Settings':saved?'Render a saved plan':'Sync jobs';audioSection.classList.toggle('hidden',saved||settings);subSection.classList.toggle('hidden',saved||settings);$('saved').classList.toggle('hidden',!saved);
 for(const id of ['mode-section','audio-advanced'])$(id).classList.toggle('hidden',!audio);$('single').classList.toggle('hidden',!audio||task!=='Single episode');$('batch-panel').classList.toggle('hidden',!audio||task!=='Batch CSV');$('analyze-label').classList.toggle('hidden',!audio);$('subtitles-panel').classList.toggle('hidden',!sub);
 // Saved-plan export overrides remain available in their own panel.
 if(saved){$('saved').append($('audio-advanced'));$('audio-advanced').classList.remove('hidden');}else audioSection.append($('audio-advanced'));
 subtitleMode();subtitleBatchLayout();refreshTracks();$('audio-tracks').classList.toggle('hidden',!audio||(task==='Batch CSV'&&$('use_csv').checked));if(typeof applyPreferences==='function')applyPreferences();if(typeof refreshReadiness==='function')refreshReadiness();if(typeof applyRemodel==='function')applyRemodel();
}
for(const id of ['enable-audio','enable-subtitles'])$(id).onchange=()=>{applyWorkspace();};
document.querySelector('nav').addEventListener('click',e=>{const button=e.target.closest('.nav');if(!button||running)return;workspace=button.dataset.task;document.querySelectorAll('.nav').forEach(b=>b.classList.toggle('active',b===button));applyWorkspace();});
$('start').onclick=async()=>{
 if(running)return;try{
  if(importing||subtitleImporting||trackLoading)throw Error('Wait for file and track detection to finish.');
  destinationRequest([]);const jobs=[];if(workspace==='Saved plan')jobs.push(audioJob());else{if($('enable-audio').checked)jobs.push(audioJob());if(subtitlesEnabled())jobs.push(subtitleBatchJob(subtitleValues()));}if(!jobs.length)throw Error('Enable Audio, Subtitles, or both.');const job=destinationRequest(jobs);
  busy(true);$('status').textContent='Starting…';log('\n──── New run ────\n');await window.autosync.start(job);
 }catch(e){busy(false);error(e);}
};
applyWorkspace();
