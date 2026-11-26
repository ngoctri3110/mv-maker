#!/usr/bin/env python3
"""mv.py - storyboard-driven music-video pipeline built on FFmpeg.

Run through the launcher next to SKILL.md: `mv` (macOS/Linux/Git-Bash) or `mv.cmd` (Windows).

Subcommands:
  demo     [story|blur|lyric-poster|lyric-styles|all]   build + render a demo with synthetic media
  new      <project>                 create a project skeleton
  analyze  <project> [--lyrics]      tempo / beats / sections (+ whisper lyric timing)
  align    <project>                 lyrics.txt + Whisper timing -> lyrics.yaml (per-word times)
  fonts                              download the Vietnamese-ready font pack (Google Fonts, OFL)
  review   <project>                 storyboard.yaml -> storyboard.md (for human approval)
  search   "query" [-n 10]           list YouTube candidates (id | title | duration | url)
  fetch    <project>                 download every source that has a url (yt-dlp)
  sheet    <project> <source_id>     contact sheet with timecodes, to pick in-points
  scenes   <project> <source_id>     scene-cut list (PySceneDetect)
  render   <project> --mode proxy|final [--encoder libx264|h264_nvenc|hevc_nvenc|h264_qsv]

Missing sources render as labelled placeholder cards, so a storyboard can be
previewed as an animatic before any footage is downloaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("Missing PyYAML - run setup.ps1 (or pip install -r requirements.txt)")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lyrics as LY  # noqa: E402

# Shot cache key includes the renderer source, so code changes re-render cached shots.
ENGINE_HASH = hashlib.sha1(b"".join(p.read_bytes() for p in sorted(Path(__file__).resolve().parent.glob("*.py")))).hexdigest()[:10]

FORMATS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}
MODES = {
    "proxy": dict(scale=0.5, fps=24, crf=26, preset="ultrafast"),
    "final": dict(scale=1.0, fps=None, crf=14, preset="veryfast"),
}
XFADE = {
    "fade", "fadeblack", "fadewhite", "fadegrays", "dissolve", "wipeleft", "wiperight", "wipeup",
    "wipedown", "slideleft", "slideright", "slideup", "slidedown", "circleopen", "circleclose",
    "circlecrop", "rectcrop", "radial", "pixelize", "hblur", "zoomin", "smoothleft", "smoothright",
    "smoothup", "smoothdown", "distance", "squeezeh", "squeezev", "diagtl", "diagbr", "hlslice",
    "vuslice", "horzopen", "vertopen",
}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXT = (".mp4", ".mkv", ".webm", ".mov", ".m4v")
BLEND_MODES = {"normal", "screen", "overlay", "softlight", "lighten", "darken", "multiply",
               "addition", "hardlight", "difference"}
DEFAULT_FEATHER = 0.2  # split_v/split_h get a soft seam unless the shot sets feather: 0
LAYOUTS = {"full", "split_v", "split_h", "split_3v", "pip", "fit_blur", "poster"}
BEAT_FX = {"flash", "zoom", "shake"}
CAPTION_ANIMS = {"fade", "pop", "rise", "none"}
PLACEHOLDER_COLORS = ["0x2b3a55", "0x553a2b", "0x2b553a", "0x4a2b55", "0x55502b", "0x2b5055"]


def die(msg: str):
    sys.exit(f"[mv] ERROR: {msg}")


def tsec(v) -> float:
    """Accept 12.5, '12.5', '1:02.5', '0:01:02.5'."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    sec = 0.0
    for part in str(v).strip().split(":"):
        sec = sec * 60 + float(part)
    return sec


def even(n: float) -> int:
    return max(2, int(round(n)) // 2 * 2)


def fmt_t(sec: float) -> str:
    m, s = divmod(sec, 60)
    return f"{int(m)}:{s:05.2f}"


def venv_tool(name: str) -> list[str]:
    """Run a python-module tool from the same interpreter (venv) as this script."""
    return [sys.executable, "-m", name]


def probe_wh(f: Path) -> tuple[int, int]:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(f)], capture_output=True, text=True)
    try:
        w, h = (int(x) for x in r.stdout.strip().split(",")[:2])
        return w, h
    except ValueError:
        return 1, 1


def run(cmd: list[str], cwd: Path | None = None, quiet: bool = True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=quiet, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        tail = (r.stderr or "")[-2500:] if quiet else ""
        die(f"command failed ({r.returncode}): {' '.join(map(str, cmd[:6]))} ...\n{tail}")
    return r


# --------------------------------------------------------------------------- project
class Project:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        sb_path = self.root / "storyboard.yaml"
        if not sb_path.exists():
            die(f"{sb_path} not found (run: mv.py new {root})")
        self.sb = yaml.safe_load(sb_path.read_text(encoding="utf-8")) or {}
        self.sources: dict = self.sb.get("sources") or {}
        self.shots: list = self.sb.get("shots") or []
        if not self.shots:
            die("storyboard has no shots")
        self.build = self.root / "build"
        self.out = self.root / "out"
        an = self.root / "analysis.json"
        self.beats: list[float] = json.loads(an.read_text(encoding="utf-8")).get("beats", []) if an.exists() else []

    def lyric_lines(self) -> list[dict]:
        lf = self.sb.get("lyrics_file")
        if not lf:
            return []
        f = self.root / lf
        if not f.exists():
            die(f"lyrics_file {f} not found (run: mv.py align {self.root})")
        return (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("lines", [])

    def beats_in(self, start: float, end: float, every: int = 1) -> list[float]:
        """Beat times inside [start, end) relative to start; every=4 ~ downbeats only."""
        if not self.beats:
            die("beat_fx needs beat times - run: mv.py analyze <project> first")
        return [b - start for i, b in enumerate(self.beats) if i % every == 0 and start <= b < end]

    def source_file(self, sid: str) -> Path | None:
        info = self.sources.get(sid) or {}
        if info.get("path"):
            p = (self.root / info["path"]).resolve()
            return p if p.exists() else None
        for ext in VIDEO_EXT + tuple(IMAGE_EXT):
            p = self.root / "sources" / f"{sid}{ext}"
            if p.exists():
                return p
        return None

    def source_offset(self, sid: str) -> float:
        """`in` points are written against the ORIGINAL video; a downloaded section starts at 0."""
        info = self.sources.get(sid) or {}
        sec = info.get("section")
        if sec and not info.get("path"):
            return tsec(str(sec).split("-")[0])
        return 0.0

    def validate(self):
        prev_end = None
        ids = set()
        for i, sh in enumerate(self.shots):
            sid = sh.setdefault("id", f"S{i + 1:02d}")
            if sid in ids:
                die(f"duplicate shot id {sid}")
            ids.add(sid)
            s, e = tsec(sh.get("start")), tsec(sh.get("end"))
            if e <= s:
                die(f"{sid}: end ({e}) must be after start ({s})")
            if prev_end is not None and abs(s - prev_end) > 0.002:
                die(f"{sid}: starts at {s} but previous shot ends at {prev_end} (shots must be contiguous)")
            prev_end = e
            for ly in sh.get("layers") or []:
                src = ly.get("src")
                if src and src not in self.sources:
                    die(f"{sid}: layer src '{src}' is not declared under sources:")
                mode = ly.get("blend")
                if mode and mode not in BLEND_MODES:
                    die(f"{sid}: blend '{mode}' not in {sorted(BLEND_MODES)}")
            if sh.get("layout", "full") not in LAYOUTS:
                die(f"{sid}: layout must be one of {sorted(LAYOUTS)}")
            bad = set(sh.get("beat_fx") or []) - BEAT_FX
            if bad:
                die(f"{sid}: beat_fx {sorted(bad)} not in {sorted(BEAT_FX)}")
            if sh.get("lyric_style", "subtitle") not in LY.LYRIC_STYLES:
                die(f"{sid}: lyric_style must be one of {sorted(LY.LYRIC_STYLES)}")
            if sh.get("caption_anim", "fade") not in CAPTION_ANIMS:
                die(f"{sid}: caption_anim must be one of {sorted(CAPTION_ANIMS)}")
            tr = parse_transition(sh.get("transition", "cut"))
            if tr[0] == "xfade" and tr[2] >= (e - s):
                die(f"{sid}: transition longer than the shot")


def parse_transition(v) -> tuple[str, str, float]:
    """-> (kind, name, duration). kind: cut | flash | fadeblack | xfade."""
    v = str(v or "cut").strip()
    name, _, d = v.partition(":")
    dur = float(d) if d else 0.5
    if name in ("cut", "", "none"):
        return ("cut", "cut", 0.0)
    if name == "flash":
        return ("flash", "flash", float(d) if d else 0.25)
    if name == "fadeblack" and not d:
        return ("fadeblack", "fadeblack", 0.6)
    if name == "fadeblack":
        return ("fadeblack", "fadeblack", dur)
    if name == "dissolve":
        return ("xfade", "fade", dur)
    if name in XFADE:
        return ("xfade", name, dur)
    die(f"unknown transition '{v}'")


# --------------------------------------------------------------------------- effects
def fx_filters(fx_list, label: str) -> list[str]:
    out: list[str] = []
    for n, raw in enumerate(fx_list or []):
        name, _, arg = str(raw).partition(":")
        a = float(arg) if arg else None
        if name == "bw":
            out.append("hue=s=0")
        elif name == "vintage":
            out += ["curves=preset=vintage", "colorbalance=rs=0.06:bs=-0.08", "eq=saturation=0.85"]
        elif name == "oldfilm":
            out += ["hue=s=0.25", "curves=preset=vintage", "noise=alls=22:allf=t+u", "vignette=PI/4"]
        elif name == "vhs":
            out += ["eq=saturation=1.35:contrast=1.08", "rgbashift=rh=-4:bh=4", "noise=alls=16:allf=t",
                    "gblur=sigma=0.6"]
        elif name == "grain":
            out.append(f"noise=alls={int(a or 12)}:allf=t+u")
        elif name == "vignette":
            out.append("vignette=PI/4.5")
        elif name == "warm":
            out.append(f"colorbalance=rs={a or 0.12}:gs=0.02:bs=-{a or 0.12}")
        elif name == "cool":
            out.append(f"colorbalance=rs=-{a or 0.08}:bs={a or 0.12}")
        elif name == "blur":
            out.append(f"gblur=sigma={a or 8}")
        elif name == "bright":
            out.append(f"eq=brightness={a if a is not None else 0.08}")
        elif name == "contrast":
            out.append(f"eq=contrast={a or 1.15}")
        elif name == "sat":
            out.append(f"eq=saturation={a if a is not None else 1.3}")
        elif name == "rgbsplit":
            px = int(a or 8)
            out.append(f"rgbashift=rh=-{px}:bh={px}")
        elif name == "mirror":
            out.append("hflip")
        elif name == "glow":
            p = f"{label}g{n}"
            out.append(f"split[{p}a][{p}b];[{p}b]gblur=sigma=14[{p}c];"
                       f"[{p}a][{p}c]blend=all_mode=screen:all_opacity={a or 0.45}")
        else:
            die(f"unknown fx '{raw}' (see reference/techniques.md)")
    return out


def cover(w: int, h: int, focus) -> str:
    fx, fy = (focus or [0.5, 0.5])[:2]
    return (f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={w}:{h}:(in_w-{w})*{fx}:(in_h-{h})*{fy}")


def feather_half(shot: dict, size: int) -> int:
    """Half-width (px) of the soft seam between split halves; 0 = hard cut."""
    f = float(shot.get("feather", DEFAULT_FEATHER) or 0)
    return even(size * f / 2) if f > 0 else 0


def slots_for(layout: str, W: int, H: int, shot: dict) -> list[tuple[int, int]]:
    if layout in ("full", "fit_blur", "poster"):
        return [(W, H)]
    if layout == "split_v":
        h1 = even(H * float(shot.get("ratio", 0.5)))
        hf = feather_half(shot, H)
        return [(W, h1 + hf), (W, H - h1 + hf)]
    if layout == "split_h":
        w1 = even(W * float(shot.get("ratio", 0.5)))
        hf = feather_half(shot, W)
        return [(w1 + hf, H), (W - w1 + hf, H)]
    if layout == "split_3v":
        h1 = even(H / 3)
        return [(W, h1), (W, h1), (W, H - 2 * h1)]
    if layout == "pip":
        ins = shot.get("inset") or {}
        iw = even(W * float(ins.get("w", 0.5)))
        aw, ah = (float(x) for x in str(ins.get("aspect", "16:9")).split(":"))
        return [(W, H), (iw, even(iw * ah / aw))]
    die(f"unknown layout '{layout}'")


# --------------------------------------------------------------------------- render
class Renderer:
    def __init__(self, prj: Project, mode: str, encoder: str, jobs: int, force: bool):
        self.p, self.mode, self.encoder, self.force = prj, mode, encoder, force
        m = MODES[mode]
        W0, H0 = FORMATS.get(str(prj.sb.get("format", "9:16")), (None, None))
        if W0 is None:
            die(f"format must be one of {list(FORMATS)}")
        self.W, self.H = even(W0 * m["scale"]), even(H0 * m["scale"])
        self.fps = m["fps"] or int(prj.sb.get("fps", 30))
        self.crf, self.preset = m["crf"], m["preset"]
        self.jobs = jobs
        self.dir = prj.build / mode
        (self.dir / "shots").mkdir(parents=True, exist_ok=True)
        (self.dir / "labels").mkdir(exist_ok=True)
        self.font = self._font()

    def _font(self) -> str:
        fonts = self.dir / "fonts"
        fonts.mkdir(exist_ok=True)
        for f in LY.FONTS_DIR.glob("*.ttf"):  # font pack (mv.py fonts) -> visible to libass via fontsdir
            if not (fonts / f.name).exists():
                shutil.copy(f, fonts / f.name)
        want = self.p.sb.get("font_file")
        cands = [Path(want)] if want else []
        cands.append(LY.FONTS_DIR / "BeVietnamPro-SemiBold.ttf")
        windir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        cands += [windir / "arial.ttf", Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
                  Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
        for c in cands:
            if c.exists():
                dst = fonts / c.name
                if not dst.exists():
                    shutil.copy(c, dst)
                return f"fonts/{c.name}"
        die("no usable .ttf font found; set font_file: in storyboard.yaml")

    # ---- one layer -> (input args, filter chain ending in [label])
    def layer(self, shot_id: str, idx: int, ly: dict, w: int, h: int, need: float,
              contain: bool = False, extra_fx: list | None = None):
        sid = ly.get("src")
        f = self.p.source_file(sid) if sid else None
        lab = f"{shot_id}l{idx}".replace("-", "_")
        speed = float(ly.get("speed", 1.0))
        chain: list[str] = []
        if f is not None and f.suffix.lower() in IMAGE_EXT:
            args = ["-loop", "1", "-framerate", str(self.fps), "-t", f"{need:.3f}", "-i", str(f)]
        elif f is not None:
            start = max(0.0, tsec(ly.get("in", 0)) - self.p.source_offset(sid))
            src_need = need * speed + 0.5
            args = ["-stream_loop", "-1", "-ss", f"{start:.3f}", "-t", f"{src_need:.3f}", "-i", str(f)]
            chain.append(f"setpts=(PTS-STARTPTS)/{speed}")
        else:  # placeholder card for the animatic
            color = PLACEHOLDER_COLORS[int(hashlib.md5(str(sid).encode()).hexdigest(), 16) % len(PLACEHOLDER_COLORS)]
            args = ["-f", "lavfi", "-t", f"{need:.3f}", "-i", f"color=c={color}:s={w}x{h}:r={self.fps}"]
            note = ly.get("note") or (self.p.sources.get(sid) or {}).get("note") or ""
            txt = self.dir / "labels" / f"{lab}.txt"
            fs = max(12, min(w, h) // 20)
            per_line = max(8, int(w * 0.8 / (fs * 0.55)))
            words, rows, cur = str(note)[:160].split(), [], ""
            for wd in words:
                if len(cur) + len(wd) + 1 > per_line and cur:
                    rows.append(cur)
                    cur = wd
                else:
                    cur = f"{cur} {wd}".strip()
            rows.append(cur)
            txt.write_text(f"[{sid or 'empty'}]\n" + "\n".join(rows), encoding="utf-8", newline="\n")
            label_filter = (f"drawtext=fontfile={self.font}:textfile=labels/{lab}.txt:fontcolor=white:"
                            f"fontsize={fs}:line_spacing={fs // 3}:x=(w-text_w)/2:y=(h-text_h)/2:"
                            f"box=1:boxcolor=black@0.45:boxborderw={fs // 2}")
        fit = f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos" if contain else cover(w, h, ly.get("focus"))
        chain += [f"fps={self.fps}", fit]
        z = None if contain else ly.get("zoom")
        if z:
            amt = float(ly.get("zoom_amount", 0.12))
            frames = max(1, int(need * self.fps))
            zexpr = f"1+{amt}*on/{frames}" if z == "in" else f"{1 + amt}-{amt}*on/{frames}"
            chain += [f"scale={2 * w}:{2 * h}",
                      f"zoompan=z='{zexpr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps={self.fps}"]
        chain += fx_filters(list(ly.get("fx") or []) + list(extra_fx or []), lab)
        if f is None:
            chain.append(label_filter)  # after zoom/fx so the card text stays readable
        chain += [f"tpad=stop_mode=clone:stop_duration={need:.3f}", f"trim=duration={need:.3f}",
                  "setpts=PTS-STARTPTS", "setsar=1", "format=gbrp"]
        return args, chain, lab

    def beat_filters(self, sh: dict, s: float, e: float, need: float) -> list[str]:
        """Beat-synced punch: zoom pulse, camera shake, brightness flash (beats from analysis.json)."""
        bfx = set(sh.get("beat_fx") or [])
        if not bfx:
            return []
        W, H, fps = self.W, self.H, self.fps
        beats = self.p.beats_in(s, e, int(sh.get("beat_every", 1)))
        if not beats:
            return []
        out = ["format=yuv444p"]
        if bfx & {"zoom", "shake"}:
            dec = max(2, round(fps * 0.22))  # pulse decays over ~0.22s
            frames = [round(b * fps) for b in beats]
            pulse = "+".join(f"gte(on,{f})*max(0,1-(on-{f})/{dec})" for f in frames)
            amp = float(sh.get("beat_zoom", 0.07)) if "zoom" in bfx else 0.0
            base = 1.04 if "shake" in bfx else 1.0  # headroom so shaking never shows an edge
            z = f"{base}+{amp}*({pulse})"
            sx = f"+{W * 0.012:.1f}*sin(on*2.7)*({pulse})" if "shake" in bfx else ""
            sy = f"+{H * 0.008:.1f}*cos(on*3.1)*({pulse})" if "shake" in bfx else ""
            out += [f"scale={2 * W}:{2 * H}",
                    f"zoompan=z='{z}':x='iw/2-(iw/zoom/2){sx}':y='ih/2-(ih/zoom/2){sy}':d=1:s={W}x{H}:fps={fps}"]
        if "flash" in bfx:
            pulse_t = "+".join(f"gte(t,{b:.3f})*max(0,1-(t-{b:.3f})/0.14)" for b in beats)
            out.append(f"eq=brightness='{float(sh.get('beat_flash', 0.3))}*({pulse_t})':eval=frame")
        return out

    def shot_spec_hash(self, i: int) -> str:
        sh = self.p.shots[i]
        prev_tr = self.p.shots[i - 1].get("transition", "cut") if i > 0 else "cut"
        files = []
        for ly in sh.get("layers") or []:
            f = self.p.source_file(ly.get("src")) if ly.get("src") else None
            files.append([str(f), f.stat().st_mtime if f else 0])
        beats = self.p.beats if sh.get("beat_fx") else []
        blob = json.dumps([sh, prev_tr, files, self.W, self.H, self.fps, self.mode,
                           self.p.sources, beats, ENGINE_HASH], sort_keys=True, default=str)
        return hashlib.sha1(blob.encode()).hexdigest()[:16]

    def render_shot(self, i: int) -> Path:
        sh = self.p.shots[i]
        sid = sh["id"]
        out = self.dir / "shots" / f"{i:03d}_{sid}.mp4"
        stamp = out.with_suffix(".hash")
        h = self.shot_spec_hash(i)
        if out.exists() and stamp.exists() and stamp.read_text() == h and not self.force:
            return out
        W, H, fps = self.W, self.H, self.fps
        s, e = tsec(sh["start"]), tsec(sh["end"])
        dur = e - s
        kind, _, d = parse_transition(sh.get("transition", "cut"))
        tail = d if kind == "xfade" else 0.0
        need = dur + tail
        layout = sh.get("layout", "full")
        slots = slots_for(layout, W, H, sh)
        layers = sh.get("layers") or []
        base = [ly for ly in layers if not ly.get("blend")]
        over = [ly for ly in layers if ly.get("blend")]
        base += [{"src": None, "note": "(empty slot)"}] * max(0, len(slots) - len(base))
        over = base[len(slots):] + over  # extra un-blended layers become 'normal' overlays
        base = base[: len(slots)]

        args: list[str] = []
        graph: list[str] = []
        labels = []
        for k, ly in enumerate(base):
            a, chain, lab = self.layer(sid, k, ly, *slots[k], need)
            n_in = args.count("-i")
            args += a
            graph.append(f"[{n_in}:v]" + ",".join(chain) + f"[{lab}]")
            labels.append(lab)

        vert = layout == "split_v"
        hf = feather_half(sh, H if vert else W) if layout in ("split_v", "split_h") else 0
        if layout == "full":
            cur = labels[0]
        elif layout == "poster":  # lyric-video player: blurred cover as background + sharp cover card
            g = LY.poster_geom(W, H)
            bx, by, bw, bh = g["card"]
            f0 = self.p.source_file(base[0].get("src")) if base[0].get("src") else None
            pw, ph = probe_wh(f0) if f0 else (1, 1)
            k = min(bw / pw, bh / ph)
            cw, ch = even(pw * k), even(ph * k)
            px, py = bx + (bw - cw) // 2, by + (bh - ch) // 2
            a, chain, lab = self.layer(sid, 9, base[0], cw, ch, need)
            n_in = args.count("-i")
            args += a
            graph.append(f"[{n_in}:v]" + ",".join(chain) + f"[{lab}]")
            off, sg = max(4, W // 90), max(8, W // 40)
            bg = f"{labels[0]}bg"
            graph.append(f"[{labels[0]}]scale={even(W / 8)}:{even(H / 8)},gblur=sigma=5,scale={W}:{H},format=yuv444p,"
                         f"eq=brightness=-0.16:saturation=1.25,"
                         f"drawbox=x={px + off}:y={py + off * 2}:w={cw}:h={ch}:color=black@0.6:t=fill,"
                         f"gblur=sigma={sg},format=gbrp[{bg}]")
            graph.append(f"[{bg}][{lab}]overlay=x={px}:y={py}:format=gbrp:shortest=1[stk]")
            cur = "stk"
        elif layout == "fit_blur":  # whole source frame centred, its own blurred copy fills the rest
            a, chain, lab = self.layer(sid, 9, base[0], W, H, need, contain=True)
            n_in = args.count("-i")
            args += a
            graph.append(f"[{n_in}:v]" + ",".join(chain) + f"[{lab}]")
            bg = f"{labels[0]}bg"
            graph.append(f"[{labels[0]}]scale={even(W / 6)}:{even(H / 6)},gblur=sigma=6,scale={W}:{H},"
                         f"eq=brightness=-0.08:saturation=1.1,format=gbrp[{bg}]")
            graph.append(f"[{bg}][{lab}]overlay=x=(W-w)/2:y=(H-h)/2:format=gbrp:shortest=1[stk]")
            cur = "stk"
        elif hf:  # soft seam: both halves overlap by 2*hf px and cross-fade through a gradient mask
            size = H if vert else W
            cut = even(size * float(sh.get("ratio", 0.5)))
            mask = self.dir / "masks" / f"{layout}_{W}x{H}_{cut}_{hf}.png"
            if not mask.exists():
                mask.parent.mkdir(exist_ok=True)
                axis = "Y" if vert else "X"
                geq = f"st(0,clip(({axis}-{cut - hf})/{2 * hf},0,1));255*ld(0)*ld(0)*(3-2*ld(0))"
                run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                     f"color=black:s={W}x{H}", "-vf", f"format=gray,geq=lum='{geq}'", "-frames:v", "1", str(mask)])
            n_in = args.count("-i")
            args += ["-loop", "1", "-framerate", str(fps), "-t", f"{need:.3f}", "-i", str(mask)]
            graph.append(f"[{labels[0]}]pad={W}:{H}:0:0[fa]")
            off = cut - hf
            graph.append(f"[{labels[1]}]pad={W}:{H}:{0 if vert else off}:{off if vert else 0}[fb]")
            graph.append(f"[{n_in}:v]format=gbrp,trim=duration={need:.3f}[fm]")
            graph.append("[fa][fb][fm]maskedmerge[stk]")
            cur = "stk"
        elif layout in ("split_v", "split_3v"):
            graph.append("".join(f"[{x}]" for x in labels) + f"vstack=inputs={len(labels)}[stk]")
            cur = "stk"
        elif layout == "split_h":
            graph.append("".join(f"[{x}]" for x in labels) + f"hstack=inputs={len(labels)}[stk]")
            cur = "stk"
        elif layout == "pip":
            ins = sh.get("inset") or {}
            pos = ins.get("pos", "tr")
            mx, my = even(W * 0.05), even(H * 0.06)
            x = {"tl": f"{mx}", "bl": f"{mx}", "tr": f"W-w-{mx}", "br": f"W-w-{mx}", "c": "(W-w)/2"}.get(pos[:2] if pos != "c" else "c")
            y = {"t": f"{my}", "b": f"H-h-{my}", "c": "(H-h)/2"}[pos[0]]
            bw = max(2, W // 180)
            graph.append(f"[{labels[1]}]pad=iw+{2 * bw}:ih+{2 * bw}:{bw}:{bw}:color=white[ins]")
            graph.append(f"[{labels[0]}][ins]overlay=x={x}:y={y}:format=gbrp:shortest=1[stk]")
            cur = "stk"

        for k, ly in enumerate(over):
            a, chain, lab = self.layer(sid, 10 + k, ly, W, H, need)
            n_in = args.count("-i")
            args += a
            graph.append(f"[{n_in}:v]" + ",".join(chain) + f"[{lab}]")
            mode = ly.get("blend", "normal")
            op = float(ly.get("opacity", 0.4))
            graph.append(f"[{cur}][{lab}]blend=all_mode={mode}:all_opacity={op}[ov{k}]")
            cur = f"ov{k}"

        post = fx_filters(sh.get("fx"), f"{sid}s")
        post += self.beat_filters(sh, s, e, need)
        pk, _, pd = parse_transition(self.p.shots[i - 1].get("transition", "cut")) if i > 0 else ("cut", "", 0)
        if pk == "flash":
            post.append(f"fade=t=in:st=0:d={pd}:color=white")
        elif pk == "fadeblack":
            post.append(f"fade=t=in:st=0:d={pd / 2:.3f}")
        if i == 0 and sh.get("fade_in", True):
            post.append("fade=t=in:st=0:d=0.4")
        if kind == "fadeblack":
            post.append(f"fade=t=out:st={dur - d / 2:.3f}:d={d / 2:.3f}")
        if i == len(self.p.shots) - 1:
            fo = float(self.p.sb.get("fade_out", 1.0))
            if fo > 0:
                post.append(f"fade=t=out:st={max(0, dur - fo):.3f}:d={fo}")
        post += [f"trim=duration={need:.3f}", "setpts=PTS-STARTPTS", "format=yuv420p"]
        graph.append(f"[{cur}]" + ",".join(post) + "[vout]")

        fscript = self.dir / "shots" / f"{i:03d}_{sid}.filter"
        fscript.write_text(";\n".join(graph), encoding="utf-8")
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args,
               "-/filter_complex", str(fscript.relative_to(self.dir)), "-map", "[vout]", "-an",
               "-c:v", "libx264", "-preset", self.preset, "-crf", str(self.crf),
               "-r", str(fps), "-pix_fmt", "yuv420p", str(out.relative_to(self.dir))]
        run(cmd, cwd=self.dir)
        stamp.write_text(h)
        return out

    def poster_geom(self) -> dict | None:
        return LY.poster_geom(self.W, self.H) if any(sh.get("layout") == "poster" for sh in self.p.shots) else None

    def captions(self) -> Path:
        sb, W, H = self.p.sb, self.W, self.H
        s0, t_end = tsec(self.p.shots[0]["start"]), tsec(self.p.shots[-1]["end"])
        font = sb.get("font") or ("Be Vietnam Pro" if LY.has_font("Be Vietnam Pro") else "Arial")
        display = sb.get("display_font") or ("Anton" if LY.has_font("Anton") else font)
        aw = LY.AssWriter(W, H, font, display, sb.get("accent", "#FFD24D"), s0, t_end)

        default_anim = sb.get("caption_anim", "fade")
        for sh in self.p.shots:
            if sh.get("caption"):
                aw.caption(tsec(sh["start"]), tsec(sh["end"]), sh.get("caption_style", "lyric"),
                           sh.get("caption_anim", default_anim), sh["caption"])
        for c in sb.get("captions") or []:
            aw.caption(tsec(c["start"]), tsec(c["end"]), c.get("style", "lyric"), c.get("anim", default_anim), c["text"])

        geom = self.poster_geom()
        default_style = sb.get("lyric_style", "scroll" if geom else "subtitle")

        def style_for(t: float) -> str:
            for sh in self.p.shots:
                if tsec(sh["start"]) <= t < tsec(sh["end"]):
                    return sh.get("lyric_style", default_style)
            return default_style

        area = None
        if sb.get("lyric_area"):
            fx0, fy0, fx1, fy1 = sb["lyric_area"]
            area = (int(W * fx0), int(H * fy0), int(W * fx1), int(H * fy1))
        elif geom:
            area = geom["lyr"]
        aw.lyrics(self.p.lyric_lines(), style_for, area, geom["align"] if geom else None,
                  sb.get("lyric_highlight", "line"), sb.get("lyric_anim", default_anim))

        pc = sb.get("poster") or {}
        if geom:
            for sh in self.p.shots:
                if sh.get("layout") != "poster":
                    continue
                a, b = tsec(sh["start"]), tsec(sh["end"])
                if pc.get("title"):
                    tx, ty = geom["title"]
                    aw.add(a, b, "ptitle", f"{{\\an8\\pos({tx},{ty})\\fad(300,300)}}{pc['title']}")
                if pc.get("artist"):
                    tx, ty = geom["artist"]
                    aw.add(a, b, "partist", f"{{\\an8\\pos({tx},{ty})\\fad(300,300)}}{pc['artist']}")
        path = self.dir / "captions.ass"
        aw.write(path)
        return path

    def player_filters(self, cur: str, total: float, n_audio: int | None, graph: list[str]) -> tuple[str, str | None]:
        """Visualizer + progress bar + time labels for poster lyric videos. Returns (video label, audio label)."""
        geom = self.poster_geom()
        pc = self.p.sb.get("poster") or {}
        if not geom:
            return cur, None
        acc = LY.ff_color(self.p.sb.get("accent", "#FFD24D"))
        vcol = LY.ff_color(pc.get("visualizer_color", "#FFFFFF"))
        alabel = None
        vis = pc.get("visualizer", "wave")
        if vis != "none" and n_audio is not None:
            vx, vy, vw, vh = geom["vis"]
            graph.append(f"[{n_audio}:a]asplit=2[amain][avis]")
            if vis == "bars":
                graph.append(f"[avis]showfreqs=s={vw}x{vh}:mode=bar:ascale=sqrt:fscale=log:colors={vcol}:"
                             f"win_size=1024,fps={self.fps},format=rgba,colorkey=black:0.1:0.0[wv]")
            else:
                graph.append(f"[avis]showwaves=s={vw}x{vh}:mode=cline:rate={self.fps}:colors={vcol}:"
                             f"scale=sqrt,format=rgba[wv]")
            graph.append(f"[{cur}][wv]overlay=x={vx}:y={vy}:eof_action=pass[pv1]")
            cur, alabel = "pv1", "amain"
        if pc.get("progress", True):
            bx, by, bw, bh = geom["bar"]
            graph.append(f"color=c=0x5a5a5a:s={bw}x{bh}:r={self.fps}:d={total:.3f}[trk]")
            graph.append(f"color=c={acc}:s={bw}x{bh}:r={self.fps}:d={total:.3f}[fil]")
            graph.append(f"[trk][fil]overlay=x='-w+w*t/{total:.3f}':y=0:eval=frame[bar]")
            graph.append(f"[{cur}][bar]overlay=x={bx}:y={by}[pv2]")
            cur = "pv2"
            if pc.get("time", True):
                fs = max(10, int(min(self.W, self.H) * 0.028))
                m, s = divmod(int(round(total)), 60)
                ty = by + bh + fs // 2
                # textfile avoids filtergraph escaping of ':' and ','; drawtext still expands %{...}
                (self.dir / "labels" / "t_now.txt").write_text("%{eif:floor(t/60):d}:%{eif:mod(t,60):d:2}", encoding="utf-8")
                (self.dir / "labels" / "t_total.txt").write_text(f"{m}:{s:02d}", encoding="utf-8")
                graph.append(f"[{cur}]drawtext=fontfile={self.font}:fontsize={fs}:fontcolor=white@0.75:"
                             f"textfile=labels/t_now.txt:x={bx}:y={ty},"
                             f"drawtext=fontfile={self.font}:fontsize={fs}:fontcolor=white@0.75:"
                             f"textfile=labels/t_total.txt:expansion=none:x={bx + bw}-text_w:y={ty}[pv3]")
                cur = "pv3"
        return cur, alabel

    def assemble(self, shot_files: list[Path]) -> Path:
        p = self.p
        s0, e_last = tsec(p.shots[0]["start"]), tsec(p.shots[-1]["end"])
        total = e_last - s0
        args, graph = [], []
        for f in shot_files:
            args += ["-i", str(f.relative_to(self.dir))]
        for i in range(len(shot_files)):  # identical timebase so concat and xfade can be mixed
            graph.append(f"[{i}:v]fps={self.fps},settb=AVTB,setpts=PTS-STARTPTS[n{i}]")
        acc = "n0"
        for i in range(1, len(shot_files)):
            kind, name, d = parse_transition(p.shots[i - 1].get("transition", "cut"))
            nxt = f"v{i}"
            if kind == "xfade":
                off = tsec(p.shots[i - 1]["end"]) - s0
                graph.append(f"[{acc}][n{i}]xfade=transition={name}:duration={d}:offset={off:.3f}[{nxt}]")
            else:
                graph.append(f"[{acc}][n{i}]concat=n=2:v=1:a=0[{nxt}]")
            acc = nxt
        self.captions()
        audio = p.sb.get("audio")
        a_args, a_map, n_a = [], [], None
        if audio:
            ap = (p.root / audio).resolve()
            if not ap.exists():
                die(f"audio not found: {ap}")
            ss = tsec(p.sb.get("song_start", 0)) + s0
            a_args = ["-ss", f"{ss:.3f}", "-t", f"{total:.3f}", "-i", str(ap)]
            n_a = len(shot_files)
        acc, a_src = self.player_filters(acc, total, n_a, graph)
        graph.append(f"[{acc}]subtitles=captions.ass:fontsdir=fonts,trim=duration={total:.3f},format=yuv420p[vout]")
        if n_a is not None:
            fo = float(p.sb.get("audio_fade_out", 0))
            af = f"afade=t=out:st={max(0, total - fo):.3f}:d={fo}" if fo > 0 else "anull"
            graph.append(f"[{a_src or f'{n_a}:a'}]{af}[aout]")
            a_map = ["-map", "[aout]", "-c:a", "aac", "-b:a", "256k", "-ar", "48000"]
        fscript = self.dir / "assemble.filter"
        fscript.write_text(";\n".join(graph), encoding="utf-8")
        enc = self.encoder_args()
        p.out.mkdir(exist_ok=True)
        name = f"{p.sb.get('slug') or p.root.name}_{self.mode}_{p.sb.get('format', '9:16').replace(':', 'x')}.mp4"
        out = p.out / name
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args, *a_args,
               "-/filter_complex", "assemble.filter", "-map", "[vout]", *a_map, *enc,
               "-r", str(self.fps), "-movflags", "+faststart", "-t", f"{total:.3f}", str(out)]
        run(cmd, cwd=self.dir)
        return out

    def encoder_args(self) -> list[str]:
        if self.mode == "proxy":
            return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p"]
        e = self.encoder
        if e == "libx264":
            return ["-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-profile:v", "high"]
        if e in ("h264_nvenc", "hevc_nvenc"):
            return ["-c:v", e, "-preset", "p6", "-tune", "hq", "-rc", "vbr", "-cq", "19", "-b:v", "0",
                    "-pix_fmt", "yuv420p"] + (["-tag:v", "hvc1"] if e.startswith("hevc") else [])
        if e in ("h264_qsv", "hevc_qsv"):
            return ["-c:v", e, "-global_quality", "20", "-pix_fmt", "nv12"]
        if e in ("h264_videotoolbox", "hevc_videotoolbox"):
            return ["-c:v", e, "-q:v", "65", "-pix_fmt", "yuv420p"] + (["-tag:v", "hvc1"] if e.startswith("hevc") else [])
        if e in ("h264_amf", "hevc_amf"):
            return ["-c:v", e, "-quality", "quality", "-rc", "cqp", "-qp_i", "19", "-qp_p", "21", "-pix_fmt", "yuv420p"]
        die(f"unknown encoder {e}")

    def run_all(self) -> Path:
        n = len(self.p.shots)
        print(f"[mv] {self.mode}: {n} shots @ {self.W}x{self.H} {self.fps}fps, jobs={self.jobs}")
        with ThreadPoolExecutor(max_workers=self.jobs) as ex:
            files = list(ex.map(self.render_shot, range(n)))
        print("[mv] shots ready, assembling ...")
        return self.assemble(files)


# --------------------------------------------------------------------------- commands
def cmd_new(a):
    root = Path(a.project)
    for d in ("audio", "sources", "refs"):
        (root / d).mkdir(parents=True, exist_ok=True)
    sb = root / "storyboard.yaml"
    if sb.exists():
        die(f"{sb} already exists")
    tpl = Path(__file__).resolve().parent.parent / "reference" / "storyboard-template.yaml"
    shutil.copy(tpl, sb)
    (root / "brief.md").write_text(
        "# Brief\n\n- Bài hát / ca sĩ:\n- File audio: audio/\n- Nền tảng & khung hình: 9:16 (TikTok/Reels/Shorts) | 16:9 (YouTube)\n"
        "- Độ dài: full / cắt 60s (đoạn nào?)\n- Cảm xúc chủ đạo:\n- Ý tưởng theo từng đoạn (intro/verse/chorus/bridge/outro):\n\n"
        "## Lời bài hát\n\n(dán lời vào đây, mỗi câu một dòng)\n", encoding="utf-8")
    (root / "lyrics.txt").write_text(
        "# Lời bài hát - mỗi dòng 1 câu đúng như hát (viết đủ cả đoạn lặp lại, không ghi 'ĐK x2').\n"
        "# [Tên đoạn] để đánh dấu đoạn. 'câu tiếng Việt | translation' để thêm dòng phụ (song ngữ).\n"
        "[Verse 1]\n", encoding="utf-8")
    print(f"[mv] created {root} (audio/, sources/, refs/, brief.md, lyrics.txt, storyboard.yaml)")


def cmd_analyze(a):
    import numpy as np
    import librosa
    root = Path(a.project)
    prj_sb = yaml.safe_load((root / "storyboard.yaml").read_text(encoding="utf-8")) if (root / "storyboard.yaml").exists() else {}
    audio = Path(a.audio) if a.audio else root / (prj_sb.get("audio") or "")
    if not audio.is_file():
        die(f"audio file not found: {audio}")
    print(f"[mv] loading {audio} ...")
    y, sr = librosa.load(str(audio), sr=22050, mono=True)
    dur = len(y) / sr
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
    tempo = float(np.atleast_1d(tempo)[0])
    onset = librosa.onset.onset_detect(y=y, sr=sr, units="time", backtrack=True)
    feats = np.vstack([librosa.feature.chroma_cqt(y=y, sr=sr), librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)])
    k = a.sections or max(4, min(12, int(dur // 25)))
    bounds = librosa.segment.agglomerative(feats, k)
    btimes = sorted(set([0.0] + [float(x) for x in librosa.frames_to_time(bounds, sr=sr)] + [dur]))
    rms = librosa.feature.rms(y=y)[0]
    rtimes = librosa.times_like(rms, sr=sr)
    sections = []
    for s, e in zip(btimes, btimes[1:]):
        if e - s < 1.0:
            continue
        m = (rtimes >= s) & (rtimes < e)
        sections.append({"start": round(s, 2), "end": round(e, 2), "energy": round(float(rms[m].mean()), 4)})
    emax = max(x["energy"] for x in sections) or 1
    for x in sections:
        x["energy_rel"] = round(x["energy"] / emax, 2)
        x["guess"] = "high (chorus/drop?)" if x["energy_rel"] > 0.8 else ("low (intro/bridge?)" if x["energy_rel"] < 0.45 else "mid")
    res = {"audio": str(audio), "duration": round(dur, 3), "tempo_bpm": round(tempo, 1),
           "beat_interval": round(60 / tempo, 3) if tempo else None,
           "beats": [round(float(b), 3) for b in beats],
           "downbeats_guess": [round(float(b), 3) for b in beats[::4]],
           "onsets": [round(float(o), 3) for o in onset], "sections": sections}
    if a.lyrics:
        res["lyrics_auto"] = whisper_words(audio, a.model, a.language)
    (root / "analysis.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[mv] duration {fmt_t(dur)}  tempo ~{tempo:.1f} bpm  beats {len(beats)}  sections {len(sections)}")
    for x in sections:
        print(f"     {fmt_t(x['start'])} - {fmt_t(x['end'])}  energy {x['energy_rel']:.2f}  {x['guess']}")
    if a.lyrics:
        for seg in res["lyrics_auto"]:
            print(f"     [{fmt_t(seg['start'])}-{fmt_t(seg['end'])}] {seg['text']}")
    print(f"[mv] wrote {root / 'analysis.json'}")


def whisper_words(audio: Path, model: str, lang: str):
    from faster_whisper import WhisperModel
    print(f"[mv] whisper {model} (first run downloads the model) ...")
    wm = WhisperModel(model, device="auto", compute_type="auto")
    segs, _ = wm.transcribe(str(audio), language=lang, word_timestamps=True, vad_filter=True)
    out = []
    for s in segs:
        out.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
                    "words": [{"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)} for w in (s.words or [])]})
    return out


SKILL_DIR = Path(__file__).resolve().parent.parent
DEMOS = ["story", "blur", "lyric-poster", "lyric-styles"]
DEMO_ASSETS = {"singer_live": "bars", "A": "bars", "fans_light": "fractal", "B": "fractal",
               "memory_overlay": "photo", "C": "photo", "poster": "poster"}


def make_demo_asset(kind: str, dst: Path, title: str = "MÙA HÈ\nCỦA EM"):
    ff = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if kind == "bars":
        run(ff + ["-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=60", "-c:v", "libx264", "-preset", "ultrafast", str(dst)])
    elif kind == "fractal":
        run(ff + ["-f", "lavfi", "-i", "mandelbrot=s=1280x720:r=30", "-t", "40", "-c:v", "libx264", "-preset", "ultrafast", str(dst)])
    elif kind == "photo":
        run(ff + ["-f", "lavfi", "-i", "smptehdbars=s=1280x720:d=1", "-frames:v", "1", str(dst)])
    elif kind == "poster":
        font = LY.FONTS_DIR / "BeVietnamPro-ExtraBold.ttf"
        tmp = dst.parent
        shutil.copy(font if font.exists() else Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arialbd.ttf", tmp / "_f.ttf")
        (tmp / "_t.txt").write_text(title, encoding="utf-8", newline="\n")  # LF only: drawtext draws CR as a line
        run(ff + ["-f", "lavfi", "-i", "gradients=s=1080x1080:x0=0:y0=0:x1=0:y1=1080:c0=0x3a1c71:c1=0xd76d77:c2=0xffaf7b:n=3:duration=1:speed=0",
                  "-vf", "drawtext=fontfile=_f.ttf:textfile=_t.txt:fontsize=150:fontcolor=white:line_spacing=10:"
                         "x=(w-text_w)/2:y=(h-text_h)/2,drawbox=x=60:y=60:w=960:h=960:color=white@0.8:t=6",
                  "-frames:v", "1", dst.name], cwd=tmp)
        (tmp / "_f.ttf").unlink()
        (tmp / "_t.txt").unlink()


def cmd_demo(a):
    names = DEMOS if a.name == "all" else [a.name]
    if not LY.has_font("Be Vietnam Pro"):
        LY.download_fonts()
    for name in names:
        root = Path(a.dir) / f"demo-{name}"
        if root.exists() and not a.force:
            print(f"[mv] {root} exists - re-rendering (use --force to recreate)")
        else:
            if root.exists():
                shutil.rmtree(root)
            (root / "audio").mkdir(parents=True)
            (root / "sources").mkdir()
            ex = SKILL_DIR / "examples" / name
            if name == "story":
                shutil.copy(SKILL_DIR / "reference" / "storyboard-template.yaml", root / "storyboard.yaml")
            else:
                for f in ex.iterdir():
                    shutil.copy(f, root / f.name)
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                 "aevalsrc='0.55*sin(2*PI*220*t)*exp(-10*mod(t,0.5))+0.25*sin(2*PI*330*t)*exp(-6*mod(t+0.25,1))'"
                 ":s=44100:d=24", str(root / "audio" / "song.mp3")])
            sb = yaml.safe_load((root / "storyboard.yaml").read_text(encoding="utf-8"))
            for sid in sb.get("sources") or {}:
                kind = DEMO_ASSETS.get(sid)
                if kind:
                    ext = ".png" if kind in ("photo", "poster") else ".mp4"
                    make_demo_asset(kind, root / "sources" / f"{sid}{ext}")
            if any(sh.get("beat_fx") for sh in sb.get("shots") or []):
                cmd_analyze(argparse.Namespace(project=str(root), audio=None, lyrics=False, model="medium",
                                               language="vi", sections=None))
        cmd_review(argparse.Namespace(project=str(root)))
        cmd_render(argparse.Namespace(project=str(root), mode=a.mode, encoder=a.encoder, jobs=None, force=False))


def cmd_fonts(a):
    LY.download_fonts()
    print(f"[mv] fonts in {LY.FONTS_DIR}: " + ", ".join(f for f in LY.FONT_PACK if LY.has_font(f)))


def cmd_align(a):
    root = Path(a.project)
    txt = root / "lyrics.txt"
    if not txt.exists():
        die(f"{txt} not found - paste the lyrics there, one sung line per line")
    lines = LY.parse_lyrics_txt(txt.read_text(encoding="utf-8"))
    if not lines:
        die("lyrics.txt has no lyric lines")
    an = root / "analysis.json"
    data = json.loads(an.read_text(encoding="utf-8")) if an.exists() else {}
    segs = data.get("lyrics_auto")
    if segs:
        out, ratio = LY.align_lines(lines, segs)
        print(f"[mv] aligned {len(out)} lines, {ratio:.0%} of words matched Whisper exactly")
        if ratio < 0.5:
            print("[mv] WARN: low match - check lyrics.txt order/repeats, or re-run analyze on a vocal stem (demucs)")
    else:
        t0 = tsec(a.start) if a.start else 0.0
        t1 = tsec(a.end) if a.end else float(data.get("duration") or 0)
        if t1 <= t0:
            die("no Whisper timing in analysis.json: run `analyze --lyrics`, or give --start/--end to spread lines evenly")
        print("[mv] WARN: no Whisper timing - spreading lines evenly; fix times by hand in lyrics.yaml")
        total = sum(len(l["text"]) for l in lines)
        t, out = t0, []
        for l in lines:
            d = (t1 - t0) * len(l["text"]) / total
            out.append(dict(l, start=round(t, 2), end=round(t + d - 0.2, 2)))
            t += d
    for l in out:
        print(f"     {fmt_t(l['start'])} - {fmt_t(l['end'])}  {l['text']}")
    dst = root / "lyrics.yaml"
    dst.write_text("# generated by mv.py align - edit times freely; words = [word, start, end]\n" +
                   yaml.safe_dump({"lines": out}, allow_unicode=True, sort_keys=False, default_flow_style=None, width=200),
                   encoding="utf-8")
    print(f"[mv] wrote {dst}  (storyboard: lyrics_file: lyrics.yaml)")


def cmd_review(a):
    p = Project(a.project)
    p.validate()
    sb = p.sb
    s0, e1 = tsec(p.shots[0]["start"]), tsec(p.shots[-1]["end"])
    L = [f"# Storyboard - {sb.get('title', p.root.name)}", "",
         f"- Khung hình: **{sb.get('format', '9:16')}** · {sb.get('fps', 30)} fps · Audio: `{sb.get('audio')}`",
         f"- Thời lượng: **{fmt_t(e1 - s0)}** ({fmt_t(s0)} → {fmt_t(e1)}) · {len(p.shots)} shot · "
         f"trung bình {(e1 - s0) / len(p.shots):.1f}s/shot", ""]
    lines = p.lyric_lines()
    if lines or sb.get("lyric_style"):
        L += [f"- Lyric: kiểu **{sb.get('lyric_style', 'subtitle')}** · font `{sb.get('font', 'Be Vietnam Pro')}` / "
              f"`{sb.get('display_font', 'Anton')}` · màu nhấn `{sb.get('accent', '#FFD24D')}` · {len(lines)} câu", ""]
    if sb.get("concept"):
        L += ["## Concept", "", str(sb["concept"]).strip(), ""]
    if sb.get("song_reading"):
        L += ["## Đọc bài hát", "", str(sb["song_reading"]).strip(), ""]
    if sb.get("look"):
        L += ["## Look tổng thể", "", str(sb["look"]).strip(), ""]
    plan = sb.get("technique_plan") or []
    if plan:
        L += ["## Đề xuất kỹ thuật theo ý nghĩa bài hát", ""]
        for n, sec in enumerate(plan, 1):
            L.append(f"### {n}. {sec.get('section', '')}" + (f" - {sec['time']}" if sec.get("time") else ""))
            if sec.get("meaning"):
                L.append(f"- **Ý nghĩa / cảm xúc:** {sec['meaning']}")
            if sec.get("recommend"):
                L.append(f"- **⭐ Đề xuất:** {sec['recommend']}")
            if sec.get("why"):
                L.append(f"- **Vì sao hợp:** {sec['why']}")
            for o in sec.get("options") or []:
                L.append(f"- Phương án khác: {o}")
            L.append("")
    wow = sb.get("wow_moments") or []
    if wow:
        L += ["## Khoảnh khắc 'wow' (điểm nhấn để viral)", ""] + [f"- {w}" for w in wow] + [""]
    L += ["## Nguồn footage", "", "| id | Trạng thái | Nguồn | Ghi chú / quyền sử dụng |", "|---|---|---|---|"]
    for sid, info in p.sources.items():
        info = info or {}
        have = "✅ có file" if p.source_file(sid) else ("⬇ chờ tải" if info.get("url") else "❓ cần tìm")
        src = info.get("url") or info.get("path") or info.get("search") or ""
        if info.get("section"):
            src += f" `[{info['section']}]`"
        L.append(f"| `{sid}` | {have} | {src} | {info.get('note', '')} {('· ' + info['rights']) if info.get('rights') else ''} |")
    L += ["", "## Shot list", "", "| # | Thời gian | Lời / đoạn | Ý đồ | Kỹ thuật | Bố cục | Lớp hình | FX | → Chuyển |",
          "|---|---|---|---|---|---|---|---|---|"]
    for sh in p.shots:
        lay = []
        for ly in sh.get("layers") or []:
            t = f"`{ly.get('src')}`@{ly.get('in', 0)}"
            if ly.get("speed", 1) != 1:
                t += f" x{ly['speed']}"
            if ly.get("blend"):
                t += f" ({ly['blend']} {ly.get('opacity', 0.4)})"
            if ly.get("zoom"):
                t += f" zoom-{ly['zoom']}"
            if ly.get("fx"):
                t += " " + "+".join(map(str, ly["fx"]))
            lay.append(t)
        lyric = sh.get("lyric") or sh.get("caption") or sh.get("section", "")
        layout = sh.get("layout", "full")
        if layout in ("split_v", "split_h"):
            fv = sh.get("feather", DEFAULT_FEATHER)
            layout += f" (viền mềm {fv})" if fv else " (cắt cứng)"
        fx = list(map(str, sh.get("fx") or [])) + [f"beat-{b}" for b in sh.get("beat_fx") or []]
        tech = ", ".join(f"`{t}`" for t in sh.get("technique") or [])
        if sh.get("lyric_style"):
            tech += f"<br>lyric: {sh['lyric_style']}"
        L.append(f"| {sh['id']} | {fmt_t(tsec(sh['start']))}–{fmt_t(tsec(sh['end']))} | {lyric} | {sh.get('intent', '')} | "
                 f"{tech} | {layout} | {'<br>'.join(lay)} | {'+'.join(fx)} | {sh.get('transition', 'cut')} |")
    alts = [(sh["id"], a) for sh in p.shots for a in sh.get("alt") or []]
    if alts:
        L += ["", "## Phương án thay thế từng shot (chọn để đổi)", ""] + [f"- **{i}:** {a}" for i, a in alts]
    L += ["", "> Duyệt: trả lời OK, hoặc ghi số shot + phương án muốn đổi (vd. `S03 -> dùng phương án 2`)."]
    out = p.root / "storyboard.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[mv] wrote {out}")


def cmd_search(a):
    q = f"ytsearch{a.n}:{a.query}"
    r = run(venv_tool("yt_dlp") + ["--flat-playlist", "--no-warnings", "--print",
                                   "%(id)s | %(duration_string)s | %(channel)s | %(title)s | %(url)s", q])
    print(r.stdout.strip())


def cmd_fetch(a):
    p = Project(a.project)
    (p.root / "sources").mkdir(exist_ok=True)
    for sid, info in p.sources.items():
        info = info or {}
        if not info.get("url") or p.source_file(sid):
            continue
        cmd = venv_tool("yt_dlp") + ["--no-warnings", "--no-playlist",
               "-f", f"bv*[height<={a.max_height}][vcodec^=avc1]/bv*[height<={a.max_height}]/b[height<={a.max_height}]/b",
               "--remux-video", "mp4", "-o", str(p.root / "sources" / f"{sid}.%(ext)s")]
        if info.get("section"):
            a0, _, b0 = str(info["section"]).partition("-")
            cmd += ["--download-sections", f"*{tsec(a0)}-{tsec(b0)}", "--force-keyframes-at-cuts"]
        cmd.append(info["url"])
        print(f"[mv] fetching {sid} <- {info['url']}")
        r = subprocess.run(cmd, text=True)
        if r.returncode != 0:
            print(f"[mv] WARN: failed to fetch {sid}")


def cmd_sheet(a):
    p = Project(a.project)
    f = p.source_file(a.source)
    if not f:
        die(f"source {a.source} has no local file yet")
    rend = Renderer(p, "proxy", "libx264", 1, False)
    out = p.root / "refs" / f"sheet_{a.source}.jpg"
    out.parent.mkdir(exist_ok=True)
    off = p.source_offset(a.source)
    probe = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)])
    dur = float((probe.stdout or "0").strip() or 0)
    if dur:
        a.rows = max(1, min(a.rows, -(-int(dur / a.every + 1) // a.cols)))
    vf = (f"fps=1/{a.every},scale=320:-2,drawtext=fontfile={rend.font}:text='%{{pts\\:hms\\:{off}}}':"
          f"fontcolor=yellow:fontsize=22:box=1:boxcolor=black@0.6:x=6:y=6,tile={a.cols}x{a.rows}")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(f), "-vf", vf, "-frames:v", "1",
         "-q:v", "3", str(out)], cwd=rend.dir)
    print(f"[mv] wrote {out} (timecodes = original-video time, 1 frame every {a.every}s)")


def cmd_scenes(a):
    p = Project(a.project)
    f = p.source_file(a.source)
    if not f:
        die(f"source {a.source} has no local file yet")
    from scenedetect import detect, AdaptiveDetector
    off = p.source_offset(a.source)
    for n, (s, e) in enumerate(detect(str(f), AdaptiveDetector())):
        print(f"{n:3d}  {fmt_t(s.get_seconds() + off)} - {fmt_t(e.get_seconds() + off)}  ({e.get_seconds() - s.get_seconds():.1f}s)")


def cmd_render(a):
    p = Project(a.project)
    p.validate()
    jobs = a.jobs or max(1, (os.cpu_count() or 4) // 4)
    r = Renderer(p, a.mode, a.encoder, jobs, a.force)
    out = r.run_all()
    print(f"[mv] done -> {out}")


def main():
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252 -> Vietnamese would crash print()
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap =argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("new"); s.add_argument("project"); s.set_defaults(fn=cmd_new)
    s = sub.add_parser("analyze"); s.add_argument("project"); s.add_argument("--audio")
    s.add_argument("--lyrics", action="store_true"); s.add_argument("--model", default="medium")
    s.add_argument("--language", default="vi"); s.add_argument("--sections", type=int); s.set_defaults(fn=cmd_analyze)
    s = sub.add_parser("review"); s.add_argument("project"); s.set_defaults(fn=cmd_review)
    s = sub.add_parser("fonts"); s.set_defaults(fn=cmd_fonts)
    s = sub.add_parser("demo"); s.add_argument("name", nargs="?", default="story", choices=DEMOS + ["all"])
    s.add_argument("--dir", default="projects"); s.add_argument("--mode", choices=list(MODES), default="proxy")
    s.add_argument("--encoder", default="libx264"); s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_demo)
    s = sub.add_parser("align"); s.add_argument("project"); s.add_argument("--start"); s.add_argument("--end")
    s.set_defaults(fn=cmd_align)
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("-n", type=int, default=10); s.set_defaults(fn=cmd_search)
    s = sub.add_parser("fetch"); s.add_argument("project"); s.add_argument("--max-height", type=int, default=1080); s.set_defaults(fn=cmd_fetch)
    s = sub.add_parser("sheet"); s.add_argument("project"); s.add_argument("source")
    s.add_argument("--every", type=float, default=2.0); s.add_argument("--cols", type=int, default=6)
    s.add_argument("--rows", type=int, default=6); s.set_defaults(fn=cmd_sheet)
    s = sub.add_parser("scenes"); s.add_argument("project"); s.add_argument("source"); s.set_defaults(fn=cmd_scenes)
    s = sub.add_parser("render"); s.add_argument("project"); s.add_argument("--mode", choices=list(MODES), default="proxy")
    s.add_argument("--encoder", default="libx264"); s.add_argument("--jobs", type=int); s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_render)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
