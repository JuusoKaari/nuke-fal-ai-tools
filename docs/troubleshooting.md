# Troubleshooting

Common issues when setting up or running **nuke-fal-ai-tools**.

**Supported Nuke versions:** Nuke 8.0+ (tested on 11.3v6 and 17.0v2). Older or untested builds may work but are not verified.

## Install layout invalid / bootstrap error on startup

**Symptom:** Dialog on Nuke startup mentioning missing `nuke/python`, or traceback from `init.py`.

**Fix:**

1. Download the [latest release zip](https://github.com/JuusoKaari/nuke-fal-ai-tools/releases/latest) or clone the [repository](https://github.com/JuusoKaari/nuke-fal-ai-tools).
2. Add the **install root** (not the inner `nuke/` folder) to `NUKE_PATH` — see [INSTALL.md](INSTALL.md).
3. Confirm the folder contains `init.py`, `menu.py`, and `nuke/python/`.
4. Fully quit and restart Nuke (environment variables are read at process start).
5. Confirm in PowerShell: `echo $env:NUKE_PATH` includes your clone path.

## Nodes menu missing **fal.ai**

**Symptom:** No **Nodes → fal.ai** submenu.

**Checks:**

- `NUKE_PATH` includes the repo root (e.g. `...\nuke-fal-ai-tools`), not `...\nuke-fal-ai-tools\nuke`.
- Script Editor shows no traceback from `init.py` / `menu.py` on startup.

## Nuke with Python 3 (`NameError: execfile` / Execute does nothing)

**Symptom:** Execute fails on Nuke 13.2+ / 14 with Python 3 embedded; older builds worked.

**Fix:** Use a current clone that includes `_nuke_py_compat.py` and `_nuke_runner_launcher.py`. Group Execute knobs must call `_nuke_runner_launcher.execute_this_node()`, not `execfile()` directly. Re-create nodes from **Nodes → fal.ai** after updating.

**Note:** Py3-Nuke (Nuke 13.2+) is supported alongside classic Py2.7 Nuke. The toolkit targets Nuke 8.0+; primary testing is on 11.3v6 and 17.0v2. Report issues with your Nuke version and `sys.version` from the Script Editor.

## `Missing runner script` or `Missing helper script`

**Symptom:** Execute fails; path points at wrong folder or old dev machine path. The error dialog includes the GitHub repo link.

**Fix:**

1. Install or update from the [latest release](https://github.com/JuusoKaari/nuke-fal-ai-tools/releases/latest) or [repository](https://github.com/JuusoKaari/nuke-fal-ai-tools).
2. Confirm files exist under `<repo-root>\nuke\python\` (helpers and runners).
3. On the node, **Advanced → Helper path** and **Runner path** should look like:
   `__INSTALL_ROOT__/nuke/python/fal_....py`
4. Re-create the node from **Nodes → fal.ai** if knobs were edited manually or the node came from an older script with legacy filenames.

## `py -3` not found / helper fails immediately

**Symptom:** Runner prints an error; helper never runs; exit code non-zero.

**Fix:**

```powershell
py -3 --version
py -3 -m pip install -r requirements-python3.txt
```

If `py` is unavailable, set the node's **Python 3 cmd** to your launcher, e.g. `python3` or `C:\Python312\python.exe`.

## `failed to import fal_client`

**Symptom:** Helper stderr mentions `fal_client` import error.

**Fix:** Install into the **same** Python 3 that `py -3` runs:

```powershell
py -3 -m pip install fal-client
```

## fal.ai API / authentication errors

**Symptom:** HTTP 401/403, "invalid key", or fal-client `FalClientHTTPError`.

**Fix:**

- Set `FAL_KEY` in the environment (recommended), or a real key in the node's **FAL** knob (not the placeholder text).
- If you pasted a key into **FAL**, it is stored in the saved `.nk` — rotate the key on fal.ai if the script was shared or committed by mistake.
- Confirm billing/credits on your [fal.ai](https://fal.ai/) account.
- Model endpoints can change; check fal.ai model pages linked in helper script headers.

## `ffmpeg` / `ffprobe` not found

**Symptom:** Video prerender fails, Read nodes stay at frame 1-1, or Veo extend reports ffmpeg trim errors.

**Fix:**

- Install [ffmpeg](https://ffmpeg.org/download.html) and ensure **both** `ffmpeg` and `ffprobe` are on `PATH` in the environment that launches Nuke.
- Verify in a terminal:

```powershell
ffmpeg -version
ffprobe -version
```

- Restart Nuke after updating `PATH`. Video nodes need this for prerender-to-mp4, probing frame counts, and some input trimming.

## Script not saved

**Symptom:** Warning about unsaved Nuke script; writes fail or land in unexpected folders.

**Fix:** Save the `.nk` script before Execute. Runners create temp/output folders near the saved script.

## Disk usage (`nuke_fal_temp` / `nuke_fal_output`)

**Symptom:** Large folders appearing next to your `.nk` scripts after many runs.

**Expected:** Each Execute adds timestamped subfolders under `nuke_fal_temp/` (scratch) and `nuke_fal_output/` (downloads). Nothing is auto-cleaned.

**Fix:** Delete old `*_YYYYMMDD_*` subfolders when you no longer need them. Keep folders for runs whose Read nodes still point at those files.

## Prerender / sequence issues

**Symptom:** Wrong frame, empty input, or prerender errors for sequence/video nodes.

**Checks:**

- Upstream Read nodes have valid file paths and frame ranges.
- For video tools, source media is readable and within model limits (duration, resolution).
- Save the script and check the Script Editor for prerender log lines.

## Timeouts and long runs

Video generation and upscaling can take several minutes. Watch the Script Editor for helper stdout. If fal.ai queues the job, wait for completion; interrupting Nuke may leave partial temp files under the script directory.

## Still stuck?

Open a GitHub issue with:

- Nuke version (tested: 11.3v6, 17.0v2; minimum stated: 8.0+)
- Node name
- Redacted Script Editor log (no API keys)
- Whether you used the menu or pasted a group node from an old script

This project is **as-is** - there is no guaranteed support SLA.
