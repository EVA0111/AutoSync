"""Lossless timing edits for common subtitle formats; never flatten typesetting."""
from dataclasses import dataclass
from pathlib import Path
import re
import xml.etree.ElementTree as ET

@dataclass
class Cue:
    start: float
    end: float
    text: str
    spans: tuple
    style: str = ''
    effect: str = ''
    @property
    def plain(self):
        if re.search(r'\\p[1-9]', self.text): return ''
        return re.sub(r'<[^>]+>|\{[^}]*\}', '', self.text).replace(r'\N',' ').replace(r'\n',' ').replace(r'\h',' ').strip()
    @property
    def typeset(self):
        return bool(self.effect or re.search(r'\\(?:pos|move|org|clip|iclip|p[1-9]|t\(|k[fot]?\d|K\d)',self.text) or re.search(r'sign|title|karaoke|song|credit|op|ed',self.style,re.I))

def seconds(value):
    value=value.strip().replace(',','.')
    if ':' in value:
        parts=[float(x) for x in value.split(':')];return sum(x*60**i for i,x in enumerate(parts[::-1]))
    m=re.fullmatch(r'([\d.]+)(ms|s|m|h)',value)
    if m:return float(m[1])*{'ms':.001,'s':1,'m':60,'h':3600}[m[2]]
    raise ValueError('Unsupported time expression: '+value)

def timestamp(t,kind='srt'):
    precision=100 if kind=='ass' else 1000
    n=max(0,round(t*precision));h,n=divmod(n,3600*precision);m,n=divmod(n,60*precision);s,f=divmod(n,precision)
    if kind=='ass':return f'{h}:{m:02}:{s:02}.{f:02}'
    return f'{h:02}:{m:02}:{s:02}'+(',' if kind=='srt' else '.')+f'{f:03}'

def scale_ass(text,factor):
    """Scale only time-bearing ASS tags, including nested transforms. Geometry is unchanged."""
    cumulative=0.;previous=0
    def block(m):
        nonlocal cumulative,previous
        x=m.group(0)
        def time(v):return str(round(float(v)*factor))
        def simple(m):
            tag=m[1];args=m[2].split(',');indices={'fad':range(2),'fade':range(3,7),'move':range(4,6)}[tag]
            expected={'fad':2,'fade':7,'move':6}[tag]
            if len(args)!=expected:return m[0]
            for i in indices:args[i]=time(args[i])
            return '\\'+tag+'('+','.join(args)+')'
        x=re.sub(r'\\(fad|fade|move)\(([^()]*)\)',simple,x)
        # Explicit transform t1,t2 precede acceleration and/or nested override tags.
        x=re.sub(r'\\t\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*,',lambda m:'\\t('+time(m[1])+','+time(m[2])+',',x)
        # Cumulative rounding avoids drift across many karaoke syllables.
        def karaoke(m):
            nonlocal cumulative,previous
            if m[1]=='kt':
                cumulative=float(m[2])*factor;previous=round(cumulative);return '\\kt'+str(previous)
            cumulative+=float(m[2])*factor;now=round(cumulative);duration=now-previous;previous=now
            return '\\'+m[1]+str(duration)
        return re.sub(r'\\(kf|ko|kt|k|K)(\d+)',karaoke,x)
    return re.sub(r'\{[^}]*\}',block,text)

class Document:
    def __init__(self,path,encoding='utf-8-sig',fps=None):
        self.path=Path(path);self.encoding=encoding;self.fps=fps;self.kind=self.path.suffix.lower();self.cues=[]
        raw=self.path.read_bytes();self.bom=raw.startswith(b'\xef\xbb\xbf')
        if raw.startswith((b'\xff\xfe',b'\xfe\xff')):self.encoding='utf-16'
        self.text=raw.decode(self.encoding,errors='strict')
        self._parse()
        if not self.cues:raise ValueError('No subtitle cues found; choose a supported subtitle file or extract its track first.')
    def _parse(self):
        text=self.text;kind=self.kind
        if kind in ('.ass','.ssa'):
            section='';fields=[];pos=0
            for line in text.splitlines(keepends=True):
                stripped=line.strip()
                if stripped.startswith('['):section=stripped.lower()
                if section=='[events]':
                    if stripped.lower().startswith('format:'):fields=[x.strip().lower() for x in stripped.split(':',1)[1].split(',')]
                    if line.lower().startswith('dialogue:'):
                        if not fields or fields[-1]!='text':raise ValueError('ASS Events Format must end with Text.')
                        base=line.index(':')+1;parts=line[base:].rstrip('\r\n').split(',',len(fields)-1)
                        if len(parts)!=len(fields):raise ValueError('Malformed ASS dialogue row.')
                        starts=[];cursor=pos+base
                        for part in parts:starts.append((cursor,cursor+len(part)));cursor+=len(part)+1
                        d=dict(zip(fields,parts));idx=lambda key:starts[fields.index(key)]
                        self.cues.append(Cue(seconds(d['start']),seconds(d['end']),d['text'],(idx('start'),idx('end'),idx('text')),d.get('style',''),d.get('effect','')))
                pos+=len(line)
        elif kind in ('.srt','.vtt','.sbv'):
            if 'X-TIMESTAMP-MAP' in text:raise ValueError('WebVTT with X-TIMESTAMP-MAP needs conversion to a local timeline first.')
            sep=r'\s*-->\s*' if kind!='.sbv' else ','
            clock=r'(?:\d+:)?\d{2}:\d{2}[.,]\d{2,3}'
            for m in re.finditer(r'^('+clock+')'+sep+'('+clock+r')([^\r\n]*)\r?\n()',text,re.M):
                # Use a non-greedy cue body through the next blank line instead.
                end=text.find('\n\n',m.start(4));end2=text.find('\r\n\r\n',m.start(4));ends=[v for v in (end,end2) if v>=0];stop=min(ends) if ends else len(text)
                self.cues.append(Cue(seconds(m[1]),seconds(m[2]),text[m.start(4):stop],(m.span(1),m.span(2),(m.start(4),stop))))
        elif kind in ('.sub','.mpl2'):
            frame=kind=='.sub';pattern=r'^\{(\d+)\}\{(\d+)\}(.*)$' if frame else r'^\[(\d+)\]\[(\d+)\](.*)$'
            if frame and (not self.fps or self.fps<=0):raise ValueError('MicroDVD .sub requires the source FPS; binary VobSub is not a text .sub.')
            unit=1/self.fps if frame else .1
            for m in re.finditer(pattern,text,re.M):
                if frame and m[1]==m[2]=='1':continue
                self.cues.append(Cue(int(m[1])*unit,int(m[2])*unit,m[3],(m.span(1),m.span(2),m.span(3))))
        elif kind in ('.smi','.sami'):
            matches=list(re.finditer(r'<sync\b[^>]*\bstart\s*=\s*["\']?(\d+)[^>]*>',text,re.I))
            for i,m in enumerate(matches):
                end=matches[i+1].start() if i+1<len(matches) else len(text);t=int(m[1])/1000
                self.cues.append(Cue(t,int(matches[i+1][1])/1000 if i+1<len(matches) else t+2,text[m.end():end],(m.span(1),None,None)))
        elif kind in ('.ttml','.dfxp','.xml'):
            root=ET.fromstring(text)
            for el in root.iter():
                local=el.tag.split('}')[-1]
                if any(k in el.attrib for k in ('begin','end','dur')) and local!='p':raise ValueError('Nested/inherited TTML timing is not supported losslessly. Export flat timed paragraphs first.')
            for m in re.finditer(r'<(?:\w+:)?p\b([^>]*)>([\s\S]*?)</(?:\w+:)?p\s*>',text):
                attrs={x[1]:(x[3],(m.start(1)+x.start(3),m.start(1)+x.end(3))) for x in re.finditer(r'\b(begin|end|dur)\s*=\s*(["\'])(.*?)\2',m[1])}
                if 'dur' in attrs:raise ValueError('TTML dur attributes require conversion to explicit begin/end timing first.')
                if 'begin' not in attrs or 'end' not in attrs:raise ValueError('TTML requires explicit begin and end on every paragraph.')
                self.cues.append(Cue(seconds(attrs['begin'][0]),seconds(attrs['end'][0]),m[2],(attrs['begin'][1],attrs['end'][1],None)))
        else:raise ValueError('Unsupported lossless subtitle format. Supported: ASS, SSA, SRT, VTT, SBV, MicroDVD SUB, MPL2, SAMI, flat TTML/DFXP, and PGS SUP with a timing map. VobSub, STL and other binary formats require conversion first.')
        for cue in self.cues:
            if cue.end<cue.start:raise ValueError('Subtitle has an end before its start.')
    def write(self,path,mapping,target_fps=None):
        changes=[];report=[]
        for i,c in enumerate(self.cues,1):
            mapped=mapping.interval(c.start,c.end)
            if mapped is None:
                report.append({'cue':i,'source_start':c.start,'source_end':c.end,'status':'unmapped','reason':'Outside supported mapping or crossing a cut; original timing retained in DRAFT.'});continue
            start,end,scale,quality=mapped
            reason=[]
            if quality!='supported':reason.append(quality)
            if c.typeset and mapping.evidence!='visual':reason.append('Typesetting inferred without source-picture evidence; check against the target video.')
            if c.effect and abs(scale-1)>1e-6:reason.append('Legacy ASS Effect field speed needs manual review.')
            if self.kind in ('.ass','.ssa'):
                a,b=timestamp(start,'ass'),timestamp(end,'ass');body=scale_ass(c.text,scale)
            elif self.kind in ('.sub','.mpl2'):
                unit=(target_fps or self.fps) if self.kind=='.sub' else 10;a,b=str(round(start*unit)),str(round(end*unit));body=c.text
            elif self.kind in ('.smi','.sami'):a,b=str(round(start*1000)),None;body=c.text
            elif self.kind in ('.ttml','.dfxp','.xml'):a,b=f'{start:.3f}s',f'{end:.3f}s';body=c.text
            else:
                a,b=timestamp(start,'srt' if self.kind=='.srt' else 'vtt'),timestamp(end,'srt' if self.kind=='.srt' else 'vtt');body=c.text
                if self.kind=='.vtt':
                    def inline(m):
                        val=mapping.interval(seconds(m[1]),seconds(m[1]))
                        if val is None:reason.append('Unmapped inline VTT timestamp');return m[0]
                        return '<'+timestamp(val[0],'vtt')+'>'
                    body=re.sub(r'<((?:\d+:)?\d{2}:\d{2}\.\d{3})>',inline,body)
            collapsed = (seconds(b)<=seconds(a)) if self.kind in ('.ass','.ssa','.srt','.vtt','.sbv') else (int(b)<=int(a) if self.kind in ('.sub','.mpl2') else False)
            if end>start and collapsed:
                report.append({'cue':i,'source_start':c.start,'source_end':c.end,'status':'unmapped','reason':'Cue shorter than output timestamp precision; original retained.'});continue
            for span,value in zip(c.spans,(a,b,body)):
                if span and value is not None:changes.append((*span,value))
            report.append({'cue':i,'source_start':c.start,'source_end':c.end,'target_start':start,'target_end':end,'status':'review' if reason else 'mapped','reason':'; '.join(reason)})
        result=self.text
        for a,b,value in sorted(changes,reverse=True):result=result[:a]+value+result[b:]
        if self.kind=='.sub' and target_fps:
            result=re.sub(r'(?m)^(\{1\}\{1\})[0-9.]+',lambda m:m[1]+format(target_fps,'g'),result)
        enc=self.encoding
        if enc=='utf-8-sig' and not self.bom:enc='utf-8'
        Path(path).write_bytes(result.encode(enc))
        return report
