'use strict';
const {contextBridge,ipcRenderer}=require('electron');
const nle=require('./nle-project.cjs');
contextBridge.exposeInMainWorld('alignment',{
 getPlan:()=>ipcRenderer.invoke('align-get-plan'),
 waveform:track=>ipcRenderer.invoke('align-waveform',track),
 waveformRange:(track,start,end)=>ipcRenderer.invoke('align-waveform-range',track,start,end),
 frame:(track,time)=>ipcRenderer.invoke('align-frame',track,time),
 videoProxy:track=>ipcRenderer.invoke('align-video-proxy',track),
 clipEdit:(op,payload)=>ipcRenderer.invoke('align-clip-op',op,payload),
 nleCreate:plan=>plan.editor_timeline?nle.validateProject(plan.editor_timeline):nle.newProject(plan),
 nleFlatten:project=>nle.flatSegments(project),
 nleOp:(op,project,...args)=>{
  if(!['split','trim','move','remove','paste','setTrack'].includes(op))throw Error('Unsupported timeline edit.');
  return nle[op](project,...args);
 },
 nleCopy:(project,id,i,o)=>nle.copyClip(project,id,i,o),
 nleFind:(project,id)=>nle.findClip(project,id),
 nleSnap:(project,t,opts)=>nle.snap(project,t,opts),
 audio:(track,start,length,speed)=>ipcRenderer.invoke('align-audio',track,start,length,speed),
 save:(segments,timeline)=>ipcRenderer.invoke('align-save',segments,timeline),
 export:()=>ipcRenderer.invoke('align-export'),
 openFolder:()=>ipcRenderer.invoke('align-open-folder'),
 onEvent:callback=>{const handler=(_,data)=>callback(data);ipcRenderer.on('alignment-event',handler);return()=>ipcRenderer.removeListener('alignment-event',handler);}
});
