"""Dense picture comparison around an edition cut, independent of dub audio."""
import numpy as np
import visual_core as vc

RATE=25

def frames(path,start,length,speed=1.,crop='',with_dark=False):
    if start<0:raise ValueError('Visual cut search starts before source video.')
    vf=f'setpts=(PTS-STARTPTS)/{speed:.12f},'
    if crop:vf+='crop='+crop+','
    vf+=f'fps={RATE},scale=32:24,format=gray'
    raw=vc.run([vc.binary('ffmpeg'),'-v','error','-nostdin','-ss',f'{start:.9f}',
                '-i',str(path),'-map','0:v:0','-an','-t',f'{length:.9f}',
                '-vf',vf,'-pix_fmt','gray','-f','rawvideo','pipe:1'])
    x=np.frombuffer(raw,np.uint8).reshape(-1,24,32)[:,2:20,2:30].astype(np.float32)
    x=x.reshape(len(x),-1);dark=np.quantile(x,.95,axis=1)<24;valid=x.std(axis=1)>8
    x-=x.mean(axis=1,keepdims=True)
    x/=np.maximum(np.linalg.norm(x,axis=1,keepdims=True),1e-8)
    x[~valid]=0
    return (x,dark) if with_dark else x

def compare(q,x):
    # Small frame offsets tolerate ordinary frame-rate conversion/seek rounding.
    n=min(len(q),len(x));scores=np.zeros(n)
    for shift in [-1,0,1]:
        a=max(0,-shift);b=min(n,n-shift)
        if b>a:scores[a:b]=np.maximum(scores[a:b],np.sum(q[a:b]*x[a+shift:b+shift],axis=1))
    return scores

def locate_visual_cut(left,right,source_video,target_video,delay=0.,source_crop='',target_crop='',target_energy=None):
    lo=max(0.,left['last']-4);hi=right['first']+4
    if hi-lo>180:raise ValueError('Visual cut search exceeds 180 seconds; needs manual cut time.')
    q,qdark=frames(target_video,lo,hi-lo,crop=target_crop,with_dark=True)
    darks=[]
    scores=[]
    for m in (left,right):
        x,dark=frames(source_video,m['speed']*lo+m['offset']+delay,hi-lo,m['speed'],source_crop,with_dark=True)
        darks.append(dark)
        scores.append(compare(q,x))
    n=min(map(len,scores))
    if n<50:raise ValueError('Not enough pictures around cut.')
    old,new=[s[:n] for s in scores];diff=old-new
    obj=np.r_[0.,np.cumsum(diff)]/RATE
    possible=np.flatnonzero(obj>=obj.max()-.025)
    k=int(possible[len(possible)//2]);t=lo+k/RATE
    before=slice(max(0,k-2*RATE),k);after=slice(k,min(n,k+2*RATE))
    def avg(x):return float(x.mean()) if len(x) else 0.
    strong=(k>=RATE//2 and n-k>=RATE//2 and
            avg(old[before])>.80 and avg(new[after])>.80 and
            avg(diff[before])>.12 and avg(-diff[after])>.12 and
            (possible[-1]-possible[0])/RATE<=.24)
    # Some editions replace an entire eyecatch with a short black pause.
    # A single splice would retain part of its music. Verify both gap edges.
    if target_energy is not None:
        edges=np.flatnonzero(np.diff(np.r_[False,qdark[:n],False]))
        verified=[]
        for a,b in zip(edges[::2],edges[1::2]):
            if not .2<=(b-a)/RATE<=5 or a<2*RATE or b+2*RATE>n:continue
            pre=slice(a-2*RATE,a);post=slice(b,b+2*RATE)
            if min(avg(old[pre]),avg(new[post]))<.85 or min(avg(diff[pre]),avg(-diff[post]))<.2:continue
            ga,gb=lo+a/RATE,lo+b/RATE
            e=target_energy[int(ga*50):int(np.ceil(gb*50))]
            if len(e) and np.mean(e)<4e-6 and np.max(e)<1.6e-5:
                verified.append((ga,gb))
        if len(verified)==1:
            ga,gb=verified[0]
            return dict(time=ga,confidence='supported',method='picture-verified eyecatch replacement with near-silent target pause',uncertainty_start=ga,uncertainty_end=gb,target_gap=[ga,gb])
    black_candidates=[]
    # A black plateau is not a unique cut. Offer candidates only when surrounding
    # pictures independently favor the old and new mappings. Audio must verify it.
    if k>=RATE//2 and n-k>=RATE//2 and avg(old[before])>.75 and avg(new[after])>.75 and np.sum(diff[before])/RATE>.08 and -np.sum(diff[after])/RATE>.08 and (possible[-1]-possible[0])/RATE<=2:
        black_candidates=[float(lo+j/RATE) for j in possible if j<n and qdark[j] and (darks[0][j] or darks[1][j])]
    return dict(black_candidates=black_candidates,time=t,confidence='supported' if strong else 'uncertain',
        method='dense picture cut match' if strong else 'ambiguous picture cut match',
        uncertainty_start=lo+possible[0]/RATE if strong else lo,
        uncertainty_end=lo+possible[-1]/RATE if strong else hi,
        visual_before_score=avg(old[before]),visual_after_score=avg(new[after]))


def calibrated_models(left,right,visual):
    """Use local picture anchors to avoid confusing dub offsets with image edits."""
    if visual is None or len(visual)<6:return left,right
    a=visual[(visual[:,0]>=left['last']-40)&(visual[:,0]<=right['first']+40)]
    if len(a)<6:return left,right
    errors=np.array([abs(a[:,1]-(m['speed']*a[:,0]+m['offset'])) for m in (left,right)])
    groups=[]
    for i in [0,1]:
        groups.append(a[(errors[i]<.35)&(errors[1-i]-errors[i]>.08)])
    if min(map(len,groups))<3:return left,right
    if groups[0][-1,0]>=groups[1][0,0]:return left,right
    result=[]
    for m,g in zip((left,right),groups):
        offsets=g[:,1]-m['speed']*g[:,0];off=float(np.median(offsets))
        if np.quantile(abs(offsets-off),.9)>.08:return left,right
        new=dict(m);new.update(offset=off,first=float(g[0,0]),last=float(g[-1,0]));result.append(new)
    return tuple(result)


def quiet_black_cut(visual_cut,left,right,source_energy,target_energy,rate=50):
    """Only resolve a black-frame ambiguity when the removed audio is near silence."""
    if source_energy is None or target_energy is None:return None
    candidates=visual_cut.get('black_candidates',[])
    choices=[]
    for t in candidates:
        a=left['speed']*t+left['offset'];b=right['speed']*t+right['offset']
        if not .25<b-a<5:continue
        lo=int(a*rate);hi=int(np.ceil(b*rate));ti=int(t*rate)
        if lo<0 or hi>len(source_energy) or not 0<ti<len(target_energy)-1:continue
        removed=source_energy[lo:hi];target=target_energy[ti-1:ti+2]
        context=source_energy[max(0,lo-5*rate):min(len(source_energy),hi+5*rate)]
        # -54 dBFS RMS ceiling and >=20 dB below the surrounding loudest audio.
        limit=min(4e-6,max(1e-12,float(np.max(context))*.01))
        if len(removed) and np.max(removed)<limit and np.max(target)<4e-6:
            choices.append((float(np.max(removed)),t,a,b))
    if not choices:return None
    _,t,a,b=min(choices)
    result=dict(visual_cut);result.pop('black_candidates',None)
    result.update(time=t,confidence='supported',method='picture-matched black transition; removed source audio verified near-silent',removed_source_start=a,removed_source_end=b)
    return result

def locate_target_insert(left,right,source_video,target_video,source_energy,delay=0.,source_crop='',target_crop='',audio_models=None):
    """Verify target-only footage replacing a silent black source pause."""
    lo=max(0.,left['last']-4);hi=right['first']+4
    if hi-lo>180 or abs(left['speed']-right['speed'])>.001:return None
    missing=(left['offset']-right['offset'])/left['speed']
    if not .3<missing<15:return None
    q,qd=frames(target_video,lo,hi-lo,crop=target_crop,with_dark=True)
    scores=[]
    for m in (left,right):
        x=frames(source_video,m['speed']*lo+m['offset']+delay,hi-lo,m['speed'],source_crop)
        scores.append(compare(q,x))
    n=min(map(len,scores));old,new=[s[:n] for s in scores]
    from scipy.ndimage import uniform_filter1d
    a=uniform_filter1d(old,10);b=uniform_filter1d(new,10)
    before=np.flatnonzero((a>.85)&(a-b>.3));after=np.flatnonzero((b>.85)&(b-a>.3))
    if not len(before) or not len(after):return None
    # The last old match and first new match must be chronologically separate.
    i,j=int(before[-1]),int(after[0])
    if not 0<(j-i)/RATE<18:return None
    edges=np.flatnonzero(np.diff(np.r_[False,qd[:n],False]));runs=list(zip(edges[::2],edges[1::2]))
    starts=[x for x,y in runs if i<=x<=i+RATE and y>x]
    ends=[y for x,y in runs if j-RATE<=y<=j+5 and y>x]
    if not starts:return None
    if not ends:
        # Some eyecatches cut straight to the next shot with no closing black.
        candidates=[k for k in range(max(i+1,j-10),min(n-10,j+10)) if np.min(new[k:k+10])>.85 and np.max(old[k:k+10])<.5]
        if not candidates:return None
        ends=[candidates[0]]
    ga,gb=lo+min(starts)/RATE,lo+max(ends)/RATE
    sa=left['speed']*ga+left['offset'];sb=right['speed']*gb+right['offset']
    if not .08<sb-sa<3 or not .3<gb-ga<18:return None
    _,dark=frames(source_video,sa+delay,sb-sa,crop=source_crop,with_dark=True)
    al,ar=audio_models or (left,right)
    aa=al['speed']*ga+al['offset'];ab=ar['speed']*gb+ar['offset']
    if not 0<ab-aa<3:return None
    e=source_energy[max(0,int(aa*50)):int(ab*50)]
    if not len(dark) or dark.mean()<.95 or not len(e) or e.mean()>1e-5 or e.max()>5e-5:return None
    return dict(time=ga,target_gap=[ga,gb],target_gap_kind='reference',confidence='supported',
        method='Target-only footage replaces a verified silent black source pause; target audio required',
        uncertainty_start=ga,uncertainty_end=gb)
