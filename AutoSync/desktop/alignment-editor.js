'use strict';
const $=id=>document.getElementById(id);
const clone=value=>JSON.parse(JSON.stringify(value));
let plan=null,planFile='',segments=[],waves={source:null,target:null},selected=0,playhead=0,scroll=0,view=60;
let undo=[],redo=[],playing=false,playToken=0,frameToken=0,drag=null,saved=false,exporting=false,loop=false;
let wavesFine={source:null,target:null},waveGeneration=0,waveTimer=null,waveLoading={source:true,target:true};
let clipboard=null,inMark=null,outMark=null,frame=.04,rate=1,edited=false,stopAt=null;
let reviewed=new Set(),notes={},issueFilter='all',issueItems=[],currentIssue=null,markers=[];
const canvas=$('timeline'),ctx=canvas.getContext('2d');
const overview=$('overview'),octx=overview.getContext('2d');
const videos={source:$('source-video'),target:$('target-video')};
const videoStatus={source:'pending',target:'pending'},videoLastSync={source:0,target:0};
const videoProxyStarted=new Set();let fallbackFrameTimer=null;
const RULER=26;
const VT=globalThis.VideoTimeline;
let imports=[],mediaSel=null,originalDuration=0;
// Clip operations validate against the current output length (picture edits change it).
const clipEdit=(op,payload)=>window.alignment.clipEdit(op,{...payload,duration:plan.duration});
// Rows by index: 0 V1 (main picture), 1 A1 (source audio), 2 A2 (target audio),
// 3 MIX (edited output audio), 4+k video track V(k+2) above V1 (drawn top-down
// from the highest). vtracks[k] = {clips, locked, hidden} (video-timeline.js).
let rowTops=[RULER,0,0,0,0],rowH=80;
const BASE_ROWS=['V1','A1','A2','MIX'],BASE_DESC=['MAIN VIDEO','SOURCE AUDIO','TARGET AUDIO','EDITED OUTPUT'];
const rowName=r=>r<4?BASE_ROWS[r]:'V'+(r-2);
let vtracks=[{clips:[],locked:false,hidden:false}],locks={V1:false,MIX:false},selClip=null,activeTrack=-1,dropHint=null,flatCache=null;
const trackOf=row=>row>=4?row-4:null;
// A locked track refuses edits; a message says which one and how to unlock it.
// Names: 'V1', 'MIX', 'ALL' (every video track), or a video track index.
function locked(...tracks){
 const names=tracks.flatMap(t=>t==='ALL'?vtracks.map((_,k)=>k):[t]);
 const t=names.find(k=>typeof k==='number'?vtracks[k]?.locked:locks[k]);
 if(t!==undefined)report((typeof t==='number'?'V'+(t+2):t)+' is locked. Click its 🔒 in the track header to unlock it.',true);
 return t!==undefined;
}
// The output picture (topmost visible clip at each moment), recomputed after any change.
function flatPicture(){
 if(!flatCache)flatCache=VT.flatten(VT.baseKept(plan),vtracks);
 return flatCache;
}
const pictureNow=t=>VT.pictureAt(flatPicture(),clamp(t,0,plan.duration));
const hasTrackClips=()=>vtracks.some(t=>t.clips.length);
let tool='select',snapEnabled=true;
const trimTime=t=>{const ms=Math.max(0,Math.round(t*1000));return [Math.floor(ms/3600000),Math.floor(ms/60000)%60,Math.floor(ms/1000)%60].map(n=>String(n).padStart(2,'0')).join(':')+'.'+String(ms%1000).padStart(3,'0');};
const shortTime=t=>{const s=Math.max(0,t);return Math.floor(s/60)+':'+(s%60).toFixed(2).padStart(5,'0');};
const fmt=n=>Number(n).toFixed(3);
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const current=()=>segments[selected]||null;
const store={get(k){try{return JSON.parse(localStorage.getItem(k));}catch{return null;}},set(k,v){try{localStorage.setItem(k,JSON.stringify(v));}catch{}},del(k){try{localStorage.removeItem(k);}catch{}}};
const report=(message,error=false)=>{const el=$('editor-status');el.textContent=message;el.title=message;el.classList.toggle('error',!!error);};
function locate(t){return segments.findIndex((s,i)=>s.target_start<=t&&(t<s.target_end||i===segments.length-1));}
function mapSource(t){
 const i=locate(clamp(t,0,plan.duration)),s=segments[Math.max(0,i)];
 if(!s||s.kind!=='audio')return null;
 return s.source_start+(clamp(t,s.target_start,s.target_end)-s.target_start)*s.speed;
}
// Target picture time the output shows at t (video tracks included); null for imported clips.
function mapPicture(t){
 const pic=pictureNow(t);
 return pic?(pic.target===undefined?null:pic.target):mapTarget(t);
}
// Target time for audio (V1's mapping: the target's own sound stays with V1).
function mapTarget(t){
 const edits=plan.video_edits?.kept||[];
 if(edits.length){
  // Imported clips have no target picture or audio.
  const pic=VT.pictureAt(edits,clamp(t,0,plan.duration));
  if(pic)return pic.target===undefined?null:pic.target;
 }
 // A target trim (range marked before syncing) keeps output times zero-based
 // while the plan points at the original target file.
 const trimmed=Number(plan.input_trims?.target?.start||0);
 if(plan.main_trim)return t+Number(plan.main_trim.target_start||0)+trimmed;
 return t+trimmed;
}

// ---------- history, state and autosave ----------
// Callers record history first and then change the clips: rebuild the list after that.
function touched(){edited=true;saved=false;autosave();setButtons();setTimeout(()=>{buildIssues();draw();},0);}
function snapshot(){return {segments:clone(segments),duration:plan.duration,videoEdits:plan.video_edits?clone(plan.video_edits):null,vtracks:clone(vtracks)};}
function applySnapshot(x){
 if(Array.isArray(x)){segments=x;return;}
 segments=x.segments;plan.duration=x.duration;
 if(x.videoEdits)plan.video_edits=x.videoEdits;else delete plan.video_edits;
 if(x.vtracks)vtracks=x.vtracks;
 selClip=null;flatCache=null;
}
function saveHistory(){
 undo.push(snapshot());if(undo.length>100)undo.shift();redo=[];touched();
}
function restore(stack,other){
 if(!stack.length)return;
 other.push(snapshot());applySnapshot(stack.pop());selected=clamp(selected,0,segments.length-1);
 afterLengthChange();refresh();touched();report(stack===undo?'Undone. Ctrl+Y redoes it.':'Redone.');
}
function afterLengthChange(){
 playhead=clamp(playhead,0,plan.duration);
 view=Math.min(view,plan.duration);setScroll(scroll);
 $('zoom-label').textContent=trimTime(view)+' shown';
}
const autosaveKey=()=>'autosync-edit:'+planFile;
let autosaveTimer=null;
function autosave(){
 clearTimeout(autosaveTimer);
 autosaveTimer=setTimeout(()=>{
  if(!plan)return;
  store.set(autosaveKey(),{segments:edited?segments:null,duration:edited?plan.duration:null,
   videoEdits:edited&&plan.video_edits?plan.video_edits:null,vtracks:edited?vtracks:null,markers,locks,reviewed:[...reviewed],notes,at:Date.now()});
 },400);
}
function setButtons(){
 $('undo').disabled=!undo.length;$('redo').disabled=!redo.length;
 $('export').disabled=exporting||!saved;
 const video=plan&&(plan.video_edits||hasTrackClips()||plan.censorship?.recreate||segments.some(s=>s.censored_action==='cut'));
 $('export').textContent=video?'Export edited video':'Export corrected audio';
 $('export').title=saved?$('export').textContent:'Save your edits first (Save As…), then export';
 $('paste-clip').disabled=exporting||!clipboard;
 $('save').disabled=exporting;
 $('open-folder').disabled=!saved;
 const chip=$('state-chip');
 chip.className='chip '+(exporting?'dirty':saved?'ok':edited?'dirty':'');
 chip.textContent=exporting?'Exporting…':saved?'Saved · ready to export':edited?'Unsaved changes':'No changes';
}

// ---------- inspector ----------
function refresh(){
 const s=current(),enabled=!!s;
 const summary=$('selection-summary');
 if(!enabled)summary.textContent='Select a clip in the timeline.';
 else summary.innerHTML='<b>Clip '+(selected+1)+' of '+segments.length+'</b> · '+(s.kind==='audio'?'source audio':'target audio')+
  ' · '+shortTime(s.target_start)+'–'+shortTime(s.target_end)+' ('+(s.target_end-s.target_start).toFixed(2)+' s)';
 if(enabled&&s.kind==='media')summary.innerHTML=summary.innerHTML.replace('target audio','imported audio · '+escapeHtml(s.label||baseName(s.media)));
 for(const id of ['region-start','region-end','region-source','region-speed','apply','split','join','source-mode','target-mode','nudge-left','nudge-right','nudge-frame-left','nudge-frame-right','clip-gain','fade-in','fade-out','apply-volume'])$(id).disabled=!enabled;
 if(!enabled){draw();return;}
 $('clip-gain').value=Number(s.gain_db||0).toFixed(1);$('fade-in').value=String(Math.round(Number(s.fade_in_ms||0)));$('fade-out').value=String(Math.round(Number(s.fade_out_ms||0)));
 $('region-start').value=fmt(s.target_start);$('region-end').value=fmt(s.target_end);
 $('region-source').value=s.kind==='audio'?fmt(s.source_start):'';
 $('region-speed').value=s.kind==='audio'?Number(s.speed).toFixed(6):'';
 $('region-source').disabled=s.kind!=='audio';$('region-speed').disabled=s.kind!=='audio';
 for(const id of ['nudge-left','nudge-right','nudge-frame-left','nudge-frame-right'])$(id).disabled=s.kind!=='audio';
 $('offset-note').textContent=s.kind==='audio'?
  'Audio offset: source '+trimTime(s.source_start)+' plays at output '+trimTime(s.target_start)+(Math.abs(s.speed-1)>1e-6?' · speed '+s.speed.toFixed(4):''):
  s.kind==='media'?(s.media_stream==null?'Silence (the inserted file has no sound).':'Plays '+(s.label||baseName(s.media))+' from '+trimTime(Number(s.media_start||0))+'.'):
  'This clip plays the target\'s own audio. Choose “Source audio” to map source audio here.';
 $('join').disabled=selected===0;
 for(const id of ['copy-clip','cut-clip','mark-in','mark-out','clear-range','trim-left','trim-right'])$(id).disabled=!enabled;
 $('paste-clip').disabled=!clipboard||exporting;
 $('source-mode').classList.toggle('on',s.kind==='audio');$('target-mode').classList.toggle('on',s.kind!=='audio');
 $('source-mode').disabled=s.kind==='audio';$('target-mode').disabled=s.kind!=='audio';
 refreshSelectionOnly();
 draw();
}
function refreshSelectionOnly(){
 const s=current();
 $('split').disabled=!s||playhead<=s.target_start+.05||playhead>=s.target_end-.05;
 $('split').title=$('split').disabled?'Move the playhead inside the selected clip to split it · S':'Split the clip at the playhead · S';
}

// ---------- timeline geometry ----------
// Canvas width is measured once per paint (fitCanvas), never per coordinate:
// reading clientWidth inside drawing loops forced a layout for every pixel.
let geoW=800;
function range(){
 const scale=(geoW-150)/Math.max(1,view);
 return {w:geoW,scale,left:130,right:geoW-18};
}
const xFor=t=>range().left+(t-scroll)*range().scale;
const tFor=x=>clamp(scroll+(x-range().left)/range().scale,0,plan.duration);
const zoomFor=v=>clamp(Math.round(10*Math.log2(plan.duration/Math.max(1.5,v))),0,100);
function setScroll(v){
 scroll=clamp(v,0,Math.max(0,plan.duration-view));
 draw();scheduleFineWaveforms();
}
function resetZoom(){
 const z=Number($('zoom').value);
 view=Math.min(plan.duration,Math.max(1.5,plan.duration/Math.pow(2,z/10)));
 setScroll(scroll);
 $('zoom-label').textContent=trimTime(view)+' shown';
}
function zoomTo(newView,anchorTime=playhead,anchorX=null){
 const r=range();
 const frac=anchorX==null?clamp((anchorTime-scroll)/view,0,1):(anchorX-r.left)/(r.right-r.left);
 view=clamp(newView,1.5,plan.duration);
 $('zoom').value=String(zoomFor(view));
 $('zoom-label').textContent=trimTime(view)+' shown';
 setScroll(anchorTime-frac*view);
}
function waveSample(track,time){
 if(time==null)return 0;
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
function flaggedRegions(){
 return (plan.review||[]).filter(r=>r.confidence!=='supported'&&r.confidence!=='manual'||/\b(uncertain|review|fallback|rewind)/i.test(r.reason||''))
  .map(r=>({start:Number(r.start),end:Number(r.end)})).filter(r=>Number.isFinite(r.start)&&Number.isFinite(r.end));
}
function fitCanvas(c,cx){
 const dpr=window.devicePixelRatio||1,w=c.clientWidth||800,h=c.clientHeight||100;
 if(c.width!==Math.round(w*dpr)||c.height!==Math.round(h*dpr)){c.width=Math.round(w*dpr);c.height=Math.round(h*dpr);}
 cx.setTransform(dpr,0,0,dpr,0,0);
 if(c===canvas)geoW=w;
 return {w,h,dpr};
}
// ---------- rendering ----------
// Clips, waveforms and the ruler are painted into an offscreen layer only when
// they change (edits, scroll, zoom, resize, selection). Each frame just copies
// that layer and draws the playhead, In/Out band and drag ghost on top, so
// playback and scrubbing stay smooth on long episodes.
const layer=document.createElement('canvas'),lctx=layer.getContext('2d');
const olayer=document.createElement('canvas'),olctx=olayer.getContext('2d');
let staticDirty=true,renderQueued=false;
function draw(){staticDirty=true;flatCache=null;requestRender();}
function requestRender(){if(renderQueued)return;renderQueued=true;requestAnimationFrame(()=>{renderQueued=false;render();});}
function render(){
 if(!plan)return;
 const {w,h,dpr}=fitCanvas(canvas,ctx),o=fitCanvas(overview,octx);
 for(const [c,src] of [[layer,canvas],[olayer,overview]])if(c.width!==src.width||c.height!==src.height){c.width=src.width;c.height=src.height;staticDirty=true;}
 if(staticDirty){
  lctx.setTransform(dpr,0,0,dpr,0,0);paintTimeline(lctx,w,h);
  olctx.setTransform(dpr,0,0,dpr,0,0);paintOverview(olctx,o.w,o.h);
  staticDirty=false;
 }
 ctx.setTransform(1,0,0,1,0,0);ctx.drawImage(layer,0,0);ctx.setTransform(dpr,0,0,dpr,0,0);
 paintOverlay(ctx,w,h);
 octx.setTransform(1,0,0,1,0,0);octx.drawImage(olayer,0,0);octx.setTransform(dpr,0,0,dpr,0,0);
 octx.fillStyle='#ffcf72';octx.fillRect(playhead/plan.duration*o.w-1,0,2,o.h);
}
// Row heights and positions for the current track count (painting and hit-testing
// both use this, so a click right after adding a track lands on the right row).
function layoutRows(h=canvas.clientHeight||300){
 const n=vtracks.length;
 rowH=Math.max(24,Math.floor((h-RULER-8)/(4+n)));
 rowTops=[...[0,1,2,3].map(r=>n+r),...vtracks.map((_,k)=>n-1-k)].map(i=>RULER+i*(rowH+2));
}
function paintTimeline(ctx,w,h){
 layoutRows(h);
 const inner=rowH-4,mid=inner/2;
 ctx.clearRect(0,0,w,h);ctx.fillStyle='#101923';ctx.fillRect(0,0,w,h);
 const {scale,left,right}=range();
 // review regions behind everything
 // Output time -> clip, source and target time for every second pixel, in one pass.
 const sweep={x:[],seg:[],src:[],tgt:[]};
 for(let x=left+2,i=0;x<right;x+=2){
  const t=tFor(x);
  while(i<segments.length-1&&t>=segments[i].target_end)i++;
  const s=segments[i];if(!s)break;
  sweep.x.push(x);sweep.seg.push(s);
  sweep.src.push(s.kind==='audio'?s.source_start+(clamp(t,s.target_start,s.target_end)-s.target_start)*s.speed:null);
  sweep.tgt.push(mapTarget(t));
 }
 for(const r of flaggedRegions()){
  const a=xFor(r.start),b=xFor(r.end);if(b<left||a>right)continue;
  ctx.fillStyle='rgba(232,154,91,.10)';ctx.fillRect(Math.max(left,a),RULER,Math.min(right,b)-Math.max(left,a),h-RULER);
  ctx.fillStyle='#e89a5b';ctx.fillRect(Math.max(left,a),RULER-4,Math.max(2,Math.min(right,b)-Math.max(left,a)),3);
 }
 for(let row=0;row<4;row++){
  const y=rowTops[row];
  ctx.fillStyle=row===3?'#211d33':row===0?'#132638':'#16212e';ctx.fillRect(left,y,w-left-12,rowH);
  paintHeader(ctx,row,y);
  const loadingTrack=row===1?'source':row===2?'target':null;
  if(loadingTrack&&waveLoading[loadingTrack]&&rowH>44){ctx.fillStyle='#e8c07a';ctx.fillText('loading…',9,y+43);}
  ctx.save();ctx.beginPath();ctx.rect(left,y,w-left-12,rowH);ctx.clip();
  if(row===0){
   // Output picture: target pieces (blue) and imported clips (amber), in output order.
   const pieces=plan.video_edits?.kept?.length?plan.video_edits.kept:[{start:0,end:plan.duration,output_start:0,original_start:mapTarget(0)}];
   for(const k of pieces){
    const a=xFor(Number(k.output_start)),b=xFor(Number(k.output_start)+Number(k.end)-Number(k.start));
    if(b<left||a>w)continue;
    ctx.fillStyle=k.media?'#5a4520':k.fill?'#3d2f5c':'#21506f';ctx.fillRect(a+1,y+2,Math.max(1,b-a-2),inner);
    ctx.strokeStyle=k.media?'#e0aa5a':k.fill?'#a98be0':'#5fa9d8';ctx.lineWidth=1;ctx.strokeRect(a+1,y+2,Math.max(1,b-a-2),inner);
    if(b-a>70){
     ctx.fillStyle=k.media?'#ffe3b8':k.fill?'#e6dcfb':'#d6eafd';ctx.font='12px Segoe UI';
     const label=k.media?'▶ '+(k.label||baseName(k.media)):k.fill?'◫ Motion fill · '+trimTime(Number(k.hold)):'Target '+trimTime(Number(k.original_start));
     ctx.fillText(label,Math.max(left+6,a+6),y+16,Math.max(10,Math.min(b,w-12)-Math.max(left+6,a+6)-4));
    }
   }
   // Censored scenes marked "cut" leave the exported video.
   for(const s of segments){
    if(s.censored_action!=='cut')continue;
    const a=xFor(s.target_start),b=xFor(s.target_end);
    ctx.fillStyle='rgba(240,120,110,.35)';ctx.fillRect(a,y+2,b-a,inner);
    ctx.strokeStyle='rgba(255,170,160,.6)';ctx.lineWidth=1;
    for(let x=a-inner;x<b;x+=8){const lo=Math.max(0,a-x),hi=Math.min(inner,b-x);if(hi<=lo)continue;ctx.beginPath();ctx.moveTo(x+lo,y+2+lo);ctx.lineTo(x+hi,y+2+hi);ctx.stroke();}
    if(b-a>60){ctx.fillStyle='#ffd6d0';ctx.font='11px Segoe UI';ctx.fillText('cut on export',a+5,y+inner-6);}
   }
   for(const k of (plan.video_edits?.kept||[]).slice(1)){ctx.strokeStyle='#ffd27a';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(xFor(k.output_start),y+2);ctx.lineTo(xFor(k.output_start),y+rowH-2);ctx.stroke();ctx.lineWidth=1;}
   ctx.restore();continue;
  }
  if(row===2){
   // The target's own audio exists everywhere; it is dimmed where the output uses source audio.
   for(const s of segments){
    const a=clamp(xFor(s.target_start),left,w-12),b=clamp(xFor(s.target_end),left,w-12);if(b<=a)continue;
    ctx.fillStyle=s.kind==='audio'?'rgba(73,175,128,.10)':'rgba(73,175,128,.38)';ctx.fillRect(a,y+2,b-a,inner);
   }
  }
  for(let i=0;i<segments.length;i++){
   const s=segments[i];
   if(row===1&&s.kind!=='audio'||row===2&&(s.kind==='audio'||s.kind==='media'))continue;
   const x=xFor(s.target_start),rightX=xFor(s.target_end);
   if(rightX<left||x>w)continue;
   const start=clamp(x,left,w-12),stop=clamp(rightX,left,w-12);
   const alpha=selected===i&&row===3?.62:.40;
   const rgb=row===1?'66,155,213':row===2?'73,175,128':s.kind==='audio'?'161,120,227':s.kind==='media'?'224,170,90':'73,175,128';
   ctx.fillStyle='rgba('+rgb+','+alpha+')';ctx.fillRect(start,y+2,stop-start,inner);
   ctx.strokeStyle=selected===i?'#f1e6ff':'#6f8197';ctx.lineWidth=selected===i?2:.65;
   ctx.strokeRect(x+1,y+2,Math.max(1,rightX-x-2),inner);
   ctx.fillStyle=row===1?'#55bde5':row===2?'#62c889':'#ccabf7';
   ctx.fillRect(start,y+2,Math.max(1,stop-start),3);
   if(row===3&&rightX-x>20){
    ctx.fillStyle=selected===i?'#fff0ff':'#cfbadd';
    ctx.fillRect(x+2,y+mid-8,4,18);ctx.fillRect(rightX-6,y+mid-8,4,18);
   }
   if(stop-start>46){ctx.fillStyle='#d0e1f0';ctx.font='11px Segoe UI';ctx.fillText((i+1)+(s.kind==='audio'?' · source':s.kind==='media'?' · '+(s.label||baseName(s.media)):' · target'),start+5,y+15,stop-start-8);}
  }
  ctx.strokeStyle=row===1?'#69adf1':row===2?'#62c8aa':'#b9a8fa';ctx.lineWidth=1;
  const amp=Math.max(6,inner*.36);
  for(let k=0;k<sweep.x.length;k++){
   const s=sweep.seg[k],audio=s.kind==='audio';
   if(row===1&&!audio)continue;
   const v=row===1||row===3&&audio?waveSample('source',sweep.src[k]):waveSample('target',sweep.tgt[k]);
   const a=Math.max(.6,Math.pow(v,.6)*amp),x=sweep.x[k];
   ctx.globalAlpha=row===2&&audio?.35:1;
   ctx.beginPath();ctx.moveTo(x,y+2+mid-a);ctx.lineTo(x,y+2+mid+a);ctx.stroke();
  }
  ctx.globalAlpha=1;
  if(row===3)paintFades(ctx,y,inner);
  ctx.restore();
 }
 vtracks.forEach((_,k)=>paintTrack(ctx,w,inner,k));
 // ruler
 const step=Math.pow(10,Math.floor(Math.log10(Math.max(.01,view/7))));
 const tick=[1,2,5,10].map(n=>n*step).find(n=>view/n<=12)||step*10;
 ctx.font='10px Consolas';ctx.strokeStyle='#33445a';ctx.fillStyle='#b6c1d0';
 for(let t=Math.ceil(scroll/tick)*tick;t<=scroll+view;t+=tick){
  const x=xFor(t);ctx.beginPath();ctx.moveTo(x,RULER-8);ctx.lineTo(x,h-4);ctx.stroke();
  ctx.fillText(trimTime(t),x+3,12);
 }
 // review markers on the ruler
 for(const item of issueItems){
  const x=xFor(item.t);if(x<left||x>right)continue;
  ctx.fillStyle=reviewed.has(item.key)?'#46b8ac':item.kind==='flag'?'#e89a5b':'#a98ae8';
  ctx.beginPath();ctx.moveTo(x-5,RULER-12);ctx.lineTo(x+5,RULER-12);ctx.lineTo(x,RULER-4);ctx.fill();
 }
  for(const m of markers){
  const x=xFor(m);if(x<left||x>right)continue;
  ctx.fillStyle='#7fd4ff';ctx.fillRect(x-1,RULER-14,3,10);ctx.fillRect(x-4,RULER-14,9,3);
 }
}
// Track header: name and buttons. V1 and video tracks: ⧉ duplicate (a copy above it);
// video tracks also ✕ delete and 👁 show/hide; V1, MIX and video tracks: 🔒 lock.
function headerButtons(row,y){
 const out=[],b=(kind,x)=>out.push({kind,x,y:y+3,w:21,h:Math.min(20,rowH-6)});
 if(row===0)b('dup',78);
 if(row>=4){b('dup',30);b('del',53);b('eye',76);}
 if(row===0||row===3||row>=4)b('lock',101);
 return out;
}
function trackFlag(row,kind){
 const k=trackOf(row);
 if(kind==='lock')return k===null?locks[rowName(row)]:vtracks[k].locked;
 if(kind==='eye')return !!vtracks[k]?.hidden;
 return false;
}
function paintHeader(ctx,row,y){
 const active=row>=4?activeTrack===trackOf(row):row===0&&activeTrack===-1;
 ctx.fillStyle=active?'#18293b':'#111a25';ctx.fillRect(0,y,126,rowH);
 ctx.fillStyle=active?'#cfe6ff':'#9daec1';ctx.font='600 11px Segoe UI';ctx.fillText(rowName(row),9,y+15);
 if(rowH>40&&row<4){ctx.font='9px Consolas';ctx.fillStyle='#7f91a6';ctx.fillText(BASE_DESC[row],9,y+29);}
 for(const b of headerButtons(row,y)){
  const on=trackFlag(row,b.kind);
  ctx.fillStyle=on?'#5a3b22':'#1c2a3a';ctx.fillRect(b.x,b.y,b.w,b.h);
  ctx.strokeStyle=on?'#e8a35b':'#3b5068';ctx.strokeRect(b.x+.5,b.y+.5,b.w-1,b.h-1);
  ctx.font='11px Segoe UI Emoji, Segoe UI';ctx.fillStyle='#fff';
  ctx.fillText({lock:on?'🔒':'🔓',eye:on?'⊘':'👁',dup:'⧉',del:'✕'}[b.kind],b.x+4,b.y+Math.min(14,b.h-4));
 }
 if((row===0||row===3)&&trackFlag(row,'lock')){ctx.fillStyle='rgba(232,163,91,.07)';ctx.fillRect(130,y,geoW,rowH);}
}
// A video track above V1: footage (blue), imported clips (amber) and fills (purple).
function paintTrack(ctx,w,inner,k){
 const row=4+k,y=rowTops[row],t=vtracks[k],{left}=range();
 ctx.fillStyle='#16202c';ctx.fillRect(left,y,w-left-12,rowH);
 paintHeader(ctx,row,y);
 ctx.save();ctx.beginPath();ctx.rect(left,y,w-left-12,rowH);ctx.clip();
 ctx.globalAlpha=t.hidden?.35:1;
 t.clips.forEach((c,i)=>{
  const a=xFor(c.at),b=xFor(c.at+c.length);if(b<left||a>w)return;
  const media=c.media!==undefined,sel=selClip&&selClip.k===k&&selClip.i===i;
  ctx.fillStyle=media?'#5a4520':c.fill?'#3d2f5c':'#21506f';ctx.fillRect(a+1,y+2,Math.max(1,b-a-2),inner);
  ctx.strokeStyle=sel?'#fff1d0':media?'#e0aa5a':c.fill?'#a98be0':'#5fa9d8';ctx.lineWidth=sel?2:1;ctx.strokeRect(a+1,y+2,Math.max(1,b-a-2),inner);
  const item=media&&imports.find(x=>x.path===c.media),img=item&&thumbImage(item);
  if(img&&b-a>40&&inner>20){const th=inner-6,tw=Math.min(b-a-8,th*16/9);ctx.drawImage(img,a+4,y+5,tw,th);}
  if(b-a>70){
   ctx.fillStyle=media?'#ffe3b8':c.fill?'#e6dcfb':'#d6eafd';ctx.font='11px Segoe UI';
   const label=media?'▶ '+(c.label||baseName(c.media)):c.fill?(c.fill==='black'?'■ Black':'◫ Motion fill · '+trimTime(c.hold)):'Target '+trimTime(c.target);
   ctx.fillText(label,a+(img?inner*16/9+8:6),y+15,b-a-12);
  }
 });
 ctx.globalAlpha=1;
 if(t.locked){ctx.fillStyle='rgba(232,163,91,.07)';ctx.fillRect(left,y,w,rowH);}
 ctx.restore();
}
const thumbCache=new Map();
function thumbImage(item){
 if(!item.thumb)return null;
 let img=thumbCache.get(item.path);
 if(!img){img=new Image();img.onload=()=>draw();img.src=item.thumb;thumbCache.set(item.path,img);}
 return img.complete&&img.naturalWidth?img:null;
}
// Per-frame layer: In/Out band, drag ghost and playhead.
function paintOverlay(ctx,w,h){
 const {left,right}=range(),inner=rowH-4;
 if(inMark!=null||outMark!=null){
  const a=xFor(inMark??current()?.target_start??0),b=xFor(outMark??current()?.target_end??0);
  ctx.fillStyle='rgba(124,196,255,.13)';ctx.fillRect(Math.max(left,Math.min(a,b)),RULER,Math.min(right,Math.max(a,b))-Math.max(left,Math.min(a,b)),h-RULER);
  ctx.fillStyle='#7cc4ff';for(const x of [a,b])if(x>=left&&x<=right)ctx.fillRect(x-1,RULER,2,h-RULER);
 }
 if(drag?.ghost){
  const g=drag.ghost,lo=xFor(g.start),hi=xFor(g.end),gy=rowTops[g.row??3];
  ctx.fillStyle='rgba(150,209,255,.22)';ctx.fillRect(lo,gy+2,hi-lo,inner);
  ctx.strokeStyle='#c8edff';ctx.lineWidth=2;ctx.setLineDash([5,4]);
  ctx.strokeRect(lo,gy+2,hi-lo,inner);ctx.setLineDash([]);
  if(g.snap!==null){ctx.strokeStyle='#ffe8a0';ctx.beginPath();ctx.moveTo(xFor(g.snap),RULER);ctx.lineTo(xFor(g.snap),h-4);ctx.stroke();}
 }
 if(dropHint){
  const x=xFor(dropHint.time),y=rowTops[dropHint.row];
  ctx.fillStyle='rgba(124,255,180,.18)';ctx.fillRect(range().left,y,range().right-range().left,rowH);
  ctx.fillStyle='#7cffb4';ctx.fillRect(x-1,y,3,rowH);
  ctx.font='11px Segoe UI';ctx.fillText(dropHint.text,Math.min(x+6,range().right-160),y+14);
 }
 const px=xFor(playhead);
 ctx.strokeStyle='#ffcf72';ctx.lineWidth=2;
 ctx.beginPath();ctx.moveTo(px,RULER-6);ctx.lineTo(px,h-4);ctx.stroke();
 ctx.fillStyle='#ffcf72';ctx.beginPath();ctx.moveTo(px-6,RULER-14);ctx.lineTo(px+6,RULER-14);ctx.lineTo(px,RULER-5);ctx.fill();
}
// Clip gain and fades (set in the inspector) drawn on the output row.
function paintFades(ctx,y,inner){
 ctx.save();ctx.strokeStyle='#ffe08a';ctx.lineWidth=1.2;
 for(const s of segments){
  const a=xFor(s.target_start),b=xFor(s.target_end);if(b<range().left||a>range().right)continue;
  const fi=Number(s.fade_in_ms||0)/1000,fo=Number(s.fade_out_ms||0)/1000;
  if(fi>0){ctx.beginPath();ctx.moveTo(a,y+2+inner);ctx.lineTo(xFor(s.target_start+fi),y+3);ctx.stroke();}
  if(fo>0){ctx.beginPath();ctx.moveTo(xFor(s.target_end-fo),y+3);ctx.lineTo(b,y+2+inner);ctx.stroke();}
  if(Number(s.gain_db||0)&&b-a>60){ctx.fillStyle='#ffe08a';ctx.font='10px Segoe UI';ctx.fillText((s.gain_db>0?'+':'')+Number(s.gain_db).toFixed(1)+' dB',a+5,y+inner-4);}
 }
 ctx.restore();
}
function paintOverview(octx,w,h){
 const x=t=>t/plan.duration*w;
 octx.clearRect(0,0,w,h);octx.fillStyle='#0c131b';octx.fillRect(0,0,w,h);
 for(const s of segments){
  octx.fillStyle=s.kind==='audio'?'#5d4a8f':'#2f6f55';
  octx.fillRect(x(s.target_start),6,Math.max(1,x(s.target_end)-x(s.target_start)),h-12);
  octx.fillStyle='#0c131b';octx.fillRect(x(s.target_start),6,1,h-12);
 }
 for(const r of flaggedRegions()){octx.fillStyle='rgba(232,154,91,.8)';octx.fillRect(x(r.start),0,Math.max(2,x(r.end)-x(r.start)),4);}
 for(const item of issueItems){octx.fillStyle=reviewed.has(item.key)?'#46b8ac':item.kind==='flag'?'#e89a5b':'#b9a8fa';octx.fillRect(x(item.t)-1,h-4,2,4);}
 octx.strokeStyle='#cfe3f5';octx.lineWidth=1.5;octx.strokeRect(x(scroll)+.5,1,Math.max(3,x(scroll+view)-x(scroll))-1,h-2);
}
function updateClock(){
 $('clock').textContent=trimTime(playhead);
 const src=mapSource(playhead);
 $('source-time').textContent=src==null?'not used here':trimTime(src);
 $('target-time').textContent=trimTime(mapTarget(playhead));
}

// ---------- video ----------
// Chromium video decoding runs continuously. FFmpeg still-image extraction is
// ONLY for a paused seek when native playback or its proxy is unavailable.
function setupVideos(media){
 for(const track of ['source','target']){
  const v=videos[track],url=media?.[track],wait=$(track+'-wait');
  v.muted=true;v.playsInline=true;v.preload='auto';
  if(!url){videoStatus[track]='unavailable';wait.textContent='No '+track+' video available';continue;}
  v.onloadeddata=()=>{
   videoStatus[track]='ready';v.hidden=false;compareHint();
   $(track+'-frame').hidden=true;wait.hidden=true;
   syncVideos(true);
  };
  v.onerror=()=>{
   if(videoProxyStarted.has(track)){
    videoStatus[track]='unavailable';wait.hidden=false;
    wait.textContent='Video decoder unavailable; showing still frames.';
    report('Could not play '+track+' video preview.',true);return;
   }
   videoProxyStarted.add(track);videoStatus[track]='preparing';
   wait.hidden=false;wait.textContent='Creating a smooth '+track+' preview in the background…';compareHint();
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
  const t=track==='source'?mapSource(playhead):mapPicture(playhead);
  if(t===null||!Number.isFinite(t)){
   v.pause();v.hidden=true;
   $(track+'-wait').hidden=false;$(track+'-wait').textContent='Source not used at this point';
   continue;
  }
  v.hidden=false;$(track+'-wait').hidden=true;$(track+'-frame').hidden=true;
  const i=locate(playhead),s=segments[Math.max(0,i)];
  const speed=(track==='source'&&s?.kind==='audio'?s.speed:1)*rate;
  if(Math.abs(v.playbackRate-speed)>.001)v.playbackRate=speed;
  const desired=Math.min(t,Number.isFinite(v.duration)?Math.max(0,v.duration-.04):t);
  const now=performance.now();
  if(Number.isFinite(desired)&&(force||(Math.abs(v.currentTime-desired)>.35&&now-videoLastSync[track]>500))){
   videoLastSync[track]=now;
   try{v.currentTime=desired;}catch{}
  }
  // A motion fill previews as its held frame: the target viewer stays on it.
  const held=track==='target'&&pictureNow(playhead)?.piece?.fill;
  if(held){if(!v.paused)v.pause();if(Math.abs(v.currentTime-desired)>.02)try{v.currentTime=desired;}catch{}continue;}
  if(playing&&v.paused)v.play().catch(()=>{});
  if(!playing&&!v.paused)v.pause();
 }
 syncImport(force);
}
// An inserted clip replaces the target picture in the target viewer.
function syncImport(force=false){
 const v=$('import-video'),img=$('import-still');
 const pic=pictureNow(playhead);
 const item=pic?.media?imports.find(x=>x.path===pic.media):null;
 if(!pic?.media){
  if(!v.hidden){v.pause();v.hidden=true;}img.hidden=true;
  if(videoStatus.target==='ready'&&mapPicture(playhead)!=null)videos.target.hidden=false;
  return;
 }
 videos.target.hidden=true;$('target-frame').hidden=true;
 const wait=$('target-wait');
 if(!item){wait.hidden=false;wait.textContent='Imported file not found: '+baseName(pic.media);return;}
 wait.hidden=true;
 if(item.image){v.hidden=true;v.pause();if(img.dataset.src!==item.url){img.src=item.url;img.dataset.src=item.url;}img.hidden=false;return;}
 img.hidden=true;
 if(v.dataset.src!==item.url){v.src=item.url;v.dataset.src=item.url;v.load();}
 v.hidden=false;v.playbackRate=rate;
 const now=performance.now();
 if(force||Math.abs(v.currentTime-pic.time)>.35&&now-(syncImport.last||0)>500){syncImport.last=now;try{v.currentTime=pic.time;}catch{}}
 if(playing&&v.paused)v.play().catch(()=>{});
 if(!playing&&!v.paused)v.pause();
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
    // The video may have become ready while this still was decoding: a late
    // still would then cover the live video and never be replaced.
    if(videoStatus[track]==='ready'){img.hidden=true;continue;}
    if(data){img.src=data;img.hidden=false;wait.hidden=true;}
   }catch{wait.hidden=false;}
  }
 },160);
}
function movePlayhead(t,frameUpdate=true){
 playhead=clamp(t,0,plan.duration);
 if(playhead<scroll||playhead>scroll+view)setScroll(playhead-view*.35);
 updateClock();updateCurrentIssue();requestRender();refreshSelectionOnly();
 syncVideos(true);
 if(frameUpdate)updateFrames();
}
function step(frames){pause();movePlayhead(playhead+frames*frame);}

// ---------- playback ----------
// Web Audio: PCM chunks (binary from the main process) are scheduled back to
// back on one clock, so joins and chunk edges play without gaps, and the
// playhead follows that clock every animation frame. Clip gain and fades are
// applied here as in the export.
const AC=new AudioContext({sampleRate:48000,latencyHint:'interactive'});
const master=AC.createGain();master.connect(AC.destination);
const FIRST=1.2,CHUNK=6,AHEAD=7;
let clockT=0,clockCtx=0,cursorT=0,inflight=0,voices=new Set(),loopFrame=0,lastUi=0,lastSync=0;
const playTime=()=>clamp(clockT+(AC.currentTime-clockCtx)*rate,0,plan.duration);
function pause(){
 if(playing)playhead=playTime();
 playing=false;playToken++;stopAt=null;inflight=0;cancelAnimationFrame(loopFrame);
 for(const v of voices)try{v.stop();}catch{}
 voices.clear();
 $('play').textContent='▶ Play';
 for(const v of Object.values(videos))v.pause();
 $('import-video').pause();
}
async function play(){
 if(playing){pause();updateClock();requestRender();return;}
 if(playhead>=plan.duration-.01)movePlayhead(0,false);
 if(AC.state!=='running')await AC.resume();
 playing=true;const token=++playToken;$('play').textContent='❚❚ Pause';
 const first=chunkAt(playhead,FIRST);
 if(!first){pause();return;}
 let buffer;
 try{buffer=await fetchChunk(first);}catch(e){if(token===playToken){pause();report('Audio preview failed: '+e.message,true);}return;}
 if(token!==playToken)return;
 clockT=first.t;clockCtx=AC.currentTime+.03;cursorT=first.t+first.length;
 schedule(first,buffer);syncVideos(true);pump(token);
 loopFrame=requestAnimationFrame(()=>tick(token));
}
// One chunk: never crosses a clip boundary (its speed, gain and fades are constant).
function chunkAt(t,maxLen){
 const i=locate(t),s=segments[Math.max(0,i)];
 if(!s||t>=plan.duration-.001)return null;
 const length=Math.min(maxLen,plan.duration-t,s.target_end-t);
 if(length<=.0005)return null;
 const mode=$('audition').value,base={t,length,seg:s,first:Math.max(0,i)===0,last:Math.max(0,i)===segments.length-1};
 if(mode==='output'&&s.kind==='media')
  return s.media_stream==null?{...base,track:'silence',start:0,speed:1}:{...base,track:'media',start:Number(s.media_start||0)+t-s.target_start,speed:1,media:s.media};
 const track=mode==='output'?(s.kind==='audio'?'source':'target'):mode;
 const start=track==='source'?mapSource(t):mapTarget(t);
 // Nothing to hear on that track here (source not used, imported clip): silence keeps time.
 if(start==null)return {...base,track:'silence',start:0,speed:1};
 return {...base,track,start,speed:track==='source'&&s.kind==='audio'?s.speed:1};
}
// 40 ms extra per chunk: decoders return slightly less than asked, and each
// chunk is stopped exactly where the next begins, so they always meet.
const OVERLAP=.04;
async function fetchChunk(c){
 const bytes=c.track==='silence'?await window.alignment.audio('silence',0,c.length/rate+OVERLAP,1):
  // Output seconds at the preview speed; the main process reads (that x speed) source seconds.
  await window.alignment.audio(c.track,c.start,c.length/rate+OVERLAP,c.speed*rate,c.media);
 const pcm=new Int16Array(bytes.buffer,bytes.byteOffset,Math.floor(bytes.byteLength/2)),n=Math.max(1,pcm.length>>1);
 const buffer=AC.createBuffer(2,n,48000),L=buffer.getChannelData(0),R=buffer.getChannelData(1);
 for(let k=0,j=0;k<n;k++,j+=2){L[k]=pcm[j]/32768;R[k]=pcm[j+1]/32768;}
 return buffer;
}
// Gain at output time t inside clip s: its gain, its fades, and 3 ms de-click ramps at joins.
function envelope(s,t,first,last){
 const g=Math.pow(10,Number(s.gain_db||0)/20);
 const fi=Math.max(Number(s.fade_in_ms||0)/1000,first?0:.003),fo=Math.max(Number(s.fade_out_ms||0)/1000,last?0:.003);
 let k=1;
 if(fi>0)k=Math.min(k,(t-s.target_start)/fi);
 if(fo>0)k=Math.min(k,(s.target_end-t)/fo);
 return g*clamp(k,0,1);
}
function schedule(c,buffer){
 const now=AC.currentTime,when=clockCtx+(c.t-clockT)/rate,end=c.t+c.length;
 if(when+buffer.duration<=now)return;                    // arrived too late: skip it
 const src=AC.createBufferSource(),gain=AC.createGain();
 src.buffer=buffer;src.connect(gain).connect(master);
 const s=c.seg,fi=Math.max(Number(s.fade_in_ms||0)/1000,.003),fo=Math.max(Number(s.fade_out_ms||0)/1000,.003);
 const points=[c.t,s.target_start+fi,s.target_end-fo,end].filter(p=>p>=c.t&&p<=end).sort((a,b)=>a-b);
 const at=p=>Math.max(now,when+(p-c.t)/rate);
 gain.gain.setValueAtTime(envelope(s,points[0],c.first,c.last),at(points[0]));
 for(const p of points.slice(1))gain.gain.linearRampToValueAtTime(envelope(s,p,c.first,c.last),at(p));
 src.start(Math.max(now,when),Math.max(0,now-when));
 src.stop(Math.max(now,when+c.length/rate));
 voices.add(src);src.onended=()=>{voices.delete(src);src.disconnect();gain.disconnect();};
}
function pump(token){
 while(playing&&token===playToken&&inflight<2&&cursorT<plan.duration-.001&&cursorT<playTime()+AHEAD){
  const c=chunkAt(cursorT,CHUNK);if(!c)break;
  cursorT=c.t+c.length;inflight++;
  fetchChunk(c).then(b=>{if(token!==playToken)return;inflight--;schedule(c,b);pump(token);},
   e=>{if(token!==playToken)return;inflight--;report('Audio preview: '+e.message,true);pump(token);});
 }
}
function loopRange(){
 if(inMark!=null&&outMark!=null&&Math.abs(outMark-inMark)>.05)return [Math.min(inMark,outMark),Math.max(inMark,outMark)];
 const s=current();return s?[s.target_start,s.target_end]:[0,plan.duration];
}
function tick(token){
 if(token!==playToken||!playing)return;
 const t=playTime();playhead=t;
 if(stopAt!=null&&t>=stopAt){const at=stopAt;pause();movePlayhead(at,false);return;}
 if(loop&&t>=loopRange()[1]-.005){const at=loopRange()[0];pause();movePlayhead(at,false);play();return;}
 if(t>=plan.duration-.002){pause();movePlayhead(plan.duration,false);return;}
 if(playhead>scroll+view*.92||playhead<scroll)setScroll(playhead-view*.1);
 const now=performance.now();
 if(now-lastUi>100){lastUi=now;updateClock();updateCurrentIssue();refreshSelectionOnly();}
 if(now-lastSync>150){lastSync=now;syncVideos();}
 requestRender();pump(token);
 loopFrame=requestAnimationFrame(()=>tick(token));
}
// Play the marked In/Out range once (Shift+Space).
function playRange(){
 if(inMark==null||outMark==null){report('Mark In and Out first (I / O).',true);return;}
 pause();movePlayhead(Math.min(inMark,outMark));stopAt=Math.max(inMark,outMark);play();
}
function setListen(value){
 $('audition').value=value;
 document.querySelectorAll('[data-listen]').forEach(b=>{const on=b.dataset.listen===value;b.classList.toggle('on',on);b.setAttribute('aria-checked',String(on));});
 if(playing){pause();play();}
}
document.querySelectorAll('[data-listen]').forEach(b=>b.onclick=()=>setListen(b.dataset.listen));
function toggleAB(){setListen($('audition').value==='target'?'output':'target');report('Listening to '+($('audition').value==='target'?'the target\'s own audio':'the edited output')+'.');}

// ---------- edits ----------
function bound(index,time){
 if(index<=0||index>=segments.length)return false;
 const left=segments[index-1],right=segments[index];
 const value=clamp(time,left.target_start+.05,right.target_end-.05);
 if(right.kind==='audio')right.source_start+=(value-right.target_start)*right.speed;
 left.target_end=value;right.target_start=value;
 return true;
}
function offset(delta){
 if(locked('MIX'))return;
 const s=current();if(!s||s.kind!=='audio')return;
 const value=s.source_start+delta;
 if(value<0){report('Cannot shift source before zero.',true);return;}
 saveHistory();s.source_start=value;refresh();
 report('Audio of clip '+(selected+1)+' moved '+(delta>0?'later':'earlier')+' by '+Math.abs(delta*1000).toFixed(0)+' ms. Listen across the join to check.');
}
function select(index){
 selected=clamp(index,0,segments.length-1);refresh();
}
function change(){
 if(locked('MIX'))return;
 const s=current();if(!s)return;
 const start=Number($('region-start').value),end=Number($('region-end').value),
 src=Number($('region-source').value),sp=Number($('region-speed').value);
 if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end>plan.duration||start>=end){report('Invalid clip boundaries.',true);return;}
 if(s.kind==='audio'&&(!Number.isFinite(src)||src<0||!Number.isFinite(sp)||sp<.5||sp>2)){report('Invalid source position or speed.',true);return;}
 const before=clone(segments);
 if(selected>0)bound(selected,start);else if(Math.abs(start)>.001){report('The first clip must start at zero.',true);return;}
 if(selected<segments.length-1)bound(selected+1,end);else if(Math.abs(end-plan.duration)>.001){segments=before;report('The last clip must end at the output duration.',true);return;}
 if(s.kind==='audio'){s.source_start=src;s.speed=sp;}
 if(segments.some(x=>x.target_end-x.target_start<.05||x.source_start<0)){segments=before;report('Clip too short or source position negative.',true);return;}
 undo.push({...snapshot(),segments:before});redo=[];touched();refresh();report('Clip updated.');
}
// Clip gain (dB) and fade in/out (ms): heard in the preview and applied at export.
function applyVolume(){
 if(locked('MIX'))return;
 const s=current();if(!s)return;
 const g=Number($('clip-gain').value),fi=Number($('fade-in').value),fo=Number($('fade-out').value),len=(s.target_end-s.target_start)*1000;
 if(!Number.isFinite(g)||g<-60||g>24){report('Gain must be between −60 and +24 dB.',true);return;}
 if(![fi,fo].every(x=>Number.isFinite(x)&&x>=0)||fi+fo>len){report('Fades must be positive and fit inside the clip ('+Math.round(len)+' ms).',true);return;}
 saveHistory();
 for(const [k,v] of [['gain_db',g],['fade_in_ms',fi],['fade_out_ms',fo]])if(v)s[k]=v;else delete s[k];
 refresh();report('Clip '+(selected+1)+': '+(g?(g>0?'+':'')+g.toFixed(1)+' dB':'unity gain')+(fi?', fade in '+fi+' ms':'')+(fo?', fade out '+fo+' ms':'')+'.');
}
function split(){
 if(locked('MIX'))return;
 // The clip under the playhead (the selection may be another clip).
 const at=locate(playhead);if(at>=0&&at!==selected)select(at);
 const s=current();if(!s)return;
 if(playhead<=s.target_start+.05||playhead>=s.target_end-.05){report('The playhead is on a join: move it into a clip to split it.',true);return;}
 saveHistory();const right={...s,target_start:playhead};
 if(right.kind==='audio')right.source_start=s.source_start+(playhead-s.target_start)*s.speed;
 s.target_end=playhead;segments.splice(selected+1,0,right);selected++;refresh();report('Clip split at '+trimTime(playhead)+'.');
}
function join(){
 if(locked('MIX'))return;
 if(selected<=0)return;
 saveHistory();const s=segments[selected-1];
 // Joining deliberately uses the left clip's mapping across the removed boundary.
 s.target_end=segments[selected].target_end;segments.splice(selected,1);selected--;refresh();report('Joined clips. Listen across the join.');
}
function mode(kind){
 if(locked('MIX'))return;
 const s=current();if(!s||s.kind===kind)return;saveHistory();
 if(kind==='audio'){
  const prev=segments.slice(0,selected).reverse().find(x=>x.kind==='audio');
  s.kind='audio';s.speed=prev?.speed||1;
  s.source_start=Math.max(0,prev?prev.source_start+(s.target_start-prev.target_start)*prev.speed:s.target_start);
 }else{
  s.kind='reference';delete s.source_start;delete s.speed;
 }
 for(const key of ['media','media_start','media_stream','label'])delete s[key];
 refresh();report(kind==='audio'?'Using source audio; adjust its start and listen.':'Using the target\'s own audio for this clip.');}
// The timeline uses familiar non-linear-editor gestures. The picture is locked:
// moving or trimming audio never changes target-video timestamps.
function timelineRow(y){
 layoutRows();
 return rowTops.findIndex(top=>y>=top&&y<top+rowH);
}
function magnetic(time,exclude=[],enabled=snapEnabled){
 const value=clamp(time,0,plan.duration);
 if(!enabled)return {time:value,guide:null};
 const snapPoints=[0,plan.duration,playhead,...segments.flatMap(s=>[s.target_start,s.target_end])];
 let best=value,distance=9;
 for(const point of snapPoints){
  if(!Number.isFinite(point)||exclude.some(skip=>Math.abs(skip-point)<.001))continue;
  const pixels=Math.abs(value-point)*range().scale;
  if(pixels<distance){distance=pixels;best=point;}
 }
 return {time:best,guide:Math.abs(best-value)>.00001?best:null};
}
function setTool(name){
 if(!['select','razor','slip'].includes(name))return;
 tool=name;
 document.querySelectorAll('[data-tool]').forEach(b=>{
  const active=b.dataset.tool===name;
  b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));
 });
 canvas.style.cursor=name==='razor'?'crosshair':name==='slip'?'ew-resize':'default';
 report(name==='razor'?'Razor: click any audio clip to cut it.':name==='slip'?'Slip: drag source audio to move it inside its clip.':'Select: drag a clip to move it; drag its edges to trim.');
}
document.querySelectorAll('[data-tool]').forEach(b=>b.onclick=()=>setTool(b.dataset.tool));
$('snap-toggle').onclick=()=>{
 snapEnabled=!snapEnabled;
 $('snap-toggle').setAttribute('aria-pressed',String(snapEnabled));
 $('snap-toggle').innerHTML=snapEnabled?'◈ Snap: On <kbd>N</kbd>':'◇ Snap: Off <kbd>N</kbd>';
 report('Snapping '+(snapEnabled?'on':'off')+'. Hold Shift while dragging to override.');
};
function applyEdit(result,index,time,message){
 if(!result||JSON.stringify(result)===JSON.stringify(segments))return;
 undo.push(clone(segments));if(undo.length>100)undo.shift();redo=[];
 segments=result;selected=clamp(index,0,segments.length-1);
 if(Number.isFinite(time))playhead=clamp(time,0,plan.duration);
 inMark=null;outMark=null;refreshMarkLabels();
 touched();refresh();updateClock();scheduleFineWaveforms();
 report(message);
}
async function doRazor(index,time){
 const clip=segments[index];if(!clip||locked('MIX'))return;
 try{
  const result=await clipEdit('razor',{segments,index,at:time});
  applyEdit(result,index+1,time,'Razor cut at '+trimTime(time)+'. Ctrl+Z to undo.');
 }catch(err){report('Cannot cut here: '+err.message,true);}
}
function onDown(e){
 if(!plan||e.button!==0)return;
 pause();canvas.focus();
 const bounds=canvas.getBoundingClientRect(),x=e.clientX-bounds.left,y=e.clientY-bounds.top;
 const time=tFor(x),row=timelineRow(y);
 if(x<range().left&&row>=0){                       // track header buttons
  for(const b of headerButtons(row,rowTops[row]))if(x>=b.x&&x<=b.x+b.w&&y>=b.y&&y<=b.y+b.h){headerAction(row,b.kind);return;}
  activeTrack=row>=4?trackOf(row):row===0?-1:activeTrack;draw();
  return;
 }
 if(row>=4){                                         // clips on a video track
  const k=trackOf(row),i=VT.clipAt({tracks:vtracks},k,time);
  activeTrack=k;selClip=i>=0?{k,i}:null;draw();movePlayhead(time,false);
  if(i<0)return;
  if(vtracks[k].locked){report('V'+(k+2)+' is locked. Click its 🔒 in the track header to unlock it.',true);return;}
  const c=vtracks[k].clips[i];
  if(tool==='razor'){applyTrackEdit(VT.splitClip(currentTimeline(),k,i,magnetic(time,[c.at,c.at+c.length],!e.shiftKey&&snapEnabled).time),'Split the V'+(k+2)+' clip.');return;}
  const edge=Math.min(9,Math.max(4,range().scale*.06));
  const mode=tool==='slip'?'vslip':Math.abs(x-xFor(c.at))<edge?'vstart':Math.abs(x-xFor(c.at+c.length))<edge?'vend':'vmove';
  drag={mode,k,index:i,row,initialX:x,anchorTime:time,origin:{...c},moved:false,at:c.at,delta:0,ghost:null};
  canvas.setPointerCapture(e.pointerId);
  report('V'+(k+2)+' clip '+(i+1)+' · '+trimTime(c.at)+'–'+trimTime(c.at+c.length)+'. Drag to move, drag an edge to trim, Razor (C) splits, Slip (Y) changes its footage, Delete removes it.');
  return;
 }
 if(row===0)activeTrack=-1;
 if(y<RULER||row===0){
  drag={mode:'scrub'};movePlayhead(time);
  canvas.setPointerCapture(e.pointerId);return;
 }
 if(row<1)return;
 const index=locate(time),clip=segments[index];
 if(index<0||!clip)return;
 if(row===1&&clip.kind!=='audio'||row===2&&clip.kind==='audio'){
  // Clicking a gap moves the playhead; guide tracks have no invisible clips.
  movePlayhead(time);return;
 }
 if(tool==='razor'){
  const point=magnetic(time,[clip.target_start,clip.target_end],!e.shiftKey&&snapEnabled);
  doRazor(index,point.time);return;
 }
 select(index);
 movePlayhead(time,false);
 let mode='move';
 const edge=Math.min(9,Math.max(4,range().scale*.06));
 if(row===3&&tool==='select'&&Math.abs(x-xFor(clip.target_start))<edge)mode='trim-start';
 else if(row===3&&tool==='select'&&Math.abs(x-xFor(clip.target_end))<edge)mode='trim-end';
 else if(tool==='slip')mode='slip';
 if(mode==='slip'&&clip.kind!=='audio'){report('Slip works on source-audio clips only.',true);return;}
 drag={mode,index,row,initialX:x,anchorTime:time,sourceStart:clip.source_start,
  originalStart:clip.target_start,originalEnd:clip.target_end,
  original:clone(segments),copy:row!==3||e.altKey&&mode==='move',
  moved:false,at:clip.target_start,delta:0,ghost:null};
 canvas.setPointerCapture(e.pointerId);
}
function onMove(e){
 if(!plan)return;
 const b=canvas.getBoundingClientRect(),x=e.clientX-b.left,y=e.clientY-b.top,time=tFor(x);
 if(!drag){
  if(tool==='razor'){canvas.style.cursor='crosshair';return;}
  const row=timelineRow(y),index=locate(time),s=segments[index];
  canvas.style.cursor=y<RULER||row===0?'text':tool==='slip'?'ew-resize':
   row===3&&s&&[s.target_start,s.target_end].some(t=>Math.abs(x-xFor(t))<8)?'ew-resize':
   row>0&&s?'grab':'default';
  return;
 }
 if(drag.mode==='scrub'){movePlayhead(time);return;}
 const dt=(x-drag.initialX)/range().scale;
 if(Math.abs(x-drag.initialX)<3)return;
 drag.moved=true;
 if(drag.mode.startsWith('v')&&drag.k!==undefined){
  const o=drag.origin,end=o.at+o.length,row=drag.row;
  if(drag.mode==='vslip'){drag.delta=dt;drag.ghost={start:o.at,end,snap:null,row};report('Slip: footage '+(dt>=0?'+':'')+dt.toFixed(3)+' s');}
  else if(drag.mode==='vmove'){const snap=magnetic(clamp(o.at+dt,0,plan.duration-o.length),[o.at,end],!e.shiftKey&&snapEnabled);drag.at=clamp(snap.time,0,plan.duration-o.length);drag.ghost={start:drag.at,end:drag.at+o.length,snap:snap.guide,row};}
  else{const snap=magnetic(time,[o.at,end],!e.shiftKey&&snapEnabled);drag.at=snap.time;
   drag.ghost={start:drag.mode==='vstart'?Math.min(drag.at,end-.04):o.at,end:drag.mode==='vend'?Math.max(drag.at,o.at+.04):end,snap:snap.guide,row};}
  requestRender();return;
 }
 const original=drag.original[drag.index];
 if(drag.mode==='move'){
  const duration=original.target_end-original.target_start;
  const raw=clamp(drag.originalStart+dt,0,Math.max(0,plan.duration-duration));
  const snap=magnetic(raw,[drag.originalStart,drag.originalEnd],!e.shiftKey&&snapEnabled);
  drag.at=clamp(snap.time,0,Math.max(0,plan.duration-duration));
  drag.ghost={start:drag.at,end:drag.at+duration,snap:snap.guide};
 }else if(drag.mode==='slip'){
  drag.delta=dt*original.speed;
  drag.ghost={start:original.target_start,end:original.target_end,snap:null};
  report('Slip: '+(drag.delta>=0?'+':'')+(drag.delta*1000).toFixed(0)+' ms');
 }else{
  const edge=drag.mode==='trim-start'?'start':'end';
  const lo=edge==='start'?0:original.target_start+.05;
  const hi=edge==='start'?original.target_end-.05:plan.duration;
  const raw=clamp(time,lo,hi);
  const snapped=magnetic(raw,[original.target_start,original.target_end],!e.shiftKey&&snapEnabled);
  drag.at=clamp(snapped.time,lo,hi);
  drag.ghost={start:edge==='start'?drag.at:original.target_start,
   end:edge==='end'?drag.at:original.target_end,snap:snapped.guide};
 }
 requestRender();
}
async function onUp(e){
 if(!drag)return;
 const action=drag;drag=null;draw();
 if(action.mode==='scrub'||!action.moved)return;
 if(action.k!==undefined){finishTrackDrag(action);return;}
 if(locked('MIX'))return;
 const b=canvas.getBoundingClientRect(),row=timelineRow(e.clientY-b.top);
 if(action.mode==='move'&&action.row!==3&&row!==3){
  report('Drag a clip from A1 or A2 down to MIX to place it into the edited output.');return;
 }
 try{
  let op,payload={segments,index:action.index},note;
  if(action.mode==='move'){
   op='move';payload={...payload,at:action.at,copy:action.copy};
   note=(action.copy?'Copied':'Moved')+' clip to '+trimTime(action.at)+'. The picture is unchanged.';
  }else if(action.mode==='slip'){
   op='slip';payload={...payload,delta:action.delta};
   const s=action.original[action.index];
   if(waves.source&&s.source_start+action.delta+(s.target_end-s.target_start)*s.speed>waves.source.duration+.02)
    throw Error('The source clip would run past the end of its audio.');
   note='Moved source audio '+(action.delta>=0?'later':'earlier')+' by '+Math.abs(action.delta*1000).toFixed(0)+' ms (Slip).';
  }else{
   op='edge';payload={...payload,edge:action.mode==='trim-start'?'start':'end',at:action.at};
   note='Trimmed clip '+payload.edge+' to '+trimTime(action.at)+'. The freed range uses target audio.';
  }
  const result=await clipEdit(op,payload);
  const newIndex=result.findIndex((clip,i)=>clip.target_start<=action.at+.001&&(clip.target_end>action.at+.001||i===result.length-1));
  applyEdit(result,Math.max(0,newIndex),action.at,note);
 }catch(err){report('Timeline edit rejected: '+err.message,true);}
}
canvas.addEventListener('pointerdown',onDown);
canvas.addEventListener('pointermove',onMove);
canvas.addEventListener('pointerup',onUp);
canvas.addEventListener('pointercancel',()=>{drag=null;draw();});
canvas.addEventListener('lostpointercapture',()=>{if(drag){drag=null;draw();}});
canvas.addEventListener('dblclick',e=>{if(tool!=='razor')movePlayhead(tFor(e.clientX-canvas.getBoundingClientRect().left));});
canvas.addEventListener('wheel',e=>{
 if(!plan)return;e.preventDefault();
 const x=e.clientX-canvas.getBoundingClientRect().left;
 if(e.ctrlKey||e.metaKey)zoomTo(view*Math.pow(1.0015,e.deltaY),tFor(x),x);
 else setScroll(scroll+(e.deltaX||e.deltaY)*view/900);
},{passive:false});
// Overview strip: click or drag to move the visible window.
let overviewDrag=false;
function overviewSeek(e){
 const b=overview.getBoundingClientRect(),t=clamp((e.clientX-b.left)/b.width,0,1)*plan.duration;
 setScroll(t-view/2);
}
overview.addEventListener('pointerdown',e=>{if(!plan)return;overviewDrag=true;overview.setPointerCapture(e.pointerId);overviewSeek(e);});
overview.addEventListener('pointermove',e=>{if(overviewDrag)overviewSeek(e);});
overview.addEventListener('pointerup',()=>{overviewDrag=false;});
overview.addEventListener('dblclick',e=>{const b=overview.getBoundingClientRect();movePlayhead(clamp((e.clientX-b.left)/b.width,0,1)*plan.duration);});
$('zoom').oninput=resetZoom;
$('back').onclick=()=>step(-1);$('forward').onclick=()=>step(1);
$('back10').onclick=()=>step(-10);$('forward10').onclick=()=>step(10);
$('play').onclick=play;
$('rate').onchange=()=>{const was=playing;pause();rate=Number($('rate').value)||1;syncVideos(true);report('Playback speed '+rate+'×.');if(was)play();};
$('loop').onclick=()=>{loop=!loop;$('loop').setAttribute('aria-pressed',String(loop));$('loop').textContent=loop?'⟳ Loop: On':'⟳ Loop';
 report(loop?'Looping '+(inMark!=null&&outMark!=null?'the In/Out range.':'the selected clip.'):'Loop off.');};

// ---------- review list ----------
const issueKey=t=>(Math.round(t*100)/100).toFixed(2);
function buildIssues(){
 if(!plan)return;
 const items=[];
 {
  // Censored / re-edited dub: scenes the dub removed (each restore or cut) and dub-only material.
  // Found edits are listed even without the censored-dub option (then they cannot be cut).
  const outer=(s,i)=>!!s.picture_outer||(i===0&&s.target_start<=1e-3)||(i===segments.length-1&&Math.abs(s.target_end-plan.duration)<=1e-3);
  segments.forEach((s,i)=>{
   const len=s.target_end-s.target_start;
   if(!plan.censorship&&s.kind==='reference'&&s.verified_insert&&!outer(s,i)){
    items.push({t:s.target_start,end:s.target_end,kind:'dubonly',removed:true,label:'Only in the original',
     reason:'This '+len.toFixed(1)+' s scene is only in the original (the dub removed it). It keeps the original picture and audio.',confidence:''});
    return;
   }
   if(!['restore','cut'].includes(s.censored_action)||s.censored_outer)return;
   items.push({t:s.target_start,end:s.target_end,segment:i,kind:'censor',label:s.censored_action==='cut'?'Removed · cut':'Removed · restored',
    reason:'The dub removed this '+len.toFixed(1)+' s scene. '+(s.censored_action==='cut'?'It is cut from the exported video.':'It keeps the original picture and audio.'),confidence:''});
  });
  const rebuild=!!plan.censorship?.recreate;
  let prev=null;
  segments.forEach(s=>{
   if(s.kind!=='audio')return;
   if(prev){
    const skip=s.source_start-(prev.source_start+(prev.target_end-prev.target_start)*prev.speed);
    const rebuilt=rebuild&&s.dub_pictures&&Math.abs(skip-s.dub_pictures.source_length)<.05;
    if(skip>.25)items.push({t:s.target_start,kind:'dubonly',label:rebuilt?'Dub-only · rebuilt':'Dub-only material',
     reason:rebuilt?'The dub shows '+skip.toFixed(1)+' s of frozen or repeated footage here; it is rebuilt from the original\'s frames and the dub audio is kept.':
      'The dub has '+skip.toFixed(1)+' s of footage the original lacks (re-cut or extended scene); its audio is skipped here.',confidence:''});
   }
   for(const x of s.dub_replaced||[]){
    const t=s.target_start+(x.source-s.source_start)/s.speed;
    items.push({t,end:t+x.length,kind:'dubonly',label:rebuild?'Replaced shot · rebuilt':'Replaced shot',
     reason:'The dub shows another shot here for '+Number(x.length).toFixed(1)+' s'+(rebuild?'; the exported video shows it too, rebuilt from the original\'s frames.':'.'),confidence:''});
   }
   for(const x of s.dub_own||[]){
    const t=s.target_start+(x.source-s.source_start)/s.speed,len=Number(x.length).toFixed(1);
    items.push({t,end:t+x.length,kind:'dubonly',label:'Replaced shot',
     reason:x.elsewhere!=null?'The dub shows a shot from '+shortTime(x.elsewhere)+' of the original here for '+len+' s; the original shot is kept.':
      'The dub shows its own footage here for '+len+' s (not in the original); the original shot is kept.',confidence:''});
   }
   prev=s;
  });
 }
 for(const m of markers)items.push({t:m,kind:'marker',label:'Marker',reason:'Your marker (K adds or removes one at the playhead).',confidence:''});
 for(const r of plan.review||[]){
  const t=Number(r.splice??((Number(r.start)+Number(r.end))/2));
  if(!Number.isFinite(t)||t<0||t>plan.duration)continue;
  const flagged=r.confidence!=='supported'&&r.confidence!=='manual'||/\b(uncertain|review|fallback|rewind)/i.test(r.reason||'');
  const insert=/target-only|insert|target audio used/i.test(r.reason||'');
  if(plan.censorship&&items.some(x=>x.kind==='censor'&&Math.abs(x.t-t)<.06))continue;
  if(insert&&items.some(x=>x.removed&&t>=x.t-.06&&t<=x.end+.06))continue;   // listed as "Only in the original"
  items.push({t,kind:flagged?'flag':insert?'insert':'join',label:flagged?'Needs review':insert?'Target footage':'Join',reason:r.reason||'',confidence:r.confidence||''});
 }
 for(const s of segments.slice(1)){
  if(items.some(x=>Math.abs(x.t-s.target_start)<.06))continue;
  items.push({t:s.target_start,kind:'join',label:'Clip boundary',reason:'Edited or computed join between clips.',confidence:''});
 }
 // One item per moment; a dub edit wins over a join or flag at the same frame.
 const rank=x=>['censor','dubonly'].includes(x.kind)?0:1;
 items.forEach(x=>{x.key=issueKey(x.t);});
 items.sort((a,b)=>a.key===b.key?rank(a)-rank(b):a.t-b.t);
 const seen=new Set();
 issueItems=items.filter(x=>{x.key=issueKey(x.t);if(seen.has(x.key))return false;seen.add(x.key);return true;});
 renderIssues();
}
function visibleIssues(){
 return issueItems.filter(x=>issueFilter==='all'||(issueFilter==='flagged'?x.kind==='flag':issueFilter==='censor'?['censor','dubonly'].includes(x.kind):issueFilter==='markers'?x.kind==='marker':!reviewed.has(x.key)));
}
// Markers: K toggles one at the playhead (snapped to a frame); saved with the plan.
function toggleMarker(){
 const t=Math.round(playhead/frame)*frame,i=markers.findIndex(m=>Math.abs(m-t)<frame/2);
 if(i>=0)markers.splice(i,1);else{markers.push(t);markers.sort((a,b)=>a-b);}
 edited=true;saved=false;autosave();setButtons();buildIssues();draw();
 report(i>=0?'Marker removed.':'Marker added at '+trimTime(t)+'. Type a note for it in the inspector.');
}
function renderIssues(){
 const list=$('issue-list');list.textContent='';
 const shown=visibleIssues();
 if(!shown.length){const li=document.createElement('li');li.className='empty';li.textContent=issueFilter==='open'?'Everything here is checked.':'Nothing to show.';list.appendChild(li);}
 for(const item of shown){
  const li=document.createElement('li');
  li.className=item.kind+(reviewed.has(item.key)?' done':'')+(notes[item.key]?' has-note':'')+(currentIssue?.key===item.key?' current':'');
  li.dataset.key=item.key;li.tabIndex=-1;
  const dot=document.createElement('span');dot.className='dot';
  const time=document.createElement('span');time.className='time';time.textContent=trimTime(item.t);
  const kind=document.createElement('span');kind.className='kind';kind.textContent=item.label;
  const why=document.createElement('span');why.className='why';why.textContent=notes[item.key]?('✎ '+notes[item.key]):item.reason;why.title=item.reason;
  li.append(dot,time,kind,why);
  li.onclick=()=>goToIssue(item);
  list.appendChild(li);
 }
 const flagged=issueItems.filter(x=>x.kind==='flag'),openFlags=flagged.filter(x=>!reviewed.has(x.key)).length;
 const done=issueItems.filter(x=>reviewed.has(x.key)).length;
 $('review-count').textContent=done+' / '+issueItems.length+' checked';
 $('review-bar').firstElementChild.style.width=(issueItems.length?100*done/issueItems.length:0)+'%';
 const chip=$('issues-chip');
 chip.className='chip '+(openFlags?'warn':'ok');
 chip.textContent=openFlags?openFlags+' flagged to check':flagged.length?'All flagged points checked':issueItems.length+' joins';
}
function updateCurrentIssue(force=false){
 const inside=issueItems.find(x=>x.kind==='censor'&&playhead>=x.t-1e-3&&playhead<x.end);
 const near=issueItems.reduce((best,x)=>Math.abs(x.t-playhead)<Math.abs((best?.t??1e9)-playhead)?x:best,null);
 const now=inside||(near&&Math.abs(near.t-playhead)<=Math.max(.25,2*frame)?near:null);
 if(!force&&now?.key===currentIssue?.key&&now?.label===currentIssue?.label)return;
 currentIssue=now;
 document.querySelectorAll('#issue-list li').forEach(li=>li.classList.toggle('current',li.dataset.key===now?.key));
 const note=$('issue-note');
  const scene=now?.kind==='censor'?segments[now.segment]:null;
 $('censor-actions').hidden=!scene;
 if(scene){$('censor-restore').classList.toggle('on',scene.censored_action==='restore');$('censor-cut').classList.toggle('on',scene.censored_action==='cut');}
 if(!now){$('issue-detail').textContent='No review point at the playhead. Use J / L or click the list.';note.value='';note.disabled=true;return;}
 $('issue-detail').textContent=now.label+' at '+trimTime(now.t)+(now.confidence?' ('+now.confidence+')':'')+'. '+now.reason;
 note.disabled=false;note.value=notes[now.key]||'';
 document.querySelector('#issue-list li.current')?.scrollIntoView({block:'nearest'});
}
function goToIssue(item){
 pause();
 const i=locate(Math.max(0,Math.min(plan.duration-.001,item.t)));
 if(i>=0)select(i);
 movePlayhead(item.t);
 if(item.t<scroll+view*.15||item.t>scroll+view*.85)setScroll(item.t-view/2);
 report(item.label+' at '+trimTime(item.t)+'. Press P to play across it, A to compare with the target audio, R when checked.');
}
function jumpReview(direction){
 const all=visibleIssues();
 if(!all.length){report('No review points in this list.');return;}
 const next=direction>0?all.find(x=>x.t>playhead+.05):all.slice().reverse().find(x=>x.t<playhead-.05);
 goToIssue(next??(direction>0?all[0]:all[all.length-1]));
}
function markReviewed(){
 if(!currentIssue){report('Move to a review point first (J / L or click the list).',true);return;}
 const key=currentIssue.key;
 if(reviewed.has(key))reviewed.delete(key);else reviewed.add(key);
 autosave();renderIssues();draw();
 report(reviewed.has(key)?'Marked as checked.':'Marked as not checked.');
 if(reviewed.has(key)&&issueFilter!=='all')setTimeout(()=>jumpReview(1),120);
}
document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{
 issueFilter=b.dataset.filter;
 document.querySelectorAll('[data-filter]').forEach(x=>{const on=x===b;x.classList.toggle('on',on);x.setAttribute('aria-checked',String(on));});
 renderIssues();
});
$('issue-note').oninput=()=>{if(!currentIssue)return;const v=$('issue-note').value.trim();if(v)notes[currentIssue.key]=v;else delete notes[currentIssue.key];autosave();};
$('issue-note').onchange=renderIssues;
// Restore or cut the censored scene at the playhead (undoable; saved into the plan).
function censorAction(action){
 const item=currentIssue;if(item?.kind!=='censor')return;
 const s=segments[item.segment];if(!s||s.censored_action===action)return;
 saveHistory();s.censored_action=action;
 setTimeout(()=>updateCurrentIssue(true),0);
 report(action==='cut'?'This scene will be cut from the exported video, as in the dub.':'This scene keeps the original picture and audio.');
}
$('censor-restore').onclick=()=>censorAction('restore');$('censor-cut').onclick=()=>censorAction('cut');
$('previous-issue').onclick=()=>jumpReview(-1);
$('next-issue').onclick=()=>jumpReview(1);
$('mark-reviewed').onclick=markReviewed;
function focusRegion(){
 const s=current();if(!s||!plan)return;
 pause();
 const [a,b]=inMark!=null&&outMark!=null?[Math.min(inMark,outMark),Math.max(inMark,outMark)]:[s.target_start,s.target_end];
 zoomTo(Math.max(2,Math.min(plan.duration,(b-a)+4)));
 setScroll(a-2);
}
$('jump-opening').onclick=()=>{pause();movePlayhead(0);select(0);setScroll(0);report('At the start: check that the opening music and picture were kept.');};
$('zoom-region').onclick=focusRegion;
$('zoom-all').onclick=()=>{zoomTo(plan.duration);setScroll(0);};
function playAcrossJoin(){
 if(!plan)return;
 const s=current();if(!s)return;
 // The review point at the playhead, else the join nearest the playhead.
 const joins=segments.slice(1).map(x=>x.target_start);
 const t=currentIssue?.t??(joins.length?joins.reduce((a,b)=>Math.abs(b-playhead)<Math.abs(a-playhead)?b:a):s.target_start);
 pause();movePlayhead(Math.max(0,t-2));stopAt=Math.min(plan.duration,t+2);
 play();
 report('Playing 2 s either side of '+trimTime(t)+'. Press A to compare with the target audio.');
}
$('play-join').onclick=playAcrossJoin;
$('ab-audio').onclick=toggleAB;

// ---------- clipboard ----------
function refreshMarkLabels(){
 const inText=inMark==null?'In —':'In '+trimTime(inMark);
 const outText=outMark==null?'Out —':'Out '+trimTime(outMark);
 $('clip-range').textContent=inText+' · '+outText;
 $('clipboard-status').textContent=clipboard?'Copied '+clipboard.duration.toFixed(3)+' s':'Clipboard empty';
 $('paste-clip').disabled=!clipboard||exporting;
 requestRender();
}
// In/Out can span clips: picture edits, loops and range playback use them.
function markPoint(side){
 if(side==='in')inMark=playhead;else outMark=playhead;
 refreshMarkLabels();
}
async function copySelected(){
 if(exporting)return;
 const seg=current();if(!seg)return;
 try{
  // Copy works inside one clip: the marked range is limited to the selected clip.
  const from=clamp(inMark===null?seg.target_start:Math.min(inMark,outMark??inMark),seg.target_start,seg.target_end);
  const to=clamp(outMark===null?seg.target_end:Math.max(outMark,inMark??outMark),seg.target_start,seg.target_end);
  if(to-from<.02){report('The marked range does not overlap the selected clip.',true);return;}
  clipboard=await clipEdit('copy',{segments,index:selected,inPoint:from,outPoint:to});
  refreshMarkLabels();
  report('Copied '+clipboard.duration.toFixed(3)+' s. Move the playhead and Paste to overwrite only the audio.');
 }catch(e){report('Copy failed: '+e.message,true);}
}
async function pasteSelected(){
 if(exporting||!clipboard||locked('MIX'))return;
 try{
  const result=await clipEdit('paste',{segments,at:playhead,clip:clipboard});
  pause();saveHistory();segments=result;
  selected=clamp(locate(playhead+.001),0,segments.length-1);
  refresh();
  report('Pasted '+clipboard.duration.toFixed(3)+' s without moving the picture. Undo: Ctrl+Z.');
 }catch(e){report('Paste failed: '+e.message,true);}
}
async function trimSelected(which){
 if(exporting||locked('MIX'))return;
 // Trim the clip under the playhead (the selection may be another clip).
 const at=locate(playhead);if(at>=0&&at!==selected)select(at);
 try{
  const result=await clipEdit(which==='left'?'trim-left':'trim-right',{
   segments,index:selected,at:playhead
  });
  pause();saveHistory();segments=result;
  selected=clamp(locate(which==='left'?playhead+.001:playhead-.001),0,segments.length-1);
  refresh();
  report('Trimmed '+(which==='left'?'start':'end')+' to the playhead. The freed range uses target audio; the picture is unchanged.');
 }catch(e){report('Trim failed: '+e.message,true);}
}
async function cutSelected(){
 if(exporting||locked('MIX'))return;
 const seg=current();if(!seg)return;
 try{
  const captured=await clipEdit('copy',{segments,index:selected,
   inPoint:seg.target_start,outPoint:seg.target_end});
  const result=await clipEdit('paste',{
   segments,at:seg.target_start,clip:{kind:'reference',duration:seg.target_end-seg.target_start}
  });
  pause();saveHistory();segments=result;clipboard=captured;
  refreshMarkLabels();refresh();
  report('Cut the audio to the clipboard. The freed range uses target audio (nothing shifts).');
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
$('nudge-left').onclick=()=>offset(-.01);$('nudge-right').onclick=()=>offset(.01);
$('nudge-frame-left').onclick=()=>offset(-frame);$('nudge-frame-right').onclick=()=>offset(frame);
$('undo').onclick=()=>restore(undo,redo);$('redo').onclick=()=>restore(redo,undo);
$('apply').onclick=change;$('split').onclick=split;$('join').onclick=join;
$('apply-volume').onclick=applyVolume;
for(const id of ['clip-gain','fade-in','fade-out'])$(id).addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();applyVolume();}});
for(const id of ['region-start','region-end','region-source','region-speed'])$(id).addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();change();}});
$('source-mode').onclick=()=>mode('audio');$('target-mode').onclick=()=>mode('reference');

// ---------- save / export ----------
async function saveAs(){
 pause();
 try{
  const v1=VT.baseKept(plan);
  const picture=plan.video_edits||hasTrackClips()?{duration:plan.duration,kept:VT.flatten(v1,vtracks),v1}:null;
  const location=await window.alignment.save(segments,picture,{markers,notes,videoTracks:vtracks,locks});if(!location){report('Save cancelled.');return;}
  saved=true;edited=false;store.set(autosaveKey(),{segments:null,reviewed:[...reviewed],notes,at:Date.now()});
  setButtons();report('Saved: '+location+'. Export writes the corrected output to that folder.');
 }catch(e){report('Save failed: '+e.message,true);}
}
$('save').onclick=saveAs;
function openLog(open=true){$('log-drawer').hidden=!open;$('toggle-log').setAttribute('aria-expanded',String(open));$('toggle-log').textContent=open?'Export log ▾':'Export log ▴';}
$('toggle-log').onclick=()=>openLog($('log-drawer').hidden);
$('close-log').onclick=()=>openLog(false);
$('export').onclick=async()=>{
 if(!saved){report('Save your edits before exporting.',true);return;}
 pause();exporting=true;setButtons();$('export-log').textContent='Exporting…\n';openLog(true);report('Exporting corrected audio and any required video edits…');
 try{await window.alignment.export();}catch(e){report('Export failed: '+e.message,true);}
 finally{exporting=false;setButtons();}
};
$('open-folder').onclick=()=>window.alignment.openFolder().catch(e=>report(e.message,true));
window.alignment.onEvent(({kind,payload})=>{
 if(kind==='export-log'){$('export-log').textContent+=payload;$('export-log').scrollTop=$('export-log').scrollHeight;}
 if(kind==='export-done'){if(payload.code===0){saved=false;setButtons();}report(payload.code===0?'Export finished: '+payload.folder+'. Save again to create another export.':'Export failed. See the export log.',payload.code!==0);}
});

// ---------- layout: views, panels, splitter ----------
const VIEW_HINTS={side:'Source left · target right',overlay:'Source at 50 % over the target',difference:'Matching pictures go dark. Edges that jump with motion mean the timing is off; steady outlines are framing differences',wipe:'Source left of the line · target right'};
function setView(name){
 const pics=$('pictures');
 pics.className='pictures '+(name==='side'?'side':'stack '+name);
 document.querySelectorAll('[data-view]').forEach(b=>{const on=b.dataset.view===name;b.classList.toggle('on',on);b.setAttribute('aria-checked',String(on));});
 $('wipe').hidden=name!=='wipe';$('view-hint').textContent=VIEW_HINTS[name];
 applyWipe();layoutCompare();store.set('autosync-editor-view',name);compareHint();
}
// Overlay, difference and wipe need both pictures on screen.
function compareHint(){
 const name=document.querySelector('[data-view].on')?.dataset.view||'side';
 const waiting=['source','target'].filter(t=>videoStatus[t]!=='ready');
 $('view-hint').textContent=name!=='side'&&waiting.length?'Waiting for the '+waiting.join(' and ')+' picture: '+($(waiting[0]+'-wait').textContent||'loading…'):VIEW_HINTS[name];
}
// Comparison views show both pictures cropped to the area the analysis matched
// (plan source_crop / target_crop, "w:h:x:y" in native pixels) and fitted to
// one box, so the same content lands on the same pixels.
let videoDims={};
function cropInset(track){
 const c=String(plan?.[track+'_crop']||'').split(':').map(Number),d=videoDims[track];
 if(c.length!==4||!c.every(Number.isFinite)||!d?.width||!d?.height)return {css:'',aspect:d?.width&&d?.height?d.width/d.height:null};
 const [w,h,x,y]=c;
 return {css:'inset('+[y/d.height,(d.width-x-w)/d.width,(d.height-y-h)/d.height,x/d.width].map(v=>(Math.max(0,v)*100).toFixed(3)+'%').join(' ')+')',aspect:w/h};
}
function layoutCompare(){
 const stack=$('pictures').classList.contains('stack');
 const target=cropInset('target'),source=cropInset('source');
 const aspect=target.aspect||source.aspect||16/9;
 const area=$('pictures').getBoundingClientRect();
 let bw=area.width,bh=bw/aspect;if(bh>area.height){bh=area.height;bw=bh*aspect;}
 for(const track of ['source','target']){
  const pic=document.querySelector('.viewer[data-track='+track+'] .picture');
  const inset=track==='source'?source.css:target.css;
  for(const el of [videos[track],$(track+'-frame')]){el.style.objectViewBox=stack?inset:'';el.style.objectFit=stack?'fill':'';}
  Object.assign(pic.style,stack?{position:'absolute',flex:'none',width:bw+'px',height:bh+'px',left:(area.width-bw)/2+'px',top:(area.height-bh)/2+'px'}:{position:'',flex:'',width:'',height:'',left:'',top:''});
 }
}
new ResizeObserver(()=>layoutCompare()).observe($('pictures'));
function applyWipe(){
 const src=document.querySelector('.viewer[data-track=source] .picture');
 src.style.clipPath=$('pictures').classList.contains('wipe')?'inset(0 '+(100-Number($('wipe').value))+'% 0 0)':'';
}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>setView(b.dataset.view));
$('wipe').oninput=applyWipe;
function setPanel(side,show){
 const ws=$('workspace');ws.classList.toggle(side==='left'?'no-left':'no-right',!show);
 $(side==='left'?'show-issues':'show-inspector').hidden=show;
 store.set('autosync-editor-'+side,show);requestAnimationFrame(draw);
}
$('collapse-issues').onclick=()=>setPanel('left',false);$('show-issues').onclick=()=>setPanel('left',true);
$('collapse-inspector').onclick=()=>setPanel('right',false);$('show-inspector').onclick=()=>setPanel('right',true);
// The timeline's height is a share of the window (at most half of it), so the
// pictures and the review list keep their room on a small screen and when the
// window is resized. Older versions saved pixels: those are converted once.
const TIMELINE_DEFAULT=.36,TIMELINE_MAX=.5;
function timelineShare(){
 const v=Number(store.get('autosync-editor-timeline'));
 if(v>0&&v<1)return v;
 return v>=1?clamp(v/window.innerHeight,.2,TIMELINE_MAX):TIMELINE_DEFAULT;
}
function setTimelineHeight(px,save=true){
 const h=clamp(px,150,Math.max(150,Math.round(window.innerHeight*TIMELINE_MAX)));
 document.documentElement.style.setProperty('--timeline-h',h+'px');
 if(save)store.set('autosync-editor-timeline',+(h/window.innerHeight).toFixed(4));
 requestAnimationFrame(draw);
}
window.addEventListener('resize',()=>setTimelineHeight(timelineShare()*window.innerHeight,false));
const splitter=$('splitter');
splitter.addEventListener('pointerdown',e=>{
 splitter.setPointerCapture(e.pointerId);splitter.classList.add('drag');
 const startY=e.clientY,startH=$('timeline-area').getBoundingClientRect().height;
 const move=ev=>setTimelineHeight(startH-(ev.clientY-startY));
 const up=()=>{splitter.classList.remove('drag');splitter.removeEventListener('pointermove',move);splitter.removeEventListener('pointerup',up);};
 splitter.addEventListener('pointermove',move);splitter.addEventListener('pointerup',up);
});
splitter.addEventListener('keydown',e=>{const h=$('timeline-area').getBoundingClientRect().height;if(e.key==='ArrowUp')setTimelineHeight(h+20);if(e.key==='ArrowDown')setTimelineHeight(h-20);});
$('help').onclick=()=>$('shortcuts').showModal();
new ResizeObserver(()=>draw()).observe($('timeline-wrap'));
new ResizeObserver(()=>draw()).observe(overview);

// ---------- keyboard ----------
window.addEventListener('keydown',e=>{
 if($('shortcuts').open)return;
 if(e.target.matches('input,select,textarea'))return;
 const k=e.key.toLowerCase(),mod=e.ctrlKey||e.metaKey,plain=!mod&&!e.altKey;
 const handled=()=>e.preventDefault();
 if(e.code==='Space'){handled();if(e.shiftKey)playRange();else play();return;}
 if(mod&&e.shiftKey&&k==='s'){handled();saveFrame();return;}
 if(mod&&k==='s'){handled();saveAs();return;}
 if(mod&&k==='z'){handled();restore(undo,redo);return;}
 if(mod&&k==='y'){handled();restore(redo,undo);return;}
 if(mod&&k==='c'){handled();copySelected();return;}
 if(mod&&k==='v'){handled();pasteSelected();return;}
 if(mod&&k==='i'){handled();importMedia();return;}
 if(e.key==='Delete'&&e.shiftKey&&!mod){handled();rippleDelete();return;}
 if((e.key==='Delete'||e.key==='Backspace')&&!mod&&selClip){handled();deleteClip();return;}
 if(k==='d'&&mod&&e.shiftKey){handled();duplicateTrack();return;}
 if(mod&&k==='x'){handled();cutSelected();return;}
 if(e.key==='?'){handled();$('shortcuts').showModal();return;}
 if(e.key===','){handled();offset(e.altKey?-.01:-frame);return;}
 if(e.key==='.'){handled();offset(e.altKey?.01:frame);return;}
 if(e.key==='ArrowLeft'){handled();step(e.shiftKey?-10:-1);return;}
 if(e.key==='ArrowRight'){handled();step(e.shiftKey?10:1);return;}
 if(e.key==='Home'){handled();pause();movePlayhead(0);return;}
 if(e.key==='End'){handled();pause();movePlayhead(plan.duration);return;}
 if(e.key==='Escape'){if(drag){drag=null;requestRender();report('Drag cancelled.');}else if(document.fullscreenElement)toggleFullscreen();else pause();return;}
 if(e.altKey&&e.key==='Enter'){handled();toggleFullscreen();return;}
 if(!plain)return;
 if(e.key==='+'||e.key==='='){handled();zoomTo(view/1.5);return;}
 if(e.key==='-'||e.key==='_'){handled();zoomTo(view*1.5);return;}
 const actions={v:()=>setTool('select'),c:()=>setTool('razor'),y:()=>setTool('slip'),n:()=>$('snap-toggle').click(),
  s:()=>{if(!splitTrackClip())split();},i:()=>markPoint('in'),o:()=>markPoint('out'),q:()=>trimSelected('left'),w:()=>trimSelected('right'),
  j:()=>jumpReview(-1),l:()=>jumpReview(1),a:toggleAB,r:markReviewed,p:playAcrossJoin,b:()=>e.shiftKey?overlayMedia():insertMedia(),k:toggleMarker,
  m:()=>fillMotion(e.shiftKey?'black':'motion'),f:()=>e.shiftKey?$('zoom-all').click():focusRegion()};
 if(actions[k]){handled();actions[k]();}
});
window.addEventListener('resize',draw);
document.addEventListener('visibilitychange',()=>{if(document.hidden&&playing)pause();});

// ---------- picture edits and imported media ----------
const baseName=p=>String(p||'').split(/[\\/]/).pop();
const escapeHtml=t=>String(t).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function pictureLocked(fill=false){
 // Censored-dub scene choices are applied at export from the original timeline.
 // A motion fill keeps every time in place, so it is laid on after those cuts.
 if(!fill&&plan.censorship&&segments.some(s=>s.censored_action==='cut')){
  report('This plan cuts censored scenes at export. Restore those scenes (Review → Censorship) before editing the picture.',true);return true;}
 return exporting;
}
function currentTimeline(){return {segments:clone(segments),duration:plan.duration,kept:VT.baseKept(plan),tracks:clone(vtracks)};}
function applyPictureEdit(tl,message,select_at){
 pause();saveHistory();
 segments=tl.segments;plan.duration=tl.duration;vtracks=tl.tracks||vtracks;
 plan.video_edits={...(plan.video_edits||{original_target_duration:originalDuration,removed:[]}),kept:tl.kept};
 inMark=null;outMark=null;refreshMarkLabels();
 afterLengthChange();
 selected=clamp(locate(clamp(select_at,0,plan.duration-.001)),0,segments.length-1);
 movePlayhead(select_at);refresh();setButtons();report(message);
}
function editRange(){
 const s=current();
 if(inMark!=null&&outMark!=null)return [Math.min(inMark,outMark),Math.max(inMark,outMark)];
 return s?[s.target_start,s.target_end]:null;
}
function rippleDelete(){
 if(pictureLocked()||locked('V1','MIX','ALL'))return;
 const r=editRange();if(!r){report('Select a clip or mark In and Out first.',true);return;}
 try{
  const tl=VT.rippleDelete(currentTimeline(),r[0],r[1]);
  applyPictureEdit(tl,'Removed '+(r[1]-r[0]).toFixed(2)+' s of picture and sound; everything after moved earlier. Undo: Ctrl+Z.',r[0]);
 }catch(e){report('Ripple delete failed: '+e.message,true);}
}
// Censored dubs freeze or repeat a frame over a cut; a motion fill replaces the
// picture in a range with the frame at In, kept moving where only small parts
// of it move (built at export, video_edits.py). The sound is unchanged.
function fillMotion(kind='motion'){
 const k=activeTrack;
 if(pictureLocked(true)||locked(k>=0?k:'V1'))return;
 const sel=selClip&&selClip.k===k?vtracks[k].clips[selClip.i]:null;
 const r=inMark!=null&&outMark!=null||!sel?editRange():[sel.at,sel.at+sel.length];if(!r){report('Select a clip or mark In and Out first.',true);return;}
 try{
  if(k>=0){applyTrackEdit(VT.fillTrack(currentTimeline(),k,r[0],r[1],kind),'V'+(k+2)+': '+trimTime(r[0])+'–'+trimTime(r[1])+(kind==='black'?' is black.':' holds the frame at In, kept moving.')+' Undo: Ctrl+Z.');return;}
  const tl=VT.fillRange(currentTimeline(),r[0],r[1],kind);
  applyPictureEdit(tl,kind==='black'?'The picture in '+trimTime(r[0])+'–'+trimTime(r[1])+' is now black. Sound unchanged. Undo: Ctrl+Z.':
   'The picture in '+trimTime(r[0])+'–'+trimTime(r[1])+' is now the frame at In, kept moving (built at export; the preview shows the frame). Sound unchanged. Undo: Ctrl+Z.',r[0]);
 }catch(e){report((kind==='black'?'Fill black':'Fill motion')+' failed: '+e.message,true);}
}
// Save the output picture at the playhead as a PNG.
async function saveFrame(){
 const pic=pictureNow(playhead);
 if(pic?.piece?.fill==='black'){report('The picture is black here.',true);return;}
 try{
  const file=pic?.media?await window.alignment.snapshot('media',pic.time,pic.media):await window.alignment.snapshot('target',mapPicture(playhead));
  report(file?'Saved frame: '+file:'Frame not saved.');
 }catch(e){report('Could not save the frame: '+e.message,true);}
}
function toggleFullscreen(){
 if(document.fullscreenElement)document.exitFullscreen().catch(()=>{});
 else $('stage').requestFullscreen().catch(e=>report('Full screen unavailable: '+e.message,true));
}
function applyTrackEdit(tl,message){
 pause();saveHistory();vtracks=tl.tracks;selClip=null;touched();draw();syncVideos(true);setButtons();report(message);
}
function finishTrackDrag(a){
 try{
  const tl=a.mode==='vmove'?VT.moveClip(currentTimeline(),a.k,a.index,a.at):a.mode==='vslip'?VT.slipClip(currentTimeline(),a.k,a.index,a.delta):
   VT.trimClip(currentTimeline(),a.k,a.index,a.mode==='vstart'?'start':'end',a.at);
  applyTrackEdit(tl,{vmove:'Moved the clip to '+trimTime(a.at)+'.',vslip:'Slipped the footage '+(a.delta>=0?'+':'')+a.delta.toFixed(3)+' s.',vstart:'Trimmed the clip start.',vend:'Trimmed the clip end.'}[a.mode]);
 }catch(e){report('Track edit rejected: '+e.message,true);}
}
function deleteClip(){
 if(!selClip||locked(selClip.k))return;
 try{applyTrackEdit(VT.removeClip(currentTimeline(),selClip.k,selClip.i),'Removed the clip; the track below shows there.');}catch(e){report(e.message,true);}
}
function splitTrackClip(){
 const k=selClip?.k??(activeTrack>=0?activeTrack:null);if(k===null)return false;
 const i=VT.clipAt({tracks:vtracks},k,playhead);if(i<0||locked(k))return true;
 try{applyTrackEdit(VT.splitClip(currentTimeline(),k,i,playhead),'Split the V'+(k+2)+' clip at '+trimTime(playhead)+'.');}catch(e){report(e.message,true);}
 return true;
}
// Track header buttons and the Tracks menu.
function headerAction(row,kind){
 const k=trackOf(row);
 if(kind==='lock'){
  if(k===null){const n=rowName(row);locks[n]=!locks[n];report(n+(locks[n]?' locked: its clips cannot be changed.':' unlocked.'));}
  else{vtracks[k].locked=!vtracks[k].locked;report('V'+(k+2)+(vtracks[k].locked?' locked.':' unlocked.'));}
  autosave();draw();return;
 }
 if(kind==='eye'){pause();saveHistory();vtracks[k].hidden=!vtracks[k].hidden;draw();syncVideos(true);setButtons();report('V'+(k+2)+(vtracks[k].hidden?' hidden: not shown or exported.':' shown.'));return;}
 if(kind==='dup')return duplicateTrack(k===null?-1:k);
 if(kind==='del')return deleteTrack(k);
}
function duplicateTrack(k=activeTrack){
 if(vtracks.length>=12){report('Up to 12 video tracks.',true);return;}
 try{
  applyTrackEdit(VT.duplicateTrack(currentTimeline(),k),(k<0?'V1':'V'+(k+2))+' copied to V'+(k+3)+' above it, cut for cut. Lock the original to keep it safe; edit the copy freely — the top visible clip is what plays and exports.');
  activeTrack=k+1;draw();
 }catch(e){report('Could not duplicate: '+e.message,true);}
}
function addVideoTrack(){
 if(vtracks.length>=12){report('Up to 12 video tracks.',true);return;}
 applyTrackEdit(VT.addTrack(currentTimeline()),'Added V'+(vtracks.length+2)+'.');activeTrack=vtracks.length-1;draw();
}
function deleteTrack(k=activeTrack){
 if(k===null||k<0||!vtracks[k]){report('Select a video track above V1 first.',true);return;}
 if(locked(k))return;
 const tl=VT.deleteTrack(currentTimeline(),k);
 if(!tl.tracks.length)tl.tracks.push({clips:[],locked:false,hidden:false});
 applyTrackEdit(tl,'Deleted V'+(k+2)+'; its clips are gone (Undo: Ctrl+Z).');activeTrack=Math.min(activeTrack,vtracks.length-1);draw();
}
// Put the selected picture on track k at `at` (it covers the tracks below; the sound is unchanged).
function overlayMedia(at=playhead,item=selectedMedia(),k=activeTrack>=0?activeTrack:0){
 if(exporting||locked(k))return;
 if(!item){report('Select a file in the Media tab first.',true);return;}
 try{
  const length=item.image?Number(item.stillSeconds||5):null;
  applyTrackEdit(VT.placeMedia(currentTimeline(),k,at,item,0,length),item.name+' is on V'+(k+2)+' from '+trimTime(at)+'. It covers the tracks below; the sound is unchanged. Undo: Ctrl+Z.');
 }catch(e){report('Could not put it on V'+(k+2)+': '+e.message,true);}
}
// ---------- drag and drop: media pool and Explorer onto the timeline ----------
function dropTarget(e){
 const b=canvas.getBoundingClientRect(),x=e.clientX-b.left,y=e.clientY-b.top;
 if(x<range().left||y<RULER)return null;
 const row=timelineRow(y);if(row<0)return null;
 const time=magnetic(tFor(x),[],snapEnabled).time;
 const text=row>=4?'Put on V'+(row-2):row===0?'Insert into V1 (ripples)':'Use its sound on MIX';
 return {row,time,text:text+' at '+trimTime(time)};
}
async function filesToPool(fileList){
 const paths=window.alignment.pathsForFiles(fileList);
 if(!paths.length)return [];
 const added=await window.alignment.registerMedia(paths);
 for(const item of added){const i=imports.findIndex(x=>x.path===item.path);if(i>=0)imports[i]=item;else imports.push(item);}
 if(added.length){mediaSel=added[added.length-1].path;setLeftTab('media');renderMedia();}
 if(added.length<paths.length)report((paths.length-added.length)+' dropped file(s) could not be read as video, audio or images.',true);
 return added;
}
function placeDropped(item,target){
 mediaSel=item.path;renderMedia();
 if(target.row>=4)overlayMedia(target.time,item,trackOf(target.row));
 else if(target.row===0){if(!item.hasVideo){report(item.name+' has no picture; drop it on MIX to use its sound.',true);return;}insertMedia(target.time);}
 else{if(!item.hasAudio){report(item.name+' has no sound; drop it on a video track.',true);return;}useMediaAudio(target.time);}
}
canvas.addEventListener('dragover',e=>{if(!plan)return;e.preventDefault();dropHint=dropTarget(e);e.dataTransfer.dropEffect=dropHint?'copy':'none';requestRender();});
canvas.addEventListener('dragleave',()=>{dropHint=null;requestRender();});
canvas.addEventListener('drop',async e=>{
 e.preventDefault();e.stopPropagation();const target=dropTarget(e);dropHint=null;requestRender();
 const pooled=e.dataTransfer.getData('application/x-autosync-media');
 try{
  const items=pooled?[imports.find(x=>x.path===pooled)].filter(Boolean):await filesToPool(e.dataTransfer.files);
  if(items.length&&target)placeDropped(items[0],target);
 }catch(err){report('Drop failed: '+err.message,true);}
});
// Files dropped anywhere else go into the media pool (the window never navigates to them).
document.addEventListener('dragover',e=>{if(e.dataTransfer?.types?.includes('Files'))e.preventDefault();});
document.addEventListener('drop',e=>{if(e.target===canvas)return;e.preventDefault();if(e.dataTransfer?.files?.length)filesToPool(e.dataTransfer.files).catch(err=>report('Import failed: '+err.message,true));});
function selectedMedia(){return imports.find(x=>x.path===mediaSel)||null;}
function insertMedia(at=playhead){
 if(pictureLocked()||locked('V1','MIX','ALL'))return;
 const item=selectedMedia();if(!item){report('Select a file in the Media tab first.',true);return;}
 try{
  const length=item.image?Number(item.stillSeconds||5):null;
  const tl=VT.insertClip(currentTimeline(),at,item,0,length);
  const L=tl.duration-plan.duration;
  applyPictureEdit(tl,'Inserted '+item.name+' ('+L.toFixed(2)+' s) at '+trimTime(at)+'. Everything after moved later.',at+.001);
 }catch(e){report('Insert failed: '+e.message,true);}
}
function useMediaAudio(at=null){
 if(exporting||locked('MIX'))return;
 const item=selectedMedia();if(!item){report('Select a file in the Media tab first.',true);return;}
 const r=at!=null?[at,Math.min(plan.duration,at+(item.duration||5))]:editRange();if(!r){report('Select a clip or mark In and Out for the new audio.',true);return;}
 try{
  const tl=VT.replaceAudio(currentTimeline(),r[0],r[1],item,0);
  pause();saveHistory();segments=tl.segments;
  selected=clamp(locate(r[0]+.001),0,segments.length-1);inMark=null;outMark=null;refreshMarkLabels();refresh();
  report('The marked range now plays '+item.name+'. The picture is unchanged.');
 }catch(e){report('Could not use that audio: '+e.message,true);}
}
async function importMedia(){
 try{
  const added=await window.alignment.importMedia();
  if(!added?.length){report('Import cancelled.');return;}
  for(const item of added){const i=imports.findIndex(x=>x.path===item.path);if(i>=0)imports[i]=item;else imports.push(item);}
  mediaSel=added[added.length-1].path;setLeftTab('media');renderMedia();
  report('Imported '+added.length+' file'+(added.length>1?'s':'')+'. Insert at the playhead (B) or use the audio for a range.');
 }catch(e){report('Import failed: '+e.message,true);}
}
function renderMedia(){
 const list=$('media-list');list.textContent='';
 $('media-empty').hidden=imports.length>0;
 for(const item of imports){
  const li=document.createElement('li');li.className=item.path===mediaSel?'on':'';li.title=item.path+' · drag onto V1, V2 or MIX';
  li.draggable=true;li.ondragstart=e=>{e.dataTransfer.setData('application/x-autosync-media',item.path);e.dataTransfer.effectAllowed='copy';};
  const kind=document.createElement(item.thumb?'img':'span');kind.className='kind';
  if(item.thumb){kind.src=item.thumb;kind.alt='';}else kind.textContent=item.image?'🖼':item.hasVideo?'🎞':'🔊';
  const name=document.createElement('span');name.className='name';name.textContent=item.name;
  const meta=document.createElement('span');meta.className='meta';
  meta.textContent=(item.image?'Image · inserted for '+(item.stillSeconds||5)+' s':trimTime(item.duration))+(item.hasVideo&&!item.image?(item.hasAudio?' · picture + sound':' · picture only'):'')+(!item.hasVideo?' · sound only':'');
  li.append(kind,name,meta);
  li.onclick=()=>{mediaSel=item.path;renderMedia();};
  li.ondblclick=()=>{mediaSel=item.path;renderMedia();insertMedia();};
  list.append(li);
 }
 const item=selectedMedia();
 $('media-insert').disabled=!item?.hasVideo||exporting;
 $('media-overlay').disabled=!item?.hasVideo||exporting;
 $('media-audio').disabled=!item?.hasAudio||exporting;
}
function setLeftTab(name){
 for(const [tab,pane] of [['review','review-pane'],['media','media-pane']]){
  const on=tab===name;$('tab-'+tab).classList.toggle('on',on);$('tab-'+tab).setAttribute('aria-selected',String(on));$(pane).hidden=!on;
 }
}
$('tab-review').onclick=()=>setLeftTab('review');
$('tab-media').onclick=()=>setLeftTab('media');
$('import-media').onclick=importMedia;
$('media-insert').onclick=()=>insertMedia();
$('media-overlay').onclick=()=>overlayMedia();
$('media-audio').onclick=()=>useMediaAudio();
$('ripple-delete').onclick=rippleDelete;
// Menu bar: every command also has a button or key; menus close after a choice.
const COMMANDS={import:importMedia,save:saveAs,export:()=>$('export').click(),folder:()=>$('open-folder').click(),frame:saveFrame,
 undo:()=>restore(undo,redo),redo:()=>restore(redo,undo),cut:cutSelected,copy:copySelected,paste:pasteSelected,split,join,ripple:rippleDelete,
 in:()=>markPoint('in'),out:()=>markPoint('out'),clear:()=>$('clear-range').click(),insert:()=>insertMedia(),overlay:()=>overlayMedia(),deloverlay:deleteClip,
 dupV1:()=>duplicateTrack(-1),dupTrack:()=>duplicateTrack(),addTrack:addVideoTrack,delTrack:()=>deleteTrack(),
 fill:()=>fillMotion('motion'),black:()=>fillMotion('black'),marker:toggleMarker,prev:()=>jumpReview(-1),next:()=>jumpReview(1),
 fitall:()=>$('zoom-all').click(),fitclip:focusRegion,full:toggleFullscreen,keys:()=>$('shortcuts').showModal(),
 hideTrack:()=>activeTrack>=0?headerAction(4+activeTrack,'eye'):report('Select a video track above V1 first.',true),
 lockTrack:()=>headerAction(activeTrack>=0?4+activeTrack:0,'lock'),
 ...Object.fromEntries(['V1','MIX'].map(k=>['lock'+k,()=>headerAction(k==='V1'?0:3,'lock')])),
 ...Object.fromEntries(['side','overlay','difference','wipe'].map(v=>['view-'+v,()=>setView(v)]))};
document.querySelectorAll('[data-cmd]').forEach(b=>b.onclick=()=>{b.closest('details').open=false;COMMANDS[b.dataset.cmd]?.();});
document.addEventListener('pointerdown',e=>{for(const d of document.querySelectorAll('.menu[open]'))if(!d.contains(e.target))d.open=false;});
$('fill-motion').onclick=()=>fillMotion('motion');
$('fill-black').onclick=()=>fillMotion('black');
$('snapshot').onclick=saveFrame;
$('fullscreen').onclick=toggleFullscreen;
$('pictures').addEventListener('dblclick',toggleFullscreen);
$('play-range').onclick=playRange;
$('add-marker').onclick=toggleMarker;

document.addEventListener('DOMContentLoaded',()=>{if(globalThis.I18N)$('help').before(I18N.picker());});
// ---------- start ----------
(async()=>{
 try{
  const data=await window.alignment.getPlan();
  plan=data.plan;planFile=data.file;segments=clone(plan.segments);frame=1/(Number(data.fps)||25);videoDims=data.videos||{};
  imports=data.imports||[];originalDuration=plan.duration;renderMedia();
  markers=(Array.isArray(plan.markers)?plan.markers:[]).map(Number).filter(t=>Number.isFinite(t)&&t>=0&&t<=plan.duration);
  // A plan saved by this editor keeps V1 and V2 apart (export uses the flattened picture).
  if(plan.video_edits?.v1)plan.video_edits={...plan.video_edits,kept:plan.video_edits.v1};
  vtracks=VT.planTracks(plan);if(!vtracks.length)vtracks=[{clips:[],locked:false,hidden:false}];
  if(plan.editor_tracks?.locks){locks.V1=!!plan.editor_tracks.locks.V1;locks.MIX=!!plan.editor_tracks.locks.MIX;}
  $('project-path').textContent=data.file;$('project-path').title=data.file;
  document.title='AutoSync v1.4.3 · Preview & Edit · '+String(data.file).split(/[\\/]/).slice(-2).join('/');
  if(!segments.length)throw Error('No editable clips in the selected plan.');
  const prefs={view:store.get('autosync-editor-view'),left:store.get('autosync-editor-left'),right:store.get('autosync-editor-right'),h:store.get('autosync-editor-timeline')};
  if(prefs.view)setView(prefs.view);
  if(prefs.left===false)setPanel('left',false);
  if(prefs.right===false)setPanel('right',false);
  setTimelineHeight(timelineShare()*window.innerHeight);
  const saved_=store.get(autosaveKey());
  if(saved_){
   reviewed=new Set(saved_.reviewed||[]);notes=saved_.notes||{};
   if(Array.isArray(saved_.markers))markers=saved_.markers.filter(Number.isFinite);
   if(saved_.locks){locks.V1=!!saved_.locks.V1;locks.MIX=!!saved_.locks.MIX;}
   if(Array.isArray(saved_.segments)&&(JSON.stringify(saved_.segments)!==JSON.stringify(segments)||saved_.videoEdits)){
    $('restore-text').textContent='Unsaved edits from '+new Date(saved_.at).toLocaleString()+' were found for this plan.';
    $('restore-banner').hidden=false;
    $('restore-yes').onclick=async()=>{
     const media=[...saved_.segments,...(saved_.videoEdits?.kept||[]),...(saved_.vtracks||[]).flatMap(t=>t.clips)].filter(x=>x.media).map(x=>x.media);
     if(media.length){try{for(const item of await window.alignment.registerMedia([...new Set(media)]))if(!imports.some(x=>x.path===item.path))imports.push(item);renderMedia();}catch(e){report('Some imported media could not be found: '+e.message,true);}}
     undo.push(snapshot());applySnapshot({segments:saved_.segments,duration:saved_.duration??plan.duration,videoEdits:saved_.videoEdits??null,vtracks:saved_.vtracks??vtracks});
     $('restore-banner').hidden=true;selected=0;afterLengthChange();touched();refresh();report('Restored your unsaved edits. Undo (Ctrl+Z) returns to the analysed plan.');};
    $('restore-no').onclick=()=>{$('restore-banner').hidden=true;store.set(autosaveKey(),{segments:null,reviewed:[...reviewed],notes,at:Date.now()});report('Discarded the earlier unsaved edits.');};
   }
  }
  buildIssues();
  document.querySelector('[data-filter=censor]').hidden=!plan.censorship&&!issueItems.some(x=>x.kind==='dubonly');
  setupVideos(data.media);
  refreshMarkLabels();
  resetZoom();select(0);movePlayhead(0);setButtons();
  report('Loading waveforms… You can start reviewing now.');
  // Draw each track as soon as it arrives: the source decode is usually much faster.
  await Promise.allSettled(['source','target'].map(track=>window.alignment.waveform(track).then(w=>{waves[track]=w;},err=>{report(track+' waveform unavailable: '+err.message,true);}).finally(()=>{waveLoading[track]=false;draw();})));
  scheduleFineWaveforms();
  const flags=issueItems.filter(x=>x.kind==='flag').length;
  report(flags?flags+' point'+(flags>1?'s':'')+' flagged for review. Press L for the next one, P to play across it, ? for all shortcuts.':'Ready. J / L step through the joins, P plays across one, ? shows all shortcuts.');
  window.addEventListener('beforeunload',()=>{pause();AC.close().catch(()=>{});});
 }catch(e){report('Unable to load the editor: '+e.message,true);}
})();
