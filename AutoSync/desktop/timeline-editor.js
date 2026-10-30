'use strict';
// Three-track manual sync editor. Source and target waveforms use original file
// timelines. Output regions use the editable plan's timeline.
(function(){
  const get=id=>document.getElementById(id);
  const dlg=document.createElement('dialog');dlg.id='tl-dialog';dlg.className='timeline-dialog';
  dlg.innerHTML=[
    '<div class="tl-top"><div><h2>Preview + Edit</h2><div class="tl-help">Drag an output region to slip its source audio. Drag a boundary to trim adjacent regions. Alt-drag to reorder. Ctrl-click to split.</div></div><button id="tl-close">Close</button></div>',
    '<div class="tl-preview-images"><div><div>Source video</div><img id="tl-source-image" alt="Source preview frame"></div><div><div>Target / output picture</div><img id="tl-target-image" alt="Target preview frame"></div></div>',
    '<div class="tl-toolbar"><label>Zoom <input id="tl-zoom" type="range" min="0" max="100" value="24"></label><span id="tl-clock">00:00:00.000</span><button id="tl-back">−5s</button><button id="tl-next">+5s</button><button id="tl-play-source">Play source</button><button id="tl-play-target">Play target</button><button id="tl-play-output" class="primary">Play output</button><button id="tl-stop">Stop</button></div>',
    '<div class="tl-scroll" id="tl-scroll"><div id="tl-strip"><canvas id="tl-ruler" height="30"></canvas><div class="tl-lane-title">Source audio · original timeline</div><canvas id="tl-source-wave" height="65"></canvas><div class="tl-lane-title">Target audio · original timeline</div><canvas id="tl-target-wave" height="65"></canvas><div class="tl-lane-title">Output · draggable mapped regions</div><canvas id="tl-output-wave" height="86"></canvas></div></div>',
    '<div class="tl-actions"><label>Selected region <strong id="tl-selected">None</strong></label><label>Source time (s) <input type="number" id="tl-source-time" step=".01" min="0"></label><label>Speed <input type="number" id="tl-speed" min=".5" max="2" step=".0001"></label><button id="tl-left">◀ 0.1s</button><button id="tl-right">0.1s ▶</button><button id="tl-split">Split at cursor</button><button id="tl-undo">Undo</button></div>',
    '<div id="tl-restore" class="tl-restore" hidden><strong>Opening trimmed by AutoSync: <span id="tl-restore-duration"></span></strong><label>Matching source music begins at (seconds): <input id="tl-opening-source" type="number" min="0" step=".01" value="0"></label><button id="tl-restore-action">Restore target opening</button><small>This restores the removed target pictures and maps their audio to the source time you choose. Listen to both tracks before restoring.</small></div>',
    '<div class="tl-footer"><div id="tl-msg" role="status">Select a saved plan to start editing.</div><audio id="tl-player" controls preload="none"></audio><button id="tl-save" class="primary">Save edited plan</button><button id="tl-saved">Open Saved plan</button></div>'
  ].join('');
  document.body.append(dlg);
  const btn=document.createElement('button');btn.type='button';btn.id='timeline-open';btn.textContent='Preview + Edit';
  btn.title='Inspect source, target and output timelines with audible previews. Edit an AutoSync saved plan.';
  get('stop').before(btn);
  let original='',p=null,waves={},selected=-1,playhead=0,scale=1.2,drag=null,undo=[],seq=0,lastSaved=null;
  function note(t){get('tl-msg').textContent=t;}
  function time(t){const ms=Math.max(0,Math.round(t*1000));return [Math.floor(ms/3600000),Math.floor(ms/60000)%60,Math.floor(ms/1000)%60].map(v=>String(v).padStart(2,'0')).join(':')+'.'+String(ms%1000).padStart(3,'0');}
  function copy(x){return JSON.parse(JSON.stringify(x));}
  function snap(){undo.push(copy(p));if(undo.length>80)undo.shift();}
  function maxTime(){return Math.max(p?.duration||0,waves.source?.duration||0,waves.target?.duration||0,1);}
  function toX(t){return Math.round(t*scale);}
  function fromEvent(e){const r=get('tl-output-wave').getBoundingClientRect();return Math.max(0,Math.min(p.duration,(e.clientX-r.left)/scale));}
  function mapping(t){return p.segments.find(s=>s.target_start<=t&&t<s.target_end)||p.segments.at(-1);}
  function waveAt(data,t){
    if(!data||t<0||t>=data.duration)return 0;
    const idx=Math.max(0,Math.min(data.peaks.length-1,Math.floor(t/data.duration*data.peaks.length)));
    return data.peaks[idx]/1000;
  }
  function canvasSize(id,width){
    const c=get(id);c.width=width;c.style.width=width+'px';return c.getContext('2d');
  }
  function waveLine(ctx,h,fn,maxT,base){
    const middle=h/2;
    ctx.fillStyle=base||'#50b8a4';
    const step=Math.max(1,Math.round(Math.max(1,scale)/1.5));
    for(let x=0;x<maxT*scale;x+=step){
      const val=Math.max(.035,fn(x/scale)),amp=val*(h*.43);
      ctx.fillRect(x,middle-amp,Math.max(1,step*.72),amp*2);
    }
  }
  function draw(){
    if(!p)return;
    scale=Math.max(.25,Math.min(16,Math.min(25000/maxTime(),.35*Math.pow(1.037,Number(get('tl-zoom').value)))));
    const width=Math.max(920,Math.ceil(maxTime()*scale)+2);
    get('tl-strip').style.width=width+'px';
    let ctx=canvasSize('tl-ruler',width);ctx.clearRect(0,0,width,30);
    ctx.fillStyle='#131b25';ctx.fillRect(0,0,width,30);
    const tick=scale>=8?10:scale>=2?30:scale>=.7?60:120;
    ctx.fillStyle='#a5b5c6';ctx.strokeStyle='#415061';ctx.font='11px sans-serif';
    for(let t=0;t<=maxTime();t+=tick){const x=toX(t)+.5;ctx.beginPath();ctx.moveTo(x,18);ctx.lineTo(x,30);ctx.stroke();ctx.fillText(time(t).slice(0,8),x+3,12);}
    for(const [kind,id] of [['source','tl-source-wave'],['target','tl-target-wave']]){
      ctx=canvasSize(id,width);ctx.fillStyle='#101a25';ctx.fillRect(0,0,width,65);
      ctx.strokeStyle='#293746';ctx.beginPath();ctx.moveTo(0,32.5);ctx.lineTo(width,32.5);ctx.stroke();
      waveLine(ctx,65,t=>waveAt(waves[kind],t),maxTime(),kind==='source'?'#60bfae':'#789bd9');
    }
    ctx=canvasSize('tl-output-wave',width);ctx.fillStyle='#111a26';ctx.fillRect(0,0,width,86);
    p.segments.forEach((s,i)=>{
      const x=toX(s.target_start),w=Math.max(1,toX(s.target_end)-x);
      ctx.fillStyle=i===selected?'#274f44':i%2?'#253344':'#202c3b';ctx.fillRect(x,0,w,86);
      ctx.strokeStyle=i===selected?'#7ceacc':'#56687b';ctx.strokeRect(x+.5,.5,w,85);
      ctx.fillStyle='#cee4ef';ctx.font='11px sans-serif';
      if(w>35)ctx.fillText((i+1)+' · '+s.kind,x+5,14,Math.max(0,w-7));
      if(s.kind==='audio'){
        const fn=t=>waveAt(waves.source,s.source_start+(t-s.target_start)*s.speed);
        ctx.save();ctx.beginPath();ctx.rect(x+1,17,Math.max(0,w-2),67);ctx.clip();
        ctx.fillStyle=i===selected?'#8cebd1':'#66c4ad';
        waveLine(ctx,130,()=>0,0);
        for(let xp=x;xp<x+w;xp+=2){
          const amp=fn(xp/scale)*28;ctx.fillRect(xp,51-amp,1.5,amp*2);
        }
        ctx.restore();
      }else{
        ctx.fillStyle='#b5a473';ctx.fillText('Target audio',x+4,37,Math.max(0,w-6));
      }
    });
    const cursorX=toX(playhead);
    for(const id of ['tl-ruler','tl-source-wave','tl-target-wave','tl-output-wave']){
      const c=get(id),cctx=c.getContext('2d');cctx.strokeStyle='#f5bc79';cctx.lineWidth=1.5;cctx.beginPath();cctx.moveTo(cursorX+.5,0);cctx.lineTo(cursorX+.5,c.height);cctx.stroke();
    }
    get('tl-clock').textContent=time(playhead);
    updateSelected();
    get('tl-restore').hidden=!canRestore();
  }
  function updateSelected(){
    const s=p?.segments[selected];
    get('tl-selected').textContent=s?'#'+(selected+1)+' · '+time(s.target_start)+' – '+time(s.target_end):'None';
    get('tl-source-time').disabled=!s||s.kind!=='audio';
    get('tl-speed').disabled=!s||s.kind!=='audio';
    if(s?.kind==='audio'){
      if(document.activeElement!==get('tl-source-time'))get('tl-source-time').value=s.source_start.toFixed(4);
      if(document.activeElement!==get('tl-speed'))get('tl-speed').value=s.speed.toFixed(7);
    }else{get('tl-source-time').value='';get('tl-speed').value='';}
  }
  function canRestore(){
    const v=p?.video_edits;
    return !!(v?.removed?.some(r=>r.start<=.04&&r.end>.1)&&v?.kept?.length&&v.kept[0].start>.1);
  }
  function describeRestore(){
    if(canRestore()){get('tl-restore-duration').textContent=time(p.video_edits.kept[0].start);}
  }
  function showPosition(t){
    playhead=Math.max(0,Math.min(p.duration,t));draw();
    const scroll=get('tl-scroll');const x=toX(playhead);
    if(x<scroll.scrollLeft+30||x>scroll.scrollLeft+scroll.clientWidth-35)scroll.scrollLeft=Math.max(0,x-scroll.clientWidth*.3);
    get('tl-clock').textContent=time(playhead);
    requestThumbs();
  }
  let thumbToken=0,thumbDelay;
  function requestThumbs(){
    clearTimeout(thumbDelay);
    const token=++thumbToken;
    thumbDelay=setTimeout(async()=>{
      if(!p||!dlg.open)return;
      const s=mapping(playhead),sourceTime=s?.kind==='audio'?s.source_start+(playhead-s.target_start)*s.speed:playhead;
      let targetTime=playhead;
      const v=p.video_edits;
      if(v?.kept?.length){
        const k=v.kept.find(r=>r.output_start<=playhead&&playhead<r.output_start+r.end-r.start)||v.kept.at(-1);
        targetTime=k.start+(playhead-k.output_start);
      }else if(p.main_trim)targetTime+=p.main_trim.target_start;
      try{
        const results=await Promise.allSettled([
          window.autosync.timelineThumb(p,'source',sourceTime),
          window.autosync.timelineThumb(p,'target',targetTime)
        ]);
        if(token!==thumbToken)return;
        if(results[0].status==='fulfilled')get('tl-source-image').src=results[0].value;
        if(results[1].status==='fulfilled')get('tl-target-image').src=results[1].value;
      }catch(e){note(e.message);}
    },180);
  }
  function choose(t){
    selected=p.segments.findIndex(s=>s.target_start<=t&&t<s.target_end);
    if(selected<0)selected=p.segments.length-1;
    showPosition(t);
  }
  function split(t){
    const i=p.segments.findIndex(s=>s.target_start+.15<t&&t<s.target_end-.15);
    if(i<0){note('Choose a location at least 0.15s inside an output region.');return;}
    snap();
    const s=p.segments[i],left=Object.assign({},s,{target_end:t}),right=Object.assign({},s,{target_start:t});
    if(right.kind==='audio')right.source_start=s.source_start+(t-s.target_start)*s.speed;
    if(right.reference_target_start!==undefined)right.reference_target_start+=t-s.target_start;
    p.segments.splice(i,1,left,right);selected=i+1;note('Split at '+time(t)+'.');draw();
  }
  function selectPart(t){
    let i=p.segments.findIndex(s=>s.target_start<=t&&t<s.target_end);
    return i<0?p.segments.length-1:i;
  }
  const output=get('tl-output-wave');
  output.addEventListener('pointerdown',e=>{
    if(!p||e.button!==0)return;
    const t=fromEvent(e),i=selectPart(t);
    selected=i;playhead=t;
    if(e.ctrlKey){split(t);return;}
    const s=p.segments[i],before=p.segments[i-1];
    const boundary=before&&Math.abs(t-s.target_start)*scale<9;
    drag={mode:boundary?'boundary':e.altKey?'reorder':'slip',index:i,
      startX:e.clientX,initial:copy(p.segments),moved:false};
    output.setPointerCapture(e.pointerId);draw();
  });
  output.addEventListener('pointermove',e=>{
    if(!p||!drag)return;
    const dt=(e.clientX-drag.startX)/scale;
    if(Math.abs(e.clientX-drag.startX)<2)return;
    if(!drag.moved){snap();drag.moved=true;}
    const i=drag.index;
    p.segments=copy(drag.initial);
    const s=p.segments[i];
    if(drag.mode==='slip'){
      if(s.kind!=='audio')return;
      s.source_start=Math.max(0,drag.initial[i].source_start+dt*drag.initial[i].speed);
    }else if(drag.mode==='boundary'){
      const left=p.segments[i-1],old=drag.initial[i].target_start;
      if(!left)return;
      const a=left.target_start+.2,b=s.target_end-.2;
      const next=Math.max(a,Math.min(b,old+dt));
      left.target_end=next;s.target_start=next;
      if(s.kind==='audio')s.source_start=Math.max(0,drag.initial[i].source_start+(next-old)*s.speed);
      if(s.reference_target_start!==undefined)s.reference_target_start=drag.initial[i].reference_target_start+(next-old);
    }
    playhead=Math.max(0,Math.min(p.duration,fromEvent(e)));draw();
  });
  output.addEventListener('pointerup',e=>{
    if(!drag)return;
    if(drag.mode==='reorder'&&drag.moved){
      p.segments=copy(drag.initial);
      const from=drag.index,to=selectPart(fromEvent(e));
      if(from!==to){
        const [seg]=p.segments.splice(from,1);p.segments.splice(to,0,seg);
        let t=0;
        for(const s of p.segments){const d=s.target_end-s.target_start;s.target_start=t;s.target_end=t+d;t+=d;}
        selected=to;note('Region order changed. Check the picture and audio before exporting.');
      }
    }
    const pos=fromEvent(e);const moved=drag.moved;drag=null;
    if(!moved)choose(pos);else {draw();requestThumbs();}
  });
  output.addEventListener('pointercancel',()=>{if(drag){p.segments=drag.initial;drag=null;draw();}});
  for(const [id,which] of [['tl-ruler','ruler'],['tl-source-wave','source'],['tl-target-wave','target']]){
    get(id).addEventListener('pointerdown',e=>{
      if(!p)return;
      const r=get(id).getBoundingClientRect();const t=(e.clientX-r.left)/scale;
      if(which==='source')get('tl-opening-source').value=Math.max(0,t).toFixed(2);
      showPosition(t);
    });
  }
  async function play(which){
    if(!p)return;
    const player=get('tl-player');player.pause();player.removeAttribute('src');
    note('Rendering '+which+' audio at '+time(playhead)+'…');
    try{
      const data=await window.autosync.timelineAudio(p,which,playhead);
      if(!dlg.open)return;
      player.src=data;player.load();await player.play();
      note('Playing '+which+' at '+time(playhead)+' (9-second preview).');
    }catch(e){note('Audio preview: '+e.message);}
  }
  get('tl-play-source').onclick=()=>play('source');
  get('tl-play-target').onclick=()=>play('target');
  get('tl-play-output').onclick=()=>play('output');
  get('tl-stop').onclick=()=>{get('tl-player').pause();get('tl-player').currentTime=0;};
  get('tl-back').onclick=()=>showPosition(playhead-5);
  get('tl-next').onclick=()=>showPosition(playhead+5);
  get('tl-zoom').oninput=()=>draw();
  get('tl-undo').onclick=()=>{if(undo.length){p=undo.pop();selected=-1;describeRestore();draw();note('Last change undone.');}};
  get('tl-source-time').onchange=()=>{
    const s=p?.segments[selected],v=Number(get('tl-source-time').value);
    if(!s||s.kind!=='audio'||!Number.isFinite(v)||v<0)return;
    snap();s.source_start=v;draw();note('Region source offset updated.');
  };
  get('tl-speed').onchange=()=>{
    const s=p?.segments[selected],v=Number(get('tl-speed').value);
    if(!s||s.kind!=='audio'||!Number.isFinite(v)||v<.5||v>2)return;
    snap();s.speed=v;draw();note('Region speed updated.');
  };
  function nudge(delta){const s=p?.segments[selected];if(!s||s.kind!=='audio')return;snap();s.source_start=Math.max(0,s.source_start+delta);draw();}
  get('tl-left').onclick=()=>nudge(-.1);
  get('tl-right').onclick=()=>nudge(.1);
  get('tl-split').onclick=()=>{if(p)split(playhead);};
  get('tl-restore-action').onclick=()=>{
    if(!canRestore())return;
    const intro=p.video_edits.kept[0].start,sourceStart=Number(get('tl-opening-source').value);
    if(!Number.isFinite(sourceStart)||sourceStart<0){note('Choose the matching source music start time.');return;}
    if(!confirm('Restore the first '+time(intro)+' of target video and map it to source audio at '+time(sourceStart)+'?'))return;
    snap();
    const first=p.segments[0],sp=first.kind==='audio'?first.speed:1;
    for(const s of p.segments){s.target_start+=intro;s.target_end+=intro;}
    p.segments.unshift({kind:'audio',target_start:0,target_end:intro,source_start:sourceStart,speed:sp});
    p.duration+=intro;
    for(const r of p.review||[]){r.start+=intro;r.end+=intro;if(Number.isFinite(r.splice))r.splice+=intro;}
    const v=p.video_edits;
    v.kept[0].start=0;v.kept[0].original_start=0;
    for(let i=1;i<v.kept.length;i++)v.kept[i].output_start+=intro;
    v.removed=v.removed.filter(r=>!(r.start<=.04&&Math.abs(r.end-intro)<.2));
    p.reference_shift=(p.reference_shift||0)+intro;
    if(p.auto_sync?.decisions)for(const d of p.auto_sync.decisions){
      if(d.start===0&&Math.abs(d.end-intro)<.2){d.action='source_audio';d.reason='Manually restored matching target opening in the timeline editor.';}
    }
    selected=0;playhead=0;describeRestore();draw();requestThumbs();
    note('Opening restored in the editable plan. Play OUTPUT to confirm the chosen music alignment, then save.');
  };
  async function open(){
    if(typeof running!=='undefined'&&running){note('Stop the current job before editing.');return;}
    let file=get('plan')?.value?.trim();
    if(!file){file=await window.autosync.browse('plan');if(!file)return;}
    dlg.showModal();note('Loading plan and audio waveforms…');
    try{
      const loaded=await window.autosync.timelineLoad(file);
      original=loaded.path;p=loaded.plan;undo=[];selected=0;playhead=0;lastSaved=null;
      describeRestore();draw();
      const results=await Promise.allSettled([
        window.autosync.timelineWave(p,'source'),
        window.autosync.timelineWave(p,'target')
      ]);
      waves.source=results[0].status==='fulfilled'?results[0].value:null;
      waves.target=results[1].status==='fulfilled'?results[1].value:null;
      draw();requestThumbs();
      note('Ready. Source drag adjusts audio timing; Alt-drag reorders; Ctrl-click splits. Save creates a separate render folder.');
      if(results.some(r=>r.status==='rejected'))note('Waveform warning: '+results.filter(r=>r.status==='rejected').map(r=>r.reason.message).join(' / '));
    }catch(e){note('Cannot open plan: '+e.message);}
  }
  btn.onclick=()=>open().catch(e=>note(e.message));
  get('tl-close').onclick=()=>dlg.close();
  dlg.addEventListener('close',()=>{get('tl-player').pause();get('tl-player').removeAttribute('src');++thumbToken;});
  get('tl-save').onclick=async()=>{
    if(!p)return;
    note('Saving manually edited plan…');
    try{
      lastSaved=await window.autosync.timelineSave(p,original);
      if(get('plan'))get('plan').value=lastSaved;
      note('Saved: '+lastSaved+'. Open Saved plan and start to render your new FLAC and edited video.');
    }catch(e){note('Save failed: '+e.message);}
  };
  get('tl-saved').onclick=()=>{
    if(!lastSaved){note('Save your changes first.');return;}
    dlg.close();
    document.querySelector('.nav[data-task="Saved plan"]')?.click();
    if(get('plan'))get('plan').value=lastSaved;
  };
  dlg.addEventListener('keydown',e=>{
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();get('tl-undo').click();}
    else if(e.key===' '&&e.target.tagName!=='INPUT'){e.preventDefault();play('output');}
  });
})();