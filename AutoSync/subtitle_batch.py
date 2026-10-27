"""Sequential subtitle batch runner with per-episode reports and no overwrite."""
import json,re
from job_progress import emit
from pathlib import Path
from subtitle_sync import parser,run

def arguments(values):
    allowed={'mode','subtitle','reference_subtitle','source_video','target_media','timing_map','out','source_crop','target_crop','language','subtitle_track','reference_track','audio_track','encoding','source_fps','target_fps','semantic','whisper_model','source_audio_track','sushi_window','sushi_max_window'}
    if not isinstance(values,dict) or set(values)-allowed:raise ValueError('Unknown subtitle setting.')
    argv=[]
    for key,value in values.items():
        if key=='semantic':
            if value:argv.append('--semantic')
        elif value!='':argv.extend(['--'+key.replace('_','-'),str(value)])
    return parser().parse_args(argv)

def run_batch(request):
    rows=request.get('rows');values=request.get('values',{})
    if not request.get('reviewed') or not isinstance(rows,list) or not rows or len(rows)>10000:raise ValueError('Review the subtitle episode pairs first.')
    mode=values.get('mode','reference')
    if mode not in ('reference','encodes','audio','map','sushi'):raise ValueError('Unknown subtitle mode.')
    if mode=='map' and len(rows)!=1:raise ValueError('A saved timing map accepts one subtitle file at a time.')
    if not values.get('out'):raise ValueError('Choose a new subtitle batch output folder.')
    root=Path(values['out']).expanduser().resolve()
    if root.exists():raise ValueError('Subtitle batch output folder exists. Choose a new folder.')
    jobs=[]
    for i,row in enumerate(rows,1):
        if not isinstance(row,dict) or set(row)-{'subtitle','reference_subtitle','source_video','target_media','subtitle_track','reference_track','audio_track','source_audio_track'}:raise ValueError('Invalid subtitle batch row.')
        job={**values,**row}
        required=['subtitle','timing_map'] if mode=='map' else ['subtitle','reference_subtitle'] if mode=='reference' else ['subtitle','source_video','target_media'] if mode in ('encodes','sushi') else ['subtitle','target_media']
        for key in required:
            if not job.get(key) or not Path(job[key]).is_file():raise ValueError(f'Pair {i}: missing {key}.')
        name=re.sub(r'[^\w.-]+','_',Path(job['subtitle']).stem)[:100]
        job['out']=str(root/f'{i:03}_{name}');jobs.append(arguments(job))
    root.mkdir(parents=True);results=[]
    print('AUTOSYNC_OUTPUT='+json.dumps(str(root)),flush=True)
    for i,args in enumerate(jobs,1):
        emit(i-1,len(jobs),f'Subtitles: processing {i}/{len(jobs)}')
        print(f'\nSUBTITLE EPISODE {i}/{len(jobs)}: {args.subtitle}',flush=True)
        try:
            run(args);report=json.loads((Path(args.out)/'subtitle_report.json').read_text(encoding='utf-8'))
            results.append({'episode':i,'status':'review' if report['needs_review'] else 'complete','out':args.out})
        except Exception as e:
            print('FAILED: '+str(e),flush=True);results.append({'episode':i,'status':'failed','out':args.out,'error':str(e)})
        emit(i,len(jobs),f'Subtitles: finished {i}/{len(jobs)} ({results[-1]["status"]})')
        (root/'batch_report.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        (root/'report.txt').write_text('\n'.join(f"Episode {r['episode']}: {r['status']} — {r.get('error',r['out'])}" for r in results),encoding='utf-8')
    print('AUTOSYNC_OUTPUT='+json.dumps(str(root)),flush=True)
    return 2 if any(r['status']=='failed' for r in results) else 0
