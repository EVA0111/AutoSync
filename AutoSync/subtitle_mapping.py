"""Conservative piecewise source-to-target maps shared by all subtitle modes."""
import bisect,json,re
from dataclasses import dataclass,asdict
from difflib import SequenceMatcher
from pathlib import Path
import numpy as np

@dataclass
class Section:
    start:float
    end:float
    scale:float
    offset:float
    anchors:list
    quality:str='supported'

class TimingMap:
    def __init__(self,sections,evidence='reference'):
        self.sections=sorted(sections,key=lambda s:s.start);self.evidence=evidence
        if not self.sections:raise ValueError('No reliable timing sections found.')
        last=-float('inf');last_target=-float('inf')
        for s in self.sections:
            if not all(np.isfinite(v) for v in (s.start,s.end,s.scale,s.offset)) or s.end<s.start or s.scale<=0 or s.start<last:raise ValueError('Invalid or overlapping timing sections.')
            if s.scale*s.start+s.offset < last_target-1e-6:raise ValueError('Timing map reverses or overlaps target sections.')
            last=s.end;last_target=s.scale*s.end+s.offset
    def interval(self,start,end):
        for s in self.sections:
            if s.start-1e-6<=start and end<=s.end+1e-6:
                a,b=s.scale*start+s.offset,s.scale*end+s.offset
                if a<0:return None
                q=s.quality
                if s.anchors and max(min(abs(x-start) for x in s.anchors),min(abs(x-end) for x in s.anchors))>30:q='estimated: more than 30 seconds from matching evidence'
                return a,b,s.scale,q
        return None
    def save(self,path):Path(path).write_text(json.dumps({'direction':'source_to_target','evidence':self.evidence,'sections':[asdict(s) for s in self.sections]},indent=2),encoding='utf-8')
    @classmethod
    def load(cls,path):
        d=json.loads(Path(path).read_text(encoding='utf-8-sig'))
        if d.get('direction')=='source_to_target':return cls([Section(**s) for s in d['sections']],d.get('evidence','manual'))
        if 'segments' not in d:raise ValueError('Not an AutoSync plan or subtitle timing map.')
        sections=[]
        for s in d['segments']:
            if s.get('kind')!='audio':continue
            speed=float(s['speed']);start=float(s['source_start']);end=start+(s['target_end']-s['target_start'])*speed
            sections.append(Section(start,end,1/speed,s['target_start']-start/speed,[], 'estimated: imported audio map; verify source subtitle alignment'))
        return cls(sections,'audio-plan')

def increasing(rows):
    rows=sorted(rows,key=lambda r:(r[0],r[1]));tails=[];indices=[];previous=[]
    for i,r in enumerate(rows):
        k=bisect.bisect_left(tails,r[1]);previous.append(indices[k-1] if k else -1)
        if k==len(tails):tails.append(r[1]);indices.append(i)
        else:tails[k]=r[1];indices[k]=i
    result=[];i=indices[-1] if indices else -1
    while i>=0:result.append(rows[i]);i=previous[i]
    return result[::-1]

def fit_map(rows,duration,evidence='reference',tolerance=.5):
    a=np.asarray(increasing(rows),float)
    if len(a)<4:raise ValueError('Fewer than four independent matches. Add a matching reference, source video, or a manual timing map.')
    rates=[]
    for i in range(len(a)):
        for j in range(i+1,min(i+12,len(a))):
            dx=a[j,0]-a[i,0]
            if 5<dx<180:
                r=(a[j,1]-a[i,1])/dx
                if .8<r<1.25:rates.append(r)
    if not rates:raise ValueError('Matches do not establish a credible playback rate.')
    rate=float(np.median(rates));offset=a[:,1]-rate*a[:,0]
    # Discard isolated matches rather than turning them into tiny false sections.
    keep=[]
    for i in range(len(a)):
        neighbours=(np.abs(a[:,0]-a[i,0])<150)&(np.abs(offset-offset[i])<tolerance+.003*np.abs(a[:,0]-a[i,0]))
        if neighbours.sum()>=3:keep.append(i)
    a=a[keep]
    if len(a)<4:raise ValueError('No consistent subtitle timing map. Repeated phrases or different content may be causing false matches.')
    groups=[];current=[a[0]]
    for r in a[1:]:
        previous=current[-1];residual=(r[1]-previous[1])-rate*(r[0]-previous[0])
        if abs(residual)>max(tolerance*2,.003*(r[0]-previous[0])):groups.append(np.array(current));current=[]
        current.append(r)
    groups.append(np.array(current));sections=[]
    for g in groups:
        if len(g)<3 or np.ptp(g[:,0])<5:continue
        local=[]
        for i in range(len(g)):
            for j in range(i+1,min(i+20,len(g))):
                dx=g[j,0]-g[i,0]
                if dx>10:
                    r=(g[j,1]-g[i,1])/dx
                    if abs(r-rate)<.015:local.append(r)
        slope=float(np.median(local)) if local else rate
        intercept=float(np.median(g[:,1]-slope*g[:,0]));res=np.abs(g[:,1]-slope*g[:,0]-intercept)
        g=g[res<=tolerance]
        if len(g)<3:continue
        # Never interpolate across an edition cut; uncovered intervals stay unresolved.
        lo=max(0,float(g[0,0])-2);hi=min(duration,float(g[-1,0])+2)
        if not sections:lo=max(0,float(g[0,0])-30)
        quality='supported'
        if evidence=='visual' and float(np.max(np.abs(g[:,1]-slope*g[:,0]-intercept)))>.08:quality='estimated: picture anchors vary by more than 80 ms; check frame-sensitive typesetting'
        sections.append(Section(lo,hi,slope,intercept,g[:,0].tolist(),quality))
    if sections:sections[-1].end=min(duration,sections[-1].anchors[-1]+30)
    # Extensions around separate clusters must not overlap.
    for l,r in zip(sections,sections[1:]):
        if l.end>r.start:mid=(l.anchors[-1]+r.anchors[0])/2;l.end=min(l.end,mid);r.start=max(r.start,mid)
    return TimingMap(sections,evidence)

def normalized(text):return ' '.join(re.findall(r'\w+',text.casefold(),re.UNICODE))

def text_anchors(source,reference,semantic=False):
    a=[c for c in source if len(normalized(c.plain))>=8 and not c.typeset]
    b=[c for c in reference if len(normalized(c.plain))>=8 and not c.typeset]
    if not a or not b:raise ValueError('No readable dialogue available for matching; bitmap/drawing-only subtitles need a visual timing map.')
    aa=[normalized(c.plain) for c in a];bb=[normalized(c.plain) for c in b]
    if semantic:
        try:from sentence_transformers import SentenceTransformer
        except ImportError:raise RuntimeError('Cross-language matching needs Setup → Install subtitle AI (sentence-transformers).')
        print('Loading multilingual text model (first use downloads model files)…',flush=True)
        model=SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
        av=model.encode(aa,normalize_embeddings=True);bv=model.encode(bb,normalize_embeddings=True);scores=av@bv.T;threshold=.72;margin=.08
    else:
        # Character trigrams support both spaced languages and CJK without a tokenizer download.
        def grams(t):return {t[i:i+3] for i in range(max(1,len(t)-2))}
        ga=list(map(grams,aa));gb=list(map(grams,bb));index={}
        for j,gs in enumerate(gb):
            for token in gs:index.setdefault(token,[]).append(j)
        scores=np.zeros((len(a),len(b)),np.float32)
        for i,gs in enumerate(ga):
            candidates={j for token in gs for j in index.get(token,[])}
            for j in candidates:
                overlap=len(gs&gb[j])/max(1,len(gs|gb[j]))
                if overlap>.25:scores[i,j]=SequenceMatcher(None,aa[i],bb[j],autojunk=False).ratio()
        threshold=.78;margin=.10
    rows=[]
    for i,c in enumerate(a):
        j=int(np.argmax(scores[i]));score=float(scores[i,j]);other=scores[i].copy();other[j]=-1
        if score>=threshold and score-float(other.max())>=margin and int(np.argmax(scores[:,j]))==i:
            rows.append(((c.start+c.end)/2,(b[j].start+b[j].end)/2,score))
    return increasing(rows)
