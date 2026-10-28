#!/usr/bin/env python3
"""Match scene changes between two editions, then retime source-aligned audio."""
import argparse, bisect, csv, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
os.environ.setdefault('OPENBLAS_NUM_THREADS', '2')
import numpy as np

ROOT = Path(__file__).resolve().parent

def binary(name):
    for p in [ROOT / (name + '.exe'), Path('C:/ffmpeg/bin') / (name + '.exe')]:
        if p.is_file(): return str(p)
    p = shutil.which(name)
    if not p: raise RuntimeError(f'{name} not found. Put ffmpeg.exe and ffprobe.exe beside this script or on PATH.')
    return p

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode: raise RuntimeError(p.stderr.decode(errors='replace')[-6000:])
    return p.stdout

def probe(path):
    return json.loads(run([binary('ffprobe'), '-v','error','-show_format','-show_streams','-of','json',str(path)]))

def video_duration(path):
    """Presentation span of the first video track, relative to its first PTS.

    Container duration may belong to a longer dub or subtitle track. Stream tags
    may also be stale after remuxing, so measure packets without decoding video.
    """
    d = probe(path); v = next(s for s in d['streams'] if s['codec_type']=='video')
    packets = json.loads(run([binary('ffprobe'), '-v', 'error', '-select_streams', 'v:0',
        '-show_packets', '-show_entries', 'packet=pts_time,duration_time',
        '-of', 'json', str(path)])).get('packets', [])
    fallback = None
    try:
        a, b = map(float, v.get('avg_frame_rate', '0/0').split('/'))
        if a > 0 and b > 0: fallback = b / a
    except (ValueError, ZeroDivisionError): pass
    return packet_video_span(packets, fallback)

def packet_video_span(packets, frame_duration=None):
    """Use PTS rather than decode order; retain VFR gaps and nonzero origins."""
    samples = []
    for packet in packets:
        try: pts = float(packet['pts_time'])
        except (KeyError, TypeError, ValueError):
            raise RuntimeError('Video packet has no presentation timestamp; cannot safely measure video duration.')
        if not np.isfinite(pts): raise RuntimeError('Invalid video presentation timestamp.')
        try: duration = float(packet.get('duration_time', 0))
        except (TypeError, ValueError): duration = 0.
        samples.append((pts, duration if np.isfinite(duration) and duration > 0 else 0.))
    if not samples: raise RuntimeError('No video packets found; cannot measure video duration.')
    samples.sort()
    times = sorted(set(t for t, _ in samples))
    gaps = {a: b-a for a, b in zip(times, times[1:])}
    # Missing final packet duration: prefer observed cadence, then declared FPS.
    steps = list(gaps.values())
    tail = float(np.median(steps[-30:])) if steps else frame_duration
    if not tail or not np.isfinite(tail) or tail <= 0:
        tail = next((d for _, d in reversed(samples) if d > 0), None)
    ends = []
    for t, duration in samples:
        duration = duration or gaps.get(t) or tail
        if duration is None: raise RuntimeError('Cannot determine final video frame duration.')
        ends.append(t + duration)
    result = max(ends) - times[0]
    if not np.isfinite(result) or result <= 0: raise RuntimeError('Invalid measured video duration.')
    return float(result)

def scenes(path, out, name, threshold, crop):
    """Keep original presentation timestamps relative to first video frame, including VFR."""
    raw, log = out/(name+'.gray'), out/(name+'.log')
    vf = 'setpts=PTS-STARTPTS,'
    if crop: vf += 'crop='+crop+','
    vf += f"scale=96:72,select='eq(n,0)+gt(scene,{threshold})',scale=32:24,format=gray,showinfo"
    print(f'Scanning {name}: {path}', flush=True)
    with log.open('wb') as err:
        p = subprocess.run([binary('ffmpeg'),'-hide_banner','-nostdin','-y','-i',str(path),'-map','0:v:0','-an','-vf',vf,'-fps_mode','vfr','-pix_fmt','gray','-f','rawvideo',str(raw)], stderr=err, stdout=subprocess.DEVNULL)
    if p.returncode: raise RuntimeError(log.read_text(errors='replace')[-4000:])
    times = np.array([float(x) for x in re.findall(r'\bn:\s*\d+.*?\bpts_time:([\d.eE+\-]+)',log.read_text(errors='replace'))])
    frames = np.fromfile(raw,np.uint8).reshape(-1,24,32); raw.unlink()
    if len(times)!=len(frames): raise RuntimeError('Frame timestamp count mismatch; see scan log.')
    # Ignore border/subtitle region and normalize brightness/contrast independently.
    frames = frames[:,2:20,2:30].astype(np.float32)
    flat = frames.reshape(len(frames),-1); std = flat.std(axis=1)
    flat -= flat.mean(axis=1,keepdims=True)
    flat /= np.maximum(np.linalg.norm(flat,axis=1,keepdims=True),1e-6)
    valid = std > 8
    print(f'{name}: {valid.sum()} usable scene frames',flush=True)
    return times[valid], flat[valid]

def matches(st,sf,tt,tf):
    if min(len(st),len(tt))<6: raise RuntimeError('Too few scene changes. Try --scene-threshold 0.08.')
    # Block the matrix multiplication to bound memory on long videos.
    best=[]; reverse=np.full(len(st),-1); reverse_score=np.full(len(st),-2.)
    for start in range(0,len(tt),128):
        sim=tf[start:start+128]@sf.T
        for row in range(len(sim)):
            j=int(np.argmax(sim[row])); score=float(sim[row,j]); alt=sim[row].copy()
            alt[np.abs(st-st[j])<2] = -2
            margin=score-float(alt.max())
            if score>=.86 and margin>=.035: best.append((start+row,j,score))
        local=sim.argmax(axis=0); vals=sim[local,np.arange(len(st))]
        m=vals>reverse_score; reverse[m]=local[m]+start;reverse_score[m]=vals[m]
    candidates=[(float(tt[i]),float(st[j]),score) for i,j,score in best if reverse[j]==i]
    if len(candidates)<6: raise RuntimeError('Too few unique matches. Check crops, edition, and scene threshold.')
    # Longest increasing subsequence rejects reversed/repeated-shot false matches.
    tails=[]; tail_idx=[]; prev=[-1]*len(candidates)
    for i,(_,s,_) in enumerate(candidates):
        k=bisect.bisect_left(tails,s)
        if k: prev[i]=tail_idx[k-1]
        if k==len(tails): tails.append(s);tail_idx.append(i)
        else: tails[k]=s;tail_idx[k]=i
    idx=tail_idx[-1]; keep=[]
    while idx>=0: keep.append(candidates[idx]);idx=prev[idx]
    return np.array(keep[::-1])

def fit(a):
    x=a[:,0];y=a[:,1];xm=x.mean();ym=y.mean()
    slope=float(np.dot(x-xm,y-ym)/max(np.dot(x-xm,x-xm),1e-12))
    offset=float(ym-slope*xm)
    return slope,offset,np.abs(y-(slope*x+offset))

