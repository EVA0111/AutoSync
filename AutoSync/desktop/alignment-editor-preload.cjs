'use strict';
const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('alignment',{
 getPlan:()=>ipcRenderer.invoke('align-get-plan'),
 waveform:track=>ipcRenderer.invoke('align-waveform',track),
 waveformRange:(track,start,end)=>ipcRenderer.invoke('align-waveform-range',track,start,end),
 frame:(track,time,media)=>ipcRenderer.invoke('align-frame',track,time,media),
 videoProxy:track=>ipcRenderer.invoke('align-video-proxy',track),
 clipEdit:(op,payload)=>ipcRenderer.invoke('align-clip-op',op,payload),
 audio:(track,start,length,speed,media)=>ipcRenderer.invoke('align-audio',track,start,length,speed,media),
 importMedia:()=>ipcRenderer.invoke('align-import'),
 registerMedia:paths=>ipcRenderer.invoke('align-register-media',paths),
 save:(segments,timeline,extras)=>ipcRenderer.invoke('align-save',segments,timeline,extras),
 export:()=>ipcRenderer.invoke('align-export'),
 openFolder:()=>ipcRenderer.invoke('align-open-folder'),
 snapshot:(track,time,media)=>ipcRenderer.invoke('align-snapshot',track,time,media),
 onEvent:callback=>{const handler=(_,data)=>callback(data);ipcRenderer.on('alignment-event',handler);return()=>ipcRenderer.removeListener('alignment-event',handler);}
});
