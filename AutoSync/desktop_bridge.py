"""Read one desktop job on stdin and invoke the unchanged command-line engine."""
import json,sys,subprocess,os,csv
from gui_config import build_command,FIELDS,MODES

def run_request(request):
    try:
        if request.get('task')=='Managed queue':
            from output_jobs import run_managed
            return run_managed(request,run_request)
        if request.get('task')=='Queue':
            jobs=request.get('jobs',[])
            if not isinstance(jobs,list) or not 1<=len(jobs)<=2 or any(j.get('task') not in ('Single episode','Batch CSV','Subtitles','Subtitle batch') for j in jobs):raise ValueError('Invalid job queue.')
            from job_progress import emit
            def count(job):
                if job['task']=='Subtitle batch':return len(job.get('rows',[]))
                if job['task']=='Batch CSV':
                    with open(job['values']['batch'],encoding='utf-8-sig',newline='') as f:return len(list(csv.DictReader(f)))
                return 1
            counts=[count(j) for j in jobs];results=[];base=0
            previous={k:os.environ.get(k) for k in ('AUTOSYNC_PROGRESS_BASE','AUTOSYNC_PROGRESS_TOTAL')}
            try:
                os.environ['AUTOSYNC_PROGRESS_TOTAL']=str(sum(counts))
                for job,n in zip(jobs,counts):
                    os.environ['AUTOSYNC_PROGRESS_BASE']=str(base);emit(0,n,'Starting '+job['task'])
                    results.append(run_request(job));emit(n,n,'Finished '+job['task']+(' with errors' if results[-1] else ''))
                    base+=n
            finally:
                for k,v in previous.items():
                    if v is None:os.environ.pop(k,None)
                    else:os.environ[k]=v
            print(f"Queue finished: {sum(code==0 for code in results)}/{len(results)} sections succeeded.",flush=True)
            return 2 if any(results) else 0
        if request.get('task')=='Subtitle batch':
            from subtitle_batch import run_batch
            return run_batch(request)
        if request.get('task')=='Subtitles':
            from subtitle_batch import arguments
            from subtitle_sync import run
            return run(arguments(request.get('values',{})))
        v={k:d for k,_,d in FIELDS}
        v.update({k:'' for k in ['source','target','audio','reference','out','batch','plan']})
        v.update(mode='Keep target opening / ending',sync_method='standard',video_codec='h264',video_preset='veryfast')
        v.update({k:False for k in ['audio_only','analyze_only','reference_fallback','remove_unmatched_video','allow_uncertain_cuts']})
        supplied=request['values']
        if not isinstance(supplied,dict) or set(supplied)-set(v):raise ValueError('Unknown desktop settings.')
        v.update(supplied)
        if v['mode'] not in MODES:raise ValueError('Unknown mode.')
        if v['sync_method'] not in ('standard','ai_assisted'):raise ValueError('Unknown syncing method.')
        task=request['task']
        if task not in ('Single episode','Batch CSV','Saved plan'):raise ValueError('Unknown task.')
        cmd,out=build_command(v,task)
        print('AUTOSYNC_OUTPUT='+json.dumps(str(out)),flush=True)
        return subprocess.call(cmd,stdin=subprocess.DEVNULL)
    except Exception as e:
        print('Cannot start: '+str(e),flush=True);return 2

def main():
    try:return run_request(json.load(sys.stdin))
    except Exception as e:print('Cannot start: '+str(e),flush=True);return 2

if __name__=='__main__':sys.exit(main())
