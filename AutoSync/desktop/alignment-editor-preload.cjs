'use strict';
const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('alignment',{
 getPlan:()=>ipcRenderer.invoke('align-get-plan'),
 waveform:track=>ipcRenderer.invoke('align-waveform',track),
 waveformRange:(track,start,end)=>ipcRenderer.invoke('align-waveform-range',track,start,end),
 frame:(track,time)=>ipcRenderer.invoke('align-frame',track,time),
 audio:(track,start,length,speed)=>ipcRenderer.invoke('align-audio',track,start,length,speed),
 save:segments=>ipcRenderer.invoke('align-save',segments),
 export:()=>ipcRenderer.invoke('align-export'),
 openFolder:()=>ipcRenderer.invoke('align-open-folder'),
 onEvent:callback=>{const handler=(_,data)=>callback(data);ipcRenderer.on('alignment-event',handler);return()=>ipcRenderer.removeListener('alignment-event',handler);}
});
