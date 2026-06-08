# nuke-fal-ai-tools

Open-source toolbox of **fal.ai**-powered nodes for [Foundry Nuke](https://www.foundry.com/products/nuke). Image generation, editing, inpainting, depth, layering, 3D, and several video workflows - run directly from the node graph with your own fal.ai API key.

<a href="https://www.youtube.com/watch?v=nRTBxsMcXe0" title="Watch demo on YouTube">
  <img src="docs/demo.gif" alt="nuke-fal-ai-tools demo (click to watch on YouTube)" width="960">
</a>

**Status:** v0.1.0 - released **as-is** for technically capable compositors. Not a commercial product; APIs, models, and paths may change.

## What's included

16 Group nodes under **Nodes → fal.ai**:

| Category | Tools |
|----------|--------|
| **Image** | Nano Banana 2, Qwen Image Max, GPT Image 2, Qwen Inpaint, Finegrain Eraser, BiRefNet v2, Depth Anything v2, Qwen Layered |
| **Video** | LTX 2.3, Seedance 2, Pika v2.2, Kling O3, Veo 3.1, ByteDance Upscaler, DreamActor v2 |
| **3D** | Hunyuan 3D |

See [CHANGELOG.md](CHANGELOG.md) for the full v0.1.0 list.

## Quick start

1. Download the [latest release zip](https://github.com/JuusoKaari/nuke-fal-ai-tools/releases/latest) and extract it — or `git clone` if you prefer updates via `git pull`.
2. Add the **install root** (folder with `init.py`) to **`NUKE_PATH`** (e.g. `C:\Tools\nuke-fal-ai-tools`).
3. `py -3 -m pip install -r requirements-python3.txt`
4. Set **`FAL_KEY`** (fal.ai API key) in your environment — preferred over pasting into node knobs (keys in saved `.nk` scripts are a leak risk).
5. Restart Nuke → **Nodes → fal.ai**.

Full steps: **[docs/INSTALL.md](docs/INSTALL.md)** · Problems: **[docs/troubleshooting.md](docs/troubleshooting.md)**

## Requirements

- Foundry Nuke with **embedded Python 2.7 or 3.x** (Nuke 11-14+; Py3-Nuke tested on Nuke 13.2+ / 14)
- **System Python 3** for fal API helpers (`py -3` on Windows by default; `python3` on macOS/Linux) - separate from Nuke's interpreter
- **ffmpeg** and **ffprobe** on `PATH` for video prerender, frame probing, and some video tools (see [docs/INSTALL.md](docs/INSTALL.md))
- **Windows** install path tested; macOS/Linux should work but are not regularly tested (see [docs/INSTALL.md](docs/INSTALL.md))
- [`fal-client`](requirements-python3.txt) installed in that system Python 3
- fal.ai account - **you pay for API usage**

## How it works

```text
Nuke Group (.nk)  →  runner (inside Nuke)  →  helper (system Py 3 + fal-client)  →  fal.ai
```

Two Python runtimes:

| Where | Python | Role |
|-------|--------|------|
| **Inside Nuke** | Nuke's embedded 2.7 or 3.x | Runners, prerender, Read/Geo spawn (`nuke/python/*_runner_*.py`) |
| **Outside Nuke** | Your system Python 3 | fal.ai API calls (`*_helper.py` via subprocess) |

Runners pre-render inputs, call helpers via subprocess, then spawn Read (or Geo) nodes for results. `_nuke_py_compat.py` picks `execfile` vs `exec()` based on Nuke's version.

Script paths use `__INSTALL_ROOT__/nuke/python/...`, resolved at runtime from the repo root (where `init.py` lives on `NUKE_PATH`).

## Disclaimer

- **Costs:** Every Execute call uses fal.ai; charges go to your account.
- **API keys:** Prefer the `FAL_KEY` environment variable. Keys pasted into a node's **FAL** knob are stored in the `.nk` script — do not share or version-control scripts that contain real keys.
- **Disk usage:** Each run creates timestamped folders under `nuke_fal_temp/` and `nuke_fal_output/` next to your saved script (or system temp). Delete old runs manually if disk space matters.
- **Availability:** Third-party models and endpoints can change, rate-limit, or disappear.
- **Support:** Community / best-effort via GitHub issues only.
- **No warranty:** Use at your own risk in production pipelines.

## License

[Mozilla Public License 2.0](LICENSE) (MPL 2.0).

## Links

- [Demo video (YouTube)](https://www.youtube.com/watch?v=nRTBxsMcXe0)
- [Latest release (zip download)](https://github.com/JuusoKaari/nuke-fal-ai-tools/releases/latest)
- [GitHub repository](https://github.com/JuusoKaari/nuke-fal-ai-tools) - source and issue tracker
- [fal.ai](https://fal.ai/) - API keys and model docs
- Model URLs are referenced in individual helper script headers under `nuke/python/`
