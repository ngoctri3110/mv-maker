"""Machine check for mv-maker: hardware, FFmpeg features, working encoders, Python deps, quick render benchmark,
a machine profile (machine.json) and install recommendations. Nothing is installed without --install."""
from __future__ import annotations

import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
PROFILE = SKILL_DIR / "machine.json"
REQUIRED_FILTERS = ["xfade", "zoompan", "gblur", "subtitles", "drawtext", "maskedmerge", "showwaves", "blend",
                    "rgbashift", "colorbalance", "curves", "vignette", "geq", "tpad"]
HW_ENCODERS = ["h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv", "h264_amf", "hevc_amf",
               "h264_videotoolbox", "hevc_videotoolbox"]
PY_MODULES = {"yaml": "PyYAML", "yt_dlp": "yt-dlp", "librosa": "librosa", "soundfile": "soundfile",
              "faster_whisper": "faster-whisper", "scenedetect": "scenedetect", "cv2": "opencv-python-headless", "fontTools": "fonttools"}
OS = platform.system()  # Windows | Darwin | Linux


def _run(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(cmd, 127, "", str(e))


# ------------------------------------------------------------------ hardware
def cpu_name() -> str:
    try:
        if OS == "Windows":
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
        if OS == "Darwin":
            return _run(["sysctl", "-n", "machdep.cpu.brand_string"]).stdout.strip() or platform.machine()
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor() or platform.machine()


def ram_gb() -> float:
    try:
        if OS == "Windows":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + \
                           [(n, ctypes.c_ulonglong) for n in ("tp", "ap", "tpf", "apf", "tv", "av", "ae")]
            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.tp / 2**30, 1)
        if OS == "Darwin":
            return round(int(_run(["sysctl", "-n", "hw.memsize"]).stdout.strip()) / 2**30, 1)
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal"):
                return round(int(line.split()[1]) / 2**20, 1)
    except Exception:
        pass
    return 0.0


def gpus() -> list[str]:
    names: list[str] = []
    r = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
    if r.returncode == 0:
        names += [f"NVIDIA {l.strip()}" if not l.startswith("NVIDIA") else l.strip() for l in r.stdout.splitlines() if l.strip()]
    if OS == "Windows":
        r = _run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController).Name"])
        names += [l.strip() for l in r.stdout.splitlines() if l.strip() and not any(l.strip() in n for n in names)]
    elif OS == "Darwin":
        r = _run(["system_profiler", "SPDisplaysDataType"])
        names += [l.split(":", 1)[1].strip() for l in r.stdout.splitlines() if "Chipset Model" in l]
    else:
        r = _run(["sh", "-c", "lspci 2>/dev/null | grep -Ei 'vga|3d|display'"])
        names += [l.split(":", 2)[-1].strip() for l in r.stdout.splitlines() if l.strip()]
    return names


# ------------------------------------------------------------------ ffmpeg
def ffmpeg_info() -> dict:
    path = shutil.which("ffmpeg")
    if not path:
        return {"found": False}
    ver = _run(["ffmpeg", "-hide_banner", "-version"]).stdout.splitlines()[:1]
    filters = set(re.findall(r"^\s*[TSC.|]{2,3}\s+(\w+)", _run(["ffmpeg", "-hide_banner", "-filters"]).stdout, re.M))
    enc_list = _run(["ffmpeg", "-hide_banner", "-encoders"]).stdout
    return {"found": True, "path": path, "version": ver[0] if ver else "?",
            "missing_filters": [f for f in REQUIRED_FILTERS if f not in filters],
            "libx264": " libx264 " in enc_list,
            "hw_listed": [e for e in HW_ENCODERS if f" {e} " in enc_list]}


def encoder_works(enc: str) -> bool:
    vf = ["-vf", "format=nv12"] if "qsv" in enc else []
    r = _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=gray:s=640x360:r=30:d=0.3",
              *vf, "-c:v", enc, "-f", "null", "-"], timeout=40)
    return r.returncode == 0


def bench(enc: str, seconds: float = 4.0) -> float | None:
    """Real-time factor of a typical MV graph (split + blur + blend + grain) at 1080x1920 (>1 = faster than real time)."""
    g = ("[0]split[a][b];[a]scale=1080:960[t];[b]scale=1080:960,gblur=sigma=10[u];[t][u]vstack[s];"
         "[1]gblur=sigma=6[o];[s][o]blend=all_mode=screen:all_opacity=0.35,noise=alls=10:allf=t," +
         ("format=nv12" if "qsv" in enc else "format=yuv420p"))
    extra = ["-preset", "veryfast"] if enc == "libx264" else []
    t0 = time.time()
    r = _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=s=1920x1080:r=30:d={seconds}",
              "-f", "lavfi", "-i", f"testsrc=s=1080x1920:r=30:d={seconds}", "-filter_complex", g,
              "-c:v", enc, *extra, "-f", "null", "-"], timeout=300)
    dt = time.time() - t0
    return round(seconds / dt, 2) if r.returncode == 0 and dt > 0 else None


# ------------------------------------------------------------------ python side
def py_info() -> dict:
    mods = {m: importlib.util.find_spec(m) is not None for m in PY_MODULES}
    info = {"version": platform.python_version(), "executable": sys.executable,
            "in_skill_venv": str(SKILL_DIR / ".venv") in sys.executable, "modules": mods,
            "demucs": importlib.util.find_spec("demucs") is not None, "cuda_devices": 0, "yt_dlp_age_days": None}
    if mods.get("faster_whisper"):
        try:
            import ctranslate2
            info["cuda_devices"] = ctranslate2.get_cuda_device_count()
        except Exception:
            pass
    if mods.get("yt_dlp"):
        try:
            from yt_dlp.version import __version__ as v
            y, m, d = (int(x) for x in v.split(".")[:3])
            info["yt_dlp_version"] = v
            info["yt_dlp_age_days"] = (date.today() - date(y, m, d)).days
        except Exception:
            pass
    return info


def cuda_libs_installed() -> bool:
    return importlib.util.find_spec("nvidia") is not None and any(
        (Path(p) / "nvidia" / "cudnn").exists() for p in sys.path if p)


# ------------------------------------------------------------------ profile + recommendations
def build(run_bench: bool = True) -> dict:
    import lyrics as LY  # same folder
    hw = {"os": f"{OS} {platform.release()}", "arch": platform.machine(), "cpu": cpu_name(),
          "threads": os.cpu_count() or 1, "ram_gb": ram_gb(), "gpus": gpus(),
          "disk_free_gb": round(shutil.disk_usage(Path.cwd()).free / 2**30, 1)}
    ff = ffmpeg_info()
    py = py_info()
    working = [e for e in ff.get("hw_listed", []) if encoder_works(e)] if ff.get("found") else []
    has_nvidia = any("nvidia" in g.lower() for g in hw["gpus"])
    has_intel = any("intel" in g.lower() for g in hw["gpus"])
    has_amd = any(("amd" in g.lower() or "radeon" in g.lower()) for g in hw["gpus"])
    best_hw = next((e for e in ["h264_nvenc", "h264_videotoolbox", "h264_qsv", "h264_amf"] if e in working), None)

    rtf = {}
    if run_bench and ff.get("found") and ff.get("libx264"):
        rtf["libx264"] = bench("libx264")
        if best_hw:
            rtf[best_hw] = bench(best_hw)
    fastest = max((v for v in rtf.values() if v), default=None)
    # real projects measured ~2.5x slower than this synthetic graph (source decode, zoompan, 2 encode passes)
    tier = None if fastest is None else ("strong" if fastest >= 3 else "standard" if fastest >= 1.0 else "light")
    whisper_dev = "cuda" if py["cuda_devices"] > 0 else "cpu"
    whisper_model = "large-v3" if whisper_dev == "cuda" else ("medium" if hw["ram_gb"] >= 12 else "small")
    profile = {
        "encoder": best_hw or "libx264",
        "encoder_best_quality": "libx264",
        "jobs": max(1, min(hw["threads"] // 4, int(hw["ram_gb"] // 4) or 1)),
        "whisper_model": whisper_model, "whisper_device": whisper_dev, "tier": tier,
        "est_final_minutes_per_4min_song": round(240 / fastest * 2.5 / 60, 1) if fastest else None,
    }

    recs = []
    def rec(id_, level, why, auto=None, manual=None):
        recs.append({"id": id_, "level": level, "why": why, "auto": auto, "manual": manual})

    ffcmd = {"Windows": "winget install --id Gyan.FFmpeg -e", "Darwin": "brew install ffmpeg",
             "Linux": "sudo apt install ffmpeg   (or a static build from https://johnvansickle.com/ffmpeg/)"}[OS if OS in ("Windows", "Darwin") else "Linux"]
    if not ff.get("found"):
        rec("ffmpeg", "required", "FFmpeg is not on PATH - nothing can render.", manual=ffcmd)
    elif ff["missing_filters"] or not ff["libx264"]:
        rec("ffmpeg", "required", f"FFmpeg build lacks {', '.join(ff['missing_filters'] + ([] if ff['libx264'] else ['libx264']))}"
            " (lyrics/text or effects will fail). Install a full build.", manual=ffcmd)
    missing_py = [PY_MODULES[m] for m, ok in py["modules"].items() if not ok]
    if missing_py:
        rec("py-deps", "required", f"Missing Python packages: {', '.join(missing_py)}.", auto="pip install -r requirements.txt")
    if not LY.has_font("Be Vietnam Pro"):
        rec("fonts", "recommended", "Vietnamese font pack (Be Vietnam Pro, Anton, ...) for lyrics - ~2 MB.", auto="mv fonts")
    if (py.get("yt_dlp_age_days") or 0) > 60:
        rec("yt-dlp-update", "recommended", f"yt-dlp is {py['yt_dlp_age_days']} days old; YouTube/TikTok change often and old versions fail.",
            auto="pip install -U yt-dlp")
    if has_nvidia and "h264_nvenc" not in working:
        rec("nvidia-driver", "recommended", "NVIDIA GPU found but NVENC encoding failed - update the NVIDIA driver to render 3-10x faster.",
            manual="Update from https://www.nvidia.com/drivers (or NVIDIA App), then re-run: mv doctor")
    if has_intel and OS != "Darwin" and "h264_qsv" not in working and not best_hw:
        rec("intel-driver", "optional", "Intel GPU found but QuickSync encoding failed - an updated graphics driver enables faster encoding.",
            manual="Intel Driver & Support Assistant: https://www.intel.com/content/www/us/en/support/detect.html")
    if has_amd and "h264_amf" not in working and not best_hw and OS == "Windows":
        rec("amd-driver", "optional", "AMD GPU found but AMF encoding failed - update AMD Adrenalin driver for faster encoding.",
            manual="https://www.amd.com/en/support")
    if has_nvidia and py["cuda_devices"] > 0 and not cuda_libs_installed() and OS != "Darwin":
        rec("whisper-cuda", "recommended", "Run Whisper on the NVIDIA GPU (large-v3 lyric timing in ~1 min instead of ~10+ min on CPU). ~1.5 GB.",
            auto='pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"')
    if not py["demucs"]:
        heavy = "fast on this GPU" if has_nvidia else "slow on CPU (several minutes per song)"
        rec("demucs", "optional", f"Vocal separation for much better lyric timing on dense mixes - ~2 GB (PyTorch), {heavy}.",
            auto="pip install demucs")
    missing_keys = [k for k in ("PEXELS_API_KEY", "PIXABAY_API_KEY") if not os.environ.get(k)]
    if missing_keys:
        rec("stock-keys", "optional", f"Free API keys widen licence-clear footage search ({', '.join(missing_keys)} not set); "
            "Wikimedia Commons and Openverse work without keys.",
            manual="Get keys at https://www.pexels.com/api/ and https://pixabay.com/api/docs/, then set them as user "
                   "environment variables (Windows: setx PEXELS_API_KEY <key>; macOS/Linux: export in ~/.zshrc or ~/.bashrc)")
    if hw["disk_free_gb"] < 20:
        rec("disk", "recommended", f"Only {hw['disk_free_gb']} GB free here; downloads + renders of one MV can take 5-15 GB.",
            manual="Free space or work in a project folder on a bigger drive.")
    if hw["ram_gb"] and hw["ram_gb"] < 8:
        rec("low-ram", "info", "Less than 8 GB RAM: keep jobs=1, render proxies here, final on a stronger machine.")
    if tier == "light":
        rec("render-elsewhere", "info", "This machine is slow for 1080p finals: storyboard, sourcing and proxy here; final render on a stronger PC.")
    if has_nvidia or (OS == "Darwin" and platform.machine() == "arm64"):
        rec("nle", "optional", "For manual polish (speed ramps, masks, colour grading) this machine can run DaVinci Resolve (free).",
            manual="https://www.blackmagicdesign.com/products/davinciresolve")

    data = {"checked": date.today().isoformat(), "hardware": hw, "ffmpeg": ff, "encoders_working": working,
            "benchmark_rtf": rtf, "python": py, "profile": profile, "recommendations": recs}
    PROFILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def save_section(key: str, value) -> None:
    try:
        data = json.loads(PROFILE.read_text(encoding="utf-8")) if PROFILE.exists() else {}
    except ValueError:
        data = {}
    data[key] = value
    PROFILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def load_profile() -> dict:
    try:
        return json.loads(PROFILE.read_text(encoding="utf-8")).get("profile", {})
    except Exception:
        return {}


def print_report(d: dict) -> None:
    hw, ff, pr = d["hardware"], d["ffmpeg"], d["profile"]
    print("=== mv doctor ===")
    print(f"OS        {hw['os']} ({hw['arch']})")
    print(f"CPU       {hw['cpu']} · {hw['threads']} threads · RAM {hw['ram_gb']} GB · disk free {hw['disk_free_gb']} GB")
    print(f"GPU       {', '.join(hw['gpus']) or 'none detected'}")
    print(f"FFmpeg    {ff.get('version', 'NOT FOUND')}" + (f" · missing filters: {ff['missing_filters']}" if ff.get("missing_filters") else ""))
    print(f"Encoders  working HW: {', '.join(d['encoders_working']) or 'none'} · libx264: {'yes' if ff.get('libx264') else 'NO'}")
    if d["benchmark_rtf"]:
        print("Benchmark " + " · ".join(f"{k} {v}x real-time" for k, v in d["benchmark_rtf"].items() if v))
    py = d["python"]
    print(f"Python    {py['version']} · Whisper device: {pr['whisper_device']} ({py['cuda_devices']} CUDA) · demucs: {'yes' if py['demucs'] else 'no'}")
    print(f"Profile   tier={pr['tier']} · render encoder={pr['encoder']} · jobs={pr['jobs']} · whisper={pr['whisper_model']}"
          + (f" · ~{pr['est_final_minutes_per_4min_song']} min per 4-min 1080p final" if pr.get("est_final_minutes_per_4min_song") else ""))
    if d["recommendations"]:
        print("\nRecommendations (nothing is installed until you approve):")
        for r in d["recommendations"]:
            how = f"  -> mv doctor --install {r['id']}" if r["auto"] else (f"  -> {r['manual']}" if r["manual"] else "")
            print(f"  [{r['level']}] {r['id']}: {r['why']}{how}")
    else:
        print("\nNo recommendations - this machine is ready.")
    print(f"\nSaved profile: {PROFILE}")


def install(ids: list[str]) -> None:
    import lyrics as LY
    import runtime as RT
    if any(i != "fonts" for i in ids) and not RT.owned_by_mv(Path(sys.executable)):
        print(f"[mv] refusing to pip-install into {sys.executable}: it is not mv-maker's environment "
              "(reused via runtime.txt / MV_PYTHON). Use `mv doctor --use-shared` for an mv-maker-owned runtime.")
        ids = [i for i in ids if i == "fonts"]
    req = SKILL_DIR / "requirements.txt"
    pip = [sys.executable, "-m", "pip", "install"]
    cmds = {"py-deps": pip + ["-r", str(req)], "yt-dlp-update": pip + ["-U", "yt-dlp"],
            "whisper-cuda": pip + ["nvidia-cublas-cu12", "nvidia-cudnn-cu12==9.*"], "demucs": pip + ["demucs"]}
    for i in ids:
        if i == "fonts":
            LY.download_fonts()
        elif i in cmds:
            print(f"[mv] installing {i}: {' '.join(cmds[i][3:])}")
            if subprocess.run(cmds[i]).returncode != 0:
                print(f"[mv] {i} failed")
        else:
            print(f"[mv] '{i}' is a system-level change - run its manual step from `mv doctor` (with the user's OK)")
