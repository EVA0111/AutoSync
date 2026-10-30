"""Detect overlapping source-audio mappings that can replay earlier sound.

A smooth source timeline maps each output segment onto a forward-moving
portion of the source. Distinct model fits can be individually precise while
still joining at a point that rewinds the source: this is *not* a source-only
cut, and must not be silently exported as an ordinary splice.

No automatic target-audio substitution is performed here: the exact
beginning/end of a possible target-only insertion still needs verification.
"""

def source_rewinds(segments, minimum=0.25):
    """Return exact source overlaps between consecutive source-audio regions.

    Read live segment boundaries, not cached source_cuts. This also handles
    source-audio clips separated by reference/target-only audio.
    """
    found=[]
    previous=None
    for seg in segments:
        if seg.get('kind')!='audio':
            continue
        if previous is not None:
            end=float(previous['source_start']) + (
                float(previous['target_end'])-float(previous['target_start'])
            )*float(previous['speed'])
            begin=float(seg['source_start'])
            overlap=end-begin
            if overlap>minimum:
                found.append({
                    'target_time':float(seg['target_start']),
                    'previous_target_end':float(previous['target_end']),
                    'previous_source_end':end,
                    'next_source_start':begin,
                    'replayed_source_seconds':overlap,
                    'estimated_target_equivalent_seconds':overlap/max(float(seg['speed']),1e-8),
                    'status':'needs_review',
                })
        previous=seg
    return found


def annotate_rewinds(plan):
    """Annotate, never rewrite, a timing plan with overlapping-source risks."""
    overlap=source_rewinds(plan.get('segments',[]))
    plan['source_rewinds']=overlap
    if not overlap:
        return plan
    reviews=plan.setdefault('review',[])
    warnings=plan.setdefault('warnings',[])
    for issue in overlap:
        t=issue['target_time']
        duration=float(plan['duration'])
        start=max(0.,min(t,issue['previous_target_end'])-3.)
        end=min(duration,max(t,issue['previous_target_end'])+3.)
        reason=('Source mapping goes BACKWARD by '
                f"{issue['replayed_source_seconds']:.3f}s. "
                'Likely replay/overlap rather than a verified splice; '
                'target-only insert or mismatched timing requires review.')
        if not any(r.get('issue_type')=='source_rewind'
                   and abs(r.get('splice',-999)-t)<.001 for r in reviews):
            reviews.append(dict(start=start,end=end,splice=t,
                                confidence='uncertain',issue_type='source_rewind',
                                reason=reason))
        if reason not in warnings:
            warnings.append(reason+f" Target at {t:.3f}s.")
    return plan
