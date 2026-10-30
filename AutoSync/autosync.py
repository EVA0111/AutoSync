#!/usr/bin/env python3
"""Automatic per-episode visual/audio synchronization. No episode-specific timings."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
import argparse,csv,json,re,sys,tempfile,shutil,traceback,time
from pathlib import Path
import numpy as np
from scipy import signal,ndimage
import visual_core as vc
from cut_detection import locate_cut, source_cuts
from continuity_guard import source_rewinds, annotate_rewinds

RATE=50

def say(s): print(s,flush=True)
def audio_streams(path): return [s for s in vc.probe(path)['streams'] if s['codec_type']=='audio']
def wav_features(path,stream,work,label):
    say('Reading '+label+' audio...')
    pcm=work/(label+'.f32')
    vc.run([vc.binary('ffmpeg'),'-v','error','-nostdin','-y','-i',str(path),'-map',f'0:a:{stream}','-ac','1','-ar','8000','-f','f32le',str(pcm)])
    a=np.fromfile(pcm,np.float32);pcm.unlink()
    if len(a)<80000: raise RuntimeError('Audio is shorter than 10 seconds.')
    f,t,z=signal.stft(a,8000,nperseg=512,noverlap=352)
    edges=np.geomspace(150,3800,25)
    feat=np.array([np.log1p(np.abs(z[(f>=l)&(f<h)]).mean(axis=0)*1000) for l,h in zip(edges[:-1],edges[1:])],dtype=np.float32)
    feat-=ndimage.gaussian_filter1d(feat,100,axis=1)
    feat/=np.maximum(feat.std(axis=1,keepdims=True),.01)
    # Real energy, independent of normalized correlation, used to place edits quietly.
    n=len(a)//160;energy=np.mean(a[:n*160].reshape(n,160)**2,axis=1)
    return feat,energy,len(a)/8000

def correlation(source,query):
    if source.shape[1]<query.shape[1]: return np.empty(0)
    c=signal.fftconvolve(source,query[:,::-1],mode='valid',axes=1).sum(axis=0)
    energy=(source*source).sum(axis=0,dtype=np.float64);cs=np.r_[0,np.cumsum(energy)]
    n=query.shape[1];den=np.sqrt(np.maximum((cs[n:]-cs[:-n])*float((query*query).sum()),1e-12))
    return c/den

def peak(source,query):
    c=correlation(source,query)
    if len(c)==0:return None
    k=int(c.argmax());score=float(c[k]);alt=c.copy();alt[max(0,k-100):k+101]=-2
    return k,score,score-float(alt.max())

def estimate_rate(visual,source,ref):
    if len(visual)>=8:
        pairs=[]
        for i in range(len(visual)):
            for j in range(i+1,min(i+15,len(visual))):
                dt=visual[j,0]-visual[i,0]
                if 10<dt<90:
                    r=(visual[j,1]-visual[i,1])/dt
                    if .8<r<1.25:pairs.append(r)
        if pairs:
            med=float(np.median(pairs));known=np.array([1,25/24,25025/24000,24/25,24000/25025])
            near=float(known[np.abs(known-med).argmin()])
            if abs(near-med)<.0004:return near
            return med
    if source is None or ref is None: raise RuntimeError('No usable timing evidence.')
    choices=[1,25/24,25025/24000,24/25,24000/25025]
    trials=np.linspace(10,max(11,ref.shape[1]/50-20),9)
    scores=[]
    for speed in choices:
        scaled=ndimage.zoom(source,(1,1/speed),order=1)
        ss=[]
        for t in trials:
            q=ref[:,round(t*50):round((t+10)*50)];p=peak(scaled,q)
            if p:ss.append(p[1])
        scores.append(float(np.mean(sorted(ss)[-5:])))
    i=int(np.argmax(scores));say(f'Audio speed candidates: {dict(zip(choices,[round(x,3) for x in scores]))}')
    return choices[i]

def audio_anchors(source,ref,speed):
    scaled=ndimage.zoom(source,(1,1/speed),order=1);rows=[]
    times=list(np.arange(0,ref.shape[1]/RATE-8,6))
    for i,t in enumerate(times):
        q=ref[:,round(t*50):round((t+8)*50)];p=peak(scaled,q)
        if p:
            k,score,margin=p
            if score>=.30 and margin>=.055:rows.append([t+4,(k/50+4)*speed,score])
        if i%30==0:say(f'Matching audio: {i+1}/{len(times)} windows; {len(rows)} accepted')
    return np.asarray(rows,dtype=float).reshape(-1,3)

def remove_outliers(a,speed):
    if len(a)<4:return a
    keep=[]
    for i,x in enumerate(a):
        off=x[1]-speed*x[0];supported=0
        for j in range(max(0,i-5),min(len(a),i+6)):
            if i==j:continue
            y=a[j];dt=abs(x[0]-y[0])
            if dt<=100 and abs((y[1]-speed*y[0])-off)<.18+.002*dt:supported+=1
        if supported>=2:keep.append(x)
    a=np.asarray(keep).reshape(-1,3)
    if len(a)<4:raise RuntimeError('Too few consistent matches. Inputs may use different content or soundtracks.')
    # Reject isolated backwards correspondence; true reorderings are not supported.
    keep=[a[0]]
    for x in a[1:]:
        if x[1]>keep[-1][1]:keep.append(x)
    return np.array(keep)

def robust_fit(a,speed):
    # Median slope resists fade thresholds and a few inaccurate scene matches.
    slopes=[]
    if a[-1,0]-a[0,0]>=35:
        for i in range(len(a)):
            for j in range(i+1,len(a)):
                dt=a[j,0]-a[i,0]
                if dt>20:
                    val=(a[j,1]-a[i,1])/dt
                    if abs(val-speed)<.008:slopes.append(val)
    sp=float(np.median(slopes)) if slopes else speed
    off=float(np.median(a[:,1]-sp*a[:,0]))
    residual=np.abs(a[:,1]-sp*a[:,0]-off)
    return sp,off,float(np.quantile(residual,.9))

def group_anchors(a,speed):
    # A timing jump needs support on both sides; missing anchors alone never create gaps.
    offsets=a[:,1]-speed*a[:,0];splits=[0]
    for i in range(3,len(a)-2):
        if i-splits[-1]<3:continue
        left=offsets[max(splits[-1],i-4):i];right=offsets[i:i+3]
        if abs(np.median(right)-np.median(left))>.25 and np.ptp(right)<.16:
            splits.append(i)
    splits.append(len(a))
    return [a[l:h] for l,h in zip(splits[:-1],splits[1:]) if h>l]


def build_plan(anchors,speed,duration,source_length,ref,energy,source,refine_cut=None):
    groups=group_anchors(anchors,speed);models=[]
    for g in groups:
        sp,off,res=robust_fit(g,speed)
        models.append(dict(speed=sp,offset=off,first=float(g[0,0]),last=float(g[-1,0]),anchors=len(g),p90_residual=res))
    bounds=[0];notes=[];gaps=[]
    for left,right in zip(models[:-1],models[1:]):
        cut=locate_cut(left,right,ref,energy,source)
        if refine_cut is not None:cut=refine_cut(left,right,cut)
        if 'target_gap' in cut:gaps.append((*cut['target_gap'],cut.get('target_gap_kind','verified_gap'),cut.get('confidence')=='supported'))
        t=cut['time']
        bounds.append(max(bounds[-1]+.001,min(duration-.001,t)))
        t=bounds[-1]
        finish=cut.get('target_gap',[t,t])[1]
        removed=(right['speed']*finish+right['offset'])-(left['speed']*t+left['offset'])
        label=('Target-only scene/card: preserve target audio; ' if 'target_gap' in cut and
               cut.get('target_gap_kind')=='reference' else
               f'Source-only section: skip {removed:.3f}s; ' if removed>.25 else 'Timing change; ')
        notes.append(dict(start=max(0,min(t-1,cut['uncertainty_start'])),end=min(duration,max(t+1,cut['uncertainty_end'])),reason=label+cut['method']+'; preview the join',splice=t,confidence=cut['confidence']))
    bounds.append(duration);segments=[]
    for m,start,end in zip(models,bounds[:-1],bounds[1:]):
        ss=m['speed']*start+m['offset'];sp=m['speed']
        # Out-of-bounds regions are recorded, never replaced by synthetic silence.
        if ss<0:
            stop=min(end,start-ss/sp)
            segments.append(dict(kind='reference',target_start=start,target_end=stop,reason='source starts late'))
            notes.append(dict(start=start,end=stop,reason='source audio unavailable; reference fallback needed'))
            start=stop;ss=0
        supported_end=min(end,start+max(0,source_length-ss)/sp)
        if supported_end>start:segments.append(dict(kind='audio',target_start=start,target_end=supported_end,source_start=ss,speed=sp))
        if end>supported_end:
            segments.append(dict(kind='reference',target_start=supported_end,target_end=end,reason='source ends early'))
            notes.append(dict(start=supported_end,end=end,reason='source audio unavailable; reference fallback needed'))
    for ga,gb,gap_kind,verified_insert in gaps:
        updated=[]
        for section in segments:
            a,b=section['target_start'],section['target_end']
            if b<=ga or a>=gb:updated.append(section);continue
            if a<ga:updated.append(dict(section,target_end=ga))
            if b>gb:
                tail=dict(section,target_start=gb)
                if tail['kind']=='audio':tail['source_start']+=(gb-a)*tail['speed']
                updated.append(tail)
        updated.append(dict(kind=gap_kind,target_start=ga,target_end=gb,
            verified_insert=bool(verified_insert and gap_kind=='reference'),
            reason='Picture-verified target-only eyecatch/title-card; use selected target audio' if gap_kind=='reference' else 'Verified black pause with near-silent target audio'))
        segments=sorted(updated,key=lambda x:x['target_start'])
    # Audit unsupported spans but keep original-language audio playing using inferred mapping.
    points=np.r_[0,anchors[:,0],duration]
    for a,b in zip(points[:-1],points[1:]):
        if b-a>25:notes.append(dict(start=float(a),end=float(b),reason='sparse matches; estimated timing with source audio retained'))
    for m in models:
        if m['p90_residual']>.12:notes.append(dict(start=m['first'],end=m['last'],reason=f'fit scatter {m["p90_residual"]:.3f}s; inspect sync'))
    return segments,models,notes

def unresolved_cuts(plan):
    unresolved=[]
    for c in source_cuts(plan['segments']):
        notes=[r for r in plan.get('review',[]) if abs(r.get('splice',-999)-c['target_time'])<.05]
        if not notes or not any(r.get('confidence') in ('supported','manual') for r in notes):unresolved.append(c)
    return unresolved

def requires_explicit_reference_fallback(segments):
    """Verified target-only cards use target audio; other gaps need consent."""
    return any(s['kind']=='reference' and not s.get('verified_insert',False) for s in segments)


def render(plan,out,reference_fallback,allow_uncertain_cuts=False):
    rewinds=source_rewinds(plan.get('segments',[]))
    if rewinds and not allow_uncertain_cuts:
        details=', '.join(
            f"{x['target_time']:.3f}s (-{x['replayed_source_seconds']:.3f}s)"
            for x in rewinds)
        raise RuntimeError(
            'Unverified backwards source-audio joins at target '+details+
            '. No FLAC exported: joining these source spans would replay earlier '
            'audio. Review and correct the affected clips in Preview & Edit. '
            '--allow-uncertain-cuts explicitly overrides this safety check.')
    unresolved=unresolved_cuts(plan)
    if unresolved and not allow_uncertain_cuts:
        times=', '.join(f"{c['target_time']:.3f}s" for c in unresolved)
        raise RuntimeError('Source-only cut positions are unresolved at target '+times+
            '. No FLAC was exported. Read report.txt; rerun with source/target videos, or supply --cut-times with known target join times. --allow-uncertain-cuts explicitly permits estimated cuts.')
    cursor=0.0
    if not plan.get('segments'):raise RuntimeError('Plan contains no segments.')
    for section in plan['segments']:
        start=float(section['target_start']);end=float(section['target_end'])
        if not np.isfinite([start,end]).all() or end<=start or abs(start-cursor)>.0001:
            raise RuntimeError('Plan segments must be finite, contiguous, ordered, and non-overlapping.')
        if section.get('kind') not in ('audio','reference','verified_gap','target_outer'):raise RuntimeError('Unknown segment type.')
        if section['kind']=='audio':
            ss=float(section['source_start']);sp=float(section['speed'])
            if not np.isfinite([ss,sp]).all() or ss<0 or not .5<=sp<=2:raise RuntimeError('Invalid source position or speed in plan.')
        cursor=end
    if not np.isfinite(plan['duration']) or abs(cursor-plan['duration'])>.0001:raise RuntimeError('Plan does not cover its declared duration.')
    audio=plan['audio'];stream=int(plan['audio_stream']);ref=plan.get('reference');refstream=int(plan.get('reference_stream',0))
    references=[section for section in plan['segments'] if section['kind']=='reference']
    if references and (not ref or (not reference_fallback and
                       requires_explicit_reference_fallback(references))):
        raise RuntimeError('The target contains a section with no usable source audio. No silence or repeated source audio was written. '
                           'Only picture-verified target-only inserts automatically use target audio. '
                           'For other unmatched regions, enable --reference-fallback or inspect the reported interval.')
    if any(s['kind']=='verified_gap' for s in plan['segments']) and not ref:raise RuntimeError('Verified pause requires reference audio.')
    streams=audio_streams(audio);ch=int(streams[stream]['channels']);layout=streams[stream].get('channel_layout') or {1:'mono',2:'stereo',6:'5.1'}.get(ch)
    if not layout:raise RuntimeError('Unknown channel layout.')
    output=out/'synced.flac'
    if output.exists():raise RuntimeError('Output already exists. Use a new output folder.')
    with tempfile.TemporaryDirectory(prefix='render_',dir=out) as td:
        td=Path(td);parts=[]
        from pcm_audio import PCMCache
        pcm=PCMCache(td,ch)
        for i,s in enumerate(plan['segments']):
            start,end=s['target_start'],s['target_end'];dur=end-start
            if dur<=0:raise RuntimeError('Invalid segment duration.')
            n=round(end*48000)-round(start*48000)
            path,track,ss,sp=(audio,stream,s['source_start'],s['speed']) if s['kind']=='audio' else (ref,refstream,s.get('reference_target_start',start)-plan.get('reference_shift',0),1)
            if s['kind']=='target_outer':path,track,ss,sp=plan['target_video'],plan.get('outer_stream',0),s.get('reference_target_start',start)-plan.get('outer_shift',0),1.
            if ss<0:raise RuntimeError('Reference fallback begins before available reference audio.')
            # Do not hide short decodes with apad. Inspect decoded length before retiming.
            raw=td/'chunk.f32'
            pcm.cut(path,track,ss,dur*sp,raw)
            if s['kind']=='verified_gap':
                data=np.fromfile(raw,np.float32).reshape(-1,ch)
                blocks=[np.mean(z*z) for z in np.array_split(data,max(1,len(data)//960))]
                if np.mean(data*data)>4e-6 or max(blocks)>2e-5:raise RuntimeError('Target pause audio is no longer near-silent; refusing automatic replacement.')
            frames=raw.stat().st_size//(4*ch)
            if frames/48000<dur*sp-.10:raise RuntimeError(f'Source decode too short near {start:.2f}s. No silent padding was added.')
            if s['kind']=='target_outer' and i==len(plan['segments'])-1 and 0<n-frames<=4800:
                # Preserve target music timing when its audio ends a few ms before video.
                # This is the target's existing empty tail, never a missing source section.
                with raw.open('ab') as f:f.write(bytes((n-frames)*ch*4))
                frames=n
            dst=td/f'{i:04}.f32';parts.append(dst)
            # atempo can return a few ms less: constrain duration with exact final resampling,
            # never with silent padding. Overall length adjustment is normally <0.1%.
            stretched=td/'stretch.f32'
            if abs(sp-1.)<1e-10:shutil.copyfile(raw,stretched)
            else:
                vc.run([vc.binary('ffmpeg'),'-v','error','-nostdin','-y','-f','f32le','-ar','48000','-ac',str(ch),'-i',str(raw),'-af',f'atempo={sp:.10f}','-f','f32le',str(stretched)])
            x=np.memmap(stretched,dtype=np.float32,mode='r').reshape(-1,ch)
            if abs(len(x)/max(n,1)-1)>.02:raise RuntimeError('Unexpected time-stretch length error.')
            from fractions import Fraction
            ratio=Fraction((n*100000 + len(x)-1)//len(x),100000)
            fixed=np.array(x) if len(x)==n else signal.resample_poly(np.asarray(x),ratio.numerator,ratio.denominator,axis=0)[:n]
            if len(fixed)!=n:raise RuntimeError('Exact duration correction failed.')
            # Five-millisecond fades only at actual segment joins.
            fade=min(240,n//2)
            if i>0:fixed[:fade]*=np.linspace(0,1,fade,dtype=np.float32)[:,None]
            if i<len(plan['segments'])-1:fixed[-fade:]*=np.linspace(1,0,fade,dtype=np.float32)[:,None]
            fixed.astype(np.float32).tofile(dst);del x,fixed
            raw.unlink();stretched.unlink();say(f'Rendered {i+1}/{len(plan["segments"])} sections')
        joined=td/'joined.f32'
        with joined.open('wb') as dest:
            for part in parts:
                with part.open('rb') as src:shutil.copyfileobj(src,dest,4*1024*1024)
                part.unlink()
        temp=td/'synced.flac'
        vc.run([vc.binary('ffmpeg'),'-v','error','-nostdin','-y','-f','f32le','-ar','48000','-ac',str(ch),'-i',str(joined),'-c:a','flac','-sample_fmt','s32',str(temp)])
        actual=float(vc.probe(temp)['format']['duration'])
        if abs(actual-plan['duration'])>.002:raise RuntimeError('Export duration mismatch.')
        shutil.move(temp,output)
    return output

def verify_export(output,reference_features,anchors,out):
    say('Checking exported audio against matched reference windows...')
    feat,_,_=wav_features(output,0,out,'export_check')
    rows=[]
    selected=np.unique(np.linspace(0,len(anchors)-1,min(24,len(anchors))).astype(int))
    for i in selected:
        center=float(anchors[i,0]);start=max(.6,center-3)
        q=reference_features[:,round(start*50):round((start+6)*50)]
        lo=round((start-.5)*50);hi=round((start+6.5)*50)
        if q.shape[1]<200 or hi>feat.shape[1]:continue
        peak_result=peak(feat[:,lo:hi],q)
        if peak_result:
            k,score,_=peak_result
            rows.append([start,(lo+k)/50-start,score])
    with (out/'verification.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['target_seconds','measured_output_offset_seconds','correlation']);w.writerows(rows)
    good=[abs(r[1]) for r in rows if r[2]>=.30]
    if good:
        message=f'Export check: {len(good)} usable sampled windows, median offset {np.median(good):.3f}s; largest {max(good):.3f}s. This is sampled audio verification, not lip-sync verification.'
        if max(good)>.12:message+=' Some samples need spot-checking.'
    else:message='Export check inconclusive: no sufficiently strong sampled correlations.'
    with (out/'report.txt').open('a',encoding='utf-8') as f:f.write('\n\n'+message+'\n')
    say(message)

def run_job(job,args):
    from input_trims import prepare
    with prepare(job,args) as prepared:
        return _run_job(prepared,args)

def _run_job(job,args):
    audio=str(Path(job['audio']).resolve());reference=str(Path(job.get('reference') or job.get('target') or '').resolve())
    source_video=job.get('source','');target=job.get('target','');out=Path(job.get('out') or args.out).resolve()
    out.mkdir(parents=True,exist_ok=True)
    if (out/'plan.json').exists():raise RuntimeError('Output folder already has a plan. Choose a new folder to avoid mixing episodes.')
    stream=int(job.get('audio_stream') or 0);rs=int(job.get('reference_stream') or 0)
    delay=float(job.get('audio_delay') or 0);reference_delay=float(job.get('reference_delay') or 0)
    from input_trims import rebase
    input_meta=job.get('_input_trims',{})
    warnings=[];visual=np.empty((0,3));ref=None;energy=None
    sf,se,sl=wav_features(audio,stream,out,'source_audio')
    try:
        rf,re,rl=wav_features(reference,rs,out,'reference_audio');ref,energy=rf,re
    except (RuntimeError,ValueError,KeyError,OSError) as e:
        warnings.append('Reference audio unavailable: '+str(e));reference=None
    duration=vc.video_duration(target) if target else (ref.shape[1]/50 if ref is not None else 0)
    if 'target' in input_meta:duration=input_meta['target']['end']-input_meta['target']['start']
    if not target and ref is not None:duration=rl
    if duration<=0:raise RuntimeError('Target duration unavailable.')
    import manual_ranges
    source_bounds=manual_ranges.validate(args,duration,vc.video_duration(source_video) if getattr(args,'source_main_start',None) is not None else 0,sl,delay)
    # Embedded reference PTS relative to target video first PTS; external defaults to supplied delay.
    refshift=reference_delay
    if target and reference and Path(reference)==Path(target).resolve():
        p=vc.probe(target);v=next(x for x in p['streams'] if x['codec_type']=='video');a=[x for x in p['streams'] if x['codec_type']=='audio'][rs]
        refshift+=float(a.get('start_time',0))-float(v.get('start_time',0))
    source_crop=args.source_crop;target_crop=args.target_crop
    if source_video and target and not args.audio_only:
        try:
            from video_geometry import detect_crop
            if not source_crop:source_crop=detect_crop(source_video)
            if not target_crop:target_crop=detect_crop(target)
            say(f'Picture matching crops: source={source_crop or "full frame"}; target={target_crop or "full frame"}')
        except (RuntimeError,ValueError,KeyError,OSError) as e:warnings.append('Automatic border detection unavailable: '+str(e))
        try:
            st,sv=vc.scenes(source_video,out,'source_video',args.scene_threshold,source_crop)
            tt,tv=vc.scenes(target,out,'target_video',args.scene_threshold,target_crop)
            visual=vc.matches(st,sv,tt,tv);visual[:,1]-=delay
        except (RuntimeError,ValueError,KeyError,OSError) as e:warnings.append('Visual scan unavailable: '+str(e))
    visual=manual_ranges.select(visual,source_bounds)
    neural_visual=np.empty((0,3))
    neural_audio=np.empty((0,3))
    ai_mode=getattr(args,'sync_method','standard')=='ai_assisted'
    if ai_mode:
        from ai_sync import _dependencies,learned_visual_anchors
        _dependencies()  # Explicit failure with installation instructions; never silently fall back.
        say('AI-assisted synchronization enabled (AST acoustic model + optional DINOv2 scene rescue).')
        if len(visual)<8 and source_video and target and not args.audio_only:
            # The visual model only assists if classic scene matching could not
            # establish timing. Do not displace established visual evidence.
            try:
                trial_speed=estimate_rate(visual,sf,ref)
            except RuntimeError:
                trial_speed=1.  # Scene model can still recover rate from candidate pairs.
            neural_visual=learned_visual_anchors(source_video,target,trial_speed,delay,say)
            neural_visual=manual_ranges.select(neural_visual,source_bounds)
            if len(neural_visual)>=8:
                visual=neural_visual
                warnings.append('AI visual fallback used; review source/target frames at proposed joins.')
    speed=estimate_rate(visual,sf,ref);say(f'Estimated source/target speed: {speed:.9f}')
    aa=audio_anchors(sf,ref,speed) if ref is not None else np.empty((0,3))
    if len(aa):aa[:,0]+=refshift
    if source_video and target and not args.audio_only and not args.source_crop and not args.target_crop:
        from video_geometry import shared_picture_crop
        sc,tc,geometry=shared_picture_crop(source_video,target,aa,speed,source_crop,target_crop,delay)
        if geometry is not None:
            (out/'geometry_report.json').write_text(json.dumps(geometry,indent=2))
        if (sc,tc)!=(source_crop,target_crop):
            say(f'Verified edition framing crop: source={sc or "full frame"}; target={tc or "full frame"}')
            if sc!=source_crop:st,sv=vc.scenes(source_video,out,'source_video',args.scene_threshold,sc)
            if tc!=target_crop:tt,tv=vc.scenes(target,out,'target_video',args.scene_threshold,tc)
            source_crop,target_crop=sc,tc
            visual=vc.matches(st,sv,tt,tv);visual[:,1]-=delay
    visual=manual_ranges.select(visual,source_bounds)
    aa=manual_ranges.select(aa,source_bounds)
    if ai_mode and ref is not None:
        from ai_sync import learned_audio_anchors,combine_standard_and_learned
        neural_audio=learned_audio_anchors(audio,stream,reference,rs,sf,rf,speed,refshift,say)
        neural_audio=manual_ranges.select(neural_audio,source_bounds)
        original_count=len(aa)
        aa=combine_standard_and_learned(aa,neural_audio,speed)
        say(f'AI-assisted anchors: {len(neural_audio)} verified, {len(aa)-original_count} additional accepted.')
        warnings.append('AI model proposes matches only. Confirmed timing uses original audio correlation; review uncertain cuts.')
    # Use strong audio evidence for dubbing-specific offsets; visuals establish rate and fallback.
    if len(aa)>=8 and np.ptp(aa[:,0])>min(duration*.4,120):
        anchors=remove_outliers(aa,speed);method='audio matches, with visual rate estimate' if len(visual) else 'audio matches'
        if len(visual):
            offsets=[]
            for t,s,_ in anchors:
                j=int(np.argmin(abs(visual[:,0]-t)))
                if abs(visual[j,0]-t)<3:offsets.append(s-(visual[j,1]+speed*(t-visual[j,0])))
            if offsets and abs(float(np.median(offsets)))>.15:warnings.append('Audio and video mappings differ; soundtrack-specific audio matches take priority. Source dub may have an internal offset.')
    elif len(visual)>=8:
        anchors=remove_outliers(visual,speed);method='visual fallback'
        if len(aa)>=3:
            differences=[]
            for t,s,_ in aa:
                j=int(np.argmin(abs(anchors[:,0]-t)))
                if abs(anchors[j,0]-t)<10:differences.append(s-(anchors[j,1]+speed*(t-anchors[j,0])))
            if len(differences)>=3:
                anchors[:,1]+=float(np.median(differences));method+=' with audio offset calibration'
        warnings.append('Few reliable audio matches; verify the original audio is aligned to its source video.')
    else:raise RuntimeError('Not enough consistent audio or visual matches. No misleading output was produced. Check episode pairing, tracks, crops, and source alignment.')
    # Feature windows use decoded-reference coordinates; boundaries need the same timeline.
    if abs(refshift)>.001:
        warnings.append(f'Reference stream starts {refshift:.3f}s relative to target video; timestamps compensated.')
        # Feature padding/trimming to place reference on target timeline for splice detection only.
        shift=round(refshift*50)
        if shift>=0:ref=np.pad(ref,((0,0),(shift,0)));energy=np.pad(energy,(shift,0))
        else:ref=ref[:,-shift:];energy=energy[-shift:]
    manual_times=[float(x) for x in args.cut_times.split(',') if x.strip()]
    if any(not np.isfinite(x) or not 0<x<duration for x in manual_times):raise ValueError('Cut times must be finite seconds inside target duration.')
    used=set()
    def refine_cut(left,right,cut):
        lo=max(0,left['last']-4);hi=min(duration,right['first']+4)
        choices=[(i,t) for i,t in enumerate(manual_times) if lo<=t<=hi]
        if len(choices)>1:raise ValueError('Multiple manual cut times in one detected timing change.')
        if choices:
            i,t=choices[0]
            if i in used:raise ValueError('Manual cut time falls into overlapping searches.')
            used.add(i)
            return dict(time=t,confidence='manual',method='user supplied target join',uncertainty_start=t,uncertainty_end=t)
        if source_video and target and not args.audio_only and left['offset']-right['offset']>.3:
            from visual_cuts import calibrated_models,locate_target_insert
            try:
                vl,vr=calibrated_models(left,right,visual)
                inserted=locate_target_insert(vl,vr,source_video,target,se,delay,source_crop,target_crop,audio_models=(left,right))
                if inserted is not None:return inserted
            except (RuntimeError,ValueError,OSError) as e:
                warnings.append('Eyecatch/title-card verification unavailable: '+str(e))
        if cut['confidence']=='uncertain' and source_video and target and not args.audio_only:
            say(f'Checking pictures around uncertain cut: target {lo:.2f}–{hi:.2f}s')
            try:
                from visual_cuts import locate_visual_cut,calibrated_models,quiet_black_cut
                vl,vr=calibrated_models(left,right,visual)
                visual_cut=locate_visual_cut(vl,vr,source_video,target,delay,source_crop,target_crop,target_energy=energy)
                if visual_cut['confidence']=='uncertain':
                    quiet=quiet_black_cut(visual_cut,left,right,se,energy)
                    if quiet is not None:visual_cut=quiet
                if visual_cut['confidence']=='supported':return visual_cut
                warnings.append(f'Picture comparison also uncertain near {cut["time"]:.2f}s; cut requires review.')
            except (RuntimeError,ValueError,OSError) as e:warnings.append('Local picture cut check failed: '+str(e))
        return cut
    segments,models,review=build_plan(anchors,speed,duration,sl,ref,energy,sf,refine_cut)
    if len(used)!=len(manual_times):raise ValueError('A supplied --cut-times value is outside detected cut search intervals. Check target seconds against the report.')
    if ai_mode:method='AI-assisted: '+method
    plan=dict(source_crop=source_crop,target_crop=target_crop,source_cuts=source_cuts(segments),audio=audio,audio_stream=stream,reference=reference,reference_stream=rs,reference_shift=refshift,source_video=source_video,target_video=target,duration=duration,method=method,sync_method='ai_assisted' if ai_mode else 'standard',segments=segments,models=models,review=review,warnings=warnings)
    np.savez_compressed(out/'matching_diagnostics.npz',visual=visual,anchors=anchors)
    if args.main_only or args.keep_target_op_ed:
        from main_episode import detect_main,trim_plan,keep_target_outer
        (out/'full_plan.json').write_text(json.dumps(rebase(plan,input_meta),indent=2),encoding='utf-8')
        try:trim=detect_main(plan,visual,delay,args.main_start,args.main_end,source_features=sf,target_features=ref,keep_target_outer=bool(args.keep_target_op_ed))
        except (RuntimeError,ValueError,OSError) as e:
            (out/'trim_report.json').write_text(json.dumps({'status':'needs_review','reason':str(e)},indent=2))
            raise
        (out/'trim_report.json').write_text(json.dumps(trim,indent=2),encoding='utf-8')
        a,b=trim['target_start'],trim['target_end']
        anchors=anchors[(anchors[:,0]>=a)&(anchors[:,0]<b)].copy()
        if args.keep_target_op_ed:
            plan=keep_target_outer(plan,trim,int(job.get('outer_stream') or args.outer_stream))
            say(f'Keeping target opening/ending; source audio for target {a:.3f}–{b:.3f}s')
        else:
            plan=trim_plan(plan,trim);anchors[:,0]-=a
            if ref is not None:ref=ref[:,round(a*50):round(b*50)]
            say(f'Main episode: original target {a:.3f}–{b:.3f}s; trimmed duration {b-a:.3f}s')
        for side,boundary in trim['boundaries'].items():
            if boundary.get('estimate') is not None or boundary['status']=='estimated':
                t=boundary['time']-(a if args.main_only else 0.)
                plan['review'].append(dict(start=max(0,t-1),end=min(plan['duration'],t+1),confidence=boundary['status'],reason='Manual '+side+' estimate: '+boundary['reason']))
        original_anchors=anchors.copy()
        if args.main_only:original_anchors[:,0]+=a
        plan=manual_ranges.apply(plan,source_bounds,original_anchors)
        segments=plan['segments'];review=plan['review']
    if getattr(args,'remove_unmatched_video',False):
        from video_edits import remove_missing,map_anchors,protect_opening
        plan=protect_opening(plan,sf,ref,sl)
        plan=remove_missing(plan);anchors=map_anchors(anchors,plan)
        segments=plan['segments'];review=plan['review']
        (out/'video_edits.json').write_text(json.dumps(plan['video_edits'],indent=2),encoding='utf-8')
    plan=annotate_rewinds(rebase(plan,input_meta));segments=plan['segments'];review=plan['review']
    if 'audio' in input_meta:anchors[:,1]+=input_meta['audio']['offset']
    if input_meta:
        if plan.get('video_edits'):(out/'video_edits.json').write_text(json.dumps(plan['video_edits'],indent=2),encoding='utf-8')
        (out/'input_trims.json').write_text(json.dumps(input_meta,indent=2),encoding='utf-8')
    (out/'plan.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
    with (out/'matches.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['target_seconds','source_audio_seconds','similarity']);w.writerows(anchors)
    lines=[f'Method: {method}',f'{len(anchors)} accepted matches; {len(models)} timing sections.', 'Within the synced main section, unmatched areas retain source audio with estimated timing; verified near-silent black pauses may use target audio.', 'Similarity is not a calibrated probability. Spot-check estimated spans and edits.', *warnings,'','Review intervals:']
    if args.main_only:lines.insert(0,f"MAIN EPISODE: keep original target {plan['main_trim']['target_start']:.3f}–{plan['main_trim']['target_end']:.3f}s; output duration {plan['duration']:.3f}s. All review times below refer to the trimmed output.")
    if args.keep_target_op_ed:lines.insert(0,'KEEP TARGET OP/ED: complete target timeline; opening/ending use target audio. Main episode uses synced source audio.')
    for c in source_cuts(segments):lines.append(f"Skip source {c['source_start']:.3f}–{c['source_end']:.3f}s ({c['removed_seconds']:.3f}s) at target {c['target_time']:.3f}s")
    for c in source_rewinds(segments):
        lines.append(f"REPLAY RISK at target {c['target_time']:.3f}s: source rewinds {c['replayed_source_seconds']:.3f}s "
                     f"(estimated {c['estimated_target_equivalent_seconds']:.3f}s of repeated material); location of any target-only segment is not verified.")
    for item in review:lines.append(f"{item['start']:.2f}–{item['end']:.2f}s: {item['reason']}")
    if unresolved_cuts(plan):lines.append('DEFAULT EXPORT BLOCKED: unresolved source-only cut(s). Picture/audio evidence did not locate the join reliably.')
    if source_rewinds(segments):lines.append('DEFAULT EXPORT BLOCKED: backwards source-audio joins would repeat earlier audio. Open Preview & Edit to correct or explicitly override.')
    (out/'report.txt').write_text('\n'.join(lines),encoding='utf-8');say('\n'.join(lines))
    if not args.analyze_only:
        output=render(plan,out,args.reference_fallback,args.allow_uncertain_cuts)
        if not plan.get('video_edits') and ref is not None and method.startswith('audio matches'):verify_export(output,ref,anchors,out)
        if plan.get('video_edits'):
            from video_edits import export_video
            video=export_video(plan,output,out,args.video_codec,args.video_preset);say(f'Saved {video}. Use the synced FLAC with this edited video.')
        elif args.main_only:
            from main_episode import export_video
            video=export_video(plan,output,out,args.video_codec,args.video_preset);say(f'Saved {video}. Synced FLAC matches this trimmed video, not the original target.')
        elif 'target' in input_meta:
            from input_trims import export_target
            video=export_target(plan,output,out,args.video_codec,args.video_preset);say(f'Saved {video}. Synced FLAC fits this trimmed target.')
        elif args.keep_target_op_ed:
            from main_episode import export_full_video
            video=export_full_video(plan,output,out);say(f'Saved {video}. Complete target video with target opening/ending and synced source main audio.')
        else:say(f'Saved {output}. Mux at 0 ms delay.')
    return out

def dialog(title,directory=False,multiple=False):
    from tkinter import Tk,filedialog
    root=Tk();root.withdraw()
    f=filedialog.askdirectory if directory else (filedialog.askopenfilenames if multiple else filedialog.askopenfilename)
    result=f(title=title);root.destroy()
    if not result:raise RuntimeError('Selection cancelled.')
    return result

def choose_stream(path,label):
    streams=audio_streams(path)
    if not streams:raise RuntimeError(f'{label} has no audio. Select a separate reference track with --reference.')
    if len(streams)==1:return 0
    say(label+' tracks:')
    for i,s in enumerate(streams):say(f'{i}: {s.get("codec_name")} {s.get("tags",{}).get("language","und")} {s.get("tags",{}).get("title","")}')
    n=int(input('Choose audio track number: '));assert 0<=n<len(streams);return n

def episode_key(path):
    name=Path(path).stem
    name=re.split(r'(?i)_track\d+',name)[0]
    m=re.search(r'(?i)(?:s\d+[ ._-]*)?(?:ep?|episode)[ ._-]*(\d{1,3})(?!\d)',name)
    if not m:m=re.search(r'(?:^|[_ .-])(\d{1,3})(?=$|[_ .\-\[])',name)
    if not m:return None
    return int(m.group(1))

def index_files(paths):
    result={}
    for path in paths:
        key=episode_key(path)
        if key is None:raise RuntimeError(f'Cannot identify episode number: {path}. Use a jobs.csv file for custom names.')
        if key in result:raise RuntimeError(f'Two files have episode number {key}. Select one file per episode, or use jobs.csv.')
        result[key]=path
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version',action='version',version='AutoSync v1.2.0')
    for name in ['source','target','audio','reference']:p.add_argument('--'+name,default='')
    p.add_argument('--out',default='AutoSync_output')
    modes=p.add_mutually_exclusive_group()
    modes.add_argument('--keep-target-op-ed',action='store_true',help='Keep full target video and its opening/ending audio; sync source main episode')
    p.add_argument('--outer-stream',type=int,default=0,help='Target audio stream for opening/ending, default 0')
    modes.add_argument('--main-only',action='store_true',help='Remove differing outer sequences and export main_episode.mkv with synced audio')
    p.add_argument('--main-start',type=float,help='Estimate main start in original target seconds')
    p.add_argument('--main-end',type=float,help='Estimate exclusive main end in original target seconds')
    for side in ('source','target'):
        for edge in ('start','end'):p.add_argument('--'+side+'-trim-'+edge,type=float,help='Exact input trim '+edge+' before syncing (video seconds)')
    p.add_argument('--source-main-start',type=float,help='Source video start paired with --main-start')
    p.add_argument('--source-main-end',type=float,help='Exclusive source video end paired with --main-end')
    p.add_argument('--video-codec',choices=['h264','ffv1'],default='h264')
    p.add_argument('--video-preset',choices=['ultrafast','veryfast','medium'],default='veryfast')
    p.add_argument('--audio-stream',type=int,default=0);p.add_argument('--reference-stream',type=int,default=0)
    p.add_argument('--audio-delay',type=float,default=0);p.add_argument('--reference-delay',type=float,default=0)
    p.add_argument('--source-crop',default='');p.add_argument('--target-crop',default='')
    p.add_argument('--scene-threshold',type=float,default=.15)
    p.add_argument('--audio-only',action='store_true');p.add_argument('--analyze-only',action='store_true')
    p.add_argument('--sync-method',choices=['standard','ai_assisted'],default='standard',help='Optional pretrained AST audio features and DINOv2 visual rescue; install AI Sync in Settings first')
    p.add_argument('--remove-unmatched-video',action='store_true',help='Remove target sections with no source audio and export edited video + FLAC')
    p.add_argument('--reference-fallback',action='store_true',help='Use target soundtrack only for missing source bounds; may switch languages')
    p.add_argument('--cut-times',default='',help='Known target join times in seconds, comma separated; applies to detected cuts')
    p.add_argument('--allow-uncertain-cuts',action='store_true',help='Explicitly permit export with guessed source-only cut positions')
    p.add_argument('--batch',help='CSV with source,target,audio,reference,out and optional stream/delay columns')
    p.add_argument('--batch-picker',action='store_true');p.add_argument('--render-plan')
    args=p.parse_args()
    if args.reference_fallback and args.remove_unmatched_video:p.error('Choose reference fallback or remove unmatched video, not both.')
    if (args.main_start is not None or args.main_end is not None) and not (args.main_only or args.keep_target_op_ed):p.error('--main-start/--main-end require --main-only or --keep-target-op-ed')
    vc.binary('ffmpeg');vc.binary('ffprobe')
    if args.render_plan:
        path=Path(args.render_plan).resolve();plan=json.loads(path.read_text())
        if args.remove_unmatched_video:
            from video_edits import remove_missing
            plan=remove_missing(plan)
            (path.parent/'edited_plan.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
        audio=render(plan,path.parent,args.reference_fallback,args.allow_uncertain_cuts)
        if plan.get('video_edits'):
            from video_edits import export_video
            export_video(plan,audio,path.parent,args.video_codec,args.video_preset)
        elif plan.get('main_trim'):
            from main_episode import export_video
            export_video(plan,audio,path.parent,args.video_codec,args.video_preset)
        elif plan.get('input_trims',{}).get('target'):
            from input_trims import export_target
            export_target(plan,audio,path.parent,args.video_codec,args.video_preset)
        elif plan.get('keep_target_op_ed'):
            from main_episode import export_full_video
            export_full_video(plan,audio,path.parent)
        return
    jobs=[]
    if args.batch:
        base=Path(args.batch).resolve().parent
        with open(args.batch,encoding='utf-8-sig',newline='') as f:jobs=list(csv.DictReader(f))
        for j in jobs:
            for k in ['source','target','audio','reference','out']:
                if j.get(k) and not Path(j[k]).is_absolute():j[k]=str(base/j[k])
    elif args.batch_picker:
        sources=index_files(dialog('Select ORIGINAL videos for all episodes',multiple=True))
        targets=index_files(dialog('Select TARGET videos for all episodes',multiple=True))
        audios=index_files(dialog('Select ORIGINAL audio files for all episodes',multiple=True))
        if sources.keys()!=targets.keys() or sources.keys()!=audios.keys():raise RuntimeError('Episode lists differ. Select the same episode numbers in all three dialogs.')
        out=Path(dialog('Choose output parent folder',directory=True));say('Episode pairing:')
        for key in sorted(sources):
            say(f'{key:03}: {Path(sources[key]).name} -> {Path(targets[key]).name} + {Path(audios[key]).name}')
            jobs.append(dict(source=sources[key],target=targets[key],audio=audios[key],reference=targets[key],out=str(out/f'EP{key:03}'),audio_stream=0,reference_stream=0))
        say('Batch uses audio track 0. Edit jobs.csv or use the CLI for other tracks.')
        if input('Do these file pairs look correct? [y/N] ').lower()!='y':return
        csvpath=out/'jobs.csv'
        if csvpath.exists():csvpath=out/f'jobs_{int(time.time())}.csv'
        with csvpath.open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(jobs[0]));w.writeheader();w.writerows(jobs)
    else:
        if not args.audio:
            args.source=dialog('1. Original SOURCE video that matches your dub')
            args.target=dialog('2. TARGET video (with reference audio)')
            args.audio=dialog('3. ORIGINAL dub audio — do not select an already synced file')
            args.audio_stream=choose_stream(args.audio,'Source audio')
            if audio_streams(args.target):args.reference=args.target
            else:args.reference=dialog('4. Target video has no audio: choose its reference audio')
            args.reference_stream=choose_stream(args.reference,'Reference audio')
            args.out=str(Path(args.target).parent/(Path(args.target).stem+'_AutoSync_'+time.strftime('%Y%m%d_%H%M%S')))
        jobs=[vars(args)]
    from job_progress import emit
    failures=[];successes=[]
    for i,job in enumerate(jobs):
        emit(i,len(jobs),f'Audio: processing {i+1}/{len(jobs)}')
        say(f'\nEPISODE {i+1}/{len(jobs)}')
        try:successes.append(str(run_job(job,args)))
        except Exception as e:
            message=f'{job.get("target",job.get("audio"))}: {e}';failures.append(message);say('FAILED: '+message)
            out=Path(job.get('out') or args.out);out.mkdir(parents=True,exist_ok=True)
            (out/'error.txt').write_text(traceback.format_exc(),encoding='utf-8')
        emit(i+1,len(jobs),f'Audio: finished {i+1}/{len(jobs)}; {len(failures)} failed')
    say(f'\nFinished: {len(successes)} succeeded, {len(failures)} failed.')
    if failures:sys.exit(1)

if __name__=='__main__':
    try:main()
    except (RuntimeError,OSError,ValueError,AssertionError) as e:say('ERROR: '+str(e));sys.exit(1)
