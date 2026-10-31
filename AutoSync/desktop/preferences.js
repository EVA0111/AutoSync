const prefDefaults={reports:false,audioAdvanced:false,subtitleAdvanced:false,csv:false,savedPlans:false,activity:true};
let prefs={...prefDefaults};try{const saved=JSON.parse(localStorage.getItem('autosync-preferences')||'{}');for(const key in prefDefaults)if(typeof saved[key]==='boolean')prefs[key]=saved[key];}catch{}
const settingsNav=document.createElement('button');settingsNav.className='nav';settingsNav.dataset.task='Settings';settingsNav.textContent='Settings';document.querySelector('nav').append(settingsNav);
const settingsPanel=document.createElement('section');settingsPanel.id='settings-panel';settingsPanel.className='panel hidden';settingsPanel.innerHTML='<h2>Settings</h2><p>Choose which optional features to show and use. Disabled advanced options use their defaults.</p>';
for(const [key,label] of [['reports','Save reports and timing plans'],['audioAdvanced','Enable advanced audio settings'],['subtitleAdvanced','Enable advanced subtitle settings'],['csv','Enable CSV job import'],['savedPlans','Enable saved-plan rendering'],['activity','Show activity log']]){const labelEl=document.createElement('label');labelEl.className='preference-row';const input=document.createElement('input');input.type='checkbox';input.id='pref-'+key;input.checked=prefs[key];input.onchange=()=>{prefs[key]=input.checked;localStorage.setItem('autosync-preferences',JSON.stringify(prefs));if(!prefs.savedPlans&&workspace==='Saved plan')workspace='Sync jobs';applyWorkspace();};labelEl.append(input,document.createTextNode(' '+label));settingsPanel.append(labelEl);}
const reportsFields=document.createElement('div');reportsFields.id='report-fields';settingsPanel.append(reportsFields);document.querySelector('main').append(settingsPanel);fileField('report-fields',['reports-destination','Reports root (optional)','output','AutoSync Reports beside the application · or choose any folder']);
let defaultReportsRoot='';
const reportsField=$('reports-destination');
const rememberedReportsRoot=localStorage.getItem('autosync-reports-folder')||'';
if(rememberedReportsRoot)reportsField.value=rememberedReportsRoot;
reportsField.addEventListener('change',()=>{
 const value=reportsField.value.trim();
 if(value)localStorage.setItem('autosync-reports-folder',value);
 else localStorage.removeItem('autosync-reports-folder');
});
window.autosync.defaultReportsPath().then(folder=>{
 defaultReportsRoot=folder;
 if(!reportsField.value.trim())reportsField.placeholder='Auto — '+folder;
 if(typeof refreshReadiness==='function')queueMicrotask(refreshReadiness);
}).catch(error=>{console.warn('Reports default path unavailable:',error);});
function reportsRoot(){return reportsField.value.trim()||defaultReportsRoot;}
const tempFields=document.createElement('div');tempFields.id='temp-fields';settingsPanel.append(tempFields);
fileField('temp-fields',['temp-destination','Temporary work folder (optional)','output','Auto — AutoSync Temp beside target video']);
const tempField=$('temp-destination');
tempField.value=localStorage.getItem('autosync-temp-folder')||'';
tempField.addEventListener('change',()=>{
 const chosen=tempField.value.trim();
 if(chosen)localStorage.setItem('autosync-temp-folder',chosen);
 else localStorage.removeItem('autosync-temp-folder');
});
const tempHint=document.createElement('p');tempHint.className='hint';
tempHint.textContent='Leave blank for an AutoSync Temp folder beside the target video. Per-run scratch files are removed on completion or failure.';
$('temp-fields').append(tempHint);
settingsPanel.append($('setup-engine').closest('details'));
const destinationPanel=document.createElement('section');destinationPanel.id='destination-panel';destinationPanel.className='panel';
destinationPanel.innerHTML='<h2>Save output</h2><p>Leave blank to save next to the target, or choose any folder or drive. Existing files are never overwritten.</p><div id="destination-fields"></div><p id="destination-reminder" role="alert" class="hidden"></p>';
$('audio-section').before(destinationPanel);
fileField('destination-fields',['output-destination','Folder (optional)','output','Auto — next to target video · or choose any folder']);
const outputField=$('output-destination');
const lastDirectory=localStorage.getItem('autosync-last-output-folder');
if(lastDirectory)outputField.value=lastDirectory;
outputField.addEventListener('change',()=>{
 const chosen=outputField.value.trim();
 if(chosen)localStorage.setItem('autosync-last-output-folder',chosen);
 else localStorage.removeItem('autosync-last-output-folder');
});
const targetFolderButton=document.createElement('button');
targetFolderButton.type='button';targetFolderButton.className='secondary';
targetFolderButton.textContent='Use target folder';
targetFolderButton.title='Save beside the target file (without overwriting the video)';
outputField.closest('.field').append(targetFolderButton);
function parentFolder(file){
 if(!file)return '';
 const match=String(file).trim().match(/^(.*)[\\/][^\\/]+$/);
 return match?match[1]:'';
}
function defaultOutputFolder(){
 const source=batchFiles.target?.[0]||$('target')?.value.trim()||$('sub_target_media')?.value.trim()
  ||$('sub_subtitle')?.value.trim()||$('plan')?.value.trim();
 const parent=parentFolder(source);
 if(!parent)return '';
 return parent+(parent.includes('\\')?'\\':'/')+'AutoSync Outputs';
}
targetFolderButton.onclick=()=>{
 const folder=parentFolder(batchFiles.target?.[0]||$('target')?.value.trim()||$('sub_target_media')?.value.trim()||$('plan')?.value.trim());
 if(!folder){$('destination-reminder').textContent='Choose a target video first.';$('destination-reminder').classList.remove('hidden');return;}
 outputField.value=folder;outputField.dispatchEvent(new Event('change'));
};
function applyPreferences(){
 const settings=workspace==='Settings',saved=workspace==='Saved plan';settingsPanel.classList.toggle('hidden',!settings);destinationPanel.classList.toggle('hidden',settings);
 $('audio-advanced').classList.toggle('hidden',!prefs.audioAdvanced||settings||(!saved&&!$('enable-audio').checked));
 $('sub-options').closest('details').classList.toggle('hidden',!prefs.subtitleAdvanced);$('sub_semantic').parentElement.classList.toggle('hidden',!prefs.subtitleAdvanced||!['reference','audio'].includes($('sub_mode').value));
 $('batch-field').closest('details').classList.toggle('hidden',!prefs.csv);if(!prefs.csv)$('use_csv').checked=false;
 $('analyze-label').classList.toggle('hidden',settings||saved||!prefs.audioAdvanced||!$('enable-audio').checked);
 $('report-fields').classList.toggle('hidden',!prefs.reports);$('report').classList.toggle('hidden',!prefs.reports);document.querySelector('[data-task="Saved plan"]').classList.toggle('hidden',!prefs.savedPlans);
 document.querySelector('.log-panel').classList.toggle('hidden',!prefs.activity);$('start').classList.toggle('hidden',settings);
 $('batch_out').closest('.field').classList.add('hidden');$('sub_out').closest('.field').classList.add('hidden');
}
function destinationRequest(jobs){
 const out=$('output-destination').value.trim()||defaultOutputFolder();const reports=reportsRoot();const note=$('destination-reminder');note.classList.add('hidden');
 if(!out){note.textContent='Choose a source or target file to determine the default output folder, or Browse to select one.';note.classList.remove('hidden');throw Error(note.textContent);}
 if(prefs.reports&&!reports){workspace='Settings';applyWorkspace();throw Error('Cannot locate the app reports folder. Choose a reports folder in Settings.');}
 return {task:'Managed queue',jobs,output_dir:out,save_reports:prefs.reports,reports_dir:reports,temp_dir:tempField.value.trim()};
}
function audioDefaultsWhenDisabled(values){if(prefs.audioAdvanced)return;for(const [id,,def] of advanced)values[id]=Array.isArray(def)?def[0]:def;for(const id of ['audio_only','reference_fallback','remove_unmatched_video','allow_uncertain_cuts','analyze_only'])values[id]=false;}
function subtitleDefaultsWhenDisabled(values){if(prefs.subtitleAdvanced)return;Object.assign(values,{encoding:'utf-8-sig',source_fps:'',target_fps:'',source_crop:'',target_crop:'',whisper_model:'small',language:'',semantic:false,sushi_window:'10',sushi_max_window:'30'});}
// One global destination replaces the old per-section output fields.
window.autosync.onDrop(({target,paths})=>{if(!running&&paths.length===1&&['output-destination','reports-destination','temp-destination'].includes(target)){$(target).value=paths[0];$(target).dispatchEvent(new Event('change'));}});
