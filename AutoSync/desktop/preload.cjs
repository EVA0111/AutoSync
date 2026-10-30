const {contextBridge,ipcRenderer,webUtils}=require('electron');
contextBridge.exposeInMainWorld('autosync',{
 openGitHub:()=>ipcRenderer.invoke('open-github-profile'),
 openAlignmentEditor:()=>ipcRenderer.invoke('alignment-editor-open'),
 previewOpen:file=>ipcRenderer.invoke('preview-open',file),
 previewFrame:index=>ipcRenderer.invoke('preview-frame',index),
 previewClose:()=>ipcRenderer.invoke('preview-close'),
 // File objects must stay in the event's native context; only paths cross the bridge.
 onDrop:callback=>{const handler=event=>{event.preventDefault();const zone=event.target.closest?.('.drop-zone');const field=event.target.closest?.('.field');const target=zone?.id||field?.querySelector('input')?.id;if(!target)return;try{const paths=Array.from(event.dataTransfer?.files||[],file=>webUtils.getPathForFile(file)).filter(Boolean);callback({target,paths});}catch(error){callback({target,paths:[],error:error.message});}};document.addEventListener('drop',handler,true);return()=>document.removeEventListener('drop',handler,true);},
 collect:(paths,videoOnly=true)=>ipcRenderer.invoke('collect',paths,videoOnly),pickBatch:folder=>ipcRenderer.invoke('pick-batch',folder),
 subtitleCollect:paths=>ipcRenderer.invoke('subtitle-collect',paths),subtitlePick:folder=>ipcRenderer.invoke('subtitle-pick',folder),
 probe:file=>ipcRenderer.invoke('probe',file),
 browse:kind=>ipcRenderer.invoke('browse',kind),start:job=>ipcRenderer.invoke('start',job),stop:()=>ipcRenderer.invoke('stop'),
 openOutput:report=>ipcRenderer.invoke('open-output',report),example:()=>ipcRenderer.invoke('example'),
 onEvent:callback=>{const handler=(_event,data)=>callback(data);ipcRenderer.on('job-event',handler);return()=>ipcRenderer.removeListener('job-event',handler);}
});
