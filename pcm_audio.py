"""Decode each input once, then cut by PCM sample index without container seeks."""
from pathlib import Path
import math
import visual_core as vc

class PCMCache:
    def __init__(self,directory,channels,rate=48000):
        self.directory=Path(directory);self.channels=channels;self.rate=rate;self.files={}

    def cut(self,path,stream,start,duration,destination):
        if not math.isfinite(start+duration) or start<0 or duration<=0:
            raise RuntimeError('Invalid decoded-audio cut interval.')
        key=(str(Path(path).resolve()),int(stream))
        if key not in self.files:
            decoded=self.directory/f'decoded_{len(self.files):03}.f32'
            print(f'Decoding audio once for accurate cuts: {Path(path).name}',flush=True)
            vc.run([vc.binary('ffmpeg'),'-v','error','-nostdin','-y','-i',str(path),'-map',f'0:a:{stream}',
                    '-vn','-ac',str(self.channels),'-ar',str(self.rate),'-f','f32le',str(decoded)])
            if decoded.stat().st_size%(4*self.channels):raise RuntimeError('Incomplete PCM sample in decoded audio.')
            self.files[key]=decoded
        decoded=self.files[key];frame_bytes=4*self.channels
        first=round(start*self.rate);last=round((start+duration)*self.rate)
        available=decoded.stat().st_size//frame_bytes
        if first>=available or min(last,available)-first < (duration-.10)*self.rate:
            raise RuntimeError(f'Decoded audio ends too early for {start:.3f}–{start+duration:.3f}s; no padding was added.')
        remaining=(min(last,available)-first)*frame_bytes
        with decoded.open('rb') as src,Path(destination).open('wb') as dst:
            src.seek(first*frame_bytes)
            while remaining:
                block=src.read(min(remaining,4*1024*1024))
                if not block:raise RuntimeError('Unexpected end of decoded audio.')
                dst.write(block);remaining-=len(block)
