"""Shared validation for the Electron desktop front end."""
import csv
import datetime as dt
import math
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parent
MODES = {
    'Sync full target audio': ('', 'Export synced.flac for the full target video.'),
    'Main episode only': ('--main-only', 'Remove differing opening/ending. Export trimmed video + synced FLAC.'),
    'Keep target opening / ending': ('--keep-target-op-ed', 'Keep the full target video and its opening/ending audio. Sync the source main audio.'),
}
FIELDS = [('audio_stream','Source audio track','0'), ('reference_stream','Reference audio track','0'),
          ('outer_stream','Target opening/ending track','0'), ('audio_delay','Source audio delay (seconds)','0'),
          ('reference_delay','Reference delay (seconds)','0'), ('main_start','Main start estimate (target seconds)',''),
          ('main_end','Main end estimate (target seconds)',''), ('source_main_start','Source range start',''), ('source_main_end','Source range end',''), ('cut_times','Manual cut times (comma-separated seconds)',''),
          ('source_crop','Source matching crop (w:h:x:y)',''), ('target_crop','Target matching crop (w:h:x:y)',''),
          ('scene_threshold','Scene threshold','0.15')]

FIELDS += [(side+'_trim_'+edge,side.title()+' trim '+edge,'') for side in ('source','target') for edge in ('start','end')]

def check_file(value, label):
    p=Path(value).expanduser()
    if not value or not p.is_file():raise ValueError(f'{label}: select an existing file.')
    return str(p.resolve())


def build_command(values, job_type):
    """Validate a snapshot before launching; no shell interpolation."""
    if values.get('reference_fallback') and values.get('remove_unmatched_video'):raise ValueError('Choose reference fallback or remove unmatched video, not both.')
    v=values;cmd=[sys.executable,'-u',str(ROOT/'autosync.py')]
    if job_type=='Saved plan':
        cmd+=['--render-plan',check_file(v['plan'],'Saved plan')]
        for flag in ['reference_fallback','remove_unmatched_video','allow_uncertain_cuts']:
            if v.get(flag):cmd.append('--'+flag.replace('_','-'))
        cmd+=['--video-codec',v['video_codec'],'--video-preset',v['video_preset']]
        return cmd,Path(v['plan']).resolve().parent
    mode=MODES[v['mode']][0]
    if mode:cmd.append(mode)
    if job_type=='Batch CSV':
        path=Path(check_file(v['batch'],'Batch CSV'))
        with path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
        if not rows:raise ValueError('The batch CSV has no jobs.')
        outputs=[]
        for i,row in enumerate(rows,1):
            for key in ['source','target','audio']:
                x=row.get(key,'').strip()
                check_file(str(path.parent/x) if x and not Path(x).is_absolute() else x,f'CSV row {i}: {key}')
            for key in ['reference']:
                x=row.get(key,'').strip()
                if x:check_file(str(path.parent/x) if not Path(x).is_absolute() else x,f'CSV row {i}: {key}')
            x=row.get('out','').strip()
            if not x:raise ValueError(f'CSV row {i}: an out folder is required.')
            out=Path(x) if Path(x).is_absolute() else path.parent/x
            outputs.append(out.resolve())
        if len(set(outputs))!=len(outputs):raise ValueError('Each CSV job needs a different output folder.')
        if any((o/'plan.json').exists() for o in outputs):raise ValueError('A batch output folder already has a plan. Use new output folders.')
        cmd+=['--batch',str(path)];out=outputs[0]
    else:
        src=check_file(v['source'],'Source video');target=check_file(v['target'],'Target video')
        audio=check_file(v['audio'] or src,'Source audio')
        ref=check_file(v['reference'] or target,'Reference audio')
        if not v['out'].strip():raise ValueError('Choose an output folder.')
        out=Path(v['out']).expanduser().resolve()
        if out.exists() and not out.is_dir():raise ValueError('Output must be a folder.')
        if (out/'plan.json').exists():raise ValueError('This folder already has a plan. Choose a new folder or use Saved plan.')
        cmd+=['--source',src,'--target',target,'--audio',audio,'--reference',ref,'--out',str(out)]
    for key,_,_ in FIELDS:
        x=str(v.get(key,'')).strip()
        if not x:continue
        if key in ('main_start','main_end','source_main_start','source_main_end') and not mode:raise ValueError('Main boundaries require one of the main-episode modes.')
        if key.endswith('_stream'):
            if int(x)<0:raise ValueError('Track numbers must be 0 or greater.')
        elif key not in ('source_crop','target_crop','cut_times'):
            if not math.isfinite(float(x)):raise ValueError(f'{key}: enter a finite number.')
            if key in ('main_start','main_end','source_main_start','source_main_end') and float(x)<0:raise ValueError('Main boundaries cannot be negative.')
        if key=='cut_times':
            if any(not math.isfinite(float(t)) or float(t)<=0 for t in x.split(',')):raise ValueError('Cut times must be positive seconds.')
        if key.endswith('_crop'):
            parts=x.split(':')
            if len(parts)!=4 or any(int(n)<0 for n in parts) or min(map(int,parts[:2]))==0:raise ValueError('Crop format: width:height:x:y, using whole numbers.')
        if job_type=='Batch CSV' and key in ('audio_stream','reference_stream','audio_delay','reference_delay'):continue
        cmd+=['--'+key.replace('_','-'),x]
    for side in ('source','target'):
        a,b=(str(v.get(side+'_trim_'+edge,'')).strip() for edge in ('start','end'))
        if bool(a)!=bool(b):raise ValueError(side.title()+' trim requires both start and end.')
        if a and not 0<=float(a)<float(b):raise ValueError(side.title()+' trim end must be after start.')
    if v['main_start'] and v['main_end'] and float(v['main_start'])>=float(v['main_end']):raise ValueError('Main end must be after main start.')
    if v.get('source_main_start') or v.get('source_main_end'):
        if not all(str(v.get(k,'')).strip() for k in ('source_main_start','source_main_end','main_start','main_end')):raise ValueError('Source marks require matching target start and end marks.')
        if float(v['source_main_end'])<=float(v['source_main_start']):raise ValueError('Source end must be after source start.')
    if v['audio_only'] and mode:raise ValueError('Automatic main-episode detection requires picture matching. Disable Audio-only matching.')
    for key in ('analyze_only','audio_only','reference_fallback','remove_unmatched_video','allow_uncertain_cuts'):
        if v.get(key):cmd.append('--'+key.replace('_','-'))
    cmd+=['--video-codec',v['video_codec'],'--video-preset',v['video_preset']]
    return cmd,out
