"""Runtime selection and duplicate-avoidance for mv-maker.

Scopes
- project (default): only the skill's own folders (this skill dir, the shared mv-maker runtime ~/.mv-maker),
  the current project and tools on PATH are inspected. No consent needed.
- machine (opt-in, needs the user's OK): READ-ONLY scan for existing Python environments, other mv-maker copies,
  FFmpeg installs, system fonts and downloaded model caches, so the agent can propose reuse instead of new installs.

Python used by the launchers (mv / mv.cmd), first match wins:
  $MV_PYTHON  ->  SKILL_DIR/runtime.txt (written by --use-python / --use-shared)  ->  SKILL_DIR/.venv  ->  ~/.mv-maker/venv
Nothing here installs into, or deletes from, an environment that mv-maker did not create.
"""
from __future__ import annotations

import glob
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
HOME = Path.home()
SHARED_HOME = Path(os.environ.get("MV_MAKER_HOME", HOME / ".mv-maker"))
SHARED_VENV = SHARED_HOME / "venv"
RUNTIME_TXT = SKILL_DIR / "runtime.txt"      # python path for the launchers
RUNTIME_JSON = SKILL_DIR / "runtime.json"    # extra settings read by mv.py (e.g. ffmpeg_dir)
WIN = platform.system() == "Windows"
REQUIRED = ["yaml", "yt_dlp", "librosa", "soundfile", "faster_whisper", "scenedetect", "cv2", "fontTools"]
OPTIONAL = ["torch", "demucs", "ctranslate2", "imageio_ffmpeg"]
PACK_FAMILIES = ["BeVietnamPro", "Anton", "Montserrat", "PlayfairDisplay", "DancingScript", "Pacifico"]

PROBE = r"""
import json, importlib.util, importlib.metadata as md, sys
mods = %s
out = {"python": sys.executable, "version": sys.version.split()[0], "mods": {}}
dist = {"yaml": "PyYAML", "yt_dlp": "yt-dlp", "cv2": "opencv-python-headless", "fontTools": "fonttools",
        "faster_whisper": "faster-whisper", "imageio_ffmpeg": "imageio-ffmpeg"}
for m in mods:
    if importlib.util.find_spec(m) is None:
        continue
    v = "?"
    for d in (dist.get(m, m), m, "opencv-python", "opencv-contrib-python"):
        try:
            v = md.version(d); break
        except Exception:
            pass
    out["mods"][m] = v
try:
    import ctranslate2; out["cuda"] = ctranslate2.get_cuda_device_count()
except Exception:
    out["cuda"] = 0
try:
    import imageio_ffmpeg; out["imageio_ffmpeg"] = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    pass
print(json.dumps(out))
"""


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if WIN else "bin/python")


def runtime_source() -> str:
    exe = Path(sys.executable).resolve()
    if os.environ.get("MV_PYTHON"):
        return "MV_PYTHON"
    if RUNTIME_TXT.exists() and Path(RUNTIME_TXT.read_text().strip()).resolve() == exe:
        return "runtime.txt (reused)" if not str(exe).startswith(str(SHARED_VENV.resolve())) else "shared"
    if str(exe).startswith(str((SKILL_DIR / ".venv").resolve())):
        return "local"
    if str(exe).startswith(str(SHARED_VENV.resolve())):
        return "shared"
    return "other"


def owned_by_mv(exe: Path) -> bool:
    """True for environments mv-maker created (its own .venv or the shared runtime) - the only ones it may modify."""
    e = str(Path(exe).resolve())
    return e.startswith(str((SKILL_DIR / ".venv").resolve())) or e.startswith(str(SHARED_VENV.resolve()))


def probe_python(exe: Path, timeout: int = 40) -> dict | None:
    try:
        r = subprocess.run([str(exe), "-I", "-c", PROBE % repr(REQUIRED + OPTIONAL)], capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        return json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 and r.stdout.strip() else None
    except Exception:
        return None


def dir_size_mb(p: Path, max_files: int = 200000) -> float:
    total, n = 0, 0
    for root, _, files in os.walk(p):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
            n += 1
            if n > max_files:
                return round(total / 2**20, 0)
    return round(total / 2**20, 0)


# ------------------------------------------------------------------ discovery
def _skill_copies(scope: str) -> list[Path]:
    """Folders that contain an mv-maker skill (SKILL.md with name: mv-maker)."""
    pats = [str(Path.cwd() / d / "mv-maker") for d in (".claude/skills", ".agents/skills", "skills")]
    if scope == "machine":
        pats += [str(HOME / ".claude/skills/*"), str(HOME / ".agents/skills/*"),
                 str(HOME / ".claude/plugins/cache/*/*/*/skills/mv-maker"),
                 str(HOME / ".claude/plugins/cache/*/*/skills/mv-maker"),
                 str(HOME / ".claude/plugins/marketplaces/*/skills/mv-maker")]
    seen, out = set(), []
    for pat in pats:
        for d in glob.glob(pat):
            sk = Path(d) / "SKILL.md"
            try:
                if sk.exists() and "name: mv-maker" in sk.read_text(encoding="utf-8", errors="ignore")[:400]:
                    r = Path(d).resolve()
                    if r not in seen:
                        seen.add(r)
                        out.append(Path(d))
            except OSError:
                continue
    return out


def _python_candidates(scope: str) -> list[tuple[str, Path]]:
    c: list[tuple[str, Path]] = []
    for sk in _skill_copies(scope):
        c.append((f"mv-maker copy: {sk}", venv_python(sk / ".venv")))
    c.append(("mv-maker shared runtime", venv_python(SHARED_VENV)))
    for d in (".venv", "venv", "env"):
        c.append((f"project env ./{d}", venv_python(Path.cwd() / d)))
    if scope == "machine":
        for name in ("python", "python3"):
            p = shutil.which(name)
            if p:
                c.append((f"PATH {name}", Path(p)))
        if WIN and shutil.which("py"):
            r = subprocess.run(["py", "-0p"], capture_output=True, text=True)
            for line in r.stdout.splitlines():
                parts = line.split()
                if parts and parts[-1].lower().endswith("python.exe"):
                    c.append(("py launcher " + parts[0], Path(parts[-1])))
        conda = shutil.which("conda")
        if conda:
            r = subprocess.run([conda, "env", "list", "--json"], capture_output=True, text=True, timeout=60)
            try:
                for env in json.loads(r.stdout).get("envs", []):
                    c.append((f"conda env {Path(env).name}", Path(env) / ("python.exe" if WIN else "bin/python")))
            except ValueError:
                pass
        for d in glob.glob(str(HOME / ".claude/skills/*/.venv")) + glob.glob(str(HOME / ".agents/skills/*/.venv")):
            c.append((f"other skill venv: {Path(d).parent.name}", venv_python(Path(d))))
    out, seen = [], set()
    for label, exe in c:
        try:
            r = exe.resolve()
        except OSError:
            continue
        if exe.exists() and r not in seen:
            seen.add(r)
            out.append((label, exe))
    return out[:20]


def _ffmpegs(scope: str) -> list[dict]:
    paths = []
    if WIN:
        r = subprocess.run(["where", "ffmpeg"], capture_output=True, text=True)
        paths += [l.strip() for l in r.stdout.splitlines() if l.strip()]
    else:
        r = subprocess.run(["sh", "-c", "which -a ffmpeg 2>/dev/null"], capture_output=True, text=True)
        paths += [l.strip() for l in r.stdout.splitlines() if l.strip()]
    if scope == "machine":
        pats = ([str(HOME / "AppData/Local/Microsoft/WinGet/Packages/*FFmpeg*/*/bin/ffmpeg.exe"),
                 "C:/ProgramData/chocolatey/bin/ffmpeg.exe", str(HOME / "scoop/apps/ffmpeg*/current/bin/ffmpeg.exe"),
                 "C:/ffmpeg/bin/ffmpeg.exe", "C:/Program Files/ffmpeg/bin/ffmpeg.exe"] if WIN else
                ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg", "/snap/bin/ffmpeg"])
        for p in pats:
            paths += glob.glob(p)
    out, seen = [], set()
    for p in paths:
        rp = os.path.realpath(p)
        if rp in seen or not os.path.exists(p):
            continue
        seen.add(rp)
        v = subprocess.run([p, "-hide_banner", "-version"], capture_output=True, text=True, errors="replace").stdout
        f = subprocess.run([p, "-hide_banner", "-filters"], capture_output=True, text=True, errors="replace").stdout
        from doctor import REQUIRED_FILTERS
        missing = [x for x in REQUIRED_FILTERS if f" {x} " not in f]
        out.append({"path": p, "version": (v.splitlines() or ["?"])[0][:70], "missing_filters": missing,
                    "on_path": os.path.realpath(shutil.which("ffmpeg") or "") == rp})
    return out


def _system_fonts() -> list[str]:
    dirs = ([Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts", HOME / "AppData/Local/Microsoft/Windows/Fonts"] if WIN
            else [Path("/Library/Fonts"), HOME / "Library/Fonts", Path("/usr/share/fonts"), HOME / ".local/share/fonts",
                  HOME / ".fonts"])
    names = []
    for d in dirs:
        if d.exists():
            names += [p.name.lower() for p in d.rglob("*") if p.suffix.lower() in (".ttf", ".otf")]
    return [fam for fam in PACK_FAMILIES if any(n.startswith(fam.lower()) for n in names)]


def _model_caches() -> list[dict]:
    out = []
    hf = Path(os.environ.get("HF_HUB_CACHE") or Path(os.environ.get("HF_HOME", HOME / ".cache/huggingface")) / "hub")
    for d in glob.glob(str(hf / "models--Systran--faster-whisper-*")) + glob.glob(str(hf / "models--*whisper*")):
        out.append({"kind": "whisper", "path": d, "mb": dir_size_mb(Path(d))})
    th = Path(os.environ.get("TORCH_HOME", HOME / ".cache/torch")) / "hub" / "checkpoints"
    if th.exists():
        for f in th.glob("*.th"):
            out.append({"kind": "demucs", "path": str(f), "mb": round(f.stat().st_size / 2**20)})
    seen, uniq = set(), []
    for m in out:
        if m["path"] not in seen:
            seen.add(m["path"])
            uniq.append(m)
    return uniq


# ------------------------------------------------------------------ scan + recommendations
def scan(scope: str = "project") -> dict:
    cur = Path(sys.executable)
    envs = []
    for label, exe in _python_candidates(scope):
        pr = probe_python(exe)
        if not pr:
            continue
        missing = [m for m in REQUIRED if m not in pr["mods"]]
        venv_dir = exe.parent.parent
        envs.append({"label": label, "python": str(exe), "version": pr["version"], "missing": missing,
                     "complete": not missing, "torch": pr["mods"].get("torch"), "demucs": pr["mods"].get("demucs"),
                     "cuda": pr.get("cuda", 0), "owned": owned_by_mv(exe),
                     "current": exe.resolve() == cur.resolve(),
                     "size_mb": dir_size_mb(venv_dir) if (venv_dir / "pyvenv.cfg").exists() else None})
    copies = [{"path": str(p), "venv_mb": dir_size_mb(p / ".venv") if (p / ".venv").exists() else 0}
              for p in _skill_copies(scope)]
    data = {"scope": scope, "runtime": {"python": sys.executable, "source": runtime_source()},
            "envs": envs, "skill_copies": copies, "ffmpeg": _ffmpegs(scope),
            "fonts_installed": _system_fonts() if scope == "machine" else [],
            "model_caches": _model_caches() if scope == "machine" else []}
    data["suggestions"] = suggest(data)
    return data


def suggest(d: dict) -> list[dict]:
    s = []
    def add(id_, why, cmd=None, consent=True):
        s.append({"id": id_, "why": why, "cmd": cmd, "needs_consent": consent})

    cur = next((e for e in d["envs"] if e["current"]), None)
    shared = next((e for e in d["envs"] if e["label"] == "mv-maker shared runtime"), None)
    venvs = [c for c in d["skill_copies"] if c["venv_mb"]]
    if shared and shared["complete"] and (not cur or not cur["owned"] or "shared" not in d["runtime"]["source"]):
        add("use-shared", f"A complete shared mv-maker runtime already exists ({shared['python']}) - reuse it, no install.",
            "mv doctor --use-shared")
    elif len(venvs) >= 2:
        tot = sum(c["venv_mb"] for c in venvs)
        add("use-shared", f"{len(venvs)} mv-maker copies each have their own .venv ({tot:.0f} MB total). One shared "
            f"runtime in {SHARED_VENV} serves all copies (plugin, project, Codex).", "mv doctor --use-shared")
    for e in d["envs"]:
        if e["complete"] and not e["current"] and not e["owned"]:
            add("reuse-python", f"'{e['label']}' already has every package mv-maker needs ({e['python']}). Pointing "
                "mv-maker at it avoids a new install - but it is not mv-maker's environment: upgrades made by its "
                "owner could break mv-maker, and mv-maker will never install into it.",
                f'mv doctor --use-python "{e["python"]}"')
    if cur and not cur["complete"]:
        donor = next((e for e in d["envs"] if e["complete"] and not e["current"]), None)
        add("missing-deps", f"Current runtime lacks {', '.join(cur['missing'])}."
            + (f" '{donor['label']}' is complete - reuse it instead of installing." if donor else ""),
            (f'mv doctor --use-python "{donor["python"]}"' if donor else "mv doctor --install py-deps"))
    if cur and cur["torch"] and not cur["demucs"] and cur["owned"]:  # --install targets the running runtime
        add("demucs-small", f"PyTorch {cur['torch']} is already in the current runtime: demucs would add only "
            "~100 MB instead of ~2 GB.", "mv doctor --install demucs")
    path_ff = next((f for f in d["ffmpeg"] if f["on_path"]), None)
    better = next((f for f in d["ffmpeg"] if not f["missing_filters"] and not f["on_path"]), None)
    if (not path_ff or path_ff["missing_filters"]) and better:
        add("use-ffmpeg", f"FFmpeg at {better['path']} has every filter mv-maker needs"
            + (f" (the one on PATH lacks {path_ff['missing_filters']})" if path_ff else " (none on PATH)")
            + " - reuse it instead of installing another.", f'mv doctor --use-ffmpeg "{better["path"]}"')
    for m in d.get("model_caches", []):
        add("models-cached", f"{m['kind']} model already downloaded ({m['mb']:.0f} MB at {m['path']}) - reused "
            "automatically, nothing to download.", None, consent=False)
    if d.get("fonts_installed"):
        add("fonts-installed", f"Already installed system-wide: {', '.join(d['fonts_installed'])} - usable by name.",
            None, consent=False)
    return s


def print_scan(d: dict) -> None:
    print(f"=== runtime & reuse check (scope: {d['scope']}{' - read-only' if d['scope'] == 'machine' else ''}) ===")
    print(f"Running on  {d['runtime']['python']}  [{d['runtime']['source']}]")
    for e in d["envs"]:
        tag = "complete" if e["complete"] else f"missing {', '.join(e['missing'])}"
        extra = (f" · torch {e['torch']}" if e["torch"] else "") + (f" · {e['size_mb']:.0f} MB" if e["size_mb"] else "")
        mark = "*" if e["current"] else " "
        print(f" {mark} {e['label']:<40} py {e['version']:<8} {tag}{extra}")
    for c in d["skill_copies"]:
        print(f"   copy  {c['path']}  (.venv {c['venv_mb']:.0f} MB)")
    for f in d["ffmpeg"]:
        print(f"   ffmpeg {'[PATH] ' if f['on_path'] else ''}{f['path']}  {f['version'][15:45]}"
              + (f"  missing {f['missing_filters']}" if f["missing_filters"] else "  full"))
    if d["suggestions"]:
        print("\nReuse / dedup suggestions (nothing is changed until the user agrees):")
        for x in d["suggestions"]:
            print(f"  [{x['id']}] {x['why']}" + (f"\n      -> {x['cmd']}" if x["cmd"] else ""))
    else:
        print("\nNo duplicates found.")


# ------------------------------------------------------------------ actions (run only after consent)
def use_python(path: str) -> None:
    exe = Path(path)
    pr = probe_python(exe)
    if not pr:
        raise RuntimeError(f"{exe} is not a working Python")
    missing = [m for m in REQUIRED if m not in pr["mods"]]
    if missing:
        raise RuntimeError(f"{exe} lacks {missing} - mv-maker does not install into environments it does not own; "
                           "use --use-shared instead")
    RUNTIME_TXT.write_text(str(exe), encoding="utf-8")
    print(f"[mv] launchers now use {exe} (delete {RUNTIME_TXT.name} to undo)")


def use_shared(python_for_new: str | None = None) -> None:
    py = venv_python(SHARED_VENV)
    if not py.exists():
        base = python_for_new or sys.executable
        print(f"[mv] creating shared runtime {SHARED_VENV} ...")
        SHARED_VENV.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([base, "-m", "venv", str(SHARED_VENV)], check=True)
    pr = probe_python(py) or {"mods": {}}
    missing = [m for m in REQUIRED if m not in pr["mods"]]
    if missing:  # the shared runtime is mv-maker's own, so completing it is allowed
        print(f"[mv] installing into the shared runtime (missing {', '.join(missing)}) ...")
        subprocess.run([str(py), "-m", "ensurepip", "--upgrade"], capture_output=True)
        subprocess.run([str(py), "-m", "pip", "install", "-q", "--upgrade", "pip"], check=True)
        subprocess.run([str(py), "-m", "pip", "install", "-q", "-r", str(SKILL_DIR / "requirements.txt")], check=True)
    RUNTIME_TXT.write_text(str(py), encoding="utf-8")
    print(f"[mv] this copy now uses the shared runtime {SHARED_VENV}")
    local = SKILL_DIR / ".venv"
    if local.exists():
        print(f"[mv] the local {local} ({dir_size_mb(local):.0f} MB) is no longer needed: mv doctor --remove-local-venv")


def remove_local_venv() -> None:
    local = SKILL_DIR / ".venv"
    if not local.exists():
        print("[mv] no local .venv")
        return
    if str(Path(sys.executable).resolve()).startswith(str(local.resolve())):
        raise RuntimeError("the local .venv is the running interpreter - switch first (--use-shared / --use-python)")
    if not RUNTIME_TXT.exists():
        raise RuntimeError("no other runtime configured - the launcher would reinstall it; run --use-shared first")
    shutil.rmtree(local)
    print(f"[mv] removed {local}")


def use_ffmpeg(path: str) -> None:
    p = Path(path)
    if not p.exists():
        raise RuntimeError(f"{p} not found")
    cfg = json.loads(RUNTIME_JSON.read_text(encoding="utf-8")) if RUNTIME_JSON.exists() else {}
    cfg["ffmpeg_dir"] = str(p.parent)
    RUNTIME_JSON.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    print(f"[mv] mv-maker will use FFmpeg from {p.parent} (system PATH unchanged)")


def apply_runtime_env() -> None:
    """Called by mv.py at start: prepend a chosen FFmpeg folder to PATH for this process only."""
    if RUNTIME_JSON.exists():
        try:
            d = json.loads(RUNTIME_JSON.read_text(encoding="utf-8")).get("ffmpeg_dir")
            if d and Path(d).exists():
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
        except ValueError:
            pass
