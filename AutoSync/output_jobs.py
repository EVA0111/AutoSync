"""Desktop-only clean output publication; engines keep their private working layout."""
import csv,json,os,re,shutil,tempfile,uuid,filecmp
from pathlib import Path
from datetime import datetime
from job_progress import emit

def folder(value,label):
    if not isinstance(value,str) or not value.strip():raise ValueError(f'Please specify where to store {label}.')
    p=Path(value).expanduser()
    if not p.is_absolute():raise ValueError(f'Choose an absolute folder path for {label}.')
    p=p.resolve()
    if p.exists() and not p.is_dir():raise ValueError(f'{label} must be a folder.')
    return p

def flatten(jobs):
    flat=[]
    for item in jobs:
        task=item.get('task');values=item.get('values',{})
        if task=='Folder batch':
            if not item.get('reviewed') or not item.get('pairs'):raise ValueError('Review the audio pairs first.')
            for row in item['pairs']:
                v={**values,'source':row['source'],'target':row['target'],'audio':row['source'],'reference':row['target']}
                for key in ('audio_stream','reference_stream','outer_stream','main_start','main_end','source_main_start','source_main_end','source_trim_start','source_trim_end','target_trim_start','target_trim_end'):
                    if key in row:v[key]=row[key]
                flat.append({'task':'Single episode','values':v,'name':Path(row['target']).stem})
        elif task=='Batch CSV':
            p=Path(values['batch']).resolve()
            with p.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
            for row in rows:
                v=dict(values)
                for k in ('source','target','audio','reference'):
                    if row.get(k):v[k]=str((p.parent/row[k]).resolve())
                for k in ('audio_stream','reference_stream','outer_stream','audio_delay','reference_delay','source_trim_start','source_trim_end','target_trim_start','target_trim_end'):
                    if row.get(k):v[k]=row[k]
                flat.append({'task':'Single episode','values':v,'name':Path(v.get('target','episode')).stem})
        elif task=='Subtitle batch':
            if not item.get('reviewed') or not item.get('rows'):raise ValueError('Review the subtitle pairs first.')
            if values.get('mode')=='map' and len(item['rows'])!=1:raise ValueError('Use one subtitle with a saved timing map.')
            for row in item['rows']:
                flat.append({'task':'Subtitles','values':{**values,**row},'name':Path(row['subtitle']).stem})
        elif task in ('Single episode','Subtitles','Saved plan'):
            key='subtitle' if task=='Subtitles' else 'plan' if task=='Saved plan' else 'target'
            flat.append({'task':task,'values':dict(values),'name':Path(values.get(key) or 'episode').stem})
        else:raise ValueError('Unsupported output job.')
    if not flat:raise ValueError('Add at least one file pair.')
    return flat

def safe_name(name):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',name).strip(' .')[:160] or 'episode'

def publish(source,root,name):
    """Copy completely before exposing the final name. Never overwrite user files."""
    partial=root/('.autosync-'+uuid.uuid4().hex+'.partial')
    try:
        shutil.copyfile(source,partial)
        for number in range(1,10000):
            original=Path(name);dest=root/(name if number==1 else f'{original.stem} ({number}){original.suffix}')
            try:
                if os.name=='nt':os.rename(partial,dest) # Windows rename refuses an existing destination.
                else:os.link(partial,dest);partial.unlink()
                return dest
            except FileExistsError:continue
        raise RuntimeError('Too many files with the same output name.')
    finally:partial.unlink(missing_ok=True)

def run_managed(request,runner):
    output=folder(request.get('output_dir'),'outputs')
    reports=folder(request.get('reports_dir'),'reports') if request.get('save_reports') else None
    if reports and (output==reports or output in reports.parents or reports in output.parents):raise ValueError('Choose separate, non-nested output and report folders.')
    jobs=flatten(request.get('jobs',[]))
    # Analysis-only runs still publish their plan to the chosen output folder.
    output.mkdir(parents=True,exist_ok=True)
    if reports:reports.mkdir(parents=True,exist_ok=True)
    run_id=datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
    summary=reports/(run_id+'.summary.txt') if reports else None
    if summary:print('AUTOSYNC_REPORTS='+json.dumps(str(summary)),flush=True)
    print('AUTOSYNC_OUTPUT='+json.dumps(str(output)),flush=True)
    results=[]
    # The Electron parent also owns this temp root and removes it after Stop/crash.
    base=Path(request['work_root']) if request.get('work_root') else None
    with tempfile.TemporaryDirectory(prefix='jobs-',dir=base) as td:
        previous={k:os.environ.get(k) for k in ('AUTOSYNC_PROGRESS_BASE','AUTOSYNC_PROGRESS_TOTAL')}
        try:
            os.environ['AUTOSYNC_PROGRESS_TOTAL']=str(len(jobs))
            for index,job in enumerate(jobs):
                os.environ['AUTOSYNC_PROGRESS_BASE']=str(index)
                label=('Subtitles' if job['task']=='Subtitles' else 'Audio')+' · '+job['name']
                emit(0,1,label)
                stage=Path(td)/str(index);job['values']['out']=str(stage);name=safe_name(job['name']);files=[];review=False;failure=''
                try:
                    if job['task']=='Saved plan':
                        stage.mkdir();shutil.copyfile(job['values']['plan'],stage/'plan.json');job['values']['plan']=str(stage/'plan.json')
                    code=runner({'task':job['task'],'values':job['values']})
                    if code:raise RuntimeError('Sync failed; see the activity log'+(' and saved reports.' if reports else '.'))
                    candidates=[]
                    if job['task']=='Subtitles':
                        report=json.loads((stage/'subtitle_report.json').read_text(encoding='utf-8'))
                        review=report['needs_review'];src=Path(report['output'])
                        if src.parent.resolve()!=stage.resolve():raise ValueError('Unexpected subtitle output path.')
                        candidates=[(src,name+('.DRAFT-review-required' if review else '.synced')+src.suffix)]
                    else:
                        review_plan=stage/('edited_plan.json' if (stage/'edited_plan.json').is_file() else 'plan.json')
                        if review_plan.is_file():review=bool(json.loads(review_plan.read_text(encoding='utf-8')).get('review'))
                        for src,suffix in [('synced.flac','.synced.flac'),('main_episode.mkv','.main.mkv'),('full_episode.mkv','.synced.mkv'),('edited_episode.mkv','.edited.mkv'),('trimmed_episode.mkv','.trimmed.mkv')]:
                            if (stage/src).is_file():candidates.append((stage/src,name+suffix))
                    path_map={}
                    for src,destname in candidates:
                        dest=publish(src,output,destname);files.append(str(dest));path_map[str(src)]=str(dest)
                    # An alignment belongs to the user, not a temporary staging directory.
                    # Publish even when reports are disabled and the run is analyze-only.
                    if job['task'] in ('Single episode','Saved plan') and (stage/'plan.json').is_file():
                        source_plan=stage/'plan.json'
                        published=publish(source_plan,output,name+'.alignment.json')
                        files.append(str(published))
                        path_map[str(source_plan)]=str(published)
                        print('AUTOSYNC_PLAN='+json.dumps(str(published)),flush=True)
                    # Fonts are required playback assets, not optional reports.
                    for font in stage.glob('input_subtitle_fonts/*'):
                        if font.is_file():
                            fontdir=output/'Fonts';fontdir.mkdir(exist_ok=True)
                            if not any(filecmp.cmp(font,existing,shallow=False) for existing in fontdir.iterdir() if existing.is_file()):publish(font,fontdir,font.name)
                    status='review' if review else 'complete'
                    print('Exported: '+(', '.join(files) or 'Analysis only'),flush=True)
                except Exception as e:
                    status='failed';failure=str(e);path_map={};print(label+': '+failure,flush=True)
                if reports:
                    # One permanent directory per job, including failures and repeat
                    # runs with identical episode names. No reports intermix.
                    job_reports=reports/f'{run_id}_{index+1:03}_{name}'
                    job_reports.mkdir(parents=True,exist_ok=False)
                    report_files=[p for p in stage.iterdir() if p.is_file() and p.suffix.lower() in ('.json','.csv','.txt','.log','.npz')] if stage.exists() else []
                    mapped={str(p):str(job_reports/p.name) for p in report_files}
                    mapped.update({k:v for k,v in path_map.items() if k not in mapped})
                    (job_reports/'job-status.json').write_text(
                        json.dumps({'job':job['name'],'task':job['task'],'status':status,'error':failure,
                                    'outputs':files},ensure_ascii=False,indent=2),encoding='utf-8')
                    for p in report_files:
                        dest=Path(mapped[str(p)])
                        if p.suffix=='.json':
                            def rewrite(x):
                                if isinstance(x,str):return mapped.get(x,x)
                                if isinstance(x,list):return [rewrite(y) for y in x]
                                if isinstance(x,dict):return {k:rewrite(v) for k,v in x.items()}
                                return x
                            try:dest.write_text(json.dumps(rewrite(json.loads(p.read_text(encoding='utf-8'))),ensure_ascii=False,indent=2),encoding='utf-8')
                            except (ValueError,UnicodeError):shutil.copyfile(p,dest)
                        else:shutil.copyfile(p,dest)
                results.append({'name':job['name'],'status':status,'files':files,'error':failure})
                print('AUTOSYNC_RESULT='+json.dumps(results[-1],ensure_ascii=False),flush=True)
                if summary:summary.write_text('\n'.join(f"{r['name']}: {r['status']} — {r['error'] or ', '.join(r['files'])}" for r in results),encoding='utf-8')
                emit(1,1,label+' · '+status)
        finally:
            for k,v in previous.items():
                if v is None:os.environ.pop(k,None)
                else:os.environ[k]=v
    print('AUTOSYNC_OUTPUT='+json.dumps(str(output)),flush=True)
    return 2 if any(r['status']=='failed' for r in results) else 0
