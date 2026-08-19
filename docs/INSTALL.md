# Installation

Setup guide for **nuke-fal-ai-tools**.

If an AI agent is installing this for a user: follow this document exactly. Point Nuke at the folder that contains `init.py` (not the inner `nuke/` folder). Use system Python 3 for pip (`py -3` on Windows, `python3` elsewhere), not Nuke's embedded Python. Ask before editing `~/.nuke/init.py` or replacing an existing `NUKE_PATH`. Do not write the API key into a `.nk` script or a committed file; leave that to **fal.ai -> Settings...** or `FAL_KEY`.

**Platform support:** Developed and tested on **Windows** only. macOS and Linux should work with the same env vars and folder layout, but path separators, Python launchers, and Nuke installs differ -- see [macOS / Linux](#macos--linux) below. Report platform-specific issues on GitHub.

## Requirements

| Item | Notes |
|------|--------|
| **Foundry Nuke** | Nuke 8.0+ (tested on 11.3v6 and 17.0v2). Group nodes; **embedded Python 2.7 or 3.x** (toolkit auto-detects) |
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

You need **both**: Nuke runs the graph-side runners; your OS Python 3 runs the API helpers. The **Python 3 cmd** knob (closed **Advanced** tab, default `py -3`) points at the system interpreter, not Nuke's. On macOS/Linux the runner treats that baked `py -3` value as `python3`.

Some nodes walk the node graph for inputs (sequences, video). Non-Indie Nuke may be required for full graph-walking behavior; if a node fails to find upstream inputs, check your Nuke license tier.

## 1. Get the toolkit

Pick a permanent install location, for example:

```text
C:\Tools\nuke-fal-ai-tools
```

Nuke must load the folder that contains `init.py`, `menu.py`, and `nuke/` (the **install root**). Do **not** point at the inner `nuke/` folder.

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

Each group's closed **Advanced** tab has a **Python 3 cmd** knob. The shipped default is `py -3` (Windows). On macOS/Linux the runner treats that baked `py -3` value as `python3`, so you usually do not need to change it. Set a full path only if helpers should use a venv or a non-default interpreter.

## 3. Set your fal.ai API key

Keys resolve in this cascade (each layer can override the one below):

```text
studio-wide FAL_KEY  ->  local Settings config  ->  per-node FAL knob
     (fallback)              (this machine)           (script override)
```

| Layer | Where | Role |
|-------|--------|------|
| Studio-wide | Environment variable `FAL_KEY` | Shared fallback for farms, launchers, and machines with no local Settings key |
| Local machine | **fal.ai -> Settings...** -> `~/.nuke-fal-ai/config.json` | Artist/machine key for this user account; overrides `FAL_KEY` when set |
| Per-node | Group **FAL** knob (Advanced tab) | Overrides both for that node only; **saved into the `.nk` script** |

**Key resolution order** (highest first):

1. Non-empty per-node **FAL** knob (not the placeholder text)
2. `fal_key` in `~/.nuke-fal-ai/config.json` (Settings)
3. Environment variable `FAL_KEY`

**Studios / shared machines:** set `FAL_KEY` on the user or machine (or in the Nuke launcher) as the studio-wide default. Artists can still override with Settings on their machine, or with a per-node knob when needed. Runners pass the resolved key to helpers via the subprocess environment (not the command line).

**Artists (simple):** after Nuke loads the toolkit, open **fal.ai -> Settings...**, paste the API key, click **Save**, then optionally **Test connection**. File permissions are set to owner-only on Unix when possible.

**Per-node override:** paste a key into the **FAL** knob only when you need a one-off override. Never share, email, or commit scripts that contain a real key. Clear the knob and use Settings or `FAL_KEY` when collaborating.

Get a key at [fal.ai](https://fal.ai/?utm_source=nuke-fal-ai-tools&utm_medium=docs&utm_campaign=install).

## 4. Tell Nuke where the toolkit lives

Use **either** method. Both must point at the **install root** (the folder that contains `init.py`), **not** `.../nuke/`.

### Method A: `pluginAddPath` in `~/.nuke/init.py` (artists)

Where is `~/.nuke`?

| OS | Typical path |
|----|----------------|
| Windows | `C:\Users\<you>\.nuke\` |
| macOS | `/Users/<you>/.nuke/` |
| Linux | `/home/<you>/.nuke/` |

Create or edit `init.py` in that folder and add one line (use your real install path):

```python
nuke.pluginAddPath("C:/Tools/nuke-fal-ai-tools")
```

On macOS/Linux, forward slashes work the same way:

```python
nuke.pluginAddPath("/opt/nuke-fal-ai-tools")
```

To print the exact line for the current checkout:

```powershell
py -3 tools/print_install_line.py
```

Restart Nuke after saving `~/.nuke/init.py`.

### Method B: `NUKE_PATH` (studios / experts)

Nuke loads `init.py` and `menu.py` from directories listed in `NUKE_PATH`.

Point `NUKE_PATH` at the **repository root**:

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

Restart Nuke after changing `NUKE_PATH`. No other path variables are required -- the toolkit locates `nuke/python/` and `nuke/groups/` relative to `init.py`.

## macOS / Linux

Same variables and repo layout as Windows; adjust paths and the system Python launcher.

| Item | Windows (tested) | macOS / Linux (untested) |
|------|------------------|---------------------------|
| Install root example | `C:\Tools\nuke-fal-ai-tools` | `/opt/nuke-fal-ai-tools` or `~/tools/nuke-fal-ai-tools` |
| `~/.nuke` | `%USERPROFILE%\.nuke` | `~/.nuke` |
| `NUKE_PATH` separator | `;` between paths | `:` between paths |
| System Python 3 | `py -3` (default on nodes) | Usually `python3`. The runner maps baked `py -3` to `python3`; override **Advanced / Python 3 cmd** only if needed |
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

**Artist load via `~/.nuke/init.py`**

```python
nuke.pluginAddPath("/Users/you/tools/nuke-fal-ai-tools")
```

**Environment variables (bash / zsh -- add to `~/.bashrc`, `~/.zshrc`, or your Nuke launcher script)**

```bash
export NUKE_PATH="$HOME/tools/nuke-fal-ai-tools${NUKE_PATH:+:$NUKE_PATH}"
export FAL_KEY="your-fal-api-key"   # optional if using Settings or per-node key
```

Launch Nuke from a shell that has these exports, or set them in the same place you already configure `NUKE_PATH` for other tools. Restart Nuke after changes.

**Verify Python 3 + fal-client**

```bash
python3 -c "import fal_client; print('ok')"
```

If helpers fail immediately, set **Advanced / Python 3 cmd** to the same interpreter you used for `pip install` (e.g. `/usr/bin/python3` or a venv path). On macOS/Linux the shipped `py -3` default is already treated as `python3`.

## 5. Use the tools

After restart:

1. **Nodes -> fal.ai** - pick a tool (recommended; paths are set automatically). Tab search matches labels prefixed with `fal ` (e.g. type `fal nano`).
2. Or use the top **fal.ai** menu (includes **Settings...**).
3. Connect inputs as described in each node's on-graph hint text.
4. Save your Nuke script before running (runners write temp files relative to the saved script).
5. Click **Execute**.

### Temp and output folders

Each Execute creates timestamped subfolders under:

- `nuke_fal_temp/` -- prerender scratch (PNG sequences, intermediate mp4, etc.)
- `nuke_fal_output/` -- downloaded fal.ai results

If **fal.ai -> Settings...** has a **Default output folder** that exists (or can be created) and is writable, both folders are created under that path. Otherwise they live next to your **saved** `.nk` script. Save the script before Execute when using the script-folder fallback. Folders are **not** auto-deleted; remove old `*_YYYYMMDD_*` runs manually when you need disk space.

Video tools also honor **Video output** in Settings. The default is **DWAB EXR sequence**: after the MP4 lands, Nuke Writes a `name.####.exr` sequence next to it and the spawned Read points at the EXRs. Choose **MP4** to spawn a Read on the movie instead. The MP4 is kept either way.

Successful downloads also write a `.json` sidecar next to the primary result (same stem) with non-secret run metadata.

### Path placeholders

Shipped group nodes store script paths as:

```text
__INSTALL_ROOT__/nuke/python/<script>.py
```

At run time, `__INSTALL_ROOT__` is replaced with the repo root (derived from `init.py`). If the layout is wrong or the toolkit is not on the Nuke path, Nuke shows an error -- see [troubleshooting.md](troubleshooting.md).

## Updating

Restart Nuke after updating. No path changes are needed if the install folder path stays the same.

### Zip install

1. Download the new release zip from [Releases](https://github.com/JuusoKaari/nuke-fal-ai-tools/releases/latest).
2. Extract over your existing install folder, or extract to a new folder and update `pluginAddPath` / `NUKE_PATH`.
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
