"""Optional integration smoke: actual downloaded AST/DINOv2 weights and FFmpeg.

Not part of ordinary unit tests or the base portable's dependencies.
Run on a networked machine after installing requirements-sync-ai.txt.
"""
from pathlib import Path
import subprocess
import tempfile

import numpy as np

import ai_sync

def main():
    import visual_core as vc
    with tempfile.TemporaryDirectory(prefix="autosync-ai-smoke-") as td:
        root = Path(td)
        audio=root/"source.wav"
        video=root/"scene.mp4"
        subprocess.run([vc.binary("ffmpeg"),"-v","error","-y","-f","lavfi",
            "-i","sine=frequency=600:sample_rate=16000:duration=34",
            "-c:a","pcm_s16le",str(audio)],check=True,timeout=90)
        subprocess.run([vc.binary("ffmpeg"),"-v","error","-y","-f","lavfi",
            "-i","testsrc=size=224x224:rate=1:duration=36",
            "-c:v","mpeg4",str(video)],check=True,timeout=90)
        times,features=ai_sync._audio_vectors(audio,0,print)
        assert len(times)>=3 and len(features)==len(times)
        assert features.shape[1]>64 and np.all(np.isfinite(features))
        repeated_t,repeated_f=ai_sync._audio_vectors(audio,0,print)
        np.testing.assert_array_equal(repeated_f,features)
        np.testing.assert_array_equal(repeated_t,times)
        v_times,v_features=ai_sync._image_vectors(video,print)
        assert len(v_times)>=2 and len(v_features)==len(v_times)
        assert v_features.shape[1]>64 and np.all(np.isfinite(v_features))
    print("AI Sync smoke passed: AST audio features + DINOv2 visual features + cache.")

if __name__=="__main__":
    main()
