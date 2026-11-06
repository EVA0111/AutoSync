"""Censored or re-edited dubs: find, report and act on the scenes a dub changed.

Older dubs (case 3: an Arabic dub of a Japanese original) often removed
scenes, or re-cut them from other footage. With the dub as the source and the
original as the target, the picture timeline already proves both:

* a REMOVED scene is target footage with no source picture: a target-audio
  section inside the episode;
* DUB-ONLY material is source footage the original lacks: a forward skip in
  the source between two matched sections (re-created or extended scenes).

Each removed scene gets an action on its segment, ``censored_action``:
``restore`` keeps the uncensored picture with the target's own audio; ``cut``
removes it from the exported video (the dub's edit). ``recreate`` cuts it
too and also rebuilds dub-only material that only freezes or repeats the
original's pictures (how such dubs cover a cut: the dialogue goes on over a
held frame or a repeated shot) from the original's own frames, so the dub's
audio plays without a skip. The engine finds those pictures
(``dub_pictures`` on the audio segment after the skip); material with no
counterpart in the original is still skipped. The segment is the
single source of truth, so the engine, a saved plan and Preview & Edit all
agree. Openings and endings are outer sections handled by the output mode,
not censorship, and are always kept here.
"""
import copy
import json
from pathlib import Path

ACTIONS = ('restore', 'cut')
FPS = 25                         # picture timeline frame grid (picture_timeline.FPS)
MODES = ACTIONS + ('recreate',)


def _outer(plan, i, s):
    segs = plan['segments']
    return bool(s.get('picture_outer')) or (i == 0 and s['target_start'] <= 1e-3) or \
        (i == len(segs) - 1 and abs(s['target_end'] - plan['duration']) <= 1e-3)


def _source_end(s):
    return s['source_start'] + (s['target_end'] - s['target_start']) * s['speed']


def annotate(plan, action='restore', fill='motion'):
    """Mark removed scenes with ``action`` and record a censorship summary."""
    if action not in MODES:
        raise ValueError('Censored-dub action must be restore, cut or recreate.')
    p = copy.deepcopy(plan)
    for i, s in enumerate(p['segments']):
        if s['kind'] in ('reference', 'verified_gap'):
            s['censored_action'] = 'restore' if _outer(p, i, s) else ('cut' if action == 'recreate' else action)
            if _outer(p, i, s):
                s['censored_outer'] = True
    if fill not in ('motion', 'freeze'):
        raise ValueError('Recreate fill must be motion or freeze.')
    # fill: a rebuilt freeze plays its shot back and forth ("motion") or holds one frame ("freeze").
    p['censorship'] = dict(default_action=action, smooth=True, recreate=action == 'recreate', fill=fill)
    return p


def scenes(plan):
    """Removed scenes and dub-only material, in plan (output) time."""
    segs, out = plan['segments'], []
    audio = [i for i, s in enumerate(segs) if s['kind'] == 'audio']
    marked = bool(plan.get('censorship'))
    for i, s in enumerate(segs):
        # Without the censored-dub option, picture-verified target-only footage inside the
        # episode is still reported; the export keeps it with the target's audio.
        unmarked = (not marked and s['kind'] == 'reference' and s.get('verified_insert') and not _outer(plan, i, s))
        if (s.get('censored_action') in ACTIONS and not s.get('censored_outer')) or unmarked:
            before = next((segs[j] for j in reversed(audio) if j < i), None)
            after = next((segs[j] for j in audio if j > i), None)
            replaced = after['source_start'] - _source_end(before) if before and after else 0.
            out.append(dict(kind='removed', start=s['target_start'], end=s['target_end'],
                            length=s['target_end'] - s['target_start'], action=s.get('censored_action', 'keep'),
                            dub_replacement_s=round(max(0., replaced), 3)))
    rebuild = plan.get('censorship', {}).get('recreate')
    for a, b in zip(audio, audio[1:]):
        skip = segs[b]['source_start'] - _source_end(segs[a])
        rebuilt = rebuild and recreatable(segs[a], segs[b])
        if b != a + 1 and not rebuilt:
            continue                      # across a removed scene: reported with that scene
        if skip > .25:
            out.append(dict(kind='dub_only', start=segs[b]['target_start'], end=segs[b]['target_start'],
                            length=round(skip, 3), action='recreate' if rebuilt else 'skip',
                            source_start=round(_source_end(segs[a]), 3), source_end=round(segs[b]['source_start'], 3)))
    for s in segs:
        if s['kind'] == 'audio':
            for x in s.get('dub_replaced') or []:
                t = s['target_start'] + (x['source'] - s['source_start']) / s['speed']
                out.append(dict(kind='replaced', start=round(t, 3), end=round(t + x['length'], 3), length=x['length'],
                                action='recreate' if rebuild else 'keep'))
            # Shots replaced by material the original lacks here (or shows far away): never rebuilt.
            for x in s.get('dub_own') or []:
                t = s['target_start'] + (x['source'] - s['source_start']) / s['speed']
                out.append(dict(kind='replaced', start=round(t, 3), end=round(t + x['length'], 3), length=x['length'],
                                action='keep', footage='elsewhere' if 'elsewhere' in x else 'own',
                                **({'elsewhere': x['elsewhere']} if 'elsewhere' in x else {})))
            for x in s.get('unexplained') or []:
                t = s['target_start'] + (x['source'] - s['source_start']) / s['speed']
                out.append(dict(kind='unexplained', start=round(t, 3), end=round(t + x['length'], 3),
                                length=x['length'], action='keep'))
    return sorted(out, key=lambda x: x['start'])


def picture_check(segments):
    """Share of the synced episode's informative pictures confirmed by picture (the safety net in
    autosync.dub_only_pictures). Removes the per-segment counts; None without a picture timeline."""
    total = ok = 0; seen = False
    for s in segments:
        c = s.pop('_check', None)
        if c:
            seen = True; total += c[0]; ok += c[1]
    if not seen:
        return None
    return dict(checked_s=round(total / FPS, 1), confirmed_s=round(ok / FPS, 1),
                confirmed_share=round(ok / total, 4) if total else 1.)


def unexplained_review(plan):
    """Review entries for pictures that differ from the original for no reason AutoSync can name."""
    return [dict(start=s['start'], end=s['end'], confidence='uncertain',
                 reason=f"Unexplained picture difference ({s['length']:.1f}s): the source shows a different picture "
                        f"than the original here and AutoSync cannot tell why (an edit of an unknown kind, or a "
                        f"timing problem); check it")
            for s in scenes(plan) if s['kind'] == 'unexplained']


def recreatable(before, after):
    """True when the dub-only material between two audio segments can be rebuilt from target pictures."""
    d = after.get('dub_pictures')
    return bool(d) and abs(after['source_start'] - _source_end(before) - d['source_length']) < .05


def needs_cut(plan):
    return any(s.get('censored_action') == 'cut' for s in plan.get('segments', [])) or         bool(plan.get('censorship', {}).get('recreate'))


def clock(t):
    t = max(0., t)
    return f'{int(t // 60)}:{t % 60:05.2f}'


def report(plan):
    found = scenes(plan)
    removed = [s for s in found if s['kind'] == 'removed']
    extra = [s for s in found if s['kind'] == 'dub_only']
    swapped = [s for s in found if s['kind'] == 'replaced']
    odd = [s for s in found if s['kind'] == 'unexplained']
    head = 'CENSORED / EDITED DUB' if plan.get('censorship') else 'EDITS IN THE SOURCE (censored-dub option off)'
    lines = [f"{head}: {len(removed)} scene(s) the dub removed "
             f"({sum(s['length'] for s in removed):.1f} s), {len(extra)} spot(s) of dub-only material "
             f"({sum(s['length'] for s in extra):.1f} s), {len(swapped)} shot(s) it replaced with other footage "
             f"({sum(s['length'] for s in swapped):.1f} s)"
             + (f", {len(odd)} unexplained picture difference(s) ({sum(s['length'] for s in odd):.1f} s)" if odd else '')
             + ". Times are output times."]
    for s in found:
        if s['kind'] == 'removed':
            what = {'restore': 'restored with the original audio', 'cut': 'cut from the video'}.get(
                s['action'], 'kept with the original audio')
            extra_note = f"; the dub shows {s['dub_replacement_s']:.1f} s of other footage here" if s['dub_replacement_s'] > .25 else ''
            lines.append(f"  {clock(s['start'])}–{clock(s['end'])}  removed by the dub ({s['length']:.1f} s): {what}{extra_note}")
        elif s['kind'] == 'replaced':
            what = ('rebuilt from the target frames the dub shows' if s['action'] == 'recreate'
                    else 'the original shot is kept (the dub audio fits either)')
            by = {'own': " with the dub's own footage",
                  'elsewhere': f" with a shot from {clock(s.get('elsewhere', 0.))} of the original"}.get(s.get('footage'), '')
            lines.append(f"  {clock(s['start'])}–{clock(s['end'])}  shot replaced by the dub{by} ({s['length']:.1f} s): {what}")
        elif s['kind'] == 'unexplained':
            lines.append(f"  {clock(s['start'])}–{clock(s['end'])}  UNEXPLAINED picture difference ({s['length']:.1f} s): "
                         f"check it; the timing is kept")
        else:
            what = ('rebuilt from held or repeated frames; dub audio kept' if s['action'] == 'recreate'
                    else 'no original picture; dub audio skipped')
            lines.append(f"  {clock(s['start'])}  dub-only material ({s['length']:.1f} s, source "
                         f"{clock(s['source_start'])}–{clock(s['source_end'])}): {what}")
    return lines


def write_report(plan, out):
    out = Path(out)
    (out / 'censorship.json').write_text(json.dumps(scenes(plan), indent=2), encoding='utf-8')
    (out / 'censorship_report.txt').write_text('\n'.join(report(plan)) + '\n', encoding='utf-8')


def restored_subtitles(subtitle_path, rendered_plan, out, original_shift=0.):
    """Write restored_scenes.srt: only cues inside scenes restored with the original audio.

    rendered_plan: the plan actually rendered (after any cuts), in output time;
    a kept segment's ``reference_target_start`` (or its own start) is its time
    in the analysed plan, and ``original_shift`` converts that to the original
    subtitle's clock (main-episode trim, input trims).
    """
    from subtitle_formats import Document, timestamp
    doc = Document(subtitle_path)
    cues = []
    for s in rendered_plan['segments']:
        if s.get('censored_action') != 'restore' or s.get('censored_outer'):
            continue
        a, b = s['target_start'], s['target_end']
        orig = s.get('reference_target_start', a) + original_shift
        for c in doc.cues:
            lo, hi = max(c.start, orig), min(c.end, orig + (b - a))
            if hi - lo > .05 and c.plain:
                cues.append((a + lo - orig, a + hi - orig, c.plain))
    path = Path(out) / 'restored_scenes.srt'
    path.write_text(''.join(f'{i}\n{timestamp(x)} --> {timestamp(y)}\n{text}\n\n'
                            for i, (x, y, text) in enumerate(sorted(cues), 1)), encoding='utf-8')
    return path, len(cues)
