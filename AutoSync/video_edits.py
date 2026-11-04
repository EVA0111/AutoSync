"""Remove target-only intervals, preserving source and target-outer audio positions."""
import copy
from pathlib import Path
import numpy as np
import visual_core as vc
from cut_detection import source_cuts




def same_file(a, b):
    """Compare paths as files: the engine resolves the reference path while the
    target keeps the caller's spelling (slash style, relative paths)."""
    if not a or not b:return False
    try:return Path(a).resolve()==Path(b).resolve()
    except (OSError,ValueError):return a==b


def recover_shared_opening(plan, source_features, target_features, source_length):
    """Replace only a *verified* target-audio opening with matching source audio.

    Unlike protect_opening this is safe for ordinary full-target output: when
    acoustic evidence is inconclusive, leave the plan unchanged. AI and
    Standard must use the same independent acoustic verification.
    """
    p=copy.deepcopy(plan)
    segments=p.get('segments') or []
    if not segments:return p
    opening=segments[0]
    a=float(opening['target_start']);b=float(opening['target_end'])
    if opening.get('kind')!='reference' or abs(a)>1e-3 or not .1<b<=45:
        return p
    from main_episode import opening_audio_correspondence
    speed=float((p.get('models') or [{}])[0].get('speed',1.))
    evidence=opening_audio_correspondence(source_features,target_features,b,speed)
    if not evidence or not evidence.get('matched'):return p
    source_start=float(evidence['offset'])
    if not np.isfinite(source_start) or source_start<0 or source_start+speed*b>float(source_length)+.025:
        return p
    segments[0]=dict(kind='audio',target_start=a,target_end=b,
                     source_start=source_start,speed=speed,
                     confidence='supported',
                     reason='Independently verified shared opening music from source')
    reason='Shared opening music: use aligned source audio, not target audio'
    p.setdefault('review',[]).append(dict(start=a,end=b,confidence='supported',
                                         reason=reason+'; listen at opening join'))
    p.setdefault('warnings',[]).append(reason)
    p['source_cuts']=source_cuts(segments)
    return p


def protect_opening(plan, source_features, target_features, source_length):
    """Protect unmatched target openings before destructive video trimming.

    Matching pictures are not required: alternate-language OPs may use different
    visuals over the same music. When a source-audio match is verified, map the
    opening to that source. If audio evidence is inconclusive, preserve the
    target's *video and existing music* for review instead of deleting it.
    Explicitly different audio may still be removed when requested by the user.
    """
    p=copy.deepcopy(plan)
    segments=p.get('segments') or []
    if not segments or not p.get('target_video'):return p
    opening=segments[0]
    a=float(opening['target_start']);b=float(opening['target_end'])
    if opening.get('kind')!='reference' or abs(a)>1e-3 or not .1<b<=45:
        return p
    speed=float((p.get('models') or [{}])[0].get('speed', 1.))
    from main_episode import opening_audio_correspondence
    evidence=opening_audio_correspondence(source_features,target_features,b,speed)
    outcome=None
    if evidence and evidence.get('matched'):
        source_start=float(evidence['offset'])
        if (source_start>=0 and source_start+speed*b<=float(source_length)+.025):
            segments[0]=dict(kind='audio',target_start=a,target_end=b,
                             source_start=source_start,speed=speed,
                             confidence='supported',reason='Shared opening music independently matched source audio')
            outcome='Shared opening music: kept target video and mapped matching source audio'
    if outcome is None and (evidence is None or not evidence.get('different')):
        # The program must not delete music on the strength of a picture
        # difference alone. A target-outer interval renders existing target
        # audio with the video even when remove-unmatched-video is selected.
        if same_file(p.get('reference'),p.get('target_video')):
            segments[0]=dict(kind='target_outer',target_start=a,target_end=b,
                             reference_target_start=a,
                             reason='Opening audio inconclusive; preserve target music instead of cutting video')
            p['outer_stream']=int(p.get('reference_stream',0))
            p['outer_shift']=float(p.get('reference_shift',0.))
            outcome='Opening match uncertain: kept target video and target audio for manual review'
        else:
            # Without usable target-audio evidence there is no safe replacement.
            # Refuse destructive pruning rather than silently throw away footage.
            raise ValueError('Opening cannot be safely removed: music match is inconclusive and target audio differs or is missing. Select the target audio track or review a non-destructive alignment.')
    if outcome is not None:
        p.setdefault('review',[]).append(dict(start=0.,end=b,confidence='estimated',
                                                  reason=outcome+'; listen near the opening join'))
        p.setdefault('warnings',[]).append(outcome)
        p['source_cuts']=source_cuts(segments)
    return p


def replaced_spans(section):
    """[(target_start, length, pieces)] of a segment's dub_replaced spans that still lie inside it."""
    out=[];a,b=section['target_start'],section['target_end'];u=a
    for x in section.get('dub_replaced') or []:
        ta=a+(x['source']-section['source_start'])/section['speed']
        if ta>=u-1e-6 and ta+x['length']<=b+1e-6:
            out.append((max(ta,u),x['length'],x['pieces']));u=ta+x['length']
    return out


def sway(piece,t,fill):
    """The shot stretch a held frame plays back and forth over ("motion" fill), if any."""
    w=piece.get('sway')
    if fill!='motion' or not w or w[1]-w[0]<.1:return {}
    return dict(sway=[t+w[0],t+w[1]])


def pingpong(t,lo,hi,N,fr):
    """[(first, count, backward)] frame runs inside [lo, hi] (frame indices from lo) that
    start at the held frame t and go forward, back, forward... for N frames."""
    M=int(round((hi-lo)*fr));pos=min(M,max(0,int(round((t-lo)*fr))));runs=[];step=1
    if M<2:return [(pos,N,False)]
    while N>0:
        if step>0:
            take=min(N,M-pos+1);runs.append((pos,take,False));pos=M-1;step=-1
        else:
            take=min(N,pos+1);runs.append((pos,take,True));pos=1;step=1
        N-=take
    return runs


def remove_missing(plan):
    if plan.get('video_edits'):return copy.deepcopy(plan)
    p=copy.deepcopy(plan);kept=[];removed=[];segments=[];cursor=0.;recreated=[]
    shift=p.get('main_trim',{}).get('target_start',0.)+p.get('input_trims',{}).get('target',{}).get('start',0.)
    rebuild=p.get('censorship',{}).get('recreate');last_audio=None
    fill=p.get('censorship',{}).get('fill','motion')
    for section in p['segments']:
        a,b=section['target_start'],section['target_end']
        if section['kind']=='audio':
            import censorship
            if rebuild and last_audio is not None and censorship.recreatable(last_audio,section):
                # Censored-dub "recreate": the dub's freeze or repeat, rebuilt from target
                # frames, carrying the dub audio the plan would otherwise skip.
                d=section['dub_pictures'];sp=section['speed'];start=cursor
                for piece in d['pieces']:
                    n=piece['length']/sp;t=a+piece['at']+shift
                    k=dict(start=a,end=a,output_start=cursor,recreated=True,length=n)
                    if piece['hold']:k.update(hold=t,**sway(piece,t,fill))
                    else:k.update(original_start=t,original_end=t+piece.get('span',n))
                    kept.append(k);cursor+=n
                segments.append(dict(kind='audio',target_start=start,target_end=cursor,
                                     source_start=section['source_start']-d['source_length'],speed=sp,
                                     dub_recreated=True,reference_target_start=a))
                recreated.append(dict(start=start,end=cursor,source_seconds=d['source_length']))
            last_audio=section
        # Censored-dub scenes marked "restore" keep their picture with target audio.
        if section['kind'] in ('reference','verified_gap') and section.get('censored_action')!='restore':
            removed.append(dict(start=a,end=b,reason=section.get('reason','No corresponding source audio')))
            continue
        if section['kind'] not in ('audio','target_outer','reference','verified_gap'):raise ValueError('Unknown segment kind.')
        u=a
        for ta,L,pieces in (replaced_spans(section) if rebuild else []):
            # Shots the dub replaced by a freeze or repeat, at the same length: the
            # picture is rebuilt from target frames, the audio is unchanged.
            if ta>u:kept.append(dict(start=u,end=ta,output_start=cursor+u-a,original_start=u+shift,original_end=ta+shift))
            o=cursor+ta-a;total=sum(x['length'] for x in pieces)
            for x in pieces:
                n=x['length']*L/total;t=ta+x['rel']+shift
                k=dict(start=ta,end=ta,output_start=o,recreated=True,length=n)
                if x['hold']:k.update(hold=t,**sway(x,t,fill))
                else:k.update(original_start=t,original_end=t+x.get('span',n))
                kept.append(k);o+=n
            recreated.append(dict(start=cursor+ta-a,end=cursor+ta-a+L,replaced=True))
            u=ta+L
        kept.append(dict(start=u,end=b,output_start=cursor+u-a,original_start=u+shift,original_end=b+shift))
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
    for x in recreated:
        reviews.append(dict(start=x['start'],end=x['end'],splice=x['start'],confidence='supported',
                            reason=(f"Shots the dub replaced ({x['end']-x['start']:.2f}s) rebuilt from the target frames it shows instead; preview" if x.get('replaced') else
                                    f"Dub-only material ({x['source_seconds']:.2f}s) rebuilt from held/repeated target frames; dub audio kept; preview")))
    p.update(segments=segments,duration=cursor,review=reviews,video_edits=dict(original_target_duration=p['duration'],kept=kept,removed=removed,recreated=recreated))
    p['source_cuts']=source_cuts(segments)
    return p


def map_anchors(anchors,plan):
    rows=[]
    for row in anchors:
        for k in plan['video_edits']['kept']:
            if k.get('media') or k.get('recreated') or k.get('fill'):continue
            if k['start']<=row[0]<k['end']:
                q=row.copy();q[0]+=k['output_start']-k['start'];rows.append(q);break
    return np.asarray(rows,dtype=float).reshape((-1,anchors.shape[1]))


IMAGE_EXT={'.png','.jpg','.jpeg','.bmp','.webp','.tif','.tiff'}


def target_picture(path):
    """Size, sample aspect, frame rate and pixel format every output piece is conformed to."""
    v=next(s for s in vc.probe(path)['streams'] if s['codec_type']=='video')
    sar=v.get('sample_aspect_ratio') or '1:1'
    if sar in ('0:1','N/A'):sar='1:1'
    rate=v.get('r_frame_rate') or v.get('avg_frame_rate') or '25/1'
    return int(v['width']),int(v['height']),sar.replace(':','/'),rate


def fill_pieces(plan):
    """Motion fills from Preview & Edit ({fill:'motion', hold}) as held pieces with their safe sway.

    The frames around the held one are looked at here, at export: it plays back
    and forth only over frames that differ from it in small interior parts
    (picture_timeline.sway_fine); otherwise it holds still.
    """
    kept=plan['video_edits']['kept']
    if not any(k.get('fill') and not k.get('recreated') for k in kept):return kept
    import picture_timeline as pt
    info=pt.stream_info(plan['target_video'],vc.binary('ffprobe'));out=[]
    for k in kept:
        if not k.get('fill') or k.get('recreated'):out.append(k);continue
        h=float(k['hold']);f=int(round((h-(info['origin']-info['start']))*pt.FPS))
        first=max(0,f-15);k=dict(k,recreated=True,length=float(k['end'])-float(k['start']))
        try:
            lo,hi=pt.sway_fine(pt.fine_decode(plan['target_video'],first,31,info,ffmpeg=vc.binary('ffmpeg')),f-first)
            if hi-lo>=3:k['sway']=[h+lo/pt.FPS,h+hi/pt.FPS]
        except (RuntimeError,ValueError,OSError):pass   # no frames to look at: hold still
        out.append(k)
    return out


def apply_fills(edited,fills):
    """Lay Preview & Edit motion fills (ranges in the analysed plan's time) onto an edited
    plan's video pieces, after censored-dub cuts and rebuilds: each target piece the fill
    overlaps is split and the overlap shows the fill."""
    if not fills:return edited
    e=copy.deepcopy(edited);out=[]
    for k in e['video_edits']['kept']:
        if k.get('media') or k.get('recreated') or k.get('fill'):out.append(k);continue
        u,end=float(k['start']),float(k['end']);pieces=[]
        for f in sorted(fills,key=lambda f:float(f['start'])):
            lo,hi=max(u,float(f['start'])),min(end,float(f['end']))
            if hi-lo<=1e-6:continue
            if lo>u:pieces.append((u,lo,None))
            pieces.append((lo,hi,float(f['hold'])));u=hi
        if not pieces:out.append(k);continue
        if end>u:pieces.append((u,end,None))
        for lo,hi,h in pieces:
            o=float(k['output_start'])+lo-float(k['start'])
            if h is None:
                a=float(k['original_start'])+lo-float(k['start'])
                out.append(dict(start=lo,end=hi,output_start=o,original_start=a,original_end=a+hi-lo))
            else:
                out.append(dict(start=lo,end=hi,output_start=o,original_start=h,original_end=h+hi-lo,fill='motion',hold=h))
    e['video_edits']['kept']=out
    return e


def media_graph(plan):
    """Inputs and filter graph for an output made of target ranges, imported clips and
    rebuilt dub material (held or repeated target frames), in output order."""
    from fractions import Fraction
    W,H,sar,rate=target_picture(plan['target_video'])
    fr=Fraction(rate)
    inputs=[['-i',plan['target_video']]];index={};chains=[];labels=[]
    # With rebuilt dub material (many short pieces) every target piece gets its
    # exact frame count from the output clock, so rounding cannot accumulate.
    kept=fill_pieces(plan)
    exact=any(k.get('recreated') for k in kept)
    def frames(start,length):
        o=Fraction(start).limit_denominator(10**6);e=o+Fraction(length).limit_denominator(10**6)
        return round(e*fr)-round(o*fr)
    for n,k in enumerate(kept):
        if exact and frames(k['output_start'],k['length'] if k.get('recreated') else k['end']-k['start'] if k.get('media') else k['original_end']-k['original_start'])<=0:
            continue                         # shorter than half a frame on the output clock
        if k.get('recreated') and k.get('sway'):
            # Held frame, kept moving: its shot plays forward and back around it.
            N=frames(k['output_start'],k['length']);lo,hi=k['sway'];h=.5/float(fr)
            for m,(first,count,back) in enumerate(pingpong(k['hold'],lo,hi,N,fr)):
                if back:
                    a=lo+(first-count+1)/float(fr)-h;b=lo+first/float(fr)+h;rev=',reverse'
                else:
                    a=lo+first/float(fr)-h;b=lo+(first+count-1)/float(fr)+h;rev=''
                chains.append(f'[0:v:0]trim=start={max(0.,a):.9f}:end={b:.9f},setpts=PTS-STARTPTS,scale={W}:{H},setsar={sar},format=yuv420p{rev},'
                              f'tpad=stop_mode=clone:stop={count},trim=end_frame={count},setpts=N/({rate})/TB[p{n}s{m}]')
                labels.append(f'[p{n}s{m}]')
            continue
        if k.get('recreated'):
            N=frames(k['output_start'],k['length'])
            # Half a frame either side: a piece shorter than a target frame still holds one.
            h=.5/float(fr)
            a,b=(k['hold']-h,k['hold']+h) if 'hold' in k else (k['original_start']-h,k['original_end']+h)
            # A repeat the dub played at another speed: stretch it over N frames.
            M=0 if 'hold' in k else max(1,round((k['original_end']-k['original_start'])*fr))
            stretch=f',setpts=PTS*{N/M:.6f},fps={rate}' if M and abs(N/M-1)>.08 else ''
            # The target's own frames, renumbered at its rate (an fps filter would
            # drop a lone frame at end of stream), then padded/cut to exactly N.
            chains.append(f'[0:v:0]trim=start={max(0.,a):.9f}:end={b:.9f},setpts=PTS-STARTPTS{stretch},scale={W}:{H},setsar={sar},format=yuv420p,'
                          f'tpad=stop_mode=clone:stop={N},trim=end_frame={N},setpts=N/({rate})/TB[p{n}]')
        elif k.get('media'):
            m=str(k['media'])
            if m not in index:
                index[m]=len(inputs)
                still=Path(m).suffix.lower() in IMAGE_EXT
                inputs.append(['-loop','1','-framerate',rate,'-i',m] if still else ['-i',m])
            i=index[m];a=float(k.get('media_start',0));b=a+k['end']-k['start']
            fit=(f'scale={W}:{H}:force_original_aspect_ratio=decrease:eval=frame,'
                 f'pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black')
            chains.append(f'[{i}:v:0]trim=start={a:.9f}:end={b:.9f},setpts=PTS-STARTPTS,{fit},setsar={sar},fps={rate},format=yuv420p[p{n}]')
        else:
            a,b=k['original_start'],k['original_end']
            fit=f',tpad=stop_mode=clone:stop=1,trim=end_frame={frames(k["output_start"],b-a)}' if exact else ''
            chains.append(f'[0:v:0]trim=start={a:.9f}:end={b:.9f},setpts=PTS-STARTPTS,scale={W}:{H},setsar={sar},fps={rate},format=yuv420p{fit}[p{n}]')
        labels.append(f'[p{n}]')
    # Every piece is at the target rate; one-frame rebuilt pieces carry no frame
    # duration, so concat would stack them on one timestamp. Renumber the output.
    renumber=f',setpts=N/({rate})/TB' if exact else ''
    chains.append(''.join(labels)+f'concat=n={len(labels)}:v=1:a=0{renumber}[v]')
    return inputs,';\n'.join(chains)


def export_video(plan,audio,out,codec='h264',preset='veryfast'):
    out=Path(out);dest=out/'edited_episode.mkv';tmp=out/'edited_episode.partial.mkv'
    if dest.exists():raise RuntimeError('Edited video already exists; use a new output folder.')
    if any(k.get('media') or k.get('recreated') or k.get('fill') for k in plan['video_edits']['kept']):
        return export_with_media(plan,audio,dest,tmp,codec,preset,out)
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
        vc.finish_partial(tmp,dest)
    finally:
        vc.discard_partial(tmp)
    return dest


def export_with_media(plan,audio,dest,tmp,codec,preset,out):
    """Concatenate target ranges and imported clips, each conformed to the target picture."""
    for k in plan['video_edits']['kept']:
        if k.get('media') and not Path(str(k['media'])).is_file():raise RuntimeError('Imported media file is missing: '+str(k['media']))
    inputs,graph=media_graph(plan)
    script=out/'video_edit_filter.txt';script.write_text(graph,encoding='utf-8')
    encoding=['-c:v','ffv1','-level','3'] if codec=='ffv1' else ['-c:v','libx264','-preset',preset,'-crf','16']
    print('Encoding edited video with imported clips...',flush=True)
    args=[x for pair in inputs for x in pair]
    try:
        vc.run([vc.binary('ffmpeg'),'-v','error','-nostdin','-y',*args,'-i',str(audio),'-/filter_complex',str(script),'-map','[v]','-map',f'{len(inputs)}:a:0','-t',str(plan['duration']),*encoding,'-c:a','copy','-map_metadata','-1','-map_chapters','-1',str(tmp)])
        if abs(vc.video_duration(tmp)-plan['duration'])>.15:raise RuntimeError('Edited video duration does not match synced audio.')
        vc.finish_partial(tmp,dest)
    finally:
        vc.discard_partial(tmp)
    return dest
