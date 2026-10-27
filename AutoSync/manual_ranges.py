"""Per-episode picture boundaries, expressed on each video's zero-based timeline."""
import math
import numpy as np


def validate(args, target_duration, source_duration, source_audio_duration, delay):
    start=getattr(args,'source_main_start',None);end=getattr(args,'source_main_end',None)
    if start is None and end is None:return None
    a,b=args.main_start,args.main_end
    if not (args.main_only or args.keep_target_op_ed):raise ValueError('Manual ranges require a main-episode output mode.')
    if any(v is None for v in (start,end,a,b)):raise ValueError('Source marks require both matching target marks.')
    if not all(math.isfinite(v) for v in (start,end,a,b,delay)):raise ValueError('Manual marks must be finite.')
    if not 0<=a<b<=target_duration or b-a<10:raise ValueError('Target marks must span at least 10 seconds within the video.')
    if not 0<=start<end<=source_duration+.001:raise ValueError('Source marks must be inside the source video.')
    sa,sb=start-delay,end-delay
    if sa<-.001 or sb>source_audio_duration+.1:raise ValueError('Source marks fall outside the selected audio after its delay. Adjust the marks or audio delay.')
    return dict(source_start=max(0.,sa),source_end=min(source_audio_duration,sb),target_start=a,target_end=b,source_video_start=start,source_video_end=end)


def select(anchors,bounds):
    if bounds is None:return anchors
    a,b=bounds['target_start'],bounds['target_end'];s,e=bounds['source_start'],bounds['source_end']
    return anchors[(anchors[:,0]>=a-10)&(anchors[:,0]<=b+10)&(anchors[:,1]>=s-10)&(anchors[:,1]<=e+10)].copy()


def apply(plan, bounds, anchors):
    """Record approximate guides without overriding automatic audio timing."""
    if bounds is None:return plan
    shift=plan.get('main_trim',{}).get('target_start',0.)
    points={}
    for side in ('start','end'):
        t=bounds['target_'+side]-shift
        trim=plan.get('main_trim') or plan.get('keep_target_op_ed')
        if trim:t=trim['target_'+side]-shift
        point=dict(target_estimate=bounds['target_'+side],source_estimate=bounds['source_'+side],target_used=t,status='estimated')
        sections=[s for s in plan['segments'] if s['target_start']<=t+1e-6 and s['target_end']>=t-1e-6 and s['kind']=='audio']
        if sections:
            section=sections[0 if side=='start' else -1]
            actual=section['source_start']+(t-section['target_start'])*section['speed']
            point.update(source_used=actual,source_adjustment=actual-bounds['source_'+side])
        points[side]=point
        plan.setdefault('review',[]).append(dict(start=max(0,t-1),end=min(plan.get('duration',t+1),t+1),confidence='estimated',reason='Manual '+side+' is an estimate; automatic audio timing retained. Check this boundary.'))
    plan['manual_range']={**bounds,'kind':'estimated','search_margin':10.,'points':points}
    return plan
