# nuke-fal-ai-tools

**fal.ai** nodes for [Foundry Nuke](https://www.foundry.com/products/nuke). Image, video, and 3D workflows from the node graph.

<a href="https://www.youtube.com/watch?v=nRTBxsMcXe0" title="Watch demo on YouTube">
  <img src="docs/demo.gif" alt="nuke-fal-ai-tools demo (click to watch on YouTube)" width="960">
</a>

Upcoming **v1.1.0**. APIs and models may change. Release notes: [CHANGELOG.md](CHANGELOG.md).

## Tools

32 tools under **Nodes -> fal.ai** (families with 2+ tools are submenus; singles stay flat; Utility last):

| Category | Tools |
|----------|--------|
| **Image** | Bria Extract Object, GPT Image 2 Edit, Hunyuan World, Nano Banana 2 Generate, **Qwen** (Qwen Image Inpaint, Qwen Image Layered, Qwen Image Max Edit), Seedream 5.0 Pro Edit, **Utility** (BiRefNet v2 Still, Depth Anything v2, Finegrain Eraser, Image upscale (Topaz Precision), SAM 3.1 Image) |
| **Video** | DreamActor v2 Motion Control, **FLUX 3** (FLUX 3 First/Last Frame to Video, FLUX 3 Keyframes to Video), Kling O3 V2V Edit, **LTX** (LTX 2.3 Image to Video, LTX 2.5 Image to Video Pro), **MiniMax** (MiniMax H3 Image to Video, MiniMax H3 Max Image to Video), Pika v2.2 Pikaframes, **Seedance** (Seedance 2 Image to Video, Seedance 2 Reference to Video, Seedance 2.5 Image to Video), Veo 3.1 Extend Video, **Utility** (BiRefNet v2, ByteDance Video Upscale) |
| **3D** | **Hunyuan 3D** (Hunyuan 3D Image to 3D, Hunyuan 3D Part) |
| **Text** | **OpenRouter** (Describe image, Generate text) |

## Quick start

Ask Claude, Codex, or Cursor to set it up:

```text
Help me install this toolset on my Nuke: https://github.com/JuusoKaari/nuke-fal-ai-tools
```

Or do it yourself:

1. Download the [latest release](https://github.com/JuusoKaari/nuke-fal-ai-tools/releases/latest) or `git clone`.
2. Point Nuke at the install **root** (folder with `init.py`, not the inner `nuke/`):
   - Artists: add one line to `~/.nuke/init.py`:
     `nuke.pluginAddPath("/path/to/nuke-fal-ai-tools")`
   - Studios: add that same folder to **`NUKE_PATH`**.
3. `py -3 -m pip install -r requirements-python3.txt`
4. Set your API key (cascade: studio `FAL_KEY` -> **fal.ai -> Settings...** on this machine -> optional per-node **FAL** knob).
5. Restart Nuke -> **Nodes -> fal.ai** (Tab search: type `fal`).

Install details: [docs/INSTALL.md](docs/INSTALL.md) · Issues: [docs/troubleshooting.md](docs/troubleshooting.md)

## Requirements

- Nuke 8.0+ (tested on 11.3v6 and 17.0v2)
- System Python 3.9+ with [`fal-client`](requirements-python3.txt) (`py -3` on Windows, `python3` elsewhere). Helpers use this OS interpreter, not Nuke's embedded Python 2.7 / 3.x.
- ffmpeg and ffprobe on `PATH` for video tools
- fal.ai account (usage is billed to you)

## How it works

```text
Nuke Group  ->  runner (in Nuke)  ->  helper (system Python 3.9+)  ->  fal.ai
```

Runners pre-render inputs inside Nuke, call helpers via subprocess, then wire results. Image Groups look through the connected plate on Output1. Recreate those nodes from the menu after updating. Video, 3D, and Text still spawn Read, Geo, or Text nodes.

## Notes

- Each Execute call bills your fal.ai account.
- API key cascade: studio-wide `FAL_KEY` -> local Settings (`~/.nuke-fal-ai/config.json`) -> per-node **FAL** knob.
- Output lands in `nuke_fal_temp/` and `nuke_fal_output/` next to your script (or under **fal.ai -> Settings...** Default output folder), plus a `.json` sidecar next to each primary result. **Open temp folder** / **Open output folder** on each Group Advanced tab (and in Settings) reveal those parent dirs. Video tools default to a DWAB EXR sequence Read (MP4 kept on disk; toggle in **fal.ai -> Settings...**).
- Best-effort support via [GitHub issues](https://github.com/JuusoKaari/nuke-fal-ai-tools/issues). No warranty.

## License

[Mozilla Public License 2.0](LICENSE) (MPL 2.0).

## Links

- [Demo (YouTube)](https://www.youtube.com/watch?v=nRTBxsMcXe0)
- [Latest release](https://github.com/JuusoKaari/nuke-fal-ai-tools/releases/latest)
- [fal.ai](https://fal.ai/) (API keys)
