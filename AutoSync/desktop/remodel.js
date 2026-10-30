localStorage.removeItem('autosync-language');
document.documentElement.lang='en';document.documentElement.dir='ltr';
// Presentation only: existing engine payloads and file identities stay unchanged.
const topbar=document.createElement('div');topbar.className='topbar';
const brand=document.querySelector('.brand');const github=$('github-profile');
const settingsButton=document.createElement('button');settingsButton.id='open-settings';settingsButton.textContent='⚙ Settings';settingsButton.onclick=()=>{workspace=workspace==='Settings'?'Sync jobs':'Settings';applyWorkspace();};
topbar.append(brand,settingsButton,github);document.body.prepend(topbar);
const nav=document.querySelector('nav');nav.className='workspace-tabs';topbar.after(nav);
const syncNav=nav.querySelector('[data-task="Sync jobs"]');syncNav.classList.add('hidden');settingsNav.classList.add('hidden');
for(const [key,label] of [['audio','Audio'],['subtitles','Subtitles'],['jobs','Jobs']]){const b=document.createElement('button');b.className='tab';b.dataset.tab=key;b.textContent=label;b.onclick=()=>{activeTab=key;workspace='Sync jobs';applyWorkspace();};nav.append(b);}
document.querySelector('aside').remove();document.querySelector('main>header').classList.add('hidden');
// Keep explicit inclusion so audio + subtitle batches can still run together.
audioHeader.querySelector('label').lastChild.textContent=' Include audio jobs';
subHeader.querySelector('label').lastChild.textContent=' Include subtitle jobs';
const audioHint=document.createElement('span');audioHint.textContent='Drop one episode or a whole folder';audioHeader.append(audioHint);
const subHint=document.createElement('span');subHint.textContent='Choose a timing reference, then add your files';subHeader.append(subHint);
$('batch-panel').querySelector('h2').remove();$('batch-panel').querySelector('p').remove();
for(const [side,title,help] of [['source','Source','Audio to transfer'],['target','Target','Video to match']]){const zone=$(side+'-drop');zone.querySelector('strong').textContent=title;const hint=document.createElement('p');hint.className='column-help';hint.textContent=help;zone.querySelector('.list-title').after(hint);}
// Pair editing sits below the two equal columns, rather than splitting them.
const pairDetails=document.createElement('details');pairDetails.id='pair-editor';pairDetails.innerHTML='<summary>Review pairing & reorder</summary>';
const reorder=document.querySelector('.list-controls');pairDetails.append(reorder,$('pair-episodes').parentElement);$('batch-panel').querySelector('.batch-columns').after(pairDetails);
const help=Array.from($('batch-panel').querySelectorAll('.hint')).find(el=>el.textContent.startsWith('Source row 1')); help.textContent='Rows pair in order. Select a file to reorder it. Alt + ↑ / ↓ moves a row; Delete removes it.';pairDetails.append(help);
// Compact mode selector; retain original radio values for the engine.
const modeBar=document.createElement('div');modeBar.className='mode-bar';modeBar.innerHTML='<label for="mode-select">Sync mode</label><select id="mode-select"></select><button id="mode-details" class="secondary">Mode details</button>';
const modeSelect=modeBar.querySelector('select');for(const radio of document.querySelectorAll('[name=mode]'))modeSelect.add(new Option(radio.closest('.mode').querySelector('strong').textContent,radio.value));modeSelect.value=document.querySelector('[name=mode]:checked').value;
$('mode-section').querySelector('h2').remove();$('mode-section').prepend(modeBar);$('mode-section').querySelector('.modes').classList.add('hidden');
// The matching algorithm is independent of output choice. Standard stays the
// default; selecting AI does not change full/main/OP-ED export behavior.
const methodBox=document.createElement('div');methodBox.className='sync-method-selector';
methodBox.innerHTML='<label for="sync_method">Matching method</label><select id="sync_method"><option value="standard">Standard (default)</option><option value="ai_assisted">AI-assisted (experimental)</option></select><small id="sync-method-help">Standard matching uses audio fingerprints and video scenes.</small>';
modeBar.after(methodBox);
$('sync_method').onchange=()=>{
 $('sync-method-help').textContent=$('sync_method').value==='ai_assisted'
 ?'Uses pretrained AST sound embeddings, plus DINOv2 for weak scene matching. Install AI Sync in Setup first; downloads are optional and the first analysis is slower.'
 :'Standard matching uses audio fingerprints and video scenes.';
 refreshReadiness();
};
modeSelect.onchange=()=>{const radio=Array.from(document.querySelectorAll('[name=mode]')).find(r=>r.value===modeSelect.value);radio.checked=true;radio.dispatchEvent(new Event('change'));refreshReadiness();};
$('mode-details').onclick=()=>$('mode-section').querySelector('.modes').classList.toggle('hidden');
document.querySelectorAll('[name=mode]').forEach(r=>r.addEventListener('change',()=>modeSelect.value=r.value));
$('batch-panel').after($('mode-section'));$('audio-tracks').querySelector('h2').remove();
const trackDetails=document.createElement('details');trackDetails.innerHTML='<summary>Track settings for selected pair</summary>';
trackDetails.append($('track-context'),$('audio-track-options'));$('audio-tracks').append(trackDetails);
// Output appears once, after the active input section.
$('subtitle-section').after($('destination-panel'));$('destination-panel').after(setupCheck);
$('destination-panel').querySelector('p').textContent='Reports and advanced options are available in Settings.';
$('start').textContent='Start selected jobs';
const jobsPanel=document.createElement('section');jobsPanel.id='jobs-panel';jobsPanel.className='panel hidden';jobsPanel.innerHTML='<div class="section-heading"><h2>Jobs</h2><span>Results from the current run</span></div><p id="jobs-empty" class="hint">Completed jobs and review warnings will appear here.</p><div class="jobs-scroll"><table><thead><tr><th>Job</th><th>Status</th><th>Output</th><th>Reports</th></tr></thead><tbody id="job-rows"></tbody></table></div>';
$('destination-panel').before(jobsPanel);const activity=document.querySelector('.log-panel');jobsPanel.append(activity);
function applyRemodel(){
 const sync=workspace==='Sync jobs';audioSection.classList.toggle('hidden',!sync||activeTab!=='audio');subSection.classList.toggle('hidden',!sync||activeTab!=='subtitles');jobsPanel.classList.toggle('hidden',!sync||activeTab!=='jobs');
 document.querySelectorAll('[data-tab]').forEach(b=>{b.classList.toggle('active',sync&&b.dataset.tab===activeTab);b.setAttribute('aria-current',sync&&b.dataset.tab===activeTab?'page':'false');});
 settingsButton.classList.toggle('active',workspace==='Settings');document.querySelector('[data-task="Saved plan"]').classList.toggle('active',workspace==='Saved plan');
 // Settings and job results remain navigable while a run is active; mutations do not.
 if(running)syncRemodelBusy();
}
function syncRemodelBusy(){
 for(const el of document.querySelectorAll('#settings-panel input,#settings-panel select,#settings-panel button,#mode-select,#mode-details,#pair-editor button,.inline-track'))el.disabled=running;
}
async function addInlineTrack(row,side,file){
 const select=document.createElement('select');select.className='inline-track';select.setAttribute('aria-label',side==='source'?'Source audio track':'Target reference audio');select.add(new Option('Detecting tracks…','0'));select.disabled=true;row.append(select);select.onclick=e=>e.stopPropagation();select.onkeydown=e=>e.stopPropagation();
 const role=side==='source'?'audio_stream':'reference_stream',key=role+'|'+file;
 try{const tracks=(await mediaTracks(file)).filter(t=>t.type==='audio');if(!row.isConnected)return;select.replaceChildren();if(!tracks.length)select.add(new Option('No audio tracks found','0'));for(const t of tracks)select.add(new Option(`Track ${t.index+1} · ${t.language||t.codec}${t.title?' · '+t.title:''}`,String(t.index)));select.value=trackChoices.get(key)||'0';select.disabled=running||!tracks.length;}catch{select.replaceChildren(new Option('Cannot detect tracks — see activity','0'));}
 select.onchange=()=>{trackChoices.set(key,select.value);refreshTracks();};
}
// Reflect the selected-pair editors in file-row controls as well.
for(const id of ['audio_stream','reference_stream'])$(id).addEventListener('change',()=>{const side=id==='audio_stream'?'source':'target',i=selectedIndex>=0?selectedIndex:0;const select=$(side+'-list').children[i]?.querySelector('.inline-track');if(select)select.value=$(id).value;});
window.autosync.onEvent(({type,data})=>{
 if(type==='result'){$('jobs-empty').classList.add('hidden');const row=document.createElement('tr');const name=document.createElement('td');name.textContent=data.name;name.dir='auto';const status=document.createElement('td');const badge=document.createElement('span');badge.className='result-badge '+(data.status==='review'?'review':data.status==='complete'?'success':'failed');badge.textContent=data.status==='review'?'Needs review':data.status==='complete'?'Finished':'Failed';status.append(badge);const files=document.createElement('td');files.className='output-path';files.textContent=data.error||(data.files||[]).join('\n');
 const reportCell=document.createElement('td');
 if(data.reports_folder){
  const open=document.createElement('button');open.type='button';open.className='secondary';
  open.textContent='Open reports';open.title=data.reports_folder;
  open.onclick=()=>window.autosync.openJobReports(data.reports_folder).catch(error);
  reportCell.append(open);
 }else{reportCell.textContent='—';}
 row.append(name,status,files,reportCell);$('job-rows').append(row);}
 if(type==='done')syncRemodelBusy();
});
const previousReset=resetProgress;resetProgress=function(){previousReset();$('job-rows').replaceChildren();$('jobs-empty').classList.remove('hidden');};
applyRemodel();
