"""Conservative, sampled detection of persistent black video borders."""
import numpy as np
import visual_core as vc

def detect_crop(path):
    p=vc.probe(path);v=next(s for s in p['streams'] if s['codec_type']=='video')
    w,h=int(v['width']),int(v['height']);duration=float(v.get('duration',p['format'].get('duration',0)))
    sw=320;sh=max(2,round(h*sw/w));samples=[]
    for t in np.linspace(duration*.12,duration*.88,7):
        raw=vc.run([vc.binary('ffmpeg'),'-v','error','-nostdin','-ss',str(t),'-i',str(path),'-map','0:v:0','-frames:v','1','-vf',f'scale={sw}:{sh},format=gray','-f','rawvideo','pipe:1'])
        if len(raw)==sw*sh:samples.append(np.frombuffer(raw,np.uint8).reshape(sh,sw))
    if len(samples)<5:return ''
    # A border must stay dark over several unrelated scenes. Ignore tiny trims.
    bright=np.quantile(np.stack(samples),.85,axis=0)>24
    cols=np.flatnonzero(bright.mean(axis=0)>.10);rows=np.flatnonzero(bright.mean(axis=1)>.10)
    if not len(cols) or not len(rows):return ''
    l,r=int(cols[0]),int(cols[-1]+1);top,bottom=int(rows[0]),int(rows[-1]+1)
    if min(r-l,sw)<sw*.5 or bottom-top<sh*.5:return ''
    if l<sw*.015:l=0
    if sw-r<sw*.015:r=sw
    if top<sh*.015:top=0
    if sh-bottom<sh*.015:bottom=sh
    if (l,r,top,bottom)==(0,sw,0,sh):return ''
    x=2*int(l*w/sw/2);y=2*int(top*h/sh/2)
    endx=min(w,2*int(np.ceil(r*w/sw/2)));endy=min(h,2*int(np.ceil(bottom*h/sh/2)))
    return f'{endx-x}:{endy-y}:{x}:{y}'


def shared_picture_crop(source,target,anchors,speed,source_crop='',target_crop='',delay=0.):
    """Test aspect-ratio crops against independent audio matches; never crop output."""
    from visual_cuts import frames,compare
    if len(anchors)<8:return source_crop,target_crop,None
    specs=[]
    for path,crop in [(source,source_crop),(target,target_crop)]:
        v=next(s for s in vc.probe(path)['streams'] if s['codec_type']=='video')
        w,h=int(v['width']),int(v['height']);x=y=0
        if crop:
            try:w,h,x,y=map(int,crop.split(':'))
            except ValueError:return source_crop,target_crop,None
        sar=v.get('sample_aspect_ratio','1:1').split(':')
        try:pixel=float(sar[0])/float(sar[1])
        except (ValueError,ZeroDivisionError,IndexError):pixel=1.
        specs.append((w,h,x,y,pixel))
    ratios=[w*p/h for w,h,x,y,p in specs]
    if abs(np.log(ratios[0]/ratios[1]))<.08:return source_crop,target_crop,None
    # The narrower edition may contain extra top/bottom image area.
    index=int(ratios[1]<ratios[0]);w,h,x,y,pixel=specs[index]
    nh=2*int((w*pixel/ratios[1-index])/2)
    if not .65*h<=nh<h:return source_crop,target_crop,None
    candidate=f'{w}:{nh}:{x}:{y+2*int((h-nh)/4)}'
    crops=[source_crop,target_crop];trial=crops.copy();trial[index]=candidate
    rows=[]
    for i in np.linspace(0,len(anchors)-1,min(12,len(anchors))).astype(int):
        t,s,_=anchors[i]
        if min(t,s+delay)<0:continue
        q=frames(target,t,1.5,crop=target_crop)
        z=frames(source,s+delay,1.5,speed,source_crop)
        baseline=float(np.mean(compare(q,z)))
        if index==0:z=frames(source,s+delay,1.5,speed,candidate)
        else:q=frames(target,t,1.5,crop=candidate)
        rows.append([baseline,float(np.mean(compare(q,z)))])
    a=np.asarray(rows)
    accepted=(len(a)>=8 and np.median(a[:,1])>.83 and np.median(a[:,1]-a[:,0])>.05 and np.mean(a[:,1]>a[:,0]+.03)>=.67)
    report=dict(candidate=candidate,side='source' if index==0 else 'target',accepted=bool(accepted),scores=rows)
    return (*(trial if accepted else crops),report)
