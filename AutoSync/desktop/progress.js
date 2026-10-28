const progressBox=document.createElement('div');progressBox.id='job-progress';progressBox.innerHTML='<div class="progress-caption"><span id="progress-label">Ready</span><span id="progress-count"></span></div><progress id="progress-bar" max="1" value="0" aria-label="Overall job progress"></progress><div id="progress-stage" class="hint"></div>';
document.querySelector('.run').prepend(progressBox);let progressState={completed:0,total:0},reviews=0;
function resetProgress(){progressState={completed:0,total:0};reviews=0;$('progress-bar').removeAttribute('value');$('progress-label').textContent='Preparing…';$('progress-count').textContent='';$('progress-stage').textContent='';}
window.autosync.onEvent(({type,data})=>{
 if(type==='progress'){
  const total=Number(data.total),completed=Number(data.completed);if(!(total>0)||!Number.isFinite(completed))return;progressState={total,completed:Math.min(total,Math.max(0,completed))};
  const bar=$('progress-bar');bar.max=total;if(total===1&&completed<1)bar.removeAttribute('value');else bar.value=progressState.completed;
  $('progress-label').textContent=data.label||'Processing';$('progress-count').textContent=`${progressState.completed} / ${total} jobs finished`+(total>1?` · ${Math.floor(progressState.completed/total*100)}%`:'');
 }else if(type==='log'){
  const lines=data.trim().split('\n');const stage=lines.reverse().find(s=>/^(Scanning|Decoding|Rendering|Rendered|Found|Transcrib|Checking|Exported:|Loading)/.test(s));if(stage)$('progress-stage').textContent=stage.slice(0,200);
 }else if(type==='result'){
  if(data.status==='review')reviews++;log(`\n${data.name}: ${data.status}\n`+(data.files||[]).join('\n')+'\n');
 }else if(type==='done'){
  const bar=$('progress-bar');bar.value=data.code===0&&!data.cancelled?bar.max:progressState.completed;
  $('progress-label').textContent=data.cancelled?'Stopped':data.code===0?(reviews?'Finished · results need review':'Finished'):'Finished with errors · see activity';
  if(reviews&&data.code===0&&!data.cancelled)$('status').textContent=`Finished · ${reviews} result(s) need review`;
 }
});
