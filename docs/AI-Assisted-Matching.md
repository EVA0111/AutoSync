# AI-assisted matching — optional (v1.3.0)

**You do not need AI matching.** In v1.3.0, when both videos are present AutoSync matches by picture, and that engine gives the same result with **Standard** or **AI-assisted** selected (measured on all 64 test runs). AI-assisted matching only helps the older audio-matching engine, which is used when a video is missing.

AI-assisted is a **matching method**, not an output mode: you still choose **Full target audio**, **Main episode only** or **Keep opening & ending** separately.

## Install the AI models

1. Open **Settings** (top right).
2. Under **Engine & AI models**, click **Install AI Sync models**. This downloads optional PyTorch/Transformers packages and can be large.
3. Keep internet access: the model weights download on the first AI run and are cached afterwards.

**Install subtitle AI** is a different button, for subtitle workflows only.

If your graphics card cannot run the installed GPU build (for example some RTX 50-series cards with older CUDA builds), AutoSync detects it and uses the CPU instead of failing.

## Use it

In the **Audio** tab, under **Matching → Method**, choose **AI-assisted (experimental)**, then start as usual.

## What it does

- An **Audio Spectrogram Transformer (AST)** proposes matching points between the two soundtracks.
- **DINOv2-small** scene matching can help where conventional scene matching is weak.
- AutoSync checks every proposed point against the original sound and applies the usual safety rules.

[← Wiki home](Home.md) · [Getting started](Getting-Started.md)
