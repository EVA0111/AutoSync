"""Frame-accurate placement of subtitle lines, for typesetting.

A sign is right when it appears on the same picture: from the first target
frame showing what the first source frame showed, to the last. Mapping a
timestamp and rounding to centiseconds is not enough. At 23.976 fps a frame
lasts 41.7 ms, so a mapped time can easily round into the neighbouring frame,
and a sign that starts on a scene cut then flashes over the previous shot for
one frame. This module:

* maps the middle of the first and last displayed source FRAMES (not the raw
  times) and places the line on the target frames that contain them;
* writes ASS times that fall inside those frames, so renderers that show a
  line on frames with start <= pts < end show exactly those frames;
* snaps line edges that sit on a source scene cut to the matching target cut
  (the place a frame error is most visible);
* splits an ASS line that crosses an edit into one line per kept piece,
  re-basing \\move, \\t and \\fad so each piece shows what it showed before;
* converts between container time (subtitle timestamps) and first-frame time
  (the engine's maps) using each video's start time.
"""
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

import visual_core as vc
from subtitle_mapping import Section, TimingMap

EPS = 1e-6


@dataclass
class FrameGrid:
    """Frames at origin + n/fps on the container (subtitle) timeline."""
    fps: float
    origin: float = 0.
    cuts: np.ndarray = field(default_factory=lambda: np.zeros(0))  # first-frame-relative cut times
    audio_start: float = 0.  # container time of the first audio sample (plans count source audio from it)

    def first_shown(self, t):
        """First frame whose timestamp is >= t (the frame a line starting at t appears on)."""
        return math.ceil((t - self.origin) * self.fps - 1e-4)

    def time(self, n):
        return self.origin + n / self.fps

    def mid(self, n):
        """Middle of frame n, first-frame-relative (the engine's timeline)."""
        return (n + .5) / self.fps

    def frame_at(self, rel):
        """Frame showing at first-frame-relative time rel."""
        return math.floor(rel * self.fps + 1e-4)

    def ass_time(self, n):
        """Centisecond time t with time(n-1) < t <= time(n): the line starts (or ends) exactly at frame n."""
        t = math.floor(self.time(n) * 100 + 1e-6) / 100
        if t <= self.time(n - 1) + EPS:  # only at > 100 fps
            t = math.ceil(self.time(n - 1) * 100 + 1e-6) / 100
        return max(0., t)

    def cut_frame(self, rel, within):
        """Frame of the cut nearest to rel, if one lies within `within` frames."""
        if not len(self.cuts):
            return None
        i = int(np.argmin(np.abs(self.cuts - rel)))
        if abs(self.cuts[i] - rel) * self.fps <= within:
            # Cut times are frame timestamps, stored in whole ms by MKV: round to
            # the frame (floor would land on the previous one at 23.976 fps).
            return round(self.cuts[i] * self.fps)
        return None


def scene_cuts(path, threshold=.3):
    """First-frame-relative times of the first frame of every new shot (dark shots included)."""
    import subprocess
    vf = f"setpts=PTS-STARTPTS,scale=96:72,select='gt(scene,{threshold})',showinfo"
    p = subprocess.run([vc.binary('ffmpeg'), '-hide_banner', '-nostdin', '-i', str(path), '-map', '0:v:0', '-an',
                        '-vf', vf, '-f', 'null', '-'], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    log = p.stderr.decode('utf-8', 'replace')
    if p.returncode:
        raise RuntimeError(log[-4000:])
    return np.array([float(x) for x in re.findall(r'\bn:\s*\d+.*?\bpts_time:([\d.eE+\-]+)', log)])


def video_grid(path, out=None, name='', scene_threshold=.3):
    """Frame grid of a video's first track, with its scene cuts when `out` is given."""
    d = vc.probe(path)
    v = next(s for s in d['streams'] if s['codec_type'] == 'video')
    rate = v.get('avg_frame_rate') or v.get('r_frame_rate') or '0/0'
    a, b = map(float, rate.split('/'))
    if not b or not a:
        a, b = map(float, v.get('r_frame_rate', '0/1').split('/'))
    fps = a / b if b else 0.
    if not fps or not math.isfinite(fps):
        raise ValueError(f'Cannot read a frame rate for {path}.')
    # Snap to the standard rate it measures as (avg_frame_rate can be 23.9760001).
    for std in (24000 / 1001, 24., 25., 30000 / 1001, 30., 50., 60000 / 1001, 60.):
        if abs(fps - std) < .002:
            fps = std
    origin = float(v.get('start_time') or d['format'].get('start_time') or 0.)
    audio = [s for s in d['streams'] if s['codec_type'] == 'audio']
    audio_start = float(audio[0].get('start_time') or origin) if audio else origin
    cuts = np.zeros(0)
    if out is not None:
        print(f'Finding scene cuts in {name or path}…', flush=True)
        cuts = scene_cuts(path, scene_threshold)
    return FrameGrid(fps, origin, cuts, audio_start)


def plan_map(plan_path):
    """Source-to-target map from an AutoSync plan, as picture evidence when it is one.

    A plan maps target time to SOURCE AUDIO time. When the audio is the source
    video's own track, that is the picture mapping too (frame-verified by the
    picture timeline). Reused or reordered pieces overlap in source time; the
    longer one is kept and the others are left unmapped (reported, not guessed).
    """
    d = json.loads(Path(plan_path).read_text(encoding='utf-8-sig'))
    if 'segments' not in d:
        return TimingMap.load(plan_path)
    picture = bool(d.get('source_video')) and bool(d.get('target_video')) and \
        Path(str(d.get('audio') or '')).resolve() == Path(str(d['source_video'])).resolve()
    quality = 'supported' if picture else 'estimated: imported audio map; verify source subtitle alignment'
    pieces = []
    for s in d['segments']:
        if s.get('kind') != 'audio':
            continue
        speed = float(s.get('speed', 1.))
        a = float(s['source_start'])
        b = a + (float(s['target_end']) - float(s['target_start'])) * speed
        pieces.append(Section(a, b, 1 / speed, float(s['target_start']) - a / speed, [], quality))
    # Adjacent pieces often overlap by a few ms at a join (sub-frame jitter):
    # trim that at the join. Only longer overlaps are replays.
    pieces.sort(key=lambda s: s.start)
    for x, y in zip(pieces, pieces[1:]):
        if 0 < x.end - y.start <= .12:
            x.end = y.start
    kept = []
    for s in sorted(pieces, key=lambda s: s.end - s.start, reverse=True):
        if all(s.end <= k.start + EPS or s.start >= k.end - EPS for k in kept):
            kept.append(s)
    kept.sort(key=lambda s: s.start)
    # Target order must follow source order; drop out-of-order (reordered) pieces.
    ordered = []
    for s in kept:
        if ordered and s.scale * s.start + s.offset < ordered[-1].scale * ordered[-1].end + ordered[-1].offset - 1e-3:
            if s.end - s.start <= ordered[-1].end - ordered[-1].start:
                continue
            ordered.pop()
        ordered.append(s)
    # Consecutive pieces that continue each other (a split in the plan, not an
    # edit) become one section, so lines across them are not split.
    merged = []
    for s in ordered:
        p = merged[-1] if merged else None
        if p and abs(s.start - p.end) < .05 and abs(s.scale - p.scale) < 1e-6 and abs((s.scale * s.start + s.offset) - (p.scale * s.start + p.offset)) < .005:
            p.end = s.end
        else:
            merged.append(s)
    # A merge or a join jitter must not make target time run backwards.
    for x, y in zip(merged, merged[1:]):
        ty = y.scale * y.start + y.offset
        if x.scale * x.end + x.offset > ty:
            x.end = max(x.start, (ty - x.offset) / x.scale)
    m = TimingMap(merged, 'visual' if picture else 'audio-plan')
    # Plans map target picture time to source AUDIO time.
    m.source_domain, m.target_domain = 'audio', 'picture'
    return m


@dataclass
class Piece:
    start: float          # target container time
    end: float
    scale: float          # target seconds per source second
    quality: str
    skip_ms: float = 0.   # source milliseconds of the line before this piece (for re-basing tags)
    keep_in: bool = True  # the piece contains the line's start (fade-in stays)
    keep_out: bool = True  # the piece contains the line's end (fade-out stays)


class Placer:
    """Place cues on the target's frames through a source-to-target TimingMap."""

    def __init__(self, mapping, source, target, cut_snap_frames=1.5):
        self.mapping, self.src, self.tgt, self.within = mapping, source, target, cut_snap_frames

    def to_map(self, rel):
        """Source picture time -> the map's source time base."""
        dom = getattr(self.mapping, 'source_domain', 'container')
        return rel + {'picture': 0., 'container': self.src.origin, 'audio': self.src.origin - self.src.audio_start}[dom]

    def from_map(self, t):
        """The map's target time base -> target picture time."""
        return t - (self.tgt.origin if getattr(self.mapping, 'target_domain', 'container') == 'container' else 0.)

    def point(self, rel):
        x = self.to_map(rel)
        hit = self.mapping.interval(x, x)
        return None if hit is None else (self.from_map(hit[0]), hit[2], hit[3])

    def section_spans(self, a, b):
        """(lo, hi) source sub-intervals (picture time) of [a, b) covered by single map sections."""
        shift = self.to_map(0.)
        spans = []
        for s in self.mapping.sections:
            lo, hi = max(a, s.start - shift), min(b, s.end - shift)
            if hi - lo > EPS:
                spans.append((lo, hi))
        return spans

    def edge(self, src_frame, opening, span=None):
        """Target frame for a line edge at source frame `src_frame`.

        The first target frame showing source frame `src_frame` (opening) or
        anything after it (closing). A target frame shows the source picture
        nearest its time, so the change from frame k-1 to k falls at
        (k - 0.5)/fps: mapping that boundary covers every target frame of a
        picture shown twice (25 -> 29.97 fps, pulldown) and equals frame k at
        equal rates.
        """
        rel = (src_frame - .5) / self.src.fps
        # Look up inside this piece's map section (the boundary of its first frame
        # lies half a frame before it; joins can leave ms gaps) and follow the
        # section's rate from there.
        look = min(max(rel, span[0] + 1e-4), span[1] - 1e-4) if span else rel
        hit = self.point(look)
        if hit is None:
            return None, None
        n = math.ceil((hit[0] + (rel - look) * hit[1]) * self.tgt.fps - 1e-4)
        cut_rel = src_frame / self.src.fps
        if len(self.src.cuts) and np.min(np.abs(self.src.cuts - cut_rel)) * self.src.fps <= .5:
            mapped_cut = self.point(cut_rel) or self.point(self.src.mid(src_frame))
            if mapped_cut is not None:
                snapped = self.tgt.cut_frame(mapped_cut[0], self.within)
                if snapped is not None:
                    return snapped, hit
        return n, hit

    def place(self, start, end):
        """Pieces for a cue shown from `start` to `end` (source container times), or [] if unmapped."""
        k0, k1 = self.src.first_shown(start), self.src.first_shown(end)
        if k1 <= k0:  # shown on no source frame: map the raw times
            a, b = self.to_map(start - self.src.origin), self.to_map(end - self.src.origin)
            hit = self.mapping.interval(a, b)
            if hit is None:
                return []
            return [Piece(self.from_map(hit[0]) + self.tgt.origin, self.from_map(hit[1]) + self.tgt.origin, hit[2], hit[3])]
        a, b = k0 / self.src.fps, k1 / self.src.fps
        pieces = []
        spans = self.section_spans(a, b)
        for i, (lo, hi) in enumerate(spans):
            # Section ends carry float noise (109.96002 for a 109.96 s frame boundary):
            # snap within a millisecond, or the piece reaches into removed footage.
            snap = lambda x: math.ceil(x * self.src.fps - 1e-3 * self.src.fps)
            # The line's own edges only where its section reaches them.
            f0 = k0 if lo <= a + 1e-3 else snap(lo)
            f1 = k1 if hi >= b - 1e-3 else snap(hi)
            if f1 <= f0:
                continue
            n0, h0 = self.edge(f0, True, (lo, hi))
            n1, h1 = self.edge(f1, False, (lo, hi))
            if n0 is None or n1 is None or n1 <= n0:
                continue
            pieces.append(Piece(self.tgt.ass_time(n0), self.tgt.ass_time(n1), h0[1], h0[2],
                                skip_ms=max(0., (f0 - k0) / self.src.fps * 1000),
                                keep_in=f0 == k0, keep_out=f1 == k1))
        covered = sum(hi - lo for lo, hi in spans)
        if pieces and covered < (b - a) - 1.5 / self.src.fps:
            for p in pieces:
                p.quality = 'review: part of this line falls in footage the target does not have' \
                    if p.quality == 'supported' else p.quality
        return pieces


# --- ASS override tags in a piece that starts `skip` ms into the original line ---

def _num(v):
    return float(v.strip())


def _fmt(x):
    x = round(x, 2)
    return str(int(x)) if x == int(x) else str(x)


def rebase_ass(text, skip, keep_in=True, keep_out=True):
    """Shift line-relative tag times by -skip ms; returns (text, needs_review)."""
    review = False

    def move(m):
        nonlocal review
        args = m[1].split(',')
        if len(args) != 6:
            if skip > 0:
                review = True  # implicit-time \move spans the whole original line
            return m[0]
        x1, y1, x2, y2, t1, t2 = map(_num, args)
        t1, t2 = t1 - skip, t2 - skip
        if t2 <= 0:
            return f'\\pos({_fmt(x2)},{_fmt(y2)})'
        if t1 < 0:
            f = -t1 / (t2 - t1)
            x1, y1, t1 = x1 + (x2 - x1) * f, y1 + (y2 - y1) * f, 0.
        return f'\\move({_fmt(x1)},{_fmt(y1)},{_fmt(x2)},{_fmt(y2)},{round(t1)},{round(t2)})'

    def transform(m):
        nonlocal review
        t1, t2 = _num(m[1]) - skip, _num(m[2]) - skip
        if t2 <= 0:
            return '\\t(0,1,'
        if t1 < 0:
            review = True  # a partly finished transform restarts its acceleration curve
            t1 = 0
        return f'\\t({round(t1)},{round(t2)},'

    def fad(m):
        a, b = m[1].split(',')
        return f'\\fad({a.strip() if keep_in else 0},{b.strip() if keep_out else 0})'

    def block(m):
        nonlocal review
        x = m.group(0)
        if skip > 0:
            x = re.sub(r'\\move\(([^()]*)\)', move, x)
            x = re.sub(r'\\t\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*,', transform, x)
            if re.search(r'\\t\((?!\s*-?[\d.]+\s*,\s*-?[\d.]+\s*,)', x):
                review = True  # implicit-time \t spans the whole original line
            if re.search(r'\\fade\(', x):
                review = True
            if re.search(r'\\(?:kf|ko|kt|k|K)\d', x):
                review = True
        if not (keep_in and keep_out):
            x = re.sub(r'\\fad\(([^()]*)\)', fad, x)
        return x

    return re.sub(r'\{[^}]*\}', block, text), review
