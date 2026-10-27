"""Recognize explicit outer chapter labels; never infer numbered chapters."""
import math,re
import visual_core as vc

def explicit_outer_chapters(path,duration):
    import json
    data=json.loads(vc.run([vc.binary('ffprobe'),'-v','error','-show_chapters','-show_streams','-of','json',str(path)]))
    video=next(s for s in data.get('streams',[]) if s.get('codec_type')=='video')
    origin=float(video.get('start_time',0));chapters=[]
    for c in data.get('chapters',[]):
        try:a,b=float(c['start_time'])-origin,float(c['end_time'])-origin
        except (KeyError,TypeError,ValueError):return {}
        if not all(map(math.isfinite,[a,b])) or b<=a:return {}
        title=c.get('tags',{}).get('title','').strip().lower()
        if re.fullmatch(r'(opening(?: credits| theme)?|op|オープニング)',title):kind='opening'
        elif re.fullmatch(r'(ending(?: credits| theme)?|ed|エンディング)',title):kind='ending'
        elif re.search(r'\b(?:next[ -]episode|preview)\b|次回予告',title):kind='preview'
        else:kind='other'
        chapters.append((a,b,kind,title))
    chapters.sort();result={}
    if any(y[0]<x[1]-.15 for x,y in zip(chapters,chapters[1:])):return {}
    if chapters:
        a,b,kind,title=chapters[0]
        if kind=='opening' and abs(a)<=.25 and 5<b<min(420,duration*.3):
            result['start']={'time':b,'status':'chapter','reason':'Explicit opening chapter end (video-relative timestamp)','chapter':title}
        a,b,kind,title=chapters[-1]
        if kind=='ending' and abs(b-duration)<2 and duration*.7<a<duration-5:
            # Next-episode previews are episode content. Only the ED belongs
            # to the outer target-audio region; do not move this boundary back
            # to a preceding preview chapter.
            result['end']={'time':a,'status':'chapter','reason':'Explicit ending chapter start (video-relative timestamp)','chapter':title}
    return result
