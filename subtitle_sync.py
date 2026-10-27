"""AutoSync subtitle engine: reference captions, video editions, or target speech."""
import argparse,json,math,re,struct,subprocess,sys
from pathlib import Path
from subtitle_formats import Document,Cue
from subtitle_mapping import TimingMap,fit_map,text_anchors,normalized
import visual_core as vc

VIDEO_EXT={'.mkv','.mp4','.m4v','.mov','.avi','.wmv','.m2ts','.ts','.webm'}

def subtitle_input(path,track,out,label):
    path=Path(path).expanduser().resolve()
    if not path.is_file():raise ValueError(f'Missing {label}: {path}')
    if path.suffix.lower() not in VIDEO_EXT:return path
    streams=[s for s in vc.probe(path)['streams'] if s['codec_type']=='subtitle']
    if track<0 or track>=len(streams):raise ValueError(f'{label}: subtitle track {track} does not exist. Track numbering starts at 0.')
    codec=streams[track]['codec_name'];extension={'ass':'.ass','ssa':'.ssa','subrip':'.srt','webvtt':'.vtt','hdmv_pgs_subtitle':'.sup'}.get(codec)
    if not extension:raise ValueError(f'{codec} cannot be extracted losslessly by this subtitle adapter; export a supported sidecar first.')
    dest=out/(label+extension)
    vc.run([vc.binary('ffmpeg'),'-v','error','-nostdin','-i',str(path),'-map',f'0:s:{track}','-c:s','copy','-y',str(dest)])
    if codec in ('ass','ssa'):
        # Preserve container font attachments for the original ASS typesetting.
        fonts=out/(label+'_fonts');fonts.mkdir(exist_ok=True)
        for stream in vc.probe(path)['streams']:
            if stream.get('codec_type')!='attachment':continue
            name=Path(stream.get('tags',{}).get('filename','font.bin').replace('\\','/')).name
            if Path(name).suffix.lower() not in ('.ttf','.otf','.ttc'):continue
            destfont=fonts/(str(stream['index'])+'_'+name)
            subprocess.run([vc.binary('ffmpeg'),'-v','error','-nostdin',f'-dump_attachment:{stream["index"]}',str(destfont),'-i',str(path),'-t','0','-f','null','-'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            if not destfont.is_file() or not destfont.stat().st_size:raise RuntimeError('Could not preserve font attachment: '+name)
    return dest

def visual_map(args,out,duration):
    if not args.source_video or not args.target_media:raise ValueError('Encode-to-encode mode requires both source and target videos.')
    from video_geometry import detect_crop
    source_crop=args.source_crop or detect_crop(args.source_video);target_crop=args.target_crop or detect_crop(args.target_media)
    st,sf=vc.scenes(args.source_video,out,'subtitle_source_video',args.scene_threshold,source_crop)
    tt,tf=vc.scenes(args.target_media,out,'subtitle_target_video',args.scene_threshold,target_crop)
    matches=vc.matches(st,sf,tt,tf)
    rows=[(float(s),float(t),float(score)) for t,s,score in matches]
    print(f'Found {len(rows)} unique picture anchors.',flush=True)
    return fit_map(rows,duration,'visual',.25)

def transcribe(args,out):
    if not args.target_media:raise ValueError('Audio-only target mode requires a target video or audio file.')
    try:from faster_whisper import WhisperModel
    except ImportError:raise RuntimeError('Audio-to-subtitle matching requires Setup → Install subtitle AI (faster-whisper).')
    media=Path(args.target_media).resolve();streams=[s for s in vc.probe(media)['streams'] if s['codec_type']=='audio']
    if args.audio_track<0 or args.audio_track>=len(streams):raise ValueError('Target audio track does not exist.')
    wave=out/'target_speech.wav'
    vc.run([vc.binary('ffmpeg'),'-v','error','-nostdin','-i',str(media),'-map',f'0:a:{args.audio_track}','-ac','1','-ar','16000','-y',str(wave)])
    # ffmpeg decodes from the beginning. Preserve stream offset relative to the video timeline.
    probe=vc.probe(media);video=next((s for s in probe['streams'] if s['codec_type']=='video'),None)
    origin=float(video.get('start_time',0)) if video else float(probe['format'].get('start_time',0))
    shift=float(streams[args.audio_track].get('start_time',origin))-origin
    print('Transcribing target speech. First use downloads the selected Whisper model.',flush=True)
    model=WhisperModel(args.whisper_model,device='cpu',compute_type='int8')
    segments,info=model.transcribe(str(wave),word_timestamps=True,vad_filter=True,language=args.language or None)
    cues=[];words=[]
    try:
        for s in segments:
            cues.append(Cue(s.start+shift,s.end+shift,s.text,()))
            words.extend({'start':w.start+shift,'end':w.end+shift,'text':w.word,'probability':w.probability} for w in (s.words or []))
            print(f'Transcribed through {s.end:.1f}s',flush=True)
    finally:wave.unlink(missing_ok=True)
    (out/'transcript.json').write_text(json.dumps({'language':info.language,'words':words,'segments':[{'start':c.start,'end':c.end,'text':c.text} for c in cues]},ensure_ascii=False,indent=2),encoding='utf-8')
    return cues,words

def speech_anchors(cues,words):
    from difflib import SequenceMatcher
    tokens=[]
    for w in words:
        if w['probability']<.35:continue
        for t in normalized(w['text']).split():tokens.append((t,w['start'],w['end']))
    index={}
    for j,(t,*_) in enumerate(tokens):index.setdefault(t,[]).append(j)
    rows=[]
    for c in cues:
        if c.typeset:continue
        q=normalized(c.plain).split()
        if len(q)<3:continue
        starts={max(0,j-k) for k,t in enumerate(q[:3]) for j in index.get(t,[])}
        candidates=[]
        for j in starts:
            for n in range(max(2,len(q)-2),len(q)+4):
                part=tokens[j:j+n]
                if len(part)<2:continue
                score=SequenceMatcher(None,q,[x[0] for x in part],autojunk=False).ratio()
                candidates.append((score,j,len(part)))
        candidates.sort(reverse=True)
        if not candidates:continue
        score,j,n=candidates[0];others=[x[0] for x in candidates if abs(x[1]-j)>len(q)]
        if score>=.8 and (not others or score-max(others)>=.1):rows.append(((c.start+c.end)/2,(tokens[j][1]+tokens[j+n-1][2])/2,score))
    return rows

def retime_sup(path,output,mapping):
    raw=bytearray(Path(path).read_bytes());pos=0;review=[];last=-1;last_output=-1;active_start=None
    while pos<len(raw):
        if raw[pos:pos+2]!=b'PG' or pos+13>len(raw):raise ValueError('Not a standalone PGS SUP stream.')
        pts,dts=struct.unpack_from('>II',raw,pos+2);length=struct.unpack_from('>H',raw,pos+11)[0]
        if pos+13+length>len(raw):raise ValueError('Truncated SUP packet.')
        if pts<last:raise ValueError('SUP timestamp wrapping/reordering requires a dedicated demuxer.')
        if raw[pos+10]==0x16:
            if length<11:raise ValueError('Truncated SUP presentation composition.')
            if active_start is not None and mapping.interval(active_start,pts/90000) is None:raise ValueError('A displayed SUP subtitle crosses an unresolved cut. No partial bitmap output produced.')
            active_start=pts/90000 if raw[pos+23] else None
        last=pts;hit=mapping.interval(pts/90000,pts/90000)
        if hit is None:raise ValueError('SUP packet falls outside the timing map. No partial bitmap output produced.')
        mapped=round(hit[0]*90000)
        if not 0<=mapped<=0xffffffff:raise ValueError('Mapped SUP timestamp exceeds 32 bits.')
        if mapped<last_output:raise ValueError('Mapped SUP packets would be out of order.')
        last_output=mapped
        newdts=0
        if dts:
            d=mapping.interval(dts/90000,dts/90000)
            if d is None:raise ValueError('SUP decode timestamp is outside the map.')
            newdts=round(d[0]*90000)
            if not 0<=newdts<=0xffffffff:raise ValueError('SUP decode timestamp exceeds 32 bits.')
        struct.pack_into('>II',raw,pos+2,mapped,newdts)
        if hit[3]!='supported':review.append({'source_start':pts/90000,'status':'review','reason':hit[3]})
        pos+=13+length
    Path(output).write_bytes(raw);return review

def parser():
    p=argparse.ArgumentParser(description='AutoSync subtitles: preserve styling while transferring timing')
    p.add_argument('--mode',choices=['reference','encodes','audio','map','sushi'],default='reference')
    for k in ['subtitle','reference-subtitle','source-video','target-media','timing-map','out','source-crop','target-crop','language']:p.add_argument('--'+k,default='')
    for k in ['subtitle-track','reference-track','audio-track','source-audio-track']:p.add_argument('--'+k,type=int,default=0)
    p.add_argument('--sushi-window',type=int,default=10);p.add_argument('--sushi-max-window',type=int,default=30)
    p.add_argument('--encoding',default='utf-8-sig');p.add_argument('--source-fps',type=float);p.add_argument('--target-fps',type=float)
    p.add_argument('--semantic',action='store_true');p.add_argument('--scene-threshold',type=float,default=.15)
    p.add_argument('--whisper-model',default='small');return p

def run(args):
    if not args.out:raise ValueError('Choose a new output folder.')
    for name in ('source_fps','target_fps'):
        value=getattr(args,name)
        if value is not None and (not math.isfinite(value) or value<=0):raise ValueError(name+' must be a positive, finite frame rate.')
    if not math.isfinite(args.scene_threshold) or not 0<args.scene_threshold<1:raise ValueError('Scene threshold must be between 0 and 1.')
    out=Path(args.out).expanduser().resolve()
    if out.exists():raise ValueError('Output folder exists. Choose a new folder to avoid overwriting previous work.')
    out.mkdir(parents=True);print('AUTOSYNC_OUTPUT='+json.dumps(str(out)),flush=True)
    try:
        path=subtitle_input(args.subtitle,args.subtitle_track,out,'input_subtitle');sup=path.suffix.lower()=='.sup'
        if args.mode=='sushi':
            from sushi_sync import run_sushi
            return run_sushi(args,path,out)
        doc=None if sup else Document(path,args.encoding,args.source_fps)
        duration=max(c.end for c in doc.cues) if doc else vc.video_duration(args.source_video) if args.source_video else 86400
        if args.mode=='map':mapping=TimingMap.load(args.timing_map)
        elif args.mode=='encodes':mapping=visual_map(args,out,duration)
        else:
            if sup:raise ValueError('Bitmap subtitles have no searchable text. Use encode-to-encode or a saved map; OCR is not included.')
            if args.mode=='reference':
                refpath=subtitle_input(args.reference_subtitle,args.reference_track,out,'reference_subtitle')
                ref=Document(refpath,args.encoding,args.target_fps);rows=text_anchors(doc.cues,ref.cues,args.semantic);evidence='reference'
            else:
                ref,words=transcribe(args,out);rows=text_anchors(doc.cues,ref,True) if args.semantic else speech_anchors(doc.cues,words);evidence='speech'
            print(f'Found {len(rows)} text/speech anchors.',flush=True)
            (out/'anchors.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
            mapping=fit_map(rows,duration,evidence,.6 if args.mode=='reference' else .8)
        mapping.save(out/'subtitle_map.json')
        dest=out/('synced'+path.suffix.lower())
        report=retime_sup(path,dest,mapping) if sup else doc.write(dest,mapping,args.target_fps)
        needs_review=any(r['status'] in ('review','unmapped') for r in report)
        if needs_review:
            new=dest.with_name('DRAFT-review-required'+dest.suffix);dest.rename(new);dest=new
        summary={'mode':args.mode,'evidence':mapping.evidence,'output':str(dest),'needs_review':needs_review,'items':report,'notes':['Typesetting positions, drawing coordinates and script resolution are preserved, not spatially rescaled for crop/aspect changes.','Unmapped text cues retain ORIGINAL source timing in the DRAFT; do not mux it without resolving the report.','Picture matches can still be imperfect; check signs and scene boundaries.']}
        (out/'subtitle_report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        lines=[f'Output: {dest.name}',f'Timing evidence: {mapping.evidence}',f'Review required: {needs_review}',*summary['notes'],'']
        lines += [f"Cue {r.get('cue','bitmap')} @ source {r['source_start']:.3f}s: {r['status']} — {r.get('reason','')}" for r in report if r['status']!='mapped']
        (out/'report.txt').write_text('\n'.join(lines),encoding='utf-8');print('\n'.join(lines[:3]),flush=True)
        return 0
    except Exception as e:
        (out/'report.txt').write_text('Subtitle sync failed: '+str(e),encoding='utf-8');raise

def main():
    try:return run(parser().parse_args())
    except Exception as e:print('Subtitle sync failed: '+str(e),file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
