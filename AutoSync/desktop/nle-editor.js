'use strict';
// Original clip-centric UI modelled on familiar NLE interactions (not FilmCraft source).
// Clip edits run locally; valid flattened audio segments are passed to AutoSync.
window.createNleEditor=function createNleEditor(deps){
 const $=id=>document.getElementById(id);
 const c=$('nle-timeline'),ctx=c.getContext('2d'),api=window.alignment;
 const ROWS={V1:[40,108],A1:[113,177],A2:[182,246],A3:[251,315],OUT:[320,396]},HEAD=182;
 const deep=x=>JSON.parse(JSON.stringify(x));
 const clamp=(v,lo,hi)=>Math.max(lo,Math.min(hi,v));
 let project=api.nleCreate(deps.getPlan()),history=[],future=[];
 let cachedOutput=api.nleFlatten(project);
 let selection=null,track='A3',tool='select',snapEnabled=true,clipboard=null,drag=null,preview=null;
 const format=t=>{const ms=Math.round(Math.max(0,t)*1000);return String(Math.floor(ms/3600000)).padStart(2,'0')+':'+String(Math.floor(ms/60000)%60).padStart(2,'0')+':'+String(Math.floor(ms/1000)%60).padStart(2,'0')+'.'+String(ms%1000).padStart(3,'0');};
 const dimensions=()=>{const w=c.clientWidth||900;return {w,left:HEAD,right:w-12,scale:(w-HEAD-12)/Math.max(1,deps.getView())};};
 const xAt=t=>HEAD+(t-deps.getScroll())*dimensions().scale;
 const timeAt=x=>clamp(deps.getScroll()+(x-HEAD)/dimensions().scale,0,project.duration);
 const laneAt=y=>Object.keys(ROWS).find(id=>y>=ROWS[id][0]&&y<ROWS[id][1])||null;
 const pos=e=>{const r=c.getBoundingClientRect();return {x:e.clientX-r.left,y:e.clientY-r.top};};
 const active=(id=track)=>project.tracks.find(t=>t.id===id);
 const find=(id=selection)=>id?api.nleFind(project,id):null;
 const pick=(id,t)=>active(id)?.clips.find(v=>v.start<=t&&t<=v.end)||null;
 function chosen(clip,id){
  selection=clip?.id||null;track=id||track;
  $('nle-selection-info').textContent=clip?
   (track+' · '+(clip.kind==='audio'?'Source':'Target')+' · '+format(clip.start)+'–'+format(clip.end)):
   ('No clip selected · '+track+' targeted');
  draw();
 }
 function changed(next,label){
  if(!next)return;
  const flat=api.nleFlatten(next);
  history.push(deep(project));if(history.length>80)history.shift();
  future=[];project=next;cachedOutput=flat;
  deps.onChange(flat,label||'Updated audio clip.');
  if(selection&&!project.tracks.some(t=>t.clips.some(v=>v.id===selection)))chosen(null,track);
  draw();
 }
 function action(op,...args){
  try{const next=api.nleOp(op,project,...args);changed(next,op+' completed.');return next;}
  catch(e){deps.report('Timeline: '+e.message,true);return null;}
 }
 function snap(t,id=null,shift=false){
  return snapEnabled!==shift?api.nleSnap(project,t,{
   threshold:8/Math.max(.01,dimensions().scale),playhead:deps.getPlayhead(),exclude:id}):t;
 }
 function undo(){
  if(!history.length)return false;
  future.push(deep(project));project=history.pop();cachedOutput=api.nleFlatten(project);
  deps.onChange(api.nleFlatten(project),'Undo clip edit.');draw();return true;
 }
 function redo(){
  if(!future.length)return false;
  history.push(deep(project));project=future.pop();cachedOutput=api.nleFlatten(project);
  deps.onChange(api.nleFlatten(project),'Redo clip edit.');draw();return true;
 }
 function draw(){
  if(!project)return;
  const dpr=window.devicePixelRatio||1,{w,left,right}=dimensions(),h=416;
  if(c.width!==Math.round(w*dpr)||c.height!==Math.round(h*dpr)){
   c.width=Math.round(w*dpr);c.height=Math.round(h*dpr);
  }
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.fillStyle='#111823';ctx.fillRect(0,0,w,h);
  ctx.fillStyle='#152332';ctx.fillRect(0,0,left,h);
  for(const [id,r] of Object.entries(ROWS)){
   const [top,bottom]=r;
   ctx.fillStyle=id==='V1'?'#27343e':id==='OUT'?'#2d293e':'#182431';
   ctx.fillRect(left,top,right-left,bottom-top-4);
   ctx.fillStyle='#d5e1ef';ctx.font='bold 11px Segoe UI';
   const name=id==='V1'?'Video reference · locked':id==='OUT'?'OUTPUT · Program audio':id+' · '+active(id).name;
   ctx.fillText(name,9,top+19,166);
   if(id.startsWith('A')){
    const lane=active(id);
    for(const [name,prop,at] of [['M','mute',75],['S','solo',106],['L','locked',137]]){
     ctx.fillStyle=lane[prop]?'#3c7bb5':'#2d3a48';
     ctx.fillRect(at,top+30,25,21);
     ctx.fillStyle='#fff';ctx.font='bold 11px Consolas';ctx.fillText(name,at+8,top+45);
    }
   }
   ctx.strokeStyle='#334052';ctx.beginPath();ctx.moveTo(0,bottom-3);ctx.lineTo(w,bottom-3);ctx.stroke();
  }
  ctx.fillStyle='#3c566c';ctx.fillRect(left,45,right-left,55);
  ctx.fillStyle='#dce8f4';ctx.font='12px Segoe UI';ctx.fillText('Target picture · preserved',left+9,66);
  const view=deps.getView(),step=Math.pow(10,Math.floor(Math.log10(Math.max(.01,view/9))));
  const tick=[1,2,5,10].map(n=>n*step).find(n=>view/n<=14)||step*10;
  ctx.fillStyle='#bfcdde';ctx.strokeStyle='#3a4b5b';ctx.font='11px Consolas';
  for(let t=Math.ceil(deps.getScroll()/tick)*tick;t<=Math.min(project.duration,deps.getScroll()+view);t+=tick){
   const x=xAt(t);if(x<left||x>right)continue;
   ctx.beginPath();ctx.moveTo(x,29);ctx.lineTo(x,h-4);ctx.stroke();
   ctx.fillText(format(t),x+3,18);
  }
  // Flag uncertain sync joins directly on the time ruler, rather than
  // requiring users to find them in a separate text report.
  for(const issue of deps.getPlan().review||[]){
   const t=Number(issue.splice??(Number(issue.start)+Number(issue.end))/2);
   if(!Number.isFinite(t))continue;
   const x=xAt(t);if(x<left||x>right)continue;
   ctx.fillStyle='#ef9e64';ctx.beginPath();ctx.moveTo(x-5,23);ctx.lineTo(x+5,23);ctx.lineTo(x,30);ctx.fill();
  }
  const displayed=preview||project;
  for(const lane of displayed.tracks){
   const row=ROWS[lane.id];
   ctx.save();ctx.beginPath();ctx.rect(left,row[0],right-left,row[1]-row[0]-3);ctx.clip();
   for(const clip of lane.clips){
    const x0=xAt(clip.start),x1=xAt(clip.end);
    if(x1<left||x0>right)continue;
    const lo=clamp(x0,left,right),hi=clamp(x1,left,right);
    if(hi-lo<=1)continue;
    ctx.fillStyle=lane.id==='A1'?'#215d80':lane.id==='A2'?'#3d6f4b':'#755184';
    ctx.globalAlpha=lane.mute?.48:1;
    ctx.fillRect(lo,row[0]+3,hi-lo,row[1]-row[0]-10);
    ctx.globalAlpha=1;
    ctx.lineWidth=clip.id===selection?2:1;
    ctx.strokeStyle=clip.id===selection?'#ffe8a3':'#a7b9c9';
    ctx.strokeRect(lo+.5,row[0]+3.5,Math.max(1,hi-lo-1),row[1]-row[0]-11);
    if(hi-lo>45){
     ctx.fillStyle='#eef6fb';ctx.font='11px Segoe UI';
     ctx.fillText((clip.kind==='audio'?'SOURCE':'TARGET')+' · '+format(clip.end-clip.start),lo+6,row[0]+18,hi-lo-10);
    }
    ctx.strokeStyle=lane.id==='A1'?'#78c8f0':lane.id==='A2'?'#9bd6aa':'#dbbdec';ctx.lineWidth=.9;
    for(let x=Math.max(left+2,lo+3);x<hi-2;x+=4){
     const t=timeAt(x),source=clip.kind==='audio',sampleTime=source?
      clip.sourceStart+(t-clip.start)*clip.speed:deps.mapTarget(t);
     const amp=Math.max(.7,Math.pow(Math.abs(deps.waveSample(source?'source':'target',sampleTime)),.6)*15);
     const cy=row[0]+42;
     ctx.beginPath();ctx.moveTo(x,cy-amp);ctx.lineTo(x,cy+amp);ctx.stroke();
    }
   }
   ctx.restore();
  }
  // This is a priority compositor: highest active audio lane wins, not amix.
  for(const s of displayed===project?cachedOutput:api.nleFlatten(displayed)){
   const x0=clamp(xAt(s.target_start),left,right),x1=clamp(xAt(s.target_end),left,right);
   if(x1<=x0)continue;
   ctx.fillStyle=s.kind==='audio'?'#795ba3':s.kind==='verified_gap'?'#454855':'#8a684a';
   ctx.fillRect(x0,323,x1-x0,66);
  }
  const px=xAt(deps.getPlayhead());
  if(px>=left&&px<=right){
   ctx.strokeStyle='#f2c573';ctx.lineWidth=2;
   ctx.beginPath();ctx.moveTo(px,26);ctx.lineTo(px,h-4);ctx.stroke();
   ctx.fillStyle='#f2c573';ctx.beginPath();ctx.moveTo(px-6,26);ctx.lineTo(px+6,26);ctx.lineTo(px,35);ctx.fill();
  }
 }
 function down(e){
  if(deps.isExporting())return;
  const {x,y}=pos(e),lane=laneAt(y),t=timeAt(x);
  if(y<31){deps.movePlayhead(t);return;}
  if(!lane)return;
  if(x<HEAD){
   if(lane.startsWith('A')){
    const name=x>=75&&x<=100?'mute':x>=106&&x<=131?'solo':x>=137&&x<=162?'locked':null;
    if(name)action('setTrack',lane,name,!active(lane)[name]);
    else chosen(null,lane);
   }
   return;
  }
  if(!lane.startsWith('A')){deps.movePlayhead(t);return;}
  const clip=pick(lane,t);
  chosen(clip,lane);deps.movePlayhead(t);
  if(!clip)return;
  if(tool==='razor'){action('split',clip.id,snap(t,clip.id,e.shiftKey));return;}
  const d0=Math.abs(xAt(clip.start)-x),d1=Math.abs(xAt(clip.end)-x);
  drag={id:clip.id,clip:deep(clip),lane,first:x,edge:d0<7?'in':d1<7?'out':null,moved:false,proposed:null};
  try{c.setPointerCapture(e.pointerId);}catch{}
 }
 function move(e){
  const {x,y}=pos(e),lane=laneAt(y);
  if(!drag){
   c.style.cursor=tool==='razor'?'crosshair':lane&&lane.startsWith('A')&&pick(lane,timeAt(x))?'grab':'default';return;
  }
  const delta=(x-drag.first)/dimensions().scale;
  if(Math.abs(delta*dimensions().scale)<2)return;
  drag.moved=true;
  const dest=drag.edge?drag.lane:lane&&lane.startsWith('A')?lane:drag.lane;
  let t=drag.edge==='in'?drag.clip.start+delta:drag.edge==='out'?drag.clip.end+delta:drag.clip.start+delta;
  t=snap(t,drag.id,e.shiftKey);
  try{
   drag.proposed=drag.edge?api.nleOp('trim',project,drag.id,drag.edge,t):
    api.nleOp('move',project,drag.id,dest,t);
   preview=drag.proposed;c.style.cursor=drag.edge?'ew-resize':'grabbing';
  }catch{drag.proposed=null;preview=null;c.style.cursor='not-allowed';}
  draw();
 }
 function up(){
  if(!drag)return;
  const d=drag;drag=null;preview=null;
  if(d.moved&&d.proposed)changed(d.proposed,d.edge?'Trimmed clip edge.':'Moved clip.'); 
  else if(d.moved)deps.report('Cannot place this clip there. Unlock the track or choose empty space.',true);
  draw();
 }
 c.addEventListener('pointerdown',down);c.addEventListener('pointermove',move);
 c.addEventListener('pointerup',up);c.addEventListener('lostpointercapture',up);
 c.addEventListener('dblclick',e=>{
  const {x,y}=pos(e),lane=laneAt(y),t=timeAt(x),clip=lane&&lane.startsWith('A')?pick(lane,t):null;
  if(clip)action('split',clip.id,t);
 });
 function chooseTool(name){tool=name;
  $('nle-select').classList.toggle('tool-active',name==='select');
  $('nle-razor').classList.toggle('tool-active',name==='razor');
  c.style.cursor=name==='razor'?'crosshair':'default';
 }
 function copy(){
  if(!selection)return deps.report('Select a clip first.',true);
  try{clipboard=api.nleCopy(project,selection,null,null);
   deps.report('Copied '+clipboard.duration.toFixed(3)+' seconds from '+track+'.');}
  catch(e){deps.report('Copy: '+e.message,true);}
 }
 function paste(overwrite){
  if(!clipboard)return deps.report('Copy a clip before pasting.',true);
  action('paste',clipboard,track,snap(deps.getPlayhead()),{overwrite});
 }
 function lift(){if(selection)action('remove',selection);else deps.report('Select a clip first.',true);}
 function razor(){if(selection)action('split',selection,deps.getPlayhead());}
 function trim(edge){if(selection)action('trim',selection,edge,deps.getPlayhead());}
 $('nle-select').onclick=()=>chooseTool('select');
 $('nle-razor').onclick=()=>chooseTool('razor');
 $('nle-snap').onclick=()=>{snapEnabled=!snapEnabled;
  $('nle-snap').classList.toggle('tool-active',snapEnabled);
  $('nle-snap').textContent='Snap: '+(snapEnabled?'On':'Off')+' (N)';
 };
 $('nle-copy').onclick=copy;$('nle-paste').onclick=()=>paste(false);
 $('nle-overwrite').onclick=()=>paste(true);$('nle-delete').onclick=lift;
 chosen(null,track);
 return {
  get project(){return project;},
  draw,undo,redo,copy,paste,lift,razor,trim,chooseTool,
  hasSelection:()=>Boolean(selection),hasClipboard:()=>Boolean(clipboard),canUndo:()=>history.length>0,canRedo:()=>future.length>0,
  reset(plan){
   const updated={...plan};delete updated.editor_timeline;
   project=api.nleCreate(updated);cachedOutput=api.nleFlatten(project);selection=null;history=[];future=[];chosen(null,track);draw();
  }
 };
};
