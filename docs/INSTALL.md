# Installation

Setup guide for **nuke-fal-ai-tools**.

**Platform support:** Developed and tested on **Windows** only. macOS and Linux should work with the same env vars and folder layout, but path separators, Python launchers, and Nuke installs differ — see [macOS / Linux](#macos--linux) below. Report platform-specific issues on GitHub.

## Requirements

| Item | Notes |
|------|--------|
| **Foundry Nuke** | Nuke 11+ Group nodes; **embedded Python 2.7 or 3.x** (toolkit auto-detects) |
| **System Python 3** | Separate from Nuke - runs `*_helper.py` and `fal-client` via subprocess |
| **`fal-client`** | Installed into system Python 3 (`pip install -r requirements-python3.txt`) |
| **ffmpeg + ffprobe** | On `PATH` for video prerender, Read frame-range probing, and some video tools (e.g. Veo extend tail-trim). [ffmpeg.org](https://ffmpeg.org/download.html) builds usually include both. |
| **fal.ai account** | Your own API key - usage is billed to you |
| **Internet** | Helpers call fal.ai cloud APIs |

### Two Python versions (important)

| Runtime | Version | What runs there |
|---------|---------|-----------------|
| **Nuke embedded** | 2.7 (classic) or 3.x (Nuke 13.2+) | `init.py`, `menu.py`, `*_runner_*.py`, prerender utilities |
| **System / shell** | Python 3 | `*_helper.py`, `fal-client`, fal.ai HTTP calls |

You need **both**: Nuke runs the graph-side runners; your OS Python 3 runs the API helpers. The **Python 3 cmd** knob on each node (default `py -3`) points at the system interpreter, not Nuke's.

Some nodes walk the node graph for inputs (sequences, video). Non-Indie Nuke may be required for full graph-walking behavior; if a node fails to find upstream inputs, check your Nuke license tier.

## 1. Get the toolkit

Pick a permanent install location, for example:

```text
C:\Tools\nuke-fal-ai-tools
```

`NUKE_PATH` must point at the folder that contains `init.py`, `menu.py`, and `nuke/` (the install root).

### Option A: Download release zip (recommended)

1. Open the [latest release](https://github.com/JuusoKaari/nuke-fal-ai-tools/releases/latest).
2. Download `nuke-fal-ai-tools-vX.Y.Z.zip` (asset name matches the release tag).
3. Extract the zip. It contains a single top-level folder `nuke-fal-ai-tools/`.
4. Move or rename that folder to your install path, e.g. `C:\Tools\nuke-fal-ai-tools`.

After extraction, `C:\Tools\nuke-fal-ai-tools\init.py` should exist.

### Option B: Clone with Git

Use this if you prefer `git pull` for updates.

```powershell
git clone https://github.com/JuusoKaari/nuke-fal-ai-tools.git C:\Tools\nuke-fal-ai-tools
```

## 2. Install Python 3 dependencies

From the repo root:

```powershell
cd C:\Tools\nuke-fal-ai-tools
py -3 -m pip install -r requirements-python3.txt
```

Verify:

```powershell
py -3 -c "import fal_client; print('ok')"
```

Each group's **Advanced → Python 3 cmd** knob defaults to `py -3`. Change it if your launcher is `python3` or a full path.

## 3. Set your fal.ai API key

**Recommended:** set user environment variable `FAL_KEY` to your secret key. Runners pass it to helpers via the subprocess environment (not the command line).

**Alternative:** paste the key into the **FAL** knob on each node. That value is **saved into the `.nk` script** — never share, email, or commit scripts that contain a real key. Clear the knob and use `FAL_KEY` instead when collaborating.

Get a key at [fal.ai](https://fal.ai/?utm_source=nuke-fal-ai-tools&utm_medium=docs&utm_campaign=install).

## 4. Add to `NUKE_PATH`

Nuke loads `init.py` and `menu.py` from directories listed in `NUKE_PATH`.

Point `NUKE_PATH` at the **repository root** (the folder that contains `init.py`, `menu.py`, and `nuke/`):

```text
C:\Tools\nuke-fal-ai-tools
```

Append to your existing `NUKE_PATH` if you already use custom tools.

**Windows user environment variable example**

```text
NUKE_PATH=C:\Tools\nuke-fal-ai-tools
```

Or combine paths (semicolon-separated on Windows):

```text
NUKE_PATH=C:\Other\NukeTools;C:\Tools\nuke-fal-ai-tools
```

Restart Nuke after changing `NUKE_PATH`. No other path variables are required — the toolkit locates `nuke/python/` and `nuke/groups/` relative to `init.py`.

## macOS / Linux

Same variables and repo layout as Windows; adjust paths and the system Python launcher.

| Item | Windows (tested) | macOS / Linux (untested) |
|------|------------------|---------------------------|
| Install root example | `C:\Tools\nuke-fal-ai-tools` | `/opt/nuke-fal-ai-tools` or `~/tools/nuke-fal-ai-tools` |
| `NUKE_PATH` separator | `;` between paths | `:` between paths |
| System Python 3 | `py -3` (default on nodes) | Usually `python3` — set **Advanced → Python 3 cmd** on each node |
| pip install | `py -3 -m pip install -r requirements-python3.txt` | `python3 -m pip install -r requirements-python3.txt` |

**Download zip (recommended)**

1. Get the [latest release zip](https://github.com/JuusoKaari/nuke-fal-ai-tools/releases/latest).
2. Extract the `nuke-fal-ai-tools/` folder to e.g. `~/tools/nuke-fal-ai-tools`.
3. From that folder:

```bash
cd ~/tools/nuke-fal-ai-tools
python3 -m pip install -r requirements-python3.txt
```

**Clone with Git (alternative)**

```bash
git clone https://github.com/JuusoKaari/nuke-fal-ai-tools.git ~/tools/nuke-fal-ai-tools
cd ~/tools/nuke-fal-ai-tools
python3 -m pip install -r requirements-python3.txt
```

**Environment variables (bash / zsh — add to `~/.bashrc`, `~/.zshrc`, or your Nuke launcher script)**

```bash
export NUKE_PATH="$HOME/tools/nuke-fal-ai-tools${NUKE_PATH:+:$NUKE_PATH}"
export FAL_KEY="your-fal-api-key"   # optional if set per node
```

Launch Nuke from a shell that has these exports, or set them in the same place you already configure `NUKE_PATH` for other tools. Restart Nuke after changes.

**Verify Python 3 + fal-client**

```bash
python3 -c "import fal_client; print('ok')"
```

If helpers fail immediately, set each node's **Python 3 cmd** to the same interpreter you used for `pip install` (e.g. `/usr/bin/python3` or a venv path).

## 5. Use the tools

After restart:

1. **Nodes → fal.ai** - pick a tool (recommended; paths are set automatically).
2. Connect inputs as described in each node's on-graph hint text.
3. Save your Nuke script before running (runners write temp files relative to the saved script).
4. Click **Execute**.

### Temp and output folders

Each Execute creates timestamped subfolders under:

- `nuke_fal_temp/` — prerender scratch (PNG sequences, intermediate mp4, etc.)
- `nuke_fal_output/` — downloaded fal.ai results

By default these live next to your **saved** `.nk` script (or under system temp if the script is unsaved). Folders are **not** auto-deleted; remove old `*_YYYYMMDD_*` runs manually when you need disk space.

### Path placeholders

Shipped group nodes store script paths as:

```text
__INSTALL_ROOT__/nuke/python/<script>.py
```

At run time, `__INSTALL_ROOT__` is replaced with the repo root (derived from `init.py` on `NUKE_PATH`). If the layout is wrong or `NUKE_PATH` is missing, Nuke shows an error — see [troubleshooting.md](troubleshooting.md).

## Updating

Restart Nuke after updating. No `NUKE_PATH` changes are needed if the install folder path stays the same.

### Zip install

1. Download the new release zip from [Releases](https://github.com/JuusoKaari/nuke-fal-ai-tools/releases/latest).
2. Extract over your existing install folder, or extract to a new folder and update `NUKE_PATH`.
3. Reinstall Python dependencies:

```powershell
cd C:\Tools\nuke-fal-ai-tools
py -3 -m pip install -r requirements-python3.txt
```

### Git install

```powershell
cd C:\Tools\nuke-fal-ai-tools
git pull
py -3 -m pip install -r requirements-python3.txt
```

## License

This project is licensed under the **Mozilla Public License 2.0** - see [LICENSE](../LICENSE) in the repository root.
