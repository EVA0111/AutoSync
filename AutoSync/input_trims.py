"""Exact input ranges, applied before matching; saved plans retain original media."""
import copy,json,math,tempfile
from pathlib import Path
from contextlib import contextmanager
import visual_core as vc

KEYS=tuple(f'{side}_trim_{edge}' for side in ('source','target') for edge in ('start','end'))

def range_for(job,args,side):
    values=[job.get(f'{side}_trim_{edge}',getattr(args,f'{side}_trim_{edge}',None)) for edge in ('start','end')]
    if all(v is None or v=='' for v in values):return None
    if any(v is None or v=='' for v in values):raise ValueError(f'{side.title()} trim requires both start and end.')
    a,b=map(float,values)
    if not all(map(math.isfinite,(a,b))) or not 0<=a<b:raise ValueError(f'Invalid {side} trim range.')
    return a,b

def trim_media(path,dest,bounds,tracks):
    data=vc.probe(path);v=next(s for s in data['streams'] if s['codec_type']=='video')
    audio=[s for s in data['streams'] if s['codec_type']=='audio']
    packets=json.loads(vc.run([vc.binary('ffprobe'),'-v','error','-select_streams','v:0','-show_packets','-show_entries','packet=pts_time,duration_time','-of','json',str(path)]))['packets']
    origin=min(float(p['pts_time']) for p in packets)
    duration=vc.video_duration(path);a,b=bounds
    if b>duration+.002:raise ValueError('Trim end is outside the video.')
    # The popup chooses exact frames. Reject off-frame API/CSV ranges rather
    # than silently shifting a requested boundary to a different frame.
    times=sorted(set(float(p['pts_time'])-origin for p in packets))+[duration]
    a1=min(times,key=lambda t:abs(t-a));b1=min(times,key=lambda t:abs(t-b))
    if max(abs(a-a1),abs(b-b1))>.002:raise ValueError('Trim boundaries must be video frame timestamps. Set them in the preview.')
    a,b=a1,b1
    if b<=a:raise ValueError('Trim must contain at least one frame.')
    aa,bb=origin+a,origin+b;filters=[f'[0:v:0]trim=start={aa:.9f}:end={bb:.9f},setpts=PTS-{aa:.9f}/TB[v]'];maps=['-map','[v]'];offsets={}
    for i,track in enumerate(tracks):
        if not 0<=track<len(audio):raise ValueError('Selected audio track is unavailable.')
        start=float(audio[track].get('start_time',0))
        offsets[track]=max(0.,aa-start)
        filters.append(f'[0:a:{track}]atrim=start={aa:.9f}:end={bb:.9f},asetpts=PTS-{aa:.9f}/TB[a{i}]')
        maps+=['-map',f'[a{i}]']
    seek=max(0.,aa-float(data.get('format',{}).get('start_time',0))-1.)
    print(f'Trimming video/audio before sync: {Path(path).name} {a:.3f}–{b:.3f}s',flush=True)
    vc.run([vc.binary('ffmpeg'),'-v','error','-nostdin','-y','-copyts','-ss',str(seek),'-t',str(bb-float(data.get('format',{}).get('start_time',0))-seek+.1),'-i',str(path),'-filter_complex',';'.join(filters),*maps,'-c:v','ffv1','-level','3','-c:a','flac','-fps_mode','passthrough','-enc_time_base:v','1:1000000','-map_metadata','-1','-map_chapters','-1',str(dest)])
    actual=json.loads(vc.run([vc.binary('ffprobe'),'-v','error','-select_streams','v:0','-show_packets','-show_entries','packet=pts_time','-of','json',str(dest)]))['packets']
    actual=sorted(float(p['pts_time']) for p in actual);expected=[t-a for t in times if a<=t<b]
    if len(actual)!=len(expected) or any(abs(x-y)>.002 for x,y in zip(actual,expected)):
        raise RuntimeError('Trimmed video frames do not match the exact selected range.')
    return dict(original=str(Path(path).resolve()),start=a,end=b,audio_offsets=offsets,tracks=tracks)

def external_audio(path,stream,start,end,delay,dest):
    # External audio delay is relative to the original video. Cut decoded PCM
    # so its remaining first sample maps to the marked video start.
    from pcm_audio import PCMCache
    data=vc.probe(path);tracks=[s for s in data['streams'] if s['codec_type']=='audio']
    if not 0<=stream<len(tracks):raise ValueError('Selected external audio track is unavailable.')
    offset=start-delay
    if offset<0:raise ValueError('Trim begins before the external audio is available; adjust its delay or range.')
    channels=int(tracks[stream]['channels']);raw=dest.with_suffix('.f32')
    PCMCache(dest.parent,channels).cut(path,stream,offset,end-start,raw)
    vc.run([vc.binary('ffmpeg'),'-v','error','-nostdin','-y','-f','f32le','-ar','48000','-ac',str(channels),'-i',str(raw),'-c:a','flac',str(dest)])
    raw.unlink()
    return offset

@contextmanager
def prepare(job,args):
    ranges={s:range_for(job,args,s) for s in ('source','target')}
    if not any(ranges.values()):yield job;return
    p=dict(job);meta={}
    work=Path(job.get('out') or getattr(args,'out','AutoSync_output')).resolve()
    work.mkdir(parents=True,exist_ok=True)
    if (work/'plan.json').exists():raise RuntimeError('Output folder already has a plan. Choose a new folder.')
    with tempfile.TemporaryDirectory(prefix='input-trim-',dir=work) as td:
        root=Path(td)
        for side,role,streamkey,delaykey in [('source','audio','audio_stream','audio_delay'),('target','reference','reference_stream','reference_delay')]:
            if not ranges[side]:continue
            original=str(Path(job[side]).resolve());apath=str(Path(job.get(role) or original).resolve());track=int(job.get(streamkey) or 0)
            outer=int(job.get('outer_stream') or getattr(args,'outer_stream',0));delay=float(job.get(delaykey) or 0)
            selected=set()
            silent_target=side=='target' and apath==original and not any(s['codec_type']=='audio' for s in vc.probe(original)['streams'])
            if apath==original and not silent_target:selected.add(track)
            if side=='target' and getattr(args,'keep_target_op_ed',False):selected.add(outer)
            tracks=sorted(selected);dest=root/(side+'.mkv')
            m=trim_media(original,dest,ranges[side],tracks);meta[side]=m;p[side]=str(dest)
            if silent_target:
                p[role]=str(dest)
                continue
            if apath==original:
                offset=m['audio_offsets'][track];p[role]=str(dest);p[streamkey]=tracks.index(track)
            else:
                audiofile=root/(side+'.flac');offset=external_audio(apath,track,m['start'],m['end'],delay,audiofile);p[role]=str(audiofile);p[streamkey]=0
            meta[role]=dict(original=apath,stream=track,offset=offset)
            if side=='source':p[delaykey]=delay+offset-m['start']
            else:
                p[delaykey]=delay if apath==original else 0.
                if getattr(args,'keep_target_op_ed',False):p['outer_stream']=str(tracks.index(outer));meta['outer']=dict(stream=outer,offset=m['audio_offsets'][outer])
        p['_input_trims']=meta
        yield p

def rebase(plan,meta):
    """Convert audio offsets back to originals; output times remain zero-based."""
    if not meta or plan.get('input_trims'):return plan
    p=copy.deepcopy(plan);p['input_trims']=meta
    if 'source' in meta:p['source_video']=meta['source']['original']
    if 'target' in meta:p['target_video']=meta['target']['original']
    if 'audio' in meta:
        a=meta['audio'];p.update(audio=a['original'],audio_stream=a['stream'])
        for s in p['segments']:
            if s['kind']=='audio':s['source_start']+=a['offset']
        for m in p.get('models',[]):m['offset']+=a['offset']
    if 'reference' in meta:
        r=meta['reference'];p.update(reference=r['original'],reference_stream=r['stream'],reference_shift=p.get('reference_shift',0)-r['offset'])
    if 'outer' in meta:p.update(outer_stream=meta['outer']['stream'],outer_shift=p.get('outer_shift',0)-meta['outer']['offset'])
    if 'target' in meta and p.get('video_edits'):
        for k in p['video_edits']['kept']:
            k['original_start']+=meta['target']['start'];k['original_end']+=meta['target']['start']
    from cut_detection import source_cuts
    p['source_cuts']=source_cuts(p['segments'])
    return p

def export_target(plan,audio,out,codec='h264',preset='veryfast'):
    from main_episode import export_video
    p=copy.deepcopy(plan);p['main_trim']=dict(target_start=0.,target_end=p['duration'])
    made=export_video(p,audio,out,codec,preset)
    dest=Path(out)/'trimmed_episode.mkv'
    if dest.exists():raise RuntimeError('Trimmed video already exists.')
    made.replace(dest);return dest
