# AI-assisted matching — optional (v1.2.0)

**For a first sync, use Standard instead.** AI-assisted matching is experimental, takes additional installation space and time, and does not guarantee better alignment.

AI-assisted matching is **not an output mode**. You still choose **Full target audio**, **Main episode only**, or **Keep opening & ending** separately.

## Install the AI models

1. Extract and open **AutoSync.exe** from the [Windows v1.2.0 release](https://github.com/EVA0111/AutoSync/releases/tag/v1.2.0) as explained in [Getting started](Getting-Started.md).
2. Open **Settings** (the gear button).
3. Expand **Setup**.
4. Click **Install AI Sync models**.
5. Follow the installation progress / any instructions. This step installs optional PyTorch/Transformers-related dependencies and can require a substantial download.
6. Keep internet access available. The pretrained model weights download when AI matching runs for the first time, then are cached for later runs.

**Important distinction:** **Install subtitle AI** is a different option for subtitle workflows. It is **not** the button for AI-assisted **audio** matching. Standard audio synchronization does not need either installation.

No separate manual Python installation is needed for the official Windows portable package. The project notes that compatible PyTorch CUDA may use a GPU; otherwise AI may run on CPU. Exact machine requirements and download size are not documented.

## Start an AI-assisted sync

1. Open **Audio** and check **Include audio jobs**.
2. Add the source video containing the desired audio under **Source**.
3. Add the video to match under **Target**.
4. Select the correct **Source audio** and **Target reference audio** tracks.
5. Choose the **Sync mode** appropriate for your output.
6. Under **Matching method**, change **Standard (default)** to **AI-assisted (experimental)**.
7. In **Save output**, leave the default destination or choose a folder.
8. Wait until the readiness message says **Ready to sync the selected jobs**, then click **Start selected jobs**.
9. Check the **Jobs** result and review difficult sections in **Preview & Edit**.

If the installation or AI run fails, check the activity information, return to **Standard**, and try the basic workflow. AI-assisted matching should never be your only copy of a project or a substitute for checking output.

## What does AI mode do?

- It uses a pretrained **Audio Spectrogram Transformer (AST)** to propose audio correspondence points.
- It may use **DINOv2-small** scene matches as a fallback where conventional picture matching is weak.
- AutoSync still checks proposed audio points against original sound and applies the normal cut-safety rules.
- It may be slower on the first run because the models need to download and warm up.

Reused music, different-language dubs, altered sound effects, silent footage and edited scene order can still be hard to match. **AI does not make every sync correct**; verify suspicious timing and never automatically trust flagged cuts.

## Open questions

The repository does not yet give a definitive beginner-friendly table of exact AI download sizes, disk-space needs, expected performance on CPU/GPU, or a demonstrated comparison showing where AI outperforms Standard for real videos. These should be documented after practical validation.

[← Wiki home](Home.md) · [Getting started](Getting-Started.md)
