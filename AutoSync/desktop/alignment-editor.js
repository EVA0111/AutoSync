'use strict';
const $=id=>document.getElementById(id);
const clone=value=>JSON.parse(JSON.stringify(value));
let plan=null,segments=[],waves={source:null,target:null},selected=0,playhead=0,scroll=0,view=60;
let undo=[],redo=[],playing=false,playToken=0,frameToken=0,drag=null,saved=false,exporting=false,loop=false;
let wavesFine={source:null,target:null},waveGeneration=0,waveTimer=null;
let clipboard=null,inMark=null,outMark=null;
const canvas=$('timeline'),ctx=canvas.getContext('2d'),audio=$('audio-player');
const videos={source:$('source-video'),target:$('target-video')};
const videoStatus={source:'pending',target:'pending'},videoLastSync={source:0,target:0};
const videoProxyStarted=new Set();let fallbackFrameTimer=null;
const rowTops=[40,132,224,316],rowNames=['V1','A1','A2','MIX'];
const rowDescriptions=['TARGET VIDEO','SOURCE AUDIO','TARGET AUDIO','EDITED OUTPUT'];
let tool='select',snapEnabled=true;
const trimTime=t=>{const ms=Math.max(0,Math.round(t*1000));return [Math.floor(ms/3600000),Math.floor(ms/60000)%60,Math.floor(ms/1000)%60].map(n=>String(n).padStart(2,'0')).join(':')+'.'+String(ms%1000).padStart(3,'0');};
const fmt=n=>Number(n).toFixed(3);
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const current=()=>segments[selected]||null;
const report=(message,error=false)=>{$('editor-status').textContent=message;$('editor-status').style.color=error?'#f2a8a1':'#a3d1be';};
function locate(t){return segments.findIndex((s,i)=>s.target_start<=t&&(t<s.target_end||i===segments.length-1));}
function mapSource(t){
 const i=locate(clamp(t,0,plan.duration)),s=segments[Math.max(0,i)];
 if(!s||s.kind!=='audio')return null;
 return s.source_start+(clamp(t,s.target_start,s.target_end)-s.target_start)*s.speed;
}
function mapTarget(t){
 const edits=plan.video_edits?.kept||[];
 for(const k of edits){
  const len=Number(k.end)-Number(k.start);
  if(t>=Number(k.output_start)-.001&&t<=Number(k.output_start)+len+.001)
   return Number(k.original_start)+t-Number(k.output_start);
 }
 if(plan.main_trim)return t+Number(plan.main_trim.target_start||0);
 return t;
}
function saveHistory(){
 undo.push(clone(segments));if(undo.length>100)undo.shift();redo=[];saved=false;setButtons();
}
function restore(stack,other){
 if(!stack.length)return;
 other.push(clone(segments));segments=stack.pop();selected=clamp(selected,0,segments.length-1);
 refresh();saved=false;setButtons();
}
function setButtons(){
 $('undo').disabled=!undo.length;$('redo').disabled=!redo.length;
 $('export').disabled=exporting||!saved;
 if($('paste-clip'))$('paste-clip').disabled=exporting||!clipboard;
 $('save').disabled=exporting;
 $('open-folder').disabled=!saved;
}
function refresh(){
 const s=current(),enabled=!!s;
 $('selection-summary').textContent=enabled?'Region '+(selected+1)+' / '+segments.length+' · '+(s.kind==='audio'?'Source audio':'Target / unfilled section'):'No region selected.';
 for(const id of ['region-start','region-end','region-source','region-speed','apply','split','join','source-mode','target-mode','nudge-left','nudge-right'])$(id).disabled=!enabled;
 if(!enabled)return;
 $('region-start').value=fmt(s.target_start);$('region-end').value=fmt(s.target_end);
 $('region-source').value=s.kind==='audio'?fmt(s.source_start):'';
 $('region-speed').value=s.kind==='audio'?Number(s.speed).toFixed(6):'';
 $('region-source').disabled=s.kind!=='audio';$('region-speed').disabled=s.kind!=='audio';
 $('join').disabled=selected===0;
 for(const id of ['copy-clip','cut-clip','mark-in','mark-out','clear-range','trim-left','trim-right'])$(id).disabled=!enabled;
 $('paste-clip').disabled=!clipboard||exporting;
 $('source-mode').disabled=s.kind==='audio';$('target-mode').disabled=s.kind!=='audio';
 $('split').disabled=playhead<=s.target_start+.05||playhead>=s.target_end-.05;
 draw();
}
function range(){
 const w=canvas.clientWidth||800;
 const scale=(w-150)/Math.max(1,view);
 return {w,scale,left:130,right:w-18};
}
const xFor=t=>range().left+(t-scroll)*range().scale;
const tFor=x=>clamp(scroll+(x-range().left)/range().scale,0,plan.duration);
function resetZoom(){
 const z=Number($('zoom').value);
 view=Math.min(plan.duration,Math.max(1.5,plan.duration/Math.pow(2,z/10)));
 scroll=clamp(scroll,0,Math.max(0,plan.duration-view));
 $('scroll').max=String(Math.max(0,plan.duration-view));$('scroll').value=String(scroll);
 $('zoom-label').textContent=trimTime(view)+' visible';
 draw();scheduleFineWaveforms();
}
function waveSample(track,time){
 const fine=wavesFine[track];
 if(fine&&time>=fine.start&&time<fine.start+fine.duration&&fine.peaks.length){
  const i=clamp(Math.floor((time-fine.start)/fine.duration*fine.peaks.length),0,fine.peaks.length-1);
  return fine.peaks[i];
 }
 const w=waves[track];
 if(!w||!Number.isFinite(time)||time<0||time>=w.duration)return 0;
 return w.peaks[clamp(Math.floor(time/w.duration*w.peaks.length),0,w.peaks.length-1)]||0;
}

function scheduleFineWaveforms(){
 if(waveTimer)clearTimeout(waveTimer);
 const generation=++waveGeneration;
 if(!plan||view>80)return;
 waveTimer=setTimeout(async()=>{
  const upper=Math.min(plan.duration,scroll+view);
  const sourceTimes=[];
  for(const s of segments){
   if(s.kind!=='audio'||s.target_end<scroll||s.target_start>upper)continue;
   const lo=Math.max(scroll,s.target_start),hi=Math.min(upper,s.target_end);
   sourceTimes.push(s.source_start+(lo-s.target_start)*s.speed,s.source_start+(hi-s.target_start)*s.speed);
  }
  const bounds={
   target:[mapTarget(scroll),mapTarget(upper)],
   source:sourceTimes.length?[Math.min(...sourceTimes),Math.max(...sourceTimes)]:null
  };
  for(const track of ['source','target']){
   const times=bounds[track];
   if(!times||times[1]<=times[0]||times[1]-times[0]>120)continue;
   try{
    const start=Math.max(0,times[0]-.15),end=times[1]+.15;
    const result=await window.alignment.waveformRange(track,start,end);
    if(generation!==waveGeneration)return;
    wavesFine[track]=result;
    draw();
   }catch(error){
    if(generation===waveGeneration)report('High-resolution waveform unavailable: '+error.message,true);
   }
  }
 },180);
}
function draw(){
 if(!plan)return;
 const dpr=window.devicePixelRatio||1,w=canvas.clientWidth||800,h=425;
 if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){
  canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);
 }
 ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
 ctx.fillStyle='#101923';ctx.fillRect(0,0,w,h);
 const {scale,left,right}=range();
 for(let row=0;row<4;row++){
  const y=rowTops[row];
  ctx.fillStyle=row===3?'#24203a':row===0?'#152a40':'#182433';ctx.fillRect(left,y,w-left-12,79);
  ctx.fillStyle='#9daec1';ctx.font='11px Segoe UI';ctx.fillText(rowNames[row],9,y+16);
  ctx.font='10px Consolas';ctx.fillText(rowDescriptions[row],9,y+33);
  ctx.save();ctx.beginPath();ctx.rect(left,y,w-left-12,79);ctx.clip();
  for(let i=0;i<segments.length;i++){
   const s=segments[i],x=xFor(s.target_start),rightX=xFor(s.target_end);
   if(rightX<left||x>w)continue;
   const start=clamp(x,left,w-12),stop=clamp(rightX,left,w-12);
   const alpha=selected===i?.42:.20;
   const rgb=(s.kind==='audio'?(row===0?'95,164,228':row===2?'161,135,227':'75,171,142'):(row===2?'233,159,102':'92,104,121'));
   ctx.fillStyle='rgba('+rgb+','+alpha+')';ctx.fillRect(start,y+2,stop-start,75);
   ctx.strokeStyle=selected===i?'#e0cfff':'#8293a9';ctx.lineWidth=selected===i?1.8:.65;
   ctx.beginPath();ctx.moveTo(x,y+2);ctx.lineTo(x,y+77);ctx.stroke();
   if(stop-start>38){ctx.fillStyle='#d0e1f0';ctx.font='11px Segoe UI';ctx.fillText('R'+(i+1)+(s.kind==='audio'?' · source':' · target'),start+5,y+16,stop-start-8);}
  }
  ctx.strokeStyle=row===1?'#69adf1':row===2?'#62c8aa':'#b9a8fa';ctx.lineWidth=1;
  for(let x=left+2;x<right;x+=3){
   const t=tFor(x),i=locate(t),s=segments[Math.max(0,i)];
   const sourceSec=mapSource(t),targetSec=mapTarget(t);
   const v=row===0?waveSample('source',sourceSec):row===1?waveSample('target',targetSec):(s?.kind==='audio'?waveSample('source',sourceSec):waveSample('target',targetSec));
   const amplitude=Math.max(.8,Math.pow(v,.6)*24);
   const mid=y+51;
   ctx.beginPath();ctx.moveTo(x,mid-amplitude);ctx.lineTo(x,mid+amplitude);ctx.stroke();
  }
  ctx.restore();
 }
 const step=Math.pow(10,Math.floor(Math.log10(Math.max(1,view/7))));
 const tick=[1,2,5,10].map(n=>n*step).find(n=>view/n<=12)||step*10;
 ctx.font='10px Consolas';ctx.strokeStyle='#3c4d60';ctx.fillStyle='#b6c1d0';
 for(let t=Math.ceil(scroll/tick)*tick;t<=scroll+view;t+=tick){
  const x=xFor(t);ctx.beginPath();ctx.moveTo(x,23);ctx.lineTo(x,407);ctx.stroke();
  ctx.fillText(trimTime(t),x+2,17);
 }
 const px=xFor(playhead);
 ctx.strokeStyle='#ffcf72';ctx.lineWidth=2;
 ctx.beginPath();ctx.moveTo(px,22);ctx.lineTo(px,409);ctx.stroke();
 ctx.fillStyle='#ffcf72';ctx.beginPath();ctx.moveTo(px-6,20);ctx.lineTo(px+6,20);ctx.lineTo(px,29);ctx.fill();
}
function updateClock(){ $('clock').textContent=trimTime(playhead);$('source-time').textContent=mapSource(playhead)==null?'Unmatched':trimTime(mapSource(playhead));$('target-time').textContent=trimTime(mapTarget(playhead)); }
// Chromium video decoding runs continuously. FFmpeg still-image extraction is
// ONLY for a paused seek when native playback or its proxy is unavailable.
function setupVideos(media){
 for(const track of ['source','target']){
  const v=videos[track],url=media?.[track],wait=$(track+'-wait');
  v.muted=true;v.playsInline=true;v.preload='auto';
  if(!url){videoStatus[track]='unavailable';wait.textContent='No '+track+' video available';continue;}
  v.onloadeddata=()=>{
   videoStatus[track]='ready';v.hidden=false;
   $(track+'-frame').hidden=true;wait.hidden=true;
   syncVideos(true);
  };
  v.onerror=()=>{
   if(videoProxyStarted.has(track)){
    videoStatus[track]='unavailable';wait.hidden=false;
    wait.textContent='Video decoder unavailable; use still-frame preview.';
    report('Could not play '+track+' video preview.',true);return;
   }
   videoProxyStarted.add(track);videoStatus[track]='preparing';
   wait.hidden=false;wait.textContent='Creating smooth '+track+' preview in the background…';
   window.alignment.videoProxy(track).then(proxy=>{
    if(!plan)return;
    v.src=proxy;v.load();
   }).catch(err=>{
    videoStatus[track]='unavailable';wait.hidden=false;
    wait.textContent='Preview unavailable: '+err.message;
    report('Proxy generation failed for '+track+': '+err.message,true);
   });
  };
  v.src=url;v.load();
 }
}
function syncVideos(force=false){
 if(!plan)return;
 for(const track of ['source','target']){
  const v=videos[track];if(videoStatus[track]!=='ready')continue;
  const t=track==='source'?mapSource(playhead):mapTarget(playhead);
  if(t===null||!Number.isFinite(t)){
   v.pause();v.hidden=true;
   $(track+'-wait').hidden=false;$(track+'-wait').textContent='Unmatched source video';
   continue;
  }
  v.hidden=false;$(track+'-wait').hidden=true;
  const i=locate(playhead),s=segments[Math.max(0,i)];
  const speed=track==='source'&&s?.kind==='audio'?s.speed:1;
  if(Math.abs(v.playbackRate-speed)>.001)v.playbackRate=speed;
  const desired=Math.min(t,Number.isFinite(v.duration)?Math.max(0,v.duration-.04):t);
  const now=performance.now();
  if(Number.isFinite(desired)&&(force||(Math.abs(v.currentTime-desired)>.35&&now-videoLastSync[track]>500))){
   videoLastSync[track]=now;
   try{v.currentTime=desired;}catch{}
  }
  if(playing&&v.paused)v.play().catch(()=>{});
  if(!playing&&!v.paused)v.pause();
 }
}
async function updateFrames(){
 if(playing||!plan)return;
 clearTimeout(fallbackFrameTimer);
 const generation=++frameToken;
 fallbackFrameTimer=setTimeout(async()=>{
  for(const track of ['source','target']){
   if(videoStatus[track]==='ready')continue;
   const t=track==='source'?mapSource(playhead):mapTarget(playhead);
   const img=$(track+'-frame'),wait=$(track+'-wait');
   if(t==null){img.hidden=true;wait.hidden=false;continue;}
   try{
    const data=await window.alignment.frame(track,t);
    if(generation!==frameToken)return;
    if(data){img.src=data;img.hidden=false;wait.hidden=true;}
   }catch{wait.hidden=false;}
  }
 },160);
}
function movePlayhead(t,frame=true){
 playhead=clamp(t,0,plan.duration);
 if(playhead<scroll||playhead>scroll+view){scroll=clamp(playhead-view*.35,0,Math.max(0,plan.duration-view));$('scroll').value=String(scroll);scheduleFineWaveforms();}
 updateClock();draw();refreshSelectionOnly();
 syncVideos(true);
 if(frame)updateFrames();
}
function refreshSelectionOnly(){
 $('split').disabled=!current()||playhead<=current().target_start+.05||playhead>=current().target_end-.05;
}
function pause(){
 playing=false;playToken++;nextAudioChunk=null;audio.pause();audio.removeAttribute('src');$('play').textContent='▶ Play';
 for(const v of Object.values(videos))v.pause();
}
async function play(){
 if(playing){pause();return;}
 playing=true;$('play').textContent='❚❚ Pause';await playChunk();
}
let nextAudioChunk=null;
function chunkAt(t){
 const i=locate(t),s=segments[Math.max(0,i)];
 if(!s||t>=plan.duration-.001)return null;
 const mode=$('audition').value;
 const length=Math.min(11.5,plan.duration-t,s.target_end-t);
 if(length<=.001)return null;
 const track=mode==='output'?(s.kind==='audio'?'source':'target'):mode;
 const start=track==='source'?mapSource(t):mapTarget(t);
 const speed=track==='source'&&s.kind==='audio'?s.speed:1;
 if(start==null)return null;
 return {t,length,track,start,speed,key:[t,length,track,start,speed].map(n=>String(n)).join('|')};
}
async function playChunk(){
 if(!playing||playhead>=plan.duration-.001){pause();return;}
 const token=++playToken,t0=playhead;
 const chunk=chunkAt(t0);
 if(!chunk){
  const seg=segments[Math.max(0,locate(t0))];
  if(seg&&seg.target_end-t0<=.001){
   movePlayhead(Math.min(plan.duration,seg.target_end+.002),false);
   return playChunk();
  }
  report('No source audio is mapped here. Switch to target or edited output.',true);
  pause();return;
 }
 const {length,track,start,speed,key}=chunk;
 try{
  // Fetch the next chunk while the current one plays to eliminate FFmpeg
  // launch delays and audible gaps between preview windows.
  const request=nextAudioChunk?.key===key?nextAudioChunk.promise:window.alignment.audio(track,start,length,speed);
  nextAudioChunk=null;
  const url=await request;
  if(token!==playToken||!playing)return;
  audio.pause();audio.src=url;audio.currentTime=0;
  audio.ontimeupdate=()=>{
   if(token!==playToken||!playing)return;
   playhead=clamp(t0+Math.min(length,audio.currentTime),0,plan.duration);
   updateClock();draw();refreshSelectionOnly();syncVideos();
  };
  audio.onended=()=>{
   if(token!==playToken||!playing)return;
   for(const v of Object.values(videos))v.pause();
   playhead=clamp(t0+length,0,plan.duration);
   if(loop&&playhead>=current().target_end-.01)movePlayhead(current().target_start,false);
   playChunk();
  };
  await audio.play();
  syncVideos(true);
  const nextAt=t0+length;
  if(nextAt<plan.duration-.002){
   const upcoming=chunkAt(nextAt);
   if(upcoming){
    const promise=window.alignment.audio(upcoming.track,upcoming.start,upcoming.length,upcoming.speed);
    // Keep errors attached to the promise so background prefetch is safe.
    promise.catch(()=>{});
    nextAudioChunk={key:upcoming.key,promise};
   }
  }
 }catch(e){if(token===playToken){pause();report('Audio preview failed: '+e.message,true);}}
}
function bound(index,time){
 if(index<=0||index>=segments.length)return false;
 const left=segments[index-1],right=segments[index];
 const value=clamp(time,left.target_start+.05,right.target_end-.05);
 if(right.kind==='audio')right.source_start+=(value-right.target_start)*right.speed;
 left.target_end=value;right.target_start=value;
 return true;
}
function offset(delta){
 const s=current();if(!s||s.kind!=='audio')return;
 const value=s.source_start+delta;
 if(value<0){report('Cannot shift source before zero.',true);return;}
 saveHistory();s.source_start=value;refresh();
}
function select(index){
 if(selected!==index){inMark=null;outMark=null;refreshMarkLabels();}
 selected=clamp(index,0,segments.length-1);refresh();
}
function change(){
 const s=current();if(!s)return;
 const start=Number($('region-start').value),end=Number($('region-end').value),
 src=Number($('region-source').value),sp=Number($('region-speed').value);
 if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end>plan.duration||start>=end){report('Invalid region boundaries.',true);return;}
 if(s.kind==='audio'&&(!Number.isFinite(src)||src<0||!Number.isFinite(sp)||sp<.5||sp>2)){report('Invalid source position or speed.',true);return;}
 const before=clone(segments);
 if(selected>0)bound(selected,start);else if(Math.abs(start)>.001){report('First region must start at zero.',true);return;}
 if(selected<segments.length-1)bound(selected+1,end);else if(Math.abs(end-plan.duration)>.001){segments=before;report('Last region must end at the output duration.',true);return;}
 if(s.kind==='audio'){s.source_start=src;s.speed=sp;}
 if(segments.some(x=>x.target_end-x.target_start<.05||x.source_start<0)){segments=before;report('Region too short or source position negative.',true);return;}
 undo.push(before);redo=[];saved=false;refresh();setButtons();report('Region updated.');
}
function split(){
 const s=current();if(!s||playhead<=s.target_start+.05||playhead>=s.target_end-.05)return;
 saveHistory();const right={...s,target_start:playhead};
 if(right.kind==='audio')right.source_start=s.source_start+(playhead-s.target_start)*s.speed;
 s.target_end=playhead;segments.splice(selected+1,0,right);selected++;refresh();report('Region split.');
}
function join(){
 if(selected<=0)return;
 saveHistory();const s=segments[selected-1];
 // Joining deliberately uses the left region's mapping across the removed boundary.
 s.target_end=segments[selected].target_end;segments.splice(selected,1);selected--;refresh();report('Joined regions. Listen across the join.');
}
function mode(kind){
 const s=current();if(!s||s.kind===kind)return;saveHistory();
 if(kind==='audio'){
  const prev=segments.slice(0,selected).reverse().find(x=>x.kind==='audio');
  s.kind='audio';s.speed=prev?.speed||1;
  s.source_start=Math.max(0,prev?prev.source_start+(s.target_start-prev.target_start)*prev.speed:s.target_start);
 }else{
  s.kind='reference';delete s.source_start;delete s.speed;
 }
 refresh();report(kind==='audio'?'Using source audio; adjust its start and listen.':'Using target audio for this section.');}
function onDown(e){
 if(!plan)return;pause();
 const r=canvas.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top,t=tFor(x);
 if(y<26){movePlayhead(t);return;}
 const idx=locate(t);if(idx<0)return;
 select(idx);movePlayhead(t);
 const boundary=segments.findIndex((s,j)=>j>0&&Math.abs(xFor(s.target_start)-x)<8);
 drag={initialX:x,initialTime:t,boundary:boundary>0?boundary:null,index:idx,original:clone(segments),mode:boundary>0?'boundary':'offset',moved:false,historyAdded:false};
 canvas.setPointerCapture(e.pointerId);
}
function onMove(e){
 if(!drag||!plan)return;
 const x=e.clientX-canvas.getBoundingClientRect().left,dt=(x-drag.initialX)/range().scale;
 if(Math.abs(dt)<.001)return;
 if(!drag.historyAdded){saveHistory();drag.historyAdded=true;}
 segments=clone(drag.original);drag.moved=true;
 if(drag.mode==='boundary'){
  const i=drag.boundary;bound(i,drag.original[i].target_start+dt);
 }else{
  const s=segments[drag.index];
  if(s.kind==='audio')s.source_start=Math.max(0,drag.original[drag.index].source_start+dt*s.speed);
  else{drag.moved=false;}
 }
 refresh();
}
function onUp(){
 if(!drag)return;
 if(drag.moved){saved=false;setButtons();report('Region moved; preview the result before exporting.');}
 drag=null;refresh();
}
canvas.addEventListener('pointerdown',onDown);canvas.addEventListener('pointermove',onMove);canvas.addEventListener('pointerup',onUp);canvas.addEventListener('lostpointercapture',onUp);
canvas.addEventListener('dblclick',e=>{movePlayhead(tFor(e.clientX-canvas.getBoundingClientRect().left));});
$('scroll').oninput=()=>{scroll=Number($('scroll').value);draw();scheduleFineWaveforms();};
$('zoom').oninput=resetZoom;
$('back').onclick=()=>{pause();movePlayhead(playhead-.04);};
$('forward').onclick=()=>{pause();movePlayhead(playhead+.04);};
$('play').onclick=play;$('audition').onchange=()=>{if(playing){pause();play();}};
$('loop').onclick=()=>{loop=!loop;$('loop').textContent='Loop selected region: '+(loop?'On':'Off');};
function reviewTimes(){
 if(!plan)return [];
 const flagged=(plan.review||[]).map(r=>Number(r.splice??((Number(r.start)+Number(r.end))/2)))
  .filter(Number.isFinite).filter(t=>t>=0&&t<=plan.duration);
 for(const seg of segments.slice(1))flagged.push(seg.target_start);
 return [...new Set(flagged.map(t=>Math.round(t*100)/100))].sort((a,b)=>a-b);
}
function jumpReview(direction){
 const all=reviewTimes();
 if(!all.length){report('No joins or review points were found.');return;}
 const next=direction>0?all.find(t=>t>playhead+.05):all.slice().reverse().find(t=>t<playhead-.05);
 const t=next??(direction>0?all[0]:all[all.length-1]);
 pause();movePlayhead(t);
 const i=locate(Math.max(0,Math.min(plan.duration-.001,t)));
 if(i>=0)select(i);
 report('Reviewing join at '+trimTime(t)+'. Compare edited and target audio here.');
}
function focusRegion(){
 const s=current();if(!s||!plan)return;
 pause();
 const desired=Math.max(2,Math.min(plan.duration,(s.target_end-s.target_start)+4));
 const z=Math.max(0,Math.min(100,Math.round(10*Math.log2(plan.duration/desired))));
 $('zoom').value=String(z);resetZoom();
 scroll=clamp(s.target_start-2,0,Math.max(0,plan.duration-view));
 $('scroll').value=String(scroll);draw();scheduleFineWaveforms();
}
$('jump-opening').onclick=()=>{pause();movePlayhead(0);select(0);report('Check whether the opening music and video were preserved.');};
$('previous-issue').onclick=()=>jumpReview(-1);
$('next-issue').onclick=()=>jumpReview(1);
$('zoom-region').onclick=focusRegion;
$('play-join').onclick=()=>{
 if(!plan)return;
 const s=current();if(!s)return;
 const t=selected<segments.length-1?s.target_end:s.target_start;
 pause();movePlayhead(Math.max(0,t-2));
 $('audition').value='output';$('ab-audio').textContent='A/B: Edited output';
 play();
 report('Listening across '+trimTime(t)+'; press A to compare against target audio.');
};
function toggleAB(){
 const track=$('audition');track.value=track.value==='target'?'output':'target';
 $('ab-audio').textContent=track.value==='target'?'A/B: Target':'A/B: Edited output';
 if(playing){pause();play();}
}
$('ab-audio').onclick=toggleAB;

function refreshMarkLabels(){
 const inText=inMark==null?'In —':trimTime(inMark);
 const outText=outMark==null?'Out —':trimTime(outMark);
 $('clip-range').textContent=inText+' · '+outText;
 $('clipboard-status').textContent=clipboard?'Copied '+clipboard.duration.toFixed(3)+' s':'Clipboard empty';
 $('paste-clip').disabled=!clipboard||exporting;
}
function markPoint(side){
 const seg=current();if(!seg)return;
 if(playhead<seg.target_start||playhead>seg.target_end){report('Move the playhead inside the selected clip.',true);return;}
 if(side==='in')inMark=playhead;else outMark=playhead;
 refreshMarkLabels();
}
async function copySelected(){
 if(exporting)return;
 const seg=current();if(!seg)return;
 try{
  const from=inMark===null?seg.target_start:inMark;
  const to=outMark===null?seg.target_end:outMark;
  clipboard=await window.alignment.clipEdit('copy',{segments,index:selected,inPoint:from,outPoint:to});
  refreshMarkLabels();
  report('Copied '+clipboard.duration.toFixed(3)+' s. Move playhead and Paste to overwrite only the audio.');
 }catch(e){report('Copy failed: '+e.message,true);}
}
async function pasteSelected(){
 if(exporting||!clipboard)return;
 try{
  const result=await window.alignment.clipEdit('paste',{segments,at:playhead,clip:clipboard});
  pause();saveHistory();segments=result;
  selected=clamp(locate(playhead+.001),0,segments.length-1);
  refresh();setButtons();
  report('Pasted '+clipboard.duration.toFixed(3)+' s without shifting the video. Undo: Ctrl+Z.');
 }catch(e){report('Paste failed: '+e.message,true);}
}
async function trimSelected(which){
 if(exporting)return;
 try{
  const result=await window.alignment.clipEdit(which==='left'?'trim-left':'trim-right',{
   segments,index:selected,at:playhead
  });
  pause();saveHistory();segments=result;
  selected=clamp(locate(which==='left'?playhead+.001:playhead-.001),0,segments.length-1);
  refresh();setButtons();
  report('Trimmed '+which+' to the playhead. Unused audio switches to the target; video length is unchanged.');
 }catch(e){report('Trim failed: '+e.message,true);}
}
async function cutSelected(){
 if(exporting)return;
 const seg=current();if(!seg)return;
 try{
  const captured=await window.alignment.clipEdit('copy',{segments,index:selected,
   inPoint:seg.target_start,outPoint:seg.target_end});
  const result=await window.alignment.clipEdit('paste',{
   segments,at:seg.target_start,clip:{kind:'reference',duration:seg.target_end-seg.target_start}
  });
  pause();saveHistory();segments=result;clipboard=captured;
  refreshMarkLabels();refresh();setButtons();
  report('Cut the audio clip to the clipboard. The vacated range uses target audio (no ripple).');
 }catch(e){report('Cut failed: '+e.message,true);}
}
$('mark-in').onclick=()=>markPoint('in');
$('mark-out').onclick=()=>markPoint('out');
$('clear-range').onclick=()=>{inMark=null;outMark=null;refreshMarkLabels();};
$('copy-clip').onclick=copySelected;
$('paste-clip').onclick=pasteSelected;
$('cut-clip').onclick=cutSelected;
$('trim-left').onclick=()=>trimSelected('left');
$('trim-right').onclick=()=>trimSelected('right');

$('nudge-left').onclick=()=>offset(-.04);$('nudge-right').onclick=()=>offset(.04);
$('undo').onclick=()=>restore(undo,redo);$('redo').onclick=()=>restore(redo,undo);
$('apply').onclick=change;$('split').onclick=split;$('join').onclick=join;
$('source-mode').onclick=()=>mode('audio');$('target-mode').onclick=()=>mode('reference');
$('save').onclick=async()=>{
 pause();
 try{const location=await window.alignment.save(segments);if(!location){report('Save cancelled.');return;}
  saved=true;setButtons();report('Edited project saved: '+location+'. The corrected output will be exported to that folder.');
 }catch(e){report('Save failed: '+e.message,true);}
};
$('export').onclick=async()=>{
 if(!saved){report('Save your edits before exporting.',true);return;}
 pause();exporting=true;setButtons();$('export-log').textContent='Exporting…\n';report('Exporting corrected audio and required video edits…');
 try{await window.alignment.export();}catch(e){report('Export failed: '+e.message,true);}
 finally{exporting=false;setButtons();}
};
$('open-folder').onclick=()=>window.alignment.openFolder().catch(e=>report(e.message,true));
window.alignment.onEvent(({kind,payload})=>{
 if(kind==='export-log'){$('export-log').textContent+=payload;$('export-log').scrollTop=$('export-log').scrollHeight;}
 if(kind==='export-done'){if(payload.code===0){saved=false;setButtons();}report(payload.code===0?'Export finished: '+payload.folder+'. Save again to create another corrected export.':'Export failed. Check the log.',payload.code!==0);}
});
window.addEventListener('keydown',e=>{
 if(e.target.matches('input,select,textarea'))return;
 if(e.code==='Space'){e.preventDefault();play();}
 if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='c'){e.preventDefault();copySelected();}
 if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='v'){e.preventDefault();pasteSelected();}
 if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='x'){e.preventDefault();cutSelected();}
 if(!e.ctrlKey&&!e.metaKey&&e.key.toLowerCase()==='s'){e.preventDefault();split();}
 if(!e.ctrlKey&&!e.metaKey&&e.key.toLowerCase()==='i'){e.preventDefault();markPoint('in');}
 if(!e.ctrlKey&&!e.metaKey&&e.key.toLowerCase()==='o'){e.preventDefault();markPoint('out');}
 if(!e.ctrlKey&&!e.metaKey&&e.key.toLowerCase()==='q'){e.preventDefault();trimSelected('left');}
 if(!e.ctrlKey&&!e.metaKey&&e.key.toLowerCase()==='w'){e.preventDefault();trimSelected('right');}
 if(e.key.toLowerCase()==='j'){e.preventDefault();jumpReview(-1);}
 if(e.key.toLowerCase()==='l'){e.preventDefault();jumpReview(1);}
 if(e.key.toLowerCase()==='a'){e.preventDefault();toggleAB();}
 if(e.key==='Escape'){pause();}
 if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();restore(undo,redo);}
 if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='y'){e.preventDefault();restore(redo,undo);}
 if(e.key==='ArrowLeft'){pause();movePlayhead(playhead-(e.shiftKey?1:.04));}
 if(e.key==='ArrowRight'){pause();movePlayhead(playhead+(e.shiftKey?1:.04));}
});
window.addEventListener('resize',draw);
(async()=>{
 try{
  const data=await window.alignment.getPlan();
  plan=data.plan;segments=clone(plan.segments);$('project-path').textContent=data.file;
  $('review-count').textContent=reviewTimes().length+' joins / review points';
  if(!segments.length)throw Error('No editable regions in the selected plan.');
  setupVideos(data.media);
  refreshMarkLabels();
  resetZoom();select(0);movePlayhead(0);setButtons();
  report('Loading source and target audio waveforms…');
  const results=await Promise.allSettled(['source','target'].map(x=>window.alignment.waveform(x)));
  results.forEach((r,i)=>{if(r.status==='fulfilled')waves[i===0?'source':'target']=r.value;});
  draw();scheduleFineWaveforms();report('Ready. Click or drag a region, listen, then save and export.');
 }catch(e){report('Unable to load editor: '+e.message,true);}
})();
