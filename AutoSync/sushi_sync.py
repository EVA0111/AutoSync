"""Adapter for unmodified tp7/Sushi 0.5.1. Only its cue timings are imported."""
import json,math,os,re,subprocess
from pathlib import Path
from subtitle_formats import Document,timestamp
import visual_core as vc

class CueTimingMap:
    evidence='sushi-audio'
    def __init__(self,rows):self.rows=rows
    def interval(self,start,end):
        matches=[(a,b,x,y) for a,b,x,y in self.rows if abs(a-start)<1e-5 and abs(b-end)<1e-5]
        if not matches:return None
        a,b,x,y=matches[0]
        if any(abs(xx-x)>.002 or abs(yy-y)>.002 for _,_,xx,yy in matches):return None
        scale=(y-x)/(b-a) if b>a else 1
        if abs((y-x)-(b-a))<.002:scale=1
        return x,y,scale,'estimated: Sushi audio matching; review timing against the target'

def timed_wave(media,track,destination):
    if not media or not Path(media).is_file():raise ValueError('Sushi requires both source and target audio/video files.')
    info=vc.probe(media);audio=[s for s in info['streams'] if s['codec_type']=='audio']
    if not 0<=track<len(audio):raise ValueError(f'Audio track {track+1} does not exist in {Path(media).name}.')
    video=next((s for s in info['streams'] if s['codec_type']=='video'),None)
    origin=float((video or info.get('format',{})).get('start_time',0))
    shift=float(audio[track].get('start_time',origin))-origin
    filters='asetpts=PTS-STARTPTS'
    if shift>0:filters+=f',adelay={shift*1000:.6f}:all=1'
    elif shift<0:filters+=f',atrim=start={-shift:.9f},asetpts=PTS-STARTPTS'
    vc.run([vc.binary('ffmpeg'),'-v','error','-nostdin','-i',str(media),'-map',f'0:a:{track}','-vn','-af',filters,'-ac','1','-ar','12000','-c:a','pcm_s16le','-y',str(destination)])

def read_timings(path,cues):
    result=Document(path);by_id={}
    for c in result.cues:
        m=re.fullmatch(r'AutoSync cue (\d+)',c.plain)
        if not m:raise ValueError('Sushi returned an unexpected cue identifier.')
        key=int(m[1])
        if key in by_id:raise ValueError('Sushi returned duplicate cue identifiers.')
        by_id[key]=c
    if set(by_id)!=set(range(1,len(cues)+1)):raise ValueError('Sushi returned an incomplete cue list; no subtitle is exported.')
    rows=[]
    for i,c in enumerate(cues,1):
        target=by_id[i]
        if not all(math.isfinite(x) for x in (target.start,target.end)) or target.start<0 or target.end<=target.start:continue
        # This adapter does not enable keyframe snapping or intentional duration edits.
        if abs((target.end-target.start)-(c.end-c.start))>.01:continue
        rows.append((c.start,c.end,target.start,target.end))
    return rows

def run_sushi(args,path,out,executable=None,process_factory=subprocess.Popen):
    if Path(path).suffix.lower() not in ('.ass','.srt'):raise ValueError('Sushi mode currently supports ASS and SRT, including extracted container tracks.')
    if args.sushi_window<=0 or args.sushi_max_window<args.sushi_window:raise ValueError('Sushi maximum window must be at least the search window, and both must be positive.')
    root=Path(__file__).resolve().parent
    binary=Path(executable) if executable else next((p for p in [root/'sushi/sushi.exe',root/'vendor/sushi/sushi.exe'] if p.is_file()),None)
    if binary is None or not binary.is_file():raise RuntimeError('Bundled Sushi executable is missing. Extract the complete portable package.')
    if os.name!='nt' and executable is None:raise RuntimeError('Bundled Sushi 0.5.1 is a Windows executable.')
    doc=Document(path,args.encoding);proxy=out/'sushi-input.srt';raw=out/'sushi-timings.srt'
    proxy.write_text(''.join(f'{i}\n{timestamp(c.start)} --> {timestamp(c.end)}\nAutoSync cue {i:06}\n\n' for i,c in enumerate(doc.cues,1)),encoding='utf-8-sig')
    source=out/'sushi-source.wav';target=out/'sushi-target.wav'
    print('Decoding selected audio tracks for Sushi…',flush=True)
    timed_wave(args.source_video,args.source_audio_track,source);timed_wave(args.target_media,args.audio_track,target)
    command=[str(binary),'--src',str(source),'--dst',str(target),'--script',str(proxy),'--output',str(raw),'--chapters','none','--sample-rate','12000','--window',str(args.sushi_window),'--max-window',str(args.sushi_max_window)]
    print('Sushi audio matching…',flush=True)
    with (out/'sushi.log').open('w',encoding='utf-8') as log:
        child=process_factory(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',cwd=str(out),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        for line in child.stdout:log.write(line);log.flush();print(line.rstrip(),flush=True)
        code=child.wait()
    if code or not raw.is_file():raise RuntimeError('Sushi failed to produce subtitles. See Activity or sushi.log when reports are enabled.')
    rows=read_timings(raw,doc.cues);dest=out/('DRAFT-review-required'+Path(path).suffix.lower())
    items=doc.write(dest,CueTimingMap(rows))
    report={'mode':'sushi','evidence':'sushi-audio','output':str(dest),'needs_review':True,'items':items,'notes':['Sushi 0.5.1 audio matching. Source and target must share recognizable audio.','Original subtitle text/styles are retained; only returned cue timings are applied.','No keyframe snapping is enabled. Frame-by-frame typesetting and silent signs need visual review.']}
    (out/'subtitle_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'sushi_timing_rows.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    (out/'report.txt').write_text('\n'.join(report['notes'])+'\nAll Sushi results require review.\n',encoding='utf-8')
    source.unlink(missing_ok=True);target.unlink(missing_ok=True)
    print('Sushi finished. Review the DRAFT against the target video.',flush=True);return 0
