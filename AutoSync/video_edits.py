"""Remove target-only intervals, preserving source and target-outer audio positions."""
import copy
from pathlib import Path
import numpy as np
import visual_core as vc
from cut_detection import source_cuts


def remove_missing(plan):
    if plan.get('video_edits'):return copy.deepcopy(plan)
    p=copy.deepcopy(plan);kept=[];removed=[];segments=[];cursor=0.
    shift=p.get('main_trim',{}).get('target_start',0.)+p.get('input_trims',{}).get('target',{}).get('start',0.)
    for section in p['segments']:
        a,b=section['target_start'],section['target_end']
        if section['kind'] in ('reference','verified_gap'):
            removed.append(dict(start=a,end=b,reason=section.get('reason','No corresponding source audio')))
            continue
        if section['kind'] not in ('audio','target_outer'):raise ValueError('Unknown segment kind.')
        kept.append(dict(start=a,end=b,output_start=cursor,original_start=a+shift,original_end=b+shift))
        segments.append(dict(section,target_start=cursor,target_end=cursor+b-a,reference_target_start=a))
        cursor+=b-a
    if not segments:raise ValueError('No video with usable source audio remains.')
    reviews=[]
    for r in p.get('review',[]):
        for k in kept:
            lo=max(r['start'],k['start']);hi=min(r['end'],k['end'])
            if hi<=lo:continue
            q=dict(r,start=k['output_start']+lo-k['start'],end=k['output_start']+hi-k['start'])
            if 'splice' in q:
                if not k['start']<=q['splice']<k['end']:q.pop('splice')
                else:q['splice']+=k['output_start']-k['start']
            reviews.append(q)
    for prev,k in zip(kept,kept[1:]):
        if k['start']>prev['end']+1e-6:
            t=k['output_start']
            reviews.append(dict(start=max(0,t-1),end=min(cursor,t+1),splice=t,confidence='supported',reason='Target-only video removed; inspect the new join'))
    if removed:
        reviews.append(dict(start=0.,end=cursor,confidence='estimated',reason='Target sections without source audio were removed. Review edited video, including start/end.'))
    p.update(segments=segments,duration=cursor,review=reviews,video_edits=dict(original_target_duration=p['duration'],kept=kept,removed=removed))
    p['source_cuts']=source_cuts(segments)
    return p


def map_anchors(anchors,plan):
    rows=[]
    for row in anchors:
        for k in plan['video_edits']['kept']:
            if k['start']<=row[0]<k['end']:
                q=row.copy();q[0]+=k['output_start']-k['start'];rows.append(q);break
    return np.asarray(rows,dtype=float).reshape((-1,anchors.shape[1]))


def export_video(plan,audio,out,codec='h264',preset='veryfast'):
    out=Path(out);dest=out/'edited_episode.mkv';tmp=out/'edited_episode.partial.mkv'
    if dest.exists():raise RuntimeError('Edited video already exists; use a new output folder.')
    intervals=[]
    for k in plan['video_edits']['kept']:
        a,b=k['original_start'],k['original_end']
        if intervals and abs(intervals[-1][1]-a)<1e-6:intervals[-1][1]=b
        else:intervals.append([a,b])
    select='+'.join(f'gte(t,{a:.9f})*lt(t,{b:.9f})' for a,b in intervals)
    # Subtract the cumulative removed duration at each kept interval. Using the
    # original PTS avoids cumulative rounding at joins and supports VFR input.
    removed=intervals[0][0];terms=[f'{removed:.9f}']
    for prev,cur in zip(intervals,intervals[1:]):
        gap=cur[0]-prev[1];terms.append(f'gte(T,{cur[0]:.9f})*{gap:.9f}')
    filt=f"[0:v:0]settb=AVTB,setpts=PTS-STARTPTS,select='{select}',setpts='PTS-({' + '.join(terms)})/TB'[v]"
    script=out/'video_edit_filter.txt';script.write_text(filt,encoding='utf-8')
    encoding=['-c:v','ffv1','-level','3'] if codec=='ffv1' else ['-c:v','libx264','-preset',preset,'-crf','16']
    print('Encoding edited target video with unmatched sections removed...',flush=True)
    try:
        vc.run([vc.binary('ffmpeg'),'-v','error','-nostdin','-y','-i',plan['target_video'],'-i',str(audio),'-/filter_complex',str(script),'-map','[v]','-map','1:a:0','-t',str(plan['duration']),'-fps_mode','passthrough','-enc_time_base','1:1000000',*encoding,'-c:a','copy','-map_metadata','-1','-map_chapters','-1',str(tmp)])
        if abs(vc.video_duration(tmp)-plan['duration'])>.15:raise RuntimeError('Edited video duration does not match synced audio.')
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)
    return dest
