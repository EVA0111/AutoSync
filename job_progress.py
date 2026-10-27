"""Structured completion counts; percentages describe jobs, never guessed elapsed time."""
import json,os

def emit(completed,total,label):
    base=int(os.environ.get('AUTOSYNC_PROGRESS_BASE','0'))
    overall=int(os.environ.get('AUTOSYNC_PROGRESS_TOTAL',str(total)))
    print('AUTOSYNC_PROGRESS='+json.dumps({'completed':min(base+completed,overall),'total':overall,'label':label}),flush=True)
