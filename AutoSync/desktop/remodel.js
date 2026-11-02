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

// ---------- Final layout ----------
// One top bar; Audio/Subtitles share a files column and a job-settings column;
// Jobs and Settings are full width; one run bar. Elements keep their ids, so
// the logic in renderer/workspace/preferences/readiness/progress is unchanged.
const jobsTab=nav.querySelector('[data-tab=jobs]');
brand.after(nav);
const jobsBadge=document.createElement('span');jobsBadge.id='jobs-badge';jobsBadge.className='tab-badge hidden';jobsTab.append(jobsBadge);
const workGrid=document.createElement('div');workGrid.className='work-grid';
const workMain=document.createElement('div');workMain.className='work-main';
const workSide=document.createElement('aside');workSide.className='work-side';workSide.setAttribute('aria-label','Job settings');
audioSection.before(workGrid);workGrid.append(workMain,workSide);workMain.append(audioSection,subSection,$('saved'));
function sideCard(id,title,note){const c=document.createElement('section');c.className='card';c.id=id;const h=document.createElement('h3');h.textContent=title;c.append(h);if(note){const p=document.createElement('p');p.className='card-note';p.textContent=note;c.append(p);}workSide.append(c);return c;}
const modeCard=sideCard('mode-card','Output');
modeCard.append($('mode-section'));$('mode-section').querySelector('.modes').classList.remove('hidden');modeBar.classList.add('hidden');
const methodCard=sideCard('method-card','Matching');methodCard.append(methodBox);methodBox.querySelector('label').textContent='Method';
const outputCard=sideCard('output-card','Save to');outputCard.append($('destination-panel'));
const tracksCard=sideCard('tracks-card','Audio tracks','Each file row has its own track menu; open this to edit the selected pair in detail.');
tracksCard.append($('audio-tracks'));trackDetails.querySelector('summary').textContent='Tracks for the selected pair';
$('destination-panel').querySelector('h2').remove();$('destination-panel').querySelector('p').remove();
const advancedCard=sideCard('advanced-card','Advanced');
const footNote=document.querySelector('.foot');workSide.append(footNote);
// Pairing tools stay visible under the two lists.
const pairBar=document.createElement('div');pairBar.className='pair-bar';
pairBar.append($('pair-episodes'),$('clear-batch'),$('pair-status'));
$('batch-panel').querySelector('.batch-columns').after(pairBar);
pairDetails.querySelector('summary').textContent='Reorder rows';
// "Turned off" cards instead of empty pages.
function offCard(section,checkbox,what){
 const c=document.createElement('div');c.className='off-card hidden';
 const p=document.createElement('p');p.textContent=what+' syncing is turned off for this run.';
 const b=document.createElement('button');b.className='primary';b.textContent='Turn on '+what.toLowerCase()+' syncing';
 b.onclick=()=>{if(!running){$(checkbox).checked=true;$(checkbox).dispatchEvent(new Event('change'));}};
 c.append(p,b);section.querySelector('.section-heading').after(c);return c;
}
const audioOff=offCard(audioSection,'enable-audio','Audio'),subOff=offCard(subSection,'enable-subtitles','Subtitle');
// Settings: grouped cards; engine setup is always visible.
const settings=$('settings-panel');
function settingsGroup(title,note){const g=document.createElement('section');g.className='settings-group';const h=document.createElement('h3');h.textContent=title;g.append(h);if(note){const p=document.createElement('p');p.className='card-note';p.textContent=note;g.append(p);}settings.append(g);return g;}
const featureGroup=settingsGroup('Features','Optional tools. Turned-off advanced options use their defaults.');
featureGroup.append(...settings.querySelectorAll('.preference-row'));
const folderGroup=settingsGroup('Folders');folderGroup.append($('report-fields'),$('temp-fields'));
const setupDetails=$('setup-engine').closest('details');setupDetails.open=true;
const engineGroup=settingsGroup('Engine & AI models',setupDetails.querySelector('p').textContent);
engineGroup.append($('setup-engine').parentElement);setupDetails.remove();
settings.querySelector('h2').textContent='Settings';settings.querySelector(':scope>p').remove();
// Run bar: progress and next step on the left, actions on the right.
const run=document.querySelector('.run');
const runInfo=document.createElement('div');runInfo.className='run-info';
const runActions=document.createElement('div');runActions.className='run-actions';
runInfo.append($('job-progress'),setupCheck,$('status'));
runActions.append($('analyze-label'),$('stop'),$('alignment-editor-open'),$('start'));
run.replaceChildren(runInfo,runActions);
setupCheck.classList.remove('panel');
let jobResults=0,jobReviews=0;
function showJobsBadge(){jobsBadge.textContent=jobReviews?jobReviews+' to review':String(jobResults);jobsBadge.classList.toggle('hidden',!jobResults);jobsBadge.classList.toggle('warn',!!jobReviews);}
window.autosync.onEvent(({type,data})=>{if(type==='result'){jobResults++;if(data.status==='review')jobReviews++;showJobsBadge();}});
// Progress and run status appear once a run has started; until then the next step is shown.
const resetBeforeLayout=resetProgress;resetProgress=function(){resetBeforeLayout();jobResults=0;jobReviews=0;showJobsBadge();run.classList.add('has-run');};
function applyLayout(){
 const sync=workspace==='Sync jobs',saved=workspace==='Saved plan',audioTab=sync&&activeTab==='audio';
 workGrid.classList.toggle('hidden',!(saved||(sync&&activeTab!=='jobs')));
 for(const c of [modeCard,methodCard,tracksCard])c.classList.toggle('hidden',!audioTab||!$('enable-audio').checked);
 // workspace.js re-homes the advanced panel for saved plans; keep it in its card otherwise.
 if(!saved&&$('audio-advanced').parentElement!==advancedCard)advancedCard.append($('audio-advanced'));
 advancedCard.classList.toggle('hidden',saved||!audioTab||$('audio-advanced').classList.contains('hidden'));
 audioOff.classList.toggle('hidden',!audioTab||$('enable-audio').checked);
 subOff.classList.toggle('hidden',!(sync&&activeTab==='subtitles')||$('enable-subtitles').checked);
 document.body.dataset.view=saved?'plan':workspace==='Settings'?'settings':activeTab;
}
const applyRemodelBeforeLayout=applyRemodel;applyRemodel=function(){applyRemodelBeforeLayout();applyLayout();};
applyRemodel();
