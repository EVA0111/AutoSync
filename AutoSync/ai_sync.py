"""Optional learned audio/visual matching for AutoSync.

Only this mode imports torch/transformers. Model embeddings propose coarse
matches; the original 50 Hz audio correlation verifies timing. A neural cosine
similarity is *never* treated as a precise audio timestamp or cut instruction.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

import numpy as np
from scipy import ndimage

AUDIO_MODEL = "MIT/ast-finetuned-audioset-10-10-0.4593"
VISION_MODEL = "facebook/dinov2-small"
AUDIO_HOP = 8.
VISION_HOP = 12.
CACHE = Path.home() / ".cache" / "AutoSync" / "ai-sync"


def _dependencies():
    try:
        import torch
        from transformers import AutoFeatureExtractor, AutoImageProcessor, AutoModel, AutoModelForAudioClassification
        from PIL import Image
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "AI-assisted sync needs the optional AI Sync models and libraries. "
            "Open Settings > Install AI Sync first. Standard sync requires none of these."
        ) from exc
    return torch, AutoFeatureExtractor, AutoImageProcessor, AutoModel, AutoModelForAudioClassification, Image


def _key(file, stream, model, kind):
    p = Path(file).resolve()
    st = p.stat()
    return hashlib.sha256(json.dumps(
        [str(p), st.st_size, st.st_mtime_ns, stream, model, kind, AUDIO_HOP, VISION_HOP]
    ).encode("utf-8")).hexdigest()[:28]


def _load_cached(file, stream, model, kind):
    p = CACHE / (_key(file, stream, model, kind) + ".npz")
    if p.is_file():
        try:
            with np.load(p, allow_pickle=False) as data:
                ts, feats = np.asarray(data["times"], dtype=np.float32), np.asarray(data["vectors"], dtype=np.float32)
            if feats.ndim == 2 and len(feats) == len(ts) and np.all(np.isfinite(feats)):
                return ts, feats
        except (ValueError, KeyError, OSError):
            pass
    return None


def _save_cached(file, stream, model, kind, times, feats):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / (_key(file, stream, model, kind) + ".npz")
    with tempfile.NamedTemporaryFile(prefix="cache-", suffix=".npz", dir=CACHE, delete=False) as f:
        tmp = Path(f.name)
    try:
        np.savez_compressed(tmp, times=times, vectors=feats)
        os.replace(tmp, p)
    finally:
        tmp.unlink(missing_ok=True)


def _normalize(x):
    x = np.asarray(x, dtype=np.float32)
    return x / np.maximum(np.linalg.norm(x, axis=-1, keepdims=True), 1.e-8)


def candidate_pairs(target_times, target_vec, source_times, source_vec,
                    min_similarity=.91, min_margin=.06):
    """Reciprocal, unique nearest-neighbour matches (no timing inference)."""
    target_vec, source_vec = _normalize(target_vec), _normalize(source_vec)
    if not len(target_vec) or not len(source_vec):
        return np.empty((0, 3), dtype=np.float64)
    # Bound matrix storage for long films.
    scores = np.asarray(target_vec @ source_vec.T, dtype=np.float32)
    chosen = np.argmax(scores, axis=1)
    reverse = np.argmax(scores, axis=0)
    rows = []
    for i, j in enumerate(chosen):
        score = float(scores[i, j])
        alternatives = scores[i].copy()
        alternatives[np.abs(source_times - source_times[j]) < 20.] = -2.
        margin = score - float(np.max(alternatives))
        if (score >= min_similarity and margin >= min_margin and reverse[j] == i
                and np.isfinite(score) and np.isfinite(margin)):
            rows.append([float(target_times[i]), float(source_times[j]), score])
    return np.array(rows, dtype=np.float64).reshape(-1, 3)


def _consistent(rows, speed, tolerance=1.0, minimum=4, min_span=32.):
    """Keep only anchors supported by neighbouring offsets and monotonicity."""
    if len(rows) < minimum:
        return np.empty((0, 3), dtype=np.float64)
    rows = np.asarray(sorted(rows, key=lambda r: r[0]), dtype=np.float64)
    offsets = rows[:, 1] - float(speed) * rows[:, 0]
    keep = []
    for i in range(len(rows)):
        nearby = np.abs(rows[:, 0] - rows[i, 0]) <= 110
        if np.sum(np.abs(offsets[nearby] - offsets[i]) < tolerance) >= 3:
            keep.append(rows[i])
    if len(keep) < minimum:
        return np.empty((0, 3), dtype=np.float64)
    result = np.asarray(keep).reshape(-1, 3)
    result = result[np.argsort(result[:, 0])]
    monotonic = [result[0]]
    for item in result[1:]:
        if item[1] > monotonic[-1][1]:
            monotonic.append(item)
    result = np.asarray(monotonic).reshape(-1, 3)
    if len(result) < minimum or np.ptp(result[:, 0]) < min_span:
        return np.empty((0, 3), dtype=np.float64)
    return result


def verify_audio_candidates(candidates, source_features, target_features, speed, shift=0.,
                            threshold=.38, margin=.035):
    """Refine embedding matches with independent, precise 50 Hz acoustics."""
    import autosync
    if not len(candidates):
        return np.empty((0, 3), dtype=np.float64)
    scaled = ndimage.zoom(source_features, (1, 1 / speed), order=1)
    rows = []
    for t, s, semantic in candidates:
        # The model suggests ~8s resolution; the old engine determines samples.
        center = t - shift
        qstart = int(round((center - 2.) * autosync.RATE))
        qend = qstart + 4 * autosync.RATE
        expected = (s - 2. * speed) / speed * autosync.RATE
        start = max(0, int(round(expected - 4 * autosync.RATE)))
        stop = min(scaled.shape[1], int(round(expected + 8 * autosync.RATE)))
        if qstart < 0 or qend > target_features.shape[1] or stop - start < qend - qstart:
            continue
        scores = autosync.correlation(scaled[:, start:stop], target_features[:, qstart:qend])
        if not len(scores):
            continue
        idx = int(scores.argmax())
        score = float(scores[idx])
        alt = scores.copy()
        alt[max(0, idx-100):idx+101] = -2.
        if score < threshold or score - float(alt.max()) < margin:
            continue
        source_mid = (start + idx + 2 * autosync.RATE) / autosync.RATE * speed
        rows.append([float(t), float(source_mid), score])
    return _consistent(rows, speed, tolerance=.20, minimum=4, min_span=30.)


def _audio_vectors(file, stream, progress):
    cached = _load_cached(file, stream, AUDIO_MODEL, "audio")
    if cached is not None:
        progress("Reusing cached AI audio embeddings: " + Path(file).name)
        return cached
    torch, FeatureExtractor, _, _, AudioClassifier, _ = _dependencies()
    import visual_core as vc
    progress("Extracting 16 kHz audio for learned matching: " + Path(file).name)
    with tempfile.TemporaryDirectory(prefix="autosync-ai-audio-") as temp:
        pcm = Path(temp) / "mono.f32"
        vc.run([vc.binary("ffmpeg"), "-v", "error", "-nostdin", "-y", "-i", str(file),
                "-map", f"0:a:{int(stream)}", "-ac", "1", "-ar", "16000", "-f", "f32le", str(pcm)])
        audio = np.memmap(pcm, dtype="<f4", mode="r")
        duration = len(audio) / 16000.
        times = np.arange(4., duration - 4., AUDIO_HOP, dtype=np.float32)
        if len(times) == 0:
            return np.empty(0), np.empty((0, 768), dtype=np.float32)
        progress("Loading pretrained AST sound model (download on first use)…")
        extractor = FeatureExtractor.from_pretrained(AUDIO_MODEL)
        model = AudioClassifier.from_pretrained(AUDIO_MODEL, use_safetensors=True)
        model.eval()
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = model.to(device)
        vectors = []
        batch_size = 6 if device.type == "cuda" else 2
        with torch.inference_mode():
            for k in range(0, len(times), batch_size):
                windows = [np.asarray(audio[int(round((t-4.)*16000)):int(round((t+4.)*16000))]).copy()
                           for t in times[k:k+batch_size]]
                tensors = extractor(windows, sampling_rate=16000, return_tensors="pt")
                result = model(**{n: v.to(device) for n, v in tensors.items()}, output_hidden_states=True)
                # Acoustic latent representation, not class labels.
                vector = result.hidden_states[-1][:, 0, :].float().cpu().numpy()
                vectors.append(vector)
                if k % (batch_size*10) == 0:
                    progress(f"AI audio features: {min(k+batch_size,len(times))}/{len(times)}")
        vectors = _normalize(np.vstack(vectors))
    _save_cached(file, stream, AUDIO_MODEL, "audio", times, vectors)
    return times, vectors


def _image_vectors(file, progress):
    cached = _load_cached(file, 0, VISION_MODEL, "visual")
    if cached is not None:
        progress("Reusing cached AI scene embeddings: " + Path(file).name)
        return cached
    torch, _, ImageProcessor, ImageModel, _, Image = _dependencies()
    import visual_core as vc
    progress("Extracting sparse scene frames for DINOv2: " + Path(file).name)
    with tempfile.TemporaryDirectory(prefix="autosync-ai-video-") as tmp:
        raw = Path(tmp) / "frames.rgb"
        vf = f"setpts=PTS-STARTPTS,fps=1/{int(VISION_HOP)},scale=224:224,format=rgb24"
        vc.run([vc.binary("ffmpeg"), "-v", "error", "-nostdin", "-y", "-i", str(file),
                "-map", "0:v:0", "-an", "-sn", "-dn", "-vf", vf, "-fps_mode", "vfr",
                "-f", "rawvideo", "-pix_fmt", "rgb24", str(raw)])
        data = np.memmap(raw, dtype=np.uint8, mode="r")
        count = len(data) // (224 * 224 * 3)
        if count == 0:
            return np.empty(0), np.empty((0, 384), dtype=np.float32)
        frames = data[:count*224*224*3].reshape(count,224,224,3)
        processor = ImageProcessor.from_pretrained(VISION_MODEL)
        model = ImageModel.from_pretrained(VISION_MODEL, use_safetensors=True).eval()
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model.to(device)
        vectors = []
        batch_size = 12 if device.type == "cuda" else 4
        with torch.inference_mode():
            for k in range(0,count,batch_size):
                imgs=[Image.fromarray(np.asarray(frame).copy()) for frame in frames[k:k+batch_size]]
                tensors=processor(images=imgs,return_tensors="pt")
                result=model(**{n:v.to(device) for n,v in tensors.items()})
                vectors.append(result.last_hidden_state[:,0,:].float().cpu().numpy())
                if k % (batch_size*10) == 0:
                    progress(f"AI scene features: {min(k+batch_size,count)}/{count}")
        vectors = _normalize(np.vstack(vectors))
        times = np.arange(count,dtype=np.float32)*VISION_HOP
    _save_cached(file, 0, VISION_MODEL, "visual", times, vectors)
    return times, vectors


def learned_audio_anchors(source, stream, target, reference_stream, sf, rf, speed, refshift, progress):
    src_t, src_v = _audio_vectors(source, stream, progress)
    tgt_t, tgt_v = _audio_vectors(target, reference_stream, progress)
    proposed = candidate_pairs(tgt_t + refshift,tgt_v,src_t,src_v,
                               min_similarity=.88,min_margin=.055)
    progress(f"AI audio proposed {len(proposed)} unique matches; independently checking original sound…")
    verified = verify_audio_candidates(proposed,sf,rf,speed,refshift)
    progress(f"AI audio verified {len(verified)} precise anchors")
    return verified


def learned_visual_anchors(source, target, speed, delay, progress):
    src_t, src_v = _image_vectors(source, progress)
    tgt_t, tgt_v = _image_vectors(target, progress)
    proposed = candidate_pairs(tgt_t,tgt_v,src_t,src_v,
                               min_similarity=.93,min_margin=.055)
    if len(proposed):
        proposed[:,1] -= delay
    verified = _consistent(proposed,speed,tolerance=1.5,minimum=6,min_span=45.)
    progress(f"AI scene model verified {len(verified)} candidate timing anchors")
    return verified


def combine_standard_and_learned(standard, learned, speed):
    """Prefer proven standard anchors; learned matches only fill supported gaps."""
    base = np.asarray(standard,dtype=np.float64).reshape(-1,3)
    neural = np.asarray(learned,dtype=np.float64).reshape(-1,3)
    if not len(neural):
        return base
    result = list(base)
    for point in neural:
        t, s, _ = point
        if len(base) and np.min(abs(base[:,0] - t)) < 5.:
            continue
        near = base[np.abs(base[:,0] - t) < 90.]
        if len(near) >= 2:
            offsets = near[:,1] - speed*near[:,0]
            if abs((s-speed*t) - np.median(offsets)) > .35:
                continue
        result.append(point)
    return np.asarray(sorted(result,key=lambda x:x[0]),dtype=np.float64).reshape(-1,3)
