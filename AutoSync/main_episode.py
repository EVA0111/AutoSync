"""Trim differing outer sequences using shared-picture evidence, not fixed OP lengths."""
import copy,json
from pathlib import Path
import numpy as np
from scipy.ndimage import uniform_filter1d
import visual_core as vc
from visual_cuts import frames,compare,RATE
from cut_detection import source_cuts


def boundary_from_scores(scores,dark,lo,side):
    scores=np.asarray(scores);n=len(scores)
    if n<10*RATE:raise ValueError('Too few pictures to verify a main-episode boundary.')
    objective=np.r_[0.,np.cumsum(scores-.75)]/RATE
    k=int(np.argmin(objective) if side=='start' else np.argmax(objective))
    matched=scores[k:min(n,k+10*RATE)] if side=='start' else scores[max(0,k-10*RATE):k]
    outside=scores[max(0,k-10*RATE):k] if side=='start' else scores[k:min(n,k+10*RATE)]
    # A common OP/ED cannot be identified semantically from correspondence alone.
    if (side=='start' and k<RATE) or (side=='end' and k>n-RATE):
        return dict(time=lo if side=='start' else lo+n/RATE,status='kept',reason='No clearly differing outer sequence detected')
    if len(matched)<5*RATE or len(outside)<2*RATE or matched.mean()<.83 or outside.mean()>.60:
        raise ValueError(f'{side} boundary is ambiguous; use --main-{side} with a verified target time.')
    removed=scores[:max(0,k-RATE)] if side=='start' else scores[min(n,k+RATE):]
    if len(removed)>=5*RATE and np.max(uniform_filter1d(removed,5*RATE))>.86:
        raise ValueError(f'Matching footage exists in the proposed {side} trim (possible cold open/epilogue); supply a manual boundary.')
    candidates=np.flatnonzero(abs(objective-objective[k])<.02)
    if len(candidates) and (candidates[-1]-candidates[0])/RATE>2:
        raise ValueError(f'{side} boundary has several plausible locations; supply a manual boundary.')
    # Keep the final fade to black. Do not extend into a later end card.
    edges=np.flatnonzero(np.diff(np.r_[False,dark[:n],False]))
    if side=='end':
        for a,b in zip(edges[::2],edges[1::2]):
            if a<=k+2 and b>=k and b-k<=RATE:k=int(b);break
    return dict(time=float(lo+k/RATE),status='supported',reason='Sustained shared pictures meet a differing outer sequence',matched_score=float(matched.mean()),outside_score=float(outside.mean()))


def refine_estimated_boundary(plan,visual,delay,estimate,side):
    if not np.isfinite(estimate) or not 0<=estimate<=plan['duration']:
        raise ValueError('Manual estimate is outside the video.')
    fallback=dict(time=estimate,estimate=estimate,status='estimated',reason='No verified nearby boundary; estimate retained for review')
    try:
        edge=visual[abs(visual[:,0]-estimate)<=15]
        if len(edge)<3 or np.ptp(edge[:,0])<2:return fallback
        models=plan.get('models',[])
        if not models:return fallback
        m=min(models,key=lambda m:abs((m.get('first',0)+m.get('last',plan['duration']))/2-estimate))
        offsets=edge[:,1]-m['speed']*edge[:,0];off=float(np.median(offsets))
        if np.count_nonzero(abs(offsets-off)<.1)<3:return fallback
        lo=max(0.,estimate-10);hi=min(plan['duration'],estimate+10)
        source_begin=m['speed']*lo+off+delay
        if source_begin<0:return fallback
        q,dark=frames(plan['target_video'],lo,hi-lo,crop=plan.get('target_crop',''),with_dark=True)
        x=frames(plan['source_video'],source_begin,hi-lo,m['speed'],plan.get('source_crop',''))
        result=boundary_from_scores(compare(q,x),dark,lo,side)
        if result['status']=='supported' and abs(result['time']-estimate)<=10:
            return dict(result,estimate=estimate)
    except (ValueError,RuntimeError,OSError) as error:
        fallback['detail']=str(error)
    return fallback


def detect_main(plan,visual,delay=0.,manual_start=None,manual_end=None):
    if not plan.get('source_video') or not plan.get('target_video'):raise ValueError('Main-episode detection requires both videos.')
    duration=plan['duration'];results={}
    from chapter_boundaries import explicit_outer_chapters
    chapters={} if manual_start is not None and manual_end is not None else explicit_outer_chapters(plan['target_video'],duration)
    for side,manual in [('start',manual_start),('end',manual_end)]:
        if manual is not None:
            results[side]=refine_estimated_boundary(plan,visual,delay,float(manual),side);continue
        if side in chapters:
            results[side]=chapters[side]
            print(f"Using explicit {side} chapter boundary: {results[side]['time']:.3f}s",flush=True)
            continue
        if len(visual)<8:raise ValueError('Not enough shared pictures for automatic OP/ending trimming.')
        m=plan['models'][0 if side=='start' else -1]
        edge=visual[:min(15,len(visual))] if side=='start' else visual[-min(15,len(visual)):]
        offsets=edge[:,1]-m['speed']*edge[:,0];off=float(np.median(offsets))
        good=edge[abs(offsets-off)<.1]
        if len(good)<5:raise ValueError('Unstable picture timing near '+side+'; use a manual boundary.')
        anchor=float(good[0 if side=='start' else -1,0])
        if side=='start':lo=0.;hi=min(duration,anchor+30.)
        else:lo=max(0.,anchor-40.);hi=duration
        if hi-lo>min(duration*.4,420):raise ValueError('Unmatched '+side+' is too long to safely classify as OP/ending.')
        print(f'Finding main-episode {side}: target {lo:.2f}–{hi:.2f}s',flush=True)
        source_begin=m['speed']*lo+off+delay
        if source_begin<0:raise ValueError('Source pictures unavailable at target start; supply --main-start.')
        q,dark=frames(plan['target_video'],lo,hi-lo,crop=plan.get('target_crop',''),with_dark=True)
        x=frames(plan['source_video'],source_begin,hi-lo,m['speed'],plan.get('source_crop',''))
        results[side]=boundary_from_scores(compare(q,x),dark,lo,side)
        if results[side]['status']=='kept':results[side]['time']=0. if side=='start' else duration
    if results['end']['time']-results['start']['time']<10:
        for side,manual in [('start',manual_start),('end',manual_end)]:
            if manual is not None:results[side]=dict(time=float(manual),status='estimated',reason='Refinement conflicts with the other boundary; original estimate retained')
    a,b=results['start']['time'],results['end']['time']
    if not np.isfinite([a,b]).all() or not 0<=a<b<=duration or b-a<10:raise ValueError('Invalid main-episode boundaries.')
    return dict(original_duration=duration,target_start=a,target_end=b,duration=b-a,boundaries=results)


def trim_plan(plan,trim):
    a,b=trim['target_start'],trim['target_end'];p=copy.deepcopy(plan);segments=[]
    for s in p['segments']:
        lo=max(a,s['target_start']);hi=min(b,s['target_end'])
        if hi<=lo:continue
        q=dict(s);q['target_start']=lo-a;q['target_end']=hi-a
        if q['kind']=='audio':q['source_start']=s['source_start']+(lo-s['target_start'])*s['speed']
        segments.append(q)
    review=[]
    for r in p.get('review',[]):
        lo=max(a,r['start']);hi=min(b,r['end'])
        if hi<=lo:continue
        q=dict(r);q.update(start=lo-a,end=hi-a)
        if 'splice' in q:q['splice']-=a
        review.append(q)
    p.update(segments=segments,review=review,duration=b-a,reference_shift=p.get('reference_shift',0)-a,main_trim=trim)
    p['source_cuts']=source_cuts(segments)
    for m in p.get('models',[]):m['offset']+=m['speed']*a;m['first']-=a;m['last']-=a
    return p


def export_video(plan,audio,out,codec='h264',preset='veryfast'):
    trim=plan['main_trim'];dest=Path(out)/'main_episode.mkv'
    if dest.exists():raise RuntimeError('main_episode.mkv already exists; use a new output folder.')
    tmp=Path(out)/'main_episode.partial.mkv'
    encoding=['-c:v','ffv1','-level','3'] if codec=='ffv1' else ['-c:v','libx264','-preset',preset,'-crf','16']
    print('Encoding frame-accurate trimmed target video...',flush=True)
    try:
        vc.run([vc.binary('ffmpeg'),'-v','error','-nostdin','-y','-ss',str(trim['target_start']+plan.get('input_trims',{}).get('target',{}).get('start',0.)),'-i',plan['target_video'],'-i',str(audio),'-map','0:v:0','-map','1:a:0','-t',str(plan['duration']),'-vf','setpts=PTS-STARTPTS','-fps_mode','passthrough',*encoding,'-c:a','copy','-map_metadata','-1','-map_chapters','-1',str(tmp)])
        d=vc.probe(tmp);actual=float(d['format']['duration'])
        if abs(actual-plan['duration'])>.1:raise RuntimeError('Trimmed video duration does not match trimmed audio.')
        tmp.replace(dest)
    finally:
        if tmp.exists():tmp.unlink()
    return dest


def keep_target_outer(plan,trim,stream=0):
    """Keep target timeline and replace only its main-episode soundtrack."""
    a,b=trim['target_start'],trim['target_end']
    p=trim_plan(plan,trim);p.pop('main_trim',None)
    for s in p['segments']:s['target_start']+=a;s['target_end']+=a
    for r in p['review']:
        r['start']+=a;r['end']+=a
        if 'splice' in r:r['splice']+=a
    p['models']=copy.deepcopy(plan['models'])
    p.update(duration=plan['duration'],reference_shift=plan.get('reference_shift',0),keep_target_op_ed=trim,outer_stream=stream)
    d=vc.probe(plan['target_video']);tracks=[s for s in d['streams'] if s['codec_type']=='audio']
    if not 0<=stream<len(tracks):raise ValueError('Selected target opening/ending audio stream does not exist.')
    v=next(s for s in d['streams'] if s['codec_type']=='video')
    p['outer_shift']=float(tracks[stream].get('start_time',0))-float(v.get('start_time',0))
    if a>0:p['segments'].insert(0,dict(kind='target_outer',target_start=0.,target_end=a,reason='Keep target opening audio'))
    if b<plan['duration']:p['segments'].append(dict(kind='target_outer',target_start=b,target_end=plan['duration'],reason='Keep target ending audio'))
    p['source_cuts']=source_cuts(p['segments'])
    return p


def export_full_video(plan,audio,out):
    """Mux the complete target picture without re-encoding."""
    dest=Path(out)/'full_episode.mkv';tmp=Path(out)/'full_episode.partial.mkv'
    if dest.exists():raise RuntimeError('full_episode.mkv already exists; use a new output folder.')
    try:
        video=next(s for s in vc.probe(plan['target_video'])['streams'] if s['codec_type']=='video')
        origin=float(video.get('start_time',0))
        vc.run([vc.binary('ffmpeg'),'-v','error','-nostdin','-y','-copyts','-itsoffset',str(-origin),'-i',plan['target_video'],'-i',str(audio),
                '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','copy','-map_metadata','-1','-map_chapters','0',str(tmp)])
        actual=vc.video_duration(tmp)
        if abs(actual-plan['duration'])>.15:raise RuntimeError('Full episode duration differs from target timeline.')
        tmp.replace(dest)
    finally:
        if tmp.exists():tmp.unlink()
    return dest
