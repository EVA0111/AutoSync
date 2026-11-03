#!/usr/bin/env python3
"""Synthetic target editions with exact ground truth, built from real footage.

The regression matrix uses real releases, so it only covers the edits those
releases happen to contain. This builds target videos from a real source
episode with KNOWN edits (cuts, inserted footage, reordered shots, recaps,
freezes, black frames, speed changes, frame-rate conversion, crops,
letterboxing, grading, noise, low bitrates, burned-in text, dub-like audio),
so the engine's timing can be scored against the true mapping everywhere.

    python stress_cases.py --source S.mp4 --insert OTHER.mp4 --out DIR [--only NAME,...]

Each case writes DIR/<name>/target.mkv and truth.json:
  {"speed": s, "pieces": [{"kind": "src"|"none"|"hold", "start": t0, "end": t1,
                           "source_start": a}]}
in target-video seconds (after any speed change); "src" maps t -> a + (t-t0)*s.
"""
import argparse
import json
import math
import subprocess
from pathlib import Path

FONT = 'C\\:/Windows/Fonts/arial.ttf'


def src(a, b): return ('src', a, b)
def ins(a, b): return ('ins', a, b)
def hold(t, d): return ('hold', t, d)
def black(d): return ('black', d)


# Pieces use source seconds; all cases stay inside the first ~6 minutes.
CASES = {
    'clean_copy': dict(pieces=[src(60, 360)]),
    'cuts': dict(pieces=[src(60, 110), src(116, 170), src(172.5, 230), src(238, 300), src(303, 360)]),
    'inserts': dict(pieces=[src(60, 120), ins(200, 203), src(120, 200), ins(300, 308), src(200, 280),
                            ins(400, 415), src(280, 360)]),
    'balanced_edits': dict(pieces=[src(60, 150), ins(500, 503), src(150, 158), src(161, 240), ins(520, 525),
                                   src(240, 247), src(252, 360)]),
    'reorder': dict(pieces=[src(60, 150), src(156, 162), src(150, 156), src(162, 250), src(262, 270),
                            src(250, 262), src(270, 360)]),
    'recap_new_opening': dict(pieces=[ins(10, 40), src(300, 320), src(60, 360)]),
    'pal_speedup': dict(pieces=[src(60, 150), src(155, 260), src(263, 360)], speed=25 / 24),
    'degraded_picture': dict(pieces=[src(60, 200), src(206, 360)], picture='degraded', crf=34),
    'aspect_crop': dict(pieces=[src(60, 200), src(204, 360)], picture='widescreen'),
    'holds_and_black': dict(pieces=[src(60, 120), hold(120, 2.0), src(120, 200), black(1.5), src(200, 280),
                                    hold(280, 1.2), src(280, 360)]),
    'dub_audio': dict(pieces=[src(60, 130), src(134, 250), src(252, 360)], audio='dub'),
    'many_small_cuts': dict(pieces=[src(60 + 20 * k + (0.2 + 0.06 * k if k else 0), 60 + 20 * (k + 1))
                                    for k in range(15)]),
    'fps_convert': dict(pieces=[src(60, 180), src(185, 360)], fps=30000 / 1001),
    # Target audio from another episode: nothing to hear-match, picture only.
    'foreign_audio': dict(pieces=[src(60, 140), src(147, 250), ins(600, 604), src(250, 360)], audio='foreign'),
    # PAL speed-up without pitch correction (the usual broadcast/DVD kind).
    'pal_pitch': dict(pieces=[src(60, 200), src(203, 360)], speed=25 / 24, audio='pitch'),
    # Variable frame rate: every 47th frame dropped, timestamps kept.
    'vfr_drops': dict(pieces=[src(60, 175), src(179, 360)], fps=None, picture='vfr'),
    'zoom_44k_mono': dict(pieces=[src(60, 230), src(233.4, 360)], picture='zoom', audio_fmt='44k_mono'),
    'long_insert_long_cut': dict(pieces=[src(60, 150), ins(700, 740), src(150, 210), src(235, 360)]),
    # 3:2 pulldown to interlaced 29.97 (build from a 23.976 source).
    'telecine': dict(pieces=[src(60, 190), src(194, 360)], fps=None, picture='telecine'),
}


def probe(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,width,height,r_frame_rate,start_time',
                          '-of', 'json', str(path)], stdout=subprocess.PIPE, check=True).stdout
    v = next(s for s in json.loads(out)['streams'] if s['codec_type'] == 'video')
    a, b = map(float, v['r_frame_rate'].split('/'))
    return int(v['width']), int(v['height']), a / b, float(v.get('start_time') or 0)


def build(case, source, insert, out):
    W, H, F, V0 = probe(source)
    # Every piece is a whole number of frames and starts on a source frame, so
    # the truth is exact (a fractional cut or a frame-rate conversion would
    # otherwise shift everything after it by up to a frame).
    frame_at = lambda t: math.ceil((t - V0) * F - 1e-6)
    speed = case.get('speed', 1.)
    graph, labels, truth, t = [], [], [], 0.
    for k, p in enumerate(case['pieces']):
        kind = p[0]
        if kind == 'src':
            ka, kb = frame_at(p[1]), frame_at(p[2])
            a, d = V0 + ka / F, (kb - ka) / F
            graph.append(f'[0:v]trim=start_frame={ka}:end_frame={kb},setpts=PTS-STARTPTS[v{k}]')
            graph.append(f'[0:a]atrim=start={a:.9f}:duration={d:.9f},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[a{k}]')
            truth.append(dict(kind='src', start=t, end=t + d, source_start=a))
        elif kind == 'ins':
            a, n = p[1], round((p[2] - p[1]) * F)
            d = n / F
            fit = f',scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={F}'
            graph.append(f'[1:v]trim=start={a},setpts=PTS-STARTPTS{fit},trim=end_frame={n}[v{k}]')
            graph.append(f'[1:a]atrim=start={a}:duration={d:.9f},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[a{k}]')
            truth.append(dict(kind='none', start=t, end=t + d, source_start=None))
        elif kind == 'hold':
            ka, n = frame_at(p[1]), round(p[2] * F)
            d = n / F
            graph.append(f'[0:v]trim=start_frame={ka}:end_frame={ka + 1},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop={n - 1}[v{k}]')
            graph.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={d:.9f}[a{k}]')
            truth.append(dict(kind='hold', start=t, end=t + d, source_start=V0 + ka / F))
        else:
            n = round(p[1] * F)
            d = n / F
            graph.append(f'color=black:s={W}x{H}:r={F},trim=end_frame={n}[v{k}]')
            graph.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={d:.9f}[a{k}]')
            truth.append(dict(kind='none', start=t, end=t + d, source_start=None))
        labels.append(f'[v{k}][a{k}]')
        t += truth[-1]['end'] - truth[-1]['start']
    n = len(case['pieces'])
    graph.append(''.join(labels) + f'concat=n={n}:v=1:a=1[cv][ca]')
    v = f'[cv]setpts=PTS/{speed}' if speed != 1 else '[cv]null'
    fps = case.get('fps', F * speed)
    if fps:
        v += f',fps={fps}'
    pic = case.get('picture')
    if pic == 'degraded':
        v += (f',crop=iw*0.9:ih*0.9,scale={W}:{int(H * .75) // 2 * 2},pad={W}:{H}:0:(oh-ih)/2,'
              'eq=brightness=0.06:contrast=1.15:saturation=1.3,noise=alls=12:allf=t,boxblur=1:1,'
              f"drawbox=x=iw-90:y=12:w=70:h=28:color=white@0.6:t=fill,"
              f"drawtext=fontfile='{FONT}':text='Burned-in subtitle line':x=(w-tw)/2:y=h-50:fontsize=20:fontcolor=white:borderw=2")
    elif pic == 'vfr':
        v += r",select='not(eq(mod(n\,47)\,0))'"
    elif pic == 'zoom':
        v += f',crop=iw*0.8:ih*0.8,scale={W}:{H},unsharp=5:5:0.8'
    elif pic == 'telecine':
        v += ',telecine=pattern=23'
    elif pic == 'widescreen':
        v += f',crop=iw:iw*9/16,scale=854:480,setsar=1'
    v += '[ov]'
    a = '[ca]'
    if case.get('audio') == 'foreign':
        # Same length, unrelated speech/music: the other episode from 0 s.
        graph.append(f'[1:a]atrim=0:{t},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[fa]')
        graph.append('[ca]anullsink')
        a = '[fa]'
    if speed != 1:
        a += f'asetrate={48000 * speed:.0f},aresample=48000,' if case.get('audio') == 'pitch' else f'atempo={speed},'
    if case.get('audio') == 'dub':
        a += 'highpass=f=300,lowpass=f=3400,volume=0.7,adelay=280|280,'
    a += 'aresample=44100,pan=mono|c0=0.5*c0+0.5*c1[oa]' if case.get('audio_fmt') == '44k_mono' else 'anull[oa]'
    graph += [v, a]
    out.mkdir(parents=True, exist_ok=True)
    script = out / 'graph.txt'
    script.write_text(';\n'.join(graph), encoding='utf-8')
    cmd = ['ffmpeg', '-v', 'error', '-y', '-i', str(source), '-i', str(insert), '-filter_complex_script', str(script),
           '-map', '[ov]', '-map', '[oa]', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', str(case.get('crf', 24)),
           '-c:a', 'aac', '-b:a', '128k', *(['-fps_mode', 'vfr'] if pic == 'vfr' else []), str(out / 'target.mkv')]
    subprocess.run(cmd, check=True)
    # Truth in target time after the speed change; source advances `speed` per target second.
    for piece in truth:
        piece['start'] /= speed; piece['end'] /= speed
    (out / 'truth.json').write_text(json.dumps(dict(speed=speed, pieces=truth), indent=1), encoding='utf-8')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--source', required=True); p.add_argument('--insert', required=True)
    p.add_argument('--out', required=True, type=Path); p.add_argument('--only')
    a = p.parse_args()
    names = a.only.split(',') if a.only else list(CASES)
    for name in names:
        if (a.out / name / 'truth.json').exists():
            continue
        print('building', name, flush=True)
        build(CASES[name], a.source, a.insert, a.out / name)


if __name__ == '__main__':
    main()
