#!/usr/bin/env python3
"""mv.py - storyboard-driven music-video pipeline built on FFmpeg.

Run through the launcher next to SKILL.md: `mv` (macOS/Linux/Git-Bash) or `mv.cmd` (Windows).

Subcommands:
  doctor   [--quick] [--install ids] machine check + benchmark -> machine.json + install recommendations
  demo     [story|blur|lyric-poster|lyric-styles|pro|genre-mv|lyric-kinetic|lyric-template|all]
                                     build + render a demo with synthetic media
  new      <project>                 create a project skeleton
  analyze  <project> [--lyrics]      tempo / beats / sections (+ whisper lyric timing)
  align    <project>                 lyrics.txt + Whisper timing -> lyrics.yaml (per-word times)
  fonts    [pack|list|get|check|preview]  font pack, catalogue (--lang/--tag), download "Family:900i",
                                     glyph coverage, specimen of candidates over the poster
  palette  <image>                   dominant colours (accent / text colour picks)
  status   <project>                 where the project stands + the next step (cheap to read after a context reset)
  context  [--project p] --type mv|lyric|poster [--genre g] [--platforms ..] [--mood ..]
                                     planning digest: only the genre / presets / techniques / fields this project needs
  review   <project>                 storyboard.yaml -> storyboard.md (for human approval, incl. edit check)
  proof    <project> [--only S03,S07] one labelled frame per shot in a single sheet (refs/proof.jpg) - check the edit
  stills   <project>                 shot ideas from images: detail crops + `camera:` moves (one poster -> many shots)
  qa       <project> [--mode final]  check rendered files: black / frozen frames, A/V sync, loudness, specs -> out/qa.md
  thumbnail <project> [--format f] [--at m:ss]  best frame + title -> out/thumb_<aspect>.jpg (YouTube / cover)
  srt      <project> [--cut a-b]     lyrics as SubRip captions -> out/<slug>.srt
  deliver  <project> [--mode final]  every platform version + short cut + srt + thumbnails + description + QA
  check    <project> [--genre g]     edit check against the genre's cutting grammar (reference/genres.yaml)
  genres                             list genres (cutting grammar + fitting presets)
  sync     <project> <source_id>     find a performance clip's offset to the song (audio match) -> picks.yaml
  auto     <project> --template t    lyric-video storyboard from lyrics.yaml + a template preset; with a footage
                                     preset + --genre: shots cut to the genre grammar, `layers: auto` for mv match
  search   "query" [-n 10]           list YouTube candidates (id | title | duration | url)
  find     "query" --project p --slot id [--type video|image] [--providers pexels,pixabay,commons,openverse,youtube]
           [--describe "visual description" --rank] [--deep 5] [--links "url1 url2"]
                                     licence-aware search + numbered contact sheet refs/cand_<slot>.jpg; --rank orders
                                     by how well thumbnails match the description (SigLIP 2), --deep finds the matching
                                     moment inside YouTube videos from their preview storyboards (no video download)
  scout    <project>                 find + rank + deep-scan candidates for every source that has `search:`
  match    <project> [--sheets]      pick scenes from your clips / downloaded sources for shots with `layers: auto`
                                     (by each shot's `look_for` description) -> matches.yaml + refs/match_all.jpg
  pick     <project> <source_id> <slot:n>   use candidate n for a source (written to picks.yaml)
  ingest   <project> <folder>        register your own clips/photos, rank best moments (refs/ingest_best.jpg)
  lyrics   fetch <project> --artist A --title T   synced lyrics from LRCLIB -> lyrics.yaml
  presets                            list style presets + lyric-video templates (storyboard: preset: <name>)
  credits  <project>                 out/credits.txt for the video description
  fetch    <project>                 download every source that has a url (direct or yt-dlp)
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
import re
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
import doctor as DR  # noqa: E402
import fonts as FT  # noqa: E402
import sources as SRC  # noqa: E402
import runtime as RT  # noqa: E402
import gen as GEN  # noqa: E402
import editcheck as EC  # noqa: E402
import platforms as PL  # noqa: E402
import assist as AS  # noqa: E402
import footage as FG  # noqa: E402
import deliver as DL  # noqa: E402
import threading  # noqa: E402

RT.apply_runtime_env()  # FFmpeg chosen with `mv doctor --use-ffmpeg` (this process only)

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
    # stdin=DEVNULL: FFmpeg reads the keyboard by default; with a vanished console it can spin forever
    r = subprocess.run(cmd, cwd=cwd, capture_output=quiet, text=True, encoding="utf-8", errors="replace",
                       stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        tail = (r.stderr or "")[-2500:] if quiet else ""
        die(f"command failed ({r.returncode}): {' '.join(map(str, cmd[:6]))} ...\n{tail}")
    return r


# --------------------------------------------------------------------------- presets
def load_presets() -> dict:
    return yaml.safe_load((Path(__file__).resolve().parent.parent / "reference" / "presets.yaml").read_text(encoding="utf-8"))


def apply_preset(sb: dict, shots: list) -> dict:
    """Merge a style preset / lyric-video template into the storyboard (explicit values win).
    Returns generated scene sources for shots without layers (lyric-video templates)."""
    presets = load_presets()
    pr = presets.get(sb["preset"])
    if not pr:
        die(f"unknown preset '{sb['preset']}' - one of {sorted(presets)}")
    themes = pr.get("themes") or {}
    if sb.get("theme"):
        if sb["theme"] not in themes:
            die(f"preset '{sb['preset']}' has no theme '{sb['theme']}' - one of {sorted(themes) or 'none'}")
        for k, v in themes[sb["theme"]].items():
            sb.setdefault(k, v)
    if pr.get("palette"):
        sb.setdefault("palette", list(pr["palette"]))
    if pr.get("kind") != "lyric-template":
        sb.setdefault("color_match", 0.6)  # footage from different cameras/sources looks like one film
    for k, v in (pr.get("defaults") or {}).items():
        if k == "typo":
            sb["typo"] = {**v, **(sb.get("typo") or {})}
        else:
            sb.setdefault(k, v)
    base = pr.get("shot") or {}
    scenes = pr.get("scenes") or []
    gen_sources: dict = {}
    for n, sh in enumerate(shots):
        if sh.get("preset") is False:
            continue
        sec = str(sh.get("section", "")).lower()
        secs = pr.get("sections") or {}
        ck = EC.canon(sec)  # "pre-chorus" -> pre, "hook" -> chorus (exact canonical match beats a substring)
        if ck:
            extra = secs.get(ck) or {}
        else:
            extra = next((v for k, v in secs.items() if k in sec), {}) if sec else {}
        sh["fx"] = list(base.get("fx") or []) + list(extra.get("fx") or []) + list(sh.get("fx") or [])
        for k in ("transition",):
            if k not in sh and (extra.get(k) or base.get(k)):
                sh[k] = extra.get(k) or base.get(k)
        for k in ("beat_fx", "beat_every", "beat_flash", "beat_zoom", "lyric_style"):
            if k not in sh and k in extra:
                sh[k] = extra[k]
        if scenes and not sh.get("layers"):  # template: generated background, cycling for scene variety
            k = (int(extra["scene"]) - 1 if "scene" in extra else n) % len(scenes)
            sid = f"_scene{k + 1}"
            gen_sources[sid] = {"gen": scenes[k], "note": f"template scene {k + 1}"}
            sh["layers"] = [{"src": sid, **(pr.get("scene_layer") or {})}]
    return gen_sources


# --------------------------------------------------------------------------- project
class Project:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        sb_path = self.root / "storyboard.yaml"
        if not sb_path.exists():
            die(f"{sb_path} not found (run: mv.py new {root})")
        self.sb = yaml.safe_load(sb_path.read_text(encoding="utf-8")) or {}
        self.sources: dict = self.sb.get("sources") or {}
        picks = self.root / "picks.yaml"  # written by `mv pick` / `mv ingest` - never rewrites storyboard.yaml
        if picks.exists():
            for sid, info in (yaml.safe_load(picks.read_text(encoding="utf-8")) or {}).items():
                self.sources[sid] = {**(self.sources.get(sid) or {}), **(info or {})}
        self.shots: list = self.sb.get("shots") or []
        if not self.shots:
            die("storyboard has no shots")
        for i, sh in enumerate(self.shots):
            sh.setdefault("id", f"S{i + 1:02d}")
        if self.sb.get("preset"):
            for sid, info in apply_preset(self.sb, self.shots).items():
                self.sources.setdefault(sid, info)
        self._resolve_auto()
        self._resolve_lipsync()
        self.build = self.root / "build"
        self.out = self.root / "out"
        an = self.root / "analysis.json"
        data = json.loads(an.read_text(encoding="utf-8")) if an.exists() else {}
        self.beats: list[float] = data.get("beats", [])
        self.downbeats: list[float] = data.get("downbeats_guess", [])

    def _resolve_auto(self):
        """`layers: auto` / `{src: auto}` -> the scene `mv match` chose for this shot (matches.yaml, `use:` = choice)."""
        f = self.root / "matches.yaml"
        m = ((yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("shots") or {}) if f.exists() else {}
        for sh in self.shots:
            if sh.get("layers") == "auto" or (not sh.get("layers") and sh.get("look_for")):
                sh["layers"] = [{"src": "auto"}]
            for ly in sh.get("layers") or []:
                if not isinstance(ly, dict) or ly.get("src") != "auto":
                    continue
                ent = m.get(str(sh["id"])) or {}
                cs = ent.get("candidates") or []
                k = int(ent.get("use", 1) or 1) - 1
                if 0 <= k < len(cs):
                    ly["src"] = cs[k]["src"]
                    ly.setdefault("in", cs[k].get("in", 0))
                    if cs[k].get("image"):
                        ly.setdefault("zoom", "in")
                else:
                    ly["src"] = None
                    ly["note"] = f"auto - run: mv match ({sh.get('look_for') or sh.get('intent') or 'add look_for'})"

    def gen_spec(self, sid) -> str | None:
        return (self.sources.get(sid) or {}).get("gen") if sid else None

    def _resolve_lipsync(self):
        """lipsync: true -> in = song time + the source's `sync` offset (from `mv sync`); lipsync: <s> = that offset.
        A performance clip shot to playback then stays in sync across every cut (multi-cam style)."""
        song0 = tsec(self.sb.get("song_start", 0))
        for sh in self.shots:
            for ly in sh.get("layers") or []:
                ls = ly.get("lipsync")
                if ls is None or ls is False:
                    continue
                off = float((self.sources.get(ly.get("src")) or {}).get("sync", 0) or 0) if ls is True else float(ls)
                ly["in"] = round(tsec(sh.get("start")) + song0 + off, 3)

    def apply_cut_lead(self, fps: int) -> float:
        """cut_lead: cut picture a frame or two BEFORE the beat (`2f` or seconds) - the eye needs ~1-2 frames to
        register a cut, so early cuts feel exactly on the beat. Audio and lyric timing are unchanged."""
        v = self.sb.get("cut_lead")
        if not v:
            return 0.0
        txt = str(v).strip()
        lead = float(txt[:-1]) / fps if txt.endswith("f") else float(txt)
        if not 0 < lead <= 0.2:
            die("cut_lead must be between 0 and 0.2 s (e.g. 2f or 0.06)")
        for i, sh in enumerate(self.shots):
            if i > 0:
                sh["start"] = tsec(sh["start"]) - lead
            if i < len(self.shots) - 1:
                sh["end"] = tsec(sh["end"]) - lead
        self._resolve_lipsync()
        return lead

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
        if self.sb.get("platforms"):
            try:
                PL.expand(self.sb["platforms"])
            except ValueError as e:
                die(str(e))
        for sid, info in self.sources.items():
            if (info or {}).get("gen"):
                try:
                    GEN.parse(info["gen"], self.sb.get("palette"), self.sb.get("accent"))
                except ValueError as e:
                    die(f"source {sid}: {e}")
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
                if src and src != "auto" and src not in self.sources:
                    die(f"{sid}: layer src '{src}' is not declared under sources:")
                mode = ly.get("blend")
                if mode and mode not in BLEND_MODES:
                    die(f"{sid}: blend '{mode}' not in {sorted(BLEND_MODES)}")
                if ly.get("lipsync") not in (None, False) and (
                        float(ly.get("speed", 1)) != 1 or ly.get("ramp") or ly.get("freeze")):
                    die(f"{sid}: a lipsync layer must play at speed 1 (no speed / ramp / freeze)")
            if sh.get("role") and sh["role"] not in EC.ROLES:
                die(f"{sid}: role must be one of {sorted(EC.ROLES)}")
            if sh.get("size") and sh["size"] not in EC.SIZES:
                die(f"{sid}: size must be one of {sorted(EC.SIZES)}")
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
    """-> (kind, name, duration). kind: cut | flash | fadeblack | glitch | xfade."""
    v = str(v or "cut").strip()
    name, _, d = v.partition(":")
    dur = float(d) if d else 0.5
    if name in ("cut", "", "none"):
        return ("cut", "cut", 0.0)
    if name == "glitch":
        return ("glitch", "glitch", float(d) if d else 0.25)
    if name in ("zoomblur", "spin", "burn"):  # beat-friendly transitions drawn on both sides of the cut
        return (name, name, float(d) if d else {"zoomblur": 0.3, "spin": 0.3, "burn": 0.45}[name])
    if name == "strobe":
        return ("flash", "flash", float(d) if d else 0.08)
    if name == "flashblack":
        return ("fadeblack", "fadeblack", float(d) if d else 0.3)
    if name == "whip":
        return ("xfade", "smoothleft", float(d) if d else 0.25)
    if name == "zoom":
        return ("xfade", "zoomin", float(d) if d else 0.4)
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
# Colour grades (fx: grade:<name>) - built from curves/colorbalance/eq, no LUT files needed.
GRADES = {
    "teal-orange": "colorbalance=rs=-0.08:gs=-0.02:bs=0.12:rh=0.12:gh=0.02:bh=-0.10,eq=saturation=1.15:contrast=1.06",
    "kodak": "curves=all='0/0.03 0.5/0.53 1/0.97',colorbalance=rm=0.06:gm=0.01:bm=-0.05,eq=saturation=1.08",
    "golden": "colorbalance=rm=0.08:gm=0.03:bm=-0.08:rh=0.06:bh=-0.06,eq=saturation=1.1:brightness=0.02",
    "moody": "eq=brightness=-0.04:contrast=1.15:saturation=0.8,colorbalance=bs=0.06:bm=0.04",
    "bleach": "eq=saturation=0.45:contrast=1.25,curves=all='0/0 0.25/0.18 0.75/0.85 1/1'",
    "noir": "hue=s=0,eq=contrast=1.4:brightness=-0.03,curves=all='0/0 0.3/0.2 0.7/0.85 1/1'",
    "pastel": "eq=saturation=0.75:brightness=0.05:contrast=0.9,colorbalance=rh=0.05:bh=0.06",
    "matte": "curves=all='0/0.08 1/0.94',eq=saturation=0.9",
    "cyberpunk": "colorbalance=rs=0.15:bs=0.2:gm=-0.08:rh=0.1:bh=0.15,eq=saturation=1.35:contrast=1.1",
    "cold-blue": "colorbalance=rs=-0.1:bs=0.15:rm=-0.05:bm=0.08,eq=saturation=0.85:contrast=1.08",
}


def fx_filters(fx_list, label: str, w: int | None = None, h: int | None = None, fps: int = 30) -> list[str]:
    out: list[str] = []
    for n, raw in enumerate(fx_list or []):
        if isinstance(raw, tuple) and raw[0] == "__raw__":  # resolved by the renderer (e.g. a LUT file)
            filt, amt = raw[1], raw[2]
            if amt >= 0.999:
                out.append(filt)
            else:
                p = f"{label}r{n}"
                out.append(f"format=gbrp,split[{p}a][{p}b];[{p}b]{filt}[{p}c];[{p}a][{p}c]blend=all_mode=normal:all_opacity={amt}")
            continue
        name, _, arg = str(raw).partition(":")
        if name == "grade":
            if arg not in GRADES:
                die(f"unknown grade '{arg}' - one of {sorted(GRADES)}")
            out.append(GRADES[arg])
            continue
        a = float(arg) if arg else None
        p = f"{label}x{n}"
        if name == "letterbox":  # cinema bars, a = bar height as a fraction of the frame
            b = a or 0.1
            out.append(f"drawbox=x=0:y=0:w=iw:h=ih*{b}:color=black:t=fill,"
                       f"drawbox=x=0:y=ih-ih*{b}:w=iw:h=ih*{b}:color=black:t=fill")
        elif name == "leak":  # procedural drifting light leak (no stock clip needed)
            if not (w and h):
                die("leak needs a known frame size")
            # blend in RGB: screen-blending YUV chroma planes tints the whole frame purple
            out.append(f"format=gbrp[{p}a];gradients=s={w}x{h}:type=radial:x0=0:y0={int(h * 0.12)}:"
                       f"x1={int(w * 0.7)}:y1={int(h * 0.54)}:c0=0xffc070:c1=0xff5a50:c2=0x000000:nb_colors=3:"
                       f"speed=0.02:rate={fps},format=gbrp,gblur=sigma={max(20, w // 14)}[{p}g];"
                       f"[{p}a][{p}g]blend=all_mode=screen:all_opacity={a or 0.4}:shortest=1")
        elif name == "handheld":  # gentle camera drift / breathing
            if not (w and h):
                die("handheld needs a known frame size")
            k = a or 1.0
            out.append(f"crop=w=iw*0.93:h=ih*0.93:x='(iw-ow)/2+iw*{0.010 * k:.4f}*sin(t*1.9)+iw*{0.005 * k:.4f}*sin(t*4.3)':"
                       f"y='(ih-oh)/2+ih*{0.008 * k:.4f}*sin(t*1.4+1.3)',scale={w}:{h}")
        elif name == "motionblur":
            out.append("tmix=frames=3:weights='1 2 1'")
        elif name == "bloom":  # warm halation around highlights
            out.append(f"format=gbrp,split[{p}a][{p}b];[{p}b]gblur=sigma=22,colorchannelmixer=rr=1:gg=0.62:bb=0.42[{p}c];"
                       f"[{p}a][{p}c]blend=all_mode=screen:all_opacity={a or 0.32}")
        elif name == "sharpen":
            out.append(f"unsharp=5:5:{a or 0.8}")
        elif name == "chroma":
            px = int(a or 4)
            out.append(f"rgbashift=rh=-{px}:bh={px}:rv={px // 2}")
        elif name == "bw":
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
        elif name == "denoise":  # phone / low-light noise (fast); denoise_hq = nlmeans (slow, cleaner)
            k = a or 1.0
            out.append(f"hqdn3d={1.5 * k:.2f}:{1.2 * k:.2f}:{5 * k:.2f}:{4 * k:.2f}")
        elif name == "denoise_hq":
            out.append(f"nlmeans=s={a or 3.0}:p=5:r=11")
        elif name == "clarity":  # local contrast ("pop") without over-sharpening edges
            out.append(f"unsharp=13:13:{a or 0.35}:13:13:0")
        elif name == "filmgrain":  # luminance grain, closer to film than RGB noise
            out += ["format=yuv444p", f"noise=c0s={int(a or 10)}:c0f=t+u"]
        elif name == "halation":  # red-orange glow bleeding from the brightest highlights (film emulsion)
            p = f"{label}h{n}"
            thr = "clip((val-185)*3,0,255)"
            out.append(f"format=gbrp,split[{p}a][{p}b];[{p}b]lutrgb=r='{thr}':g='{thr}':b='{thr}',"
                       f"gblur=sigma={max(6, (w or 1080) // 60)},colorchannelmixer=rr=1:gg=0.35:bb=0.12[{p}c];"
                       f"[{p}a][{p}c]blend=all_mode=screen:all_opacity={a or 0.5}")
        elif name == "flare":  # anamorphic horizontal streaks from highlights
            p = f"{label}f{n}"
            thr = "clip((val-200)*4,0,255)"
            out.append(f"format=gbrp,split[{p}a][{p}b];[{p}b]lutrgb=r='{thr}':g='{thr}':b='{thr}',"
                       f"gblur=sigma={max(20, (w or 1080) // 10)}:sigmaV=1.5,colorchannelmixer=rr=0.45:gg=0.75:bb=1.0[{p}c];"
                       f"[{p}a][{p}c]blend=all_mode=screen:all_opacity={a or 0.6}")
        elif name == "dust":  # flickering dust specks of projected film
            if not (w and h):
                die("dust needs a known frame size")
            p = f"{label}d{n}"
            out.append(f"format=gbrp[{p}a];color=c=black:s={w}x{h}:r={fps},noise=alls=100:allf=t,"
                       f"lutyuv=y='if(gt(val,251),255,0)':u=128:v=128,gblur=sigma=0.9,format=gbrp[{p}d];"
                       f"[{p}a][{p}d]blend=all_mode=screen:all_opacity={a or 0.6}:shortest=1")
        elif name == "weave":  # film gate weave: tiny frame-to-frame jitter
            if not (w and h):
                die("weave needs a known frame size")
            k = a or 1.0
            out.append(f"crop=w=iw*0.97:h=ih*0.97:x='(iw-ow)/2+iw*{0.0025 * k:.4f}*sin(n*1.7+cos(n*0.37))':"
                       f"y='(ih-oh)/2+ih*{0.003 * k:.4f}*sin(n*2.3+sin(n*0.71))',scale={w}:{h}")
        elif name == "lens":  # slight barrel distortion + edge softness of a vintage lens
            if not (w and h):
                die("lens needs a known frame size")
            k = a or 1.0
            out.append(f"lenscorrection=k1={-0.08 * k:.3f}:k2={-0.02 * k:.3f},scale={int(w * 1.06) // 2 * 2}:-2,"
                       f"crop={w}:{h},vignette=PI/5")
        elif name in ("stabilize", "lut"):
            die(f"'{name}' is resolved per layer by the renderer - put it in a layer's fx")
        elif name == "glow":
            p = f"{label}g{n}"
            out.append(f"format=gbrp,split[{p}a][{p}b];[{p}b]gblur=sigma=14[{p}c];"
                       f"[{p}a][{p}c]blend=all_mode=screen:all_opacity={a or 0.45}")
        else:
            die(f"unknown fx '{raw}' (see reference/techniques.md)")
    return out


def ramp_segments(keys, out_len: float, step: float = 0.1, max_segs: int = 40) -> list[tuple[float, float, float]]:
    """Speed ramp keyframes [[shot_time, speed], ...] -> piecewise segments (out_start, in_start, speed),
    speeds linearly interpolated every `step` s; last element is (out_len, in_total, 0)."""
    step = max(step, out_len / max_segs)  # keep the nested setpts expression small
    keys = sorted((float(t), float(s)) for t, s in keys)
    if keys[0][0] > 0:
        keys.insert(0, (0.0, keys[0][1]))

    def speed_at(t):
        for (t0, s0), (t1, s1) in zip(keys, keys[1:]):
            if t0 <= t < t1:
                return s0 + (s1 - s0) * (t - t0) / (t1 - t0)
        return keys[-1][1]

    segs, t, src = [], 0.0, 0.0
    while t < out_len - 1e-6:
        dt = min(step, out_len - t)
        sp = max(0.05, speed_at(t + dt / 2))
        segs.append((t, src, sp))
        t += dt
        src += dt * sp
    segs.append((out_len, src, 0.0))
    return [(round(a, 4), round(b, 4), round(c, 4)) for a, b, c in segs]


def velocity_keys(beats: list[float], out_len: float, slow: float = 0.35, fast: float = 2.2) -> list[list[float]]:
    """Velocity edit: slow motion right on each beat, fast between beats (the TikTok "velocity" look)."""
    keys = [[0.0, fast]]
    for b in beats:
        if 0.05 < b < out_len - 0.05:
            keys += [[max(0.0, b - 0.16), fast], [max(0.0, b - 0.02), slow], [min(out_len, b + 0.14), slow]]
    keys.append([out_len, fast])
    return sorted(keys)


def ramp_expr(segs) -> str:
    """setpts expression mapping input time T -> output time for ramp_segments()."""
    body = segs[:-1]
    o, i, s = body[-1]
    e = f"{o}+(T-{i})/{s}"
    for (o, i, s), (_, i_next, _) in zip(reversed(body[:-1]), reversed(body[1:])):
        e = f"if(lt(T,{i_next}),{o}+(T-{i})/{s},{e})"
    return e


CAMERA_MOVES = {  # (from, to) as [centre x, centre y, zoom] - zoom 1 = the cover-fitted frame
    "push": ([0.5, 0.5, 1.0], [0.5, 0.5, 1.22]), "pull": ([0.5, 0.5, 1.22], [0.5, 0.5, 1.0]),
    "pan-left": ([0.64, 0.5, 1.3], [0.36, 0.5, 1.3]), "pan-right": ([0.36, 0.5, 1.3], [0.64, 0.5, 1.3]),
    "pan-up": ([0.5, 0.64, 1.3], [0.5, 0.36, 1.3]), "pan-down": ([0.5, 0.36, 1.3], [0.5, 0.64, 1.3]),
    "drift": ([0.47, 0.52, 1.08], [0.53, 0.48, 1.14]),
}


def camera_path(ly: dict):
    """Virtual camera on a still (or video): `camera: push|pull|pan-left|pan-right|pan-up|pan-down|drift`,
    `camera: {detail: [x, y, zoom]}` (wide -> into a detail), `camera: {from: [x, y, z], to: [x, y, z]}`.
    The old `zoom: in|out` maps to push / pull. Returns (from, to, ease) or None."""
    cam = ly.get("camera")
    if cam is None and ly.get("zoom") in ("in", "out"):
        amt = float(ly.get("zoom_amount", 0.12))
        a, b = [0.5, 0.5, 1.0], [0.5, 0.5, 1.0 + amt]
        return (a, b, False) if ly["zoom"] == "in" else (b, a, False)
    if not cam:
        return None
    if isinstance(cam, str):
        if cam not in CAMERA_MOVES:
            die(f"camera '{cam}' - one of {sorted(CAMERA_MOVES)} or {{detail: [x, y, zoom]}} / {{from: .., to: ..}}")
        a, b = CAMERA_MOVES[cam]
        return list(a), list(b), True
    if "detail" in cam:  # start half-way towards the detail: short shots must already read as that detail
        x, y, z = (float(v) for v in (list(cam["detail"]) + [2.0])[:3])
        return [0.5 + (x - 0.5) * 0.6, 0.5 + (y - 0.5) * 0.6, 1 + (z - 1) * 0.45], [x, y, z], cam.get("ease", True)
    return [float(v) for v in cam["from"]], [float(v) for v in cam["to"]], cam.get("ease", True)


def camera_focus(ly: dict):
    """Crop anchor for a camera move: with anchor = the target point, that point keeps the same relative position in
    the cropped frame, so `detail: [0.9, 0.7]` on a square poster in 9:16 really ends on the right-hand detail."""
    cam = camera_path(ly)
    if not cam or ly.get("camera") is None:
        return None
    (x0, y0, _), (x1, y1, _), _ = cam
    if isinstance(ly["camera"], dict) and "detail" in ly["camera"]:
        return [x1, y1]
    return [round((x0 + x1) / 2, 3), round((y0 + y1) / 2, 3)]


def camera_zoompan(cam, w: int, h: int, frames: int, fps: int, zscale: float = 1.0) -> str:
    """zoompan along the camera path (input must be the cover-fitted frame at 2x); `zscale` exaggerates the zoom
    change (parallax foreground)."""
    (x0, y0, z0), (x1, y1, z1), ease = cam
    z1 = z0 + (z1 - z0) * zscale
    p = f"min(on/{max(1, frames - 1)},1)"
    e = f"({p}*{p}*(3-2*{p}))" if ease else p
    z = f"{z0}+({z1 - z0:.4f})*{e}"
    cx, cy = f"({x0}+({x1 - x0:.4f})*{e})", f"({y0}+({y1 - y0:.4f})*{e})"
    return (f"zoompan=z='{z}':x='max(0,min(iw-iw/zoom,iw*{cx}-iw/zoom/2))':"
            f"y='max(0,min(ih-ih/zoom,ih*{cy}-ih/zoom/2))':d=1:s={w}x{h}:fps={fps}")


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
        self._lock = threading.Lock()
        self.color = {}          # layer key -> colour stats (sb.color_match)
        self.color_target = None
        self.dir = prj.build / mode
        (self.dir / "shots").mkdir(parents=True, exist_ok=True)
        (self.dir / "labels").mkdir(exist_ok=True)
        self.font = self._font()

    @staticmethod
    def _sync_fonts(dst: Path):
        """Font pack + downloaded Google Fonts -> build/fonts (libass reads it via fontsdir)."""
        dst.mkdir(parents=True, exist_ok=True)
        for f in list(LY.FONTS_DIR.glob("*.ttf")) + list(FT.GF_DIR.glob("*.ttf")):
            if not (dst / f.name).exists():
                shutil.copy(f, dst / f.name)

    def _font(self) -> str:
        fonts = self.dir / "fonts"
        fonts.mkdir(exist_ok=True)
        self._sync_fonts(fonts)
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
    def add_layer(self, args: list, graph: list, shot_id: str, idx: int, ly: dict, w: int, h: int, need: float,
                  contain: bool = False) -> str:
        """Append one layer's inputs + filter statements; returns its output label."""
        a, chain, lab, pre = self.layer(shot_id, idx, ly, w, h, need, contain)
        n_in = args.count("-i")
        args += a
        head = f"[{n_in}:v]"
        if pre:  # generated background: multi-statement graph with [INk] = its k-th input
            graph += [re.sub(r"\[IN(\d+)\]", lambda m: f"[{n_in + int(m.group(1))}:v]", st) for st in pre]
            head = f"[{lab}g]"
        graph.append(head + ",".join(chain) + f"[{lab}]")
        return lab

    def layer(self, shot_id: str, idx: int, ly: dict, w: int, h: int, need: float,
              contain: bool = False, extra_fx: list | None = None):
        sid = ly.get("src")
        f = self.p.source_file(sid) if sid else None
        lab = f"{shot_id}l{idx}".replace("-", "_")
        speed = float(ly.get("speed", 1.0))
        chain: list[str] = []
        spec = self.p.gen_spec(sid)
        pre: list[str] = []
        fx_list = [self._resolve_fx(x) for x in list(ly.get("fx") or []) + list(extra_fx or [])]
        stab = next((x for x in fx_list if str(x).split(":")[0] == "stabilize"), None)
        fx_list = [x for x in fx_list if str(x).split(":")[0] != "stabilize"]
        cm = None
        span = None if spec else self._layer_span(sid, ly, need)
        if span and self.color_target is not None and ly.get("match") is not False:
            st = self.color.get(FG.key(FG.file_key(span[0]), round(span[1], 2), round(span[2], 2)))
            cm = FG.match_filter(st, self.color_target, float(self.p.sb.get("color_match") or 0) if
                                 not isinstance(self.p.sb.get("color_match"), bool) else 0.6)
        if span and ly.get("upscale"):  # AI upscale (Real-ESRGAN) of exactly the part this shot uses
            binp = FG.realesrgan_bin(SKILL_DIR)
            if binp is None:
                print(f"[mv] WARN {shot_id}: upscale skipped - Real-ESRGAN not installed (mv doctor --install upscale)")
            else:
                uf, ust, ud, img = span
                dst = self.dir / "upscaled" / f"{FG.key(FG.file_key(uf), ust, ud)}{'.png' if img else '.mp4'}"
                dst.parent.mkdir(parents=True, exist_ok=True)
                with self._lock:
                    print(f"[mv] upscaling {sid} for {shot_id} ...")
                    f = FG.upscale_clip(binp, uf, ust, ud + 0.6, self.fps, dst, image=img)
                ly = {**ly, "in": 0, "_upscaled": True}
        if spec:
            f = None
            try:
                args, pre = GEN.build(spec, w, h, self.fps, need, self.dir / "gen", f"{lab}g",
                                      self.p.sb.get("palette"), self.p.sb.get("accent"))
            except (ValueError, RuntimeError) as e:
                die(f"{shot_id}: source {sid}: {e}")
        elif f is not None and f.suffix.lower() in IMAGE_EXT and ly.get("parallax") and not contain:
            args, pre = self._parallax(f, ly, w, h, need, lab, shot_id)
            spec = "parallax"  # prebuilt like a generated source: the chain below only finishes it
        elif f is not None and f.suffix.lower() in IMAGE_EXT:
            args = ["-loop", "1", "-framerate", str(self.fps), "-t", f"{need:.3f}", "-i", str(f)]
        elif f is not None:
            start = 0.0 if ly.get("_upscaled") else max(0.0, tsec(ly.get("in", 0)) - self.p.source_offset(sid))
            ramp = ramp_segments(ly.get("ramp"), need, max_segs=int(ly.get("_ramp_segs", 40))) if ly.get("ramp") else None
            src_need = (ramp[-1][1] if ramp else need * speed) + 0.5
            args = ["-stream_loop", "-1", "-ss", f"{start:.3f}", "-t", f"{src_need:.3f}", "-i", str(f)]
            chain.append("setpts=PTS-STARTPTS")
            if stab:  # vidstab: detect pass on the exact frames (cached), transform here, before any re-timing
                k = float(str(stab).partition(":")[2] or 1)
                trf = self.dir / "stab" / f"{FG.key(FG.file_key(f), round(start, 2), round(src_need, 2))}.trf"
                if FG.stabilize_pass(f, start, src_need, trf):
                    chain.append(f"vidstabtransform=input=stab/{trf.name}:smoothing={int(20 * k)}:optzoom=1:"
                                 f"zoomspeed=0.2:interpol=bicubic,unsharp=5:5:0.5")
                else:
                    chain.append("deshake=rx=32:ry=32")
            chain.append(f"setpts='({ramp_expr(ramp)})/TB'" if ramp else f"setpts=PTS/{speed}")
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
        focus = ly.get("focus")
        if focus is None and not contain:
            focus = camera_focus(ly)  # anchor the crop on the camera's target so edge details stay reachable
        if focus in ("auto", "track") and span and not span[3] and not contain:
            fit = self._tracked_cover(f, span, ly, w, h, need, speed)
        else:
            fit = f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos" if contain else \
                cover(w, h, focus if isinstance(focus, list) else None)
        if cm:
            fit += "," + cm
        if spec:
            fit = f"scale={w}:{h}"
        if f is not None and ly.get("smooth") and (speed < 1 or ly.get("ramp")):
            # optical-flow frame interpolation for silky slow motion (CPU heavy; scale first to keep it bearable)
            chain += [fit, f"minterpolate=fps={self.fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1", f"fps={self.fps}"]
        else:
            chain += [f"fps={self.fps}", fit]
        fr = ly.get("freeze")
        if fr:  # [at, duration] in shot seconds: hold that frame, then continue
            at, hold = float(fr[0]), float(fr[1])
            chain += [f"loop=loop={max(1, int(hold * self.fps))}:size=1:start={int(at * self.fps)}",
                      f"setpts=N/{self.fps}/TB"]
        cam = None if (contain or spec) else camera_path(ly)
        if cam:
            chain += [f"scale={2 * w}:{2 * h}", camera_zoompan(cam, w, h, max(1, int(need * self.fps)), self.fps)]
        chain += fx_filters(fx_list, lab, w, h, self.fps)
        if f is None and not spec:
            chain.append(label_filter)  # after zoom/fx so the card text stays readable
        chain += [f"tpad=stop_mode=clone:stop_duration={need:.3f}", f"trim=duration={need:.3f}",
                  "setpts=PTS-STARTPTS", "setsar=1", "format=gbrp"]
        return args, chain, lab, pre

    def _velocity(self, ly: dict, s: float, e: float, need: float, sh: dict) -> dict:
        """`ramp: beat` (or shot `velocity: true`) -> ramp keys from the beats inside the shot."""
        if not isinstance(ly, dict) or ly.get("blend") or not (ly.get("ramp") == "beat" or (sh.get("velocity") and not ly.get("ramp"))):
            return ly
        v = sh.get("velocity") if isinstance(sh.get("velocity"), dict) else {}
        beats = self.p.beats_in(s, e, int(v.get("every", sh.get("beat_every", 1))))
        keys = velocity_keys(beats, need, float(v.get("slow", 0.35)), float(v.get("fast", 2.2)))
        return {**ly, "ramp": keys, "_ramp_segs": 120}

    def _parallax(self, f: Path, ly: dict, w: int, h: int, need: float, lab: str, shot_id: str):
        """2.5D: a depth model separates the foreground; it zooms ~2x faster than the background (push-in only, so
        the foreground always covers its own original position - no holes)."""
        mask = self.p.build / "depth" / f"{FG.key(FG.file_key(f))}.png"
        try:
            with self._lock:
                FG.depth_mask(f, mask, float(ly.get("parallax_fg", 0.35)))
        except RuntimeError as e:
            die(f"{shot_id}: {e}")
        cam = camera_path(ly) or ([0.5, 0.5, 1.0], [0.5, 0.5, 1.0 + float(ly.get("parallax", 0.12)
                                                                         if not isinstance(ly.get("parallax"), bool) else 0.12)], True)
        frames = max(1, int(need * self.fps))
        k = float(ly.get("parallax_depth", 2.2))
        fit = cover(2 * w, 2 * h, ly.get("focus") if isinstance(ly.get("focus"), list) else camera_focus(ly))
        args = ["-loop", "1", "-framerate", str(self.fps), "-t", f"{need:.3f}", "-i", str(f),
                "-loop", "1", "-framerate", str(self.fps), "-t", f"{need:.3f}", "-i", str(mask)]
        pre = [f"[IN0]fps={self.fps},{fit},split[{lab}pa][{lab}pb]",
               f"[{lab}pa]{camera_zoompan(cam, w, h, frames, self.fps)}[{lab}pbg]",
               f"[{lab}pb]{camera_zoompan(cam, w, h, frames, self.fps, k)}[{lab}pfg0]",
               f"[IN1]format=gray,fps={self.fps},{fit},format=yuv420p,{camera_zoompan(cam, w, h, frames, self.fps, k)},"
               f"format=gray[{lab}pm]",
               f"[{lab}pfg0][{lab}pm]alphamerge[{lab}pfg]",
               f"[{lab}pbg][{lab}pfg]overlay=format=auto:shortest=1,format=yuv420p[{lab}g]"]
        return args, pre

    def _resolve_fx(self, x):
        """`lut:<file.cube>[@0.7]` -> a raw lut3d filter with the LUT copied next to the graph."""
        if isinstance(x, str) and x.startswith("lut:"):
            try:
                filt, amt = FG.lut_filter(x[4:], self.dir / "luts", self.p.root)
            except FileNotFoundError as e:
                die(str(e))
            return ("__raw__", filt, amt)
        return x

    def _tracked_cover(self, f: Path, span, ly: dict, w: int, h: int, need: float, speed: float) -> str:
        """focus: auto - a crop window that follows the subject (faces, else motion) through the shot."""
        _, start, d, _ = span
        tf = self.p.build / "track" / f"{FG.key(FG.file_key(f), round(start, 2), round(d, 2))}.json"
        if tf.exists():
            track = [tuple(x) for x in json.loads(tf.read_text(encoding="utf-8"))]
        else:
            track = FG.track_subject(f, start, max(d, 0.5))
            tf.parent.mkdir(parents=True, exist_ok=True)
            tf.write_text(json.dumps(track), encoding="utf-8")
        ex, ey = FG.track_expr(track, 0, speed), FG.track_expr(track, 1, speed)
        # window centred on the subject: anchor = clip((centre - half window) / free space)
        return (f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
                f"crop={w}:{h}:'max(0,min(in_w-{w},in_w*({ex})-{w}/2))':'max(0,min(in_h-{h},in_h*({ey})-{h}/2))'")

    def transition_filters(self, sid: str, kind: str, d: float, pk: str, pd: float, dur: float, need: float) -> list[str]:
        """zoomblur / spin / burn: half of the move at the end of the outgoing shot, half at the start of the next."""
        W, H, fps = self.W, self.H, self.fps
        out_w = kind in ("zoomblur", "spin", "burn")
        in_w = pk in ("zoomblur", "spin", "burn")
        if not (out_w or in_w):
            return []
        f = []
        t0 = dur - d
        zt, rt, blur, burn = [], [], [], []
        if out_w:
            win = f"clip((on-{int(t0 * fps)})/{max(1, int(d * fps))},0,1)"
            twin = f"clip((t-{t0:.3f})/{d:.3f},0,1)"
            if kind in ("zoomblur", "spin"):
                zt.append(f"{1.0 if kind == 'zoomblur' else 0.5}*pow({win},2)")
                blur.append(f"gt(t,{t0 + d * 0.3:.3f})")
            if kind == "spin":
                rt.append(f"0.45*pow({twin},2)")
            if kind == "burn":  # blend expressions use T for time
                burn.append(twin.replace("(t-", "(T-"))
        if in_w:
            win = f"clip(1-on/{max(1, int(pd * fps))},0,1)"
            twin = f"clip(1-t/{pd:.3f},0,1)"
            if pk in ("zoomblur", "spin"):
                zt.append(f"{1.0 if pk == 'zoomblur' else 0.5}*pow({win},2)")
                blur.append(f"lt(t,{pd * 0.7:.3f})")
            if pk == "spin":
                rt.append(f"-0.45*pow({twin},2)")
            if pk == "burn":
                burn.append(twin.replace("1-t/", "1-T/"))
        if zt:
            f += [f"scale={2 * W}:{2 * H}",
                  f"zoompan=z='1+{'+'.join(zt)}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps}"]
        if rt:
            f.append(f"rotate=a='{'+'.join(rt)}':c=black")
        if blur:
            f.append(f"gblur=sigma={max(4, W // 60)}:enable='{'+'.join(blur)}'")
        if burn:
            p = f"{sid}b"
            k = f"max({','.join(burn)},0)" if len(burn) > 1 else burn[0]
            f.append(f"format=gbrp[{p}a];gradients=s={W}x{H}:c0=0xfff4d6:c1=0xff9a3c:c2=0xff3a10:nb_colors=3:"
                     f"x0={W // 3}:y0=0:x1={W}:y1={H}:speed=0.08:rate={fps},format=gbrp,gblur=sigma={max(10, W // 30)}[{p}g];"
                     f"[{p}a][{p}g]blend=all_expr='A+(255-A)*B/255*{k}*1.4':shortest=1")
        return f

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
        blob = json.dumps([sh, prev_tr, files, self.W, self.H, self.fps, self.mode, self.p.sources, beats,
                           self.p.sb.get("palette"), self.p.sb.get("accent"), self.p.sb.get("color_match"),
                           round(self.color_target or 0, 3), ENGINE_HASH], sort_keys=True, default=str)
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
        layers = [self._velocity(ly, s, e, need, sh) for ly in layers]
        base = [ly for ly in layers if not ly.get("blend")]
        over = [ly for ly in layers if ly.get("blend")]
        base += [{"src": None, "note": "(empty slot)"}] * max(0, len(slots) - len(base))
        over = base[len(slots):] + over  # extra un-blended layers become 'normal' overlays
        base = base[: len(slots)]

        args: list[str] = []
        graph: list[str] = []
        labels = []
        for k, ly in enumerate(base):
            labels.append(self.add_layer(args, graph, sid, k, ly, *slots[k], need))

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
            lab = self.add_layer(args, graph, sid, 9, base[0], cw, ch, need)
            off, sg = max(4, W // 90), max(8, W // 40)
            bg = f"{labels[0]}bg"
            graph.append(f"[{labels[0]}]scale={even(W / 8)}:{even(H / 8)},gblur=sigma=5,scale={W}:{H},format=yuv444p,"
                         f"eq=brightness=-0.16:saturation=1.25,"
                         f"drawbox=x={px + off}:y={py + off * 2}:w={cw}:h={ch}:color=black@0.6:t=fill,"
                         f"gblur=sigma={sg},format=gbrp[{bg}]")
            graph.append(f"[{bg}][{lab}]overlay=x={px}:y={py}:format=gbrp:shortest=1[stk]")
            cur = "stk"
        elif layout == "fit_blur":  # whole source frame centred, its own blurred copy fills the rest
            lab = self.add_layer(args, graph, sid, 9, base[0], W, H, need, contain=True)
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
            lab = self.add_layer(args, graph, sid, 10 + k, ly, W, H, need)
            mode = ly.get("blend", "normal")
            op = float(ly.get("opacity", 0.4))
            graph.append(f"[{cur}][{lab}]blend=all_mode={mode}:all_opacity={op}[ov{k}]")
            cur = f"ov{k}"

        post = []
        scam = camera_path({"camera": sh["camera"]}) if sh.get("camera") else None
        if scam:  # shot-level camera: moves the whole composition (e.g. a full poster on its blurred background)
            post += [f"scale={2 * W}:{2 * H}", camera_zoompan(scam, W, H, max(1, int(need * fps)), fps)]
        post += fx_filters(sh.get("fx"), f"{sid}s", W, H, fps)
        post += self.beat_filters(sh, s, e, need)
        pk, _, pd = parse_transition(self.p.shots[i - 1].get("transition", "cut")) if i > 0 else ("cut", "", 0)
        glitch = ("rgbashift=rh=-22:bh=22:gv=6:enable='{w}',noise=alls=45:allf=t:enable='{w}',"
                  "hue=h=70:s=1.6:enable='{w}'")
        if pk == "flash":
            post.append(f"fade=t=in:st=0:d={pd}:color=white")
        elif pk == "fadeblack":
            post.append(f"fade=t=in:st=0:d={pd / 2:.3f}")
        elif pk == "glitch":
            post.append(glitch.format(w=f"lt(t,{pd:.3f})"))
        if kind == "glitch":
            post.append(glitch.format(w=f"gt(t,{dur - d:.3f})"))
        post += self.transition_filters(sid, kind, d, pk, pd, dur, need)
        if i == 0 and sh.get("fade_in", True):
            post.append("fade=t=in:st=0:d=0.4")
        if kind == "fadeblack":
            post.append(f"fade=t=out:st={dur - d / 2:.3f}:d={d / 2:.3f}")
        if i == len(self.p.shots) - 1:
            fo = float(self.p.sb.get("fade_out", 1.0))
            if fo > 0:
                post.append(f"fade=t=out:st={max(0, dur - fo):.3f}:d={fo}")
        post += [f"trim=duration={need:.3f}", "setpts=PTS-STARTPTS", "setsar=1", "format=yuv420p"]
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
        base_font = "Be Vietnam Pro" if LY.has_font("Be Vietnam Pro") else "Arial"
        font = FT.resolve(sb.get("font"), base_font)
        display = FT.resolve(sb.get("display_font"), "Anton" if LY.has_font("Anton") else font)
        pc = sb.get("poster") or {}
        tfont = FT.resolve(pc.get("title_font"), font)
        afont = FT.resolve(pc.get("artist_font"), font)
        self._sync_fonts(self.dir / "fonts")
        lines_all = self.p.lyric_lines()
        text = "".join(str(l.get("text", "")) + str(l.get("sub", "")) for l in lines_all)
        typo = sb.get("typo") or {}
        if typo.get("upper"):
            text = text.upper()
        for nm in {font, display}:
            miss = FT.missing_glyphs(nm, text) if text else []
            if miss:
                print(f"[mv] WARN: font '{nm}' lacks {''.join(miss[:20])} - those characters will fall back to another "
                      f"font. Pick a font covering the lyric language (mv fonts list --lang ...).")
        safe = PL.safe_zone(sb["platforms"], str(sb.get("format", "9:16"))) if sb.get("platforms") else None
        aw = LY.AssWriter(W, H, font, display, sb.get("accent", "#FFD24D"), s0, t_end, typo, tfont, afont, safe)

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
                  sb.get("lyric_highlight", "line"), sb.get("lyric_anim", default_anim),
                  lead=float(sb.get("lyric_lead", 0.15)))
        if sb.get("lyric_beat") and self.p.beats:
            lb = sb["lyric_beat"]
            mode = lb if isinstance(lb, str) else (lb.get("mode", "pulse") if isinstance(lb, dict) else "pulse")
            every = int(lb.get("every", 2)) if isinstance(lb, dict) else 2
            aw.beat_react([b for i, b in enumerate(self.p.beats) if i % every == 0], mode)
        tc = sb.get("title_card")
        if tc:
            a0 = tsec(tc.get("start", s0 + 0.8))
            aw.title_card(tc, a0, a0 + float(tc.get("dur", 4)))
        ec = sb.get("end_card")
        if ec:
            d = float(ec.get("dur", 3))
            a0 = tsec(ec["start"]) if "start" in ec else t_end - d - 0.2
            aw.title_card(ec, a0, a0 + d, kind="end")

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
        vz = self.p.sb.get("visualizer")
        if not geom and not vz:
            return cur, None
        acc = LY.ff_color(self.p.sb.get("accent", "#FFD24D"))
        alabel = None
        op = 1.0
        if geom:
            vcol = LY.ff_color(pc.get("visualizer_color", "#FFFFFF"))
            vis = pc.get("visualizer", "wave")
            vx, vy, vw, vh = geom["vis"]
        else:  # top-level `visualizer:` - audio spectrum / wave on any video (lyric videos, "linear spectrum")
            vz = vz if isinstance(vz, dict) else {"type": str(vz)}
            vis = vz.get("type", "bars")
            vcol = LY.ff_color(vz.get("color", self.p.sb.get("accent", "#FFFFFF")))
            op = float(vz.get("opacity", 0.85))
            W, H = self.W, self.H
            fx0, fy0, fx1, fy1 = vz.get("area") or ([0.08, 0.80, 0.92, 0.855] if H > W else [0.06, 0.86, 0.94, 0.95])
            vx, vy, vw, vh = int(W * fx0), int(H * fy0), even(W * (fx1 - fx0)), even(H * (fy1 - fy0))
        if vis != "none" and n_audio is not None:
            graph.append(f"[{n_audio}:a]asplit=2[amain][avis]")
            if vis == "bars":
                graph.append(f"[avis]showfreqs=s={vw}x{vh}:mode=bar:ascale=sqrt:fscale=log:colors={vcol}:"
                             f"win_size=1024,fps={self.fps},format=rgba,colorkey=black:0.1:0.0[wv]")
            else:
                graph.append(f"[avis]showwaves=s={vw}x{vh}:mode=cline:rate={self.fps}:colors={vcol}:"
                             f"scale=sqrt,format=rgba[wv]")
            if op < 1:
                graph[-1] = graph[-1].replace("[wv]", f",colorchannelmixer=aa={op}[wv]")
            graph.append(f"[{cur}][wv]overlay=x={vx}:y={vy}:eof_action=pass[pv1]")
            cur, alabel = "pv1", "amain"
        if geom and pc.get("progress", True):
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
            graph.append(f"[{i}:v]fps={self.fps},settb=AVTB,setpts=PTS-STARTPTS,setsar=1[n{i}]")
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
        graph.append(f"[{acc}]subtitles=captions.ass:fontsdir=fonts,trim=duration={total:.3f}[subd]")
        acc = "subd"
        extra: list[str] = []  # inputs after the audio, so the audio keeps its index
        for i, sh in enumerate(p.shots):  # behind: true -> the person is cut out and laid back over the text
            if not sh.get("behind"):
                continue
            matte = FG.person_matte(shot_files[i], self.dir / "matte" / f"{i:03d}_{sh['id']}.mp4", self.fps, self.W, self.H)
            n_v = len(shot_files) + (1 if a_args else 0) + extra.count("-i")
            extra += ["-i", str(shot_files[i].relative_to(self.dir)), "-i", str(matte.relative_to(self.dir))]
            a0 = tsec(sh["start"]) - s0
            graph.append(f"[{n_v}:v][{n_v + 1}:v]alphamerge,setpts=PTS+{a0:.3f}/TB[bh{i}]")
            graph.append(f"[{acc}][bh{i}]overlay=eof_action=pass:enable='between(t,{a0:.3f},{tsec(sh['end']) - s0:.3f})'[bo{i}]")
            acc = f"bo{i}"
        graph.append(f"[{acc}]format=yuv420p[vout]")
        if n_a is not None:
            fo = float(p.sb.get("audio_fade_out", 0))
            af = f"afade=t=out:st={max(0, total - fo):.3f}:d={fo}" if fo > 0 else "anull"
            fi = float(p.sb.get("audio_fade_in", 0) or 0)
            if fi > 0:
                af = f"afade=t=in:st=0:d={fi}," + af
            if p.sb.get("loudness") is not None:  # only for mixes far off the platforms' ~-14 LUFS target
                af += f",loudnorm=I={float(p.sb['loudness'])}:TP=-1:LRA=11"
            graph.append(f"[{a_src or f'{n_a}:a'}]{af}[aout]")
            a_map = ["-map", "[aout]", "-c:a", "aac", "-b:a", "256k", "-ar", "48000"]
        fscript = self.dir / "assemble.filter"
        fscript.write_text(";\n".join(graph), encoding="utf-8")
        enc = self.encoder_args()
        p.out.mkdir(exist_ok=True)
        name = f"{p.sb.get('slug') or p.root.name}_{self.mode}_{p.sb.get('format', '9:16').replace(':', 'x')}.mp4"
        out = p.out / name
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args, *a_args, *extra,
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

    def _layer_span(self, sid: str, ly: dict, need: float):
        """(file, start in file, seconds of source used, is image) for a real footage layer, else None."""
        f = self.p.source_file(sid) if sid else None
        if f is None or self.p.gen_spec(sid):
            return None
        if f.suffix.lower() in IMAGE_EXT:
            return f, 0.0, need, True
        start = max(0.0, tsec(ly.get("in", 0)) - self.p.source_offset(sid))
        return f, start, need * float(ly.get("speed", 1.0) or 1.0), False

    def prepare_color(self):
        """color_match: measure every footage layer once (3 tiny frames each, cached) and aim all of them at the
        edit's median exposure with a neutral white balance."""
        if not self.p.sb.get("color_match"):
            return
        cache = FG.Cache(self.p.build / "color_stats.json")
        for sh in self.p.shots:
            dur = tsec(sh["end"]) - tsec(sh["start"])
            for ly in sh.get("layers") or []:
                if not isinstance(ly, dict) or ly.get("match") is False:
                    continue
                span = self._layer_span(ly.get("src"), ly, dur)
                if span:
                    f, st, d, img = span
                    k = FG.key(FG.file_key(f), round(st, 2), round(d, 2))
                    self.color[k] = cache.get(k, lambda: FG.color_stats(f, st, d, img))
        ys = sorted(v["y"] for v in self.color.values() if v)
        if ys:
            self.color_target = float(self.p.sb.get("color_target") or ys[len(ys) // 2])
            print(f"[mv] colour match: {len(ys)} layers -> exposure {self.color_target:.2f}")

    def run_all(self) -> Path:
        n = len(self.p.shots)
        self.prepare_color()
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
        "# Brief\n\n- Song / artist:\n- Audio file: audio/\n- Platform & aspect: 9:16 (TikTok/Reels/Shorts) | 16:9 (YouTube)\n"
        "- Length: full song / 60 s cut (which part?)\n- Main emotion:\n- Scene ideas per section (intro/verse/chorus/bridge/outro):\n\n"
        "## Lyrics\n\n(see lyrics.txt)\n", encoding="utf-8")
    (root / "lyrics.txt").write_text(
        "# Lyrics - one SUNG line per text line, in singing order; write repeats out in full (no 'Chorus x2').\n"
        "# [Section] lines mark sections. 'original line | translation' adds a sub-line (bilingual).\n"
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
    import style as ST
    res["style"] = ST.guess(ST.features(y, sr, tempo, [float(o) for o in onset], dur))
    if getattr(a, "genre_model", False):  # learned reading (AudioSet AST) on the loudest section + two more windows
        top = max(sections, key=lambda x: x["energy"]) if sections else {"start": 0, "end": dur}
        mid = (top["start"] + top["end"]) / 2
        wins = [(max(0, mid - 5), mid + 5), (dur * 0.25, dur * 0.25 + 10), (dur * 0.6, dur * 0.6 + 10)]
        try:
            res["style"]["model"] = ST.classify(y, sr, [(a0, min(b0, dur)) for a0, b0 in wins])
        except (RuntimeError, OSError) as e:
            print(f"[mv] genre model skipped: {e}")
    if a.lyrics:
        res["lyrics_auto"] = whisper_words(audio, a.model, a.language)
    (root / "analysis.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[mv] duration {fmt_t(dur)}  tempo ~{tempo:.1f} bpm  beats {len(beats)}  sections {len(sections)}")
    st = res["style"]
    print(f"[mv] style hints: {', '.join(g['genre'] + ' ' + str(g['score']) for g in st['genres'])} · mood {st['mood']} "
          f"· {st['why']}" + (f" · model: {', '.join(g['genre'] for g in st['model']['genres'])}"
                              f" {', '.join(m for m, _ in st['model']['moods'])}" if st.get("model") else ""))
    for x in sections:
        print(f"     {fmt_t(x['start'])} - {fmt_t(x['end'])}  energy {x['energy_rel']:.2f}  {x['guess']}")
    if a.lyrics:
        segs = res["lyrics_auto"]
        print(f"[mv] whisper: {len(segs)} segments, {sum(len(x.get('words') or []) for x in segs)} words"
              + ("" if getattr(a, "verbose", False) else " (--verbose prints them)"))
        for seg in segs if getattr(a, "verbose", False) else []:
            print(f"     [{fmt_t(seg['start'])}-{fmt_t(seg['end'])}] {seg['text']}")
    print(f"[mv] wrote {root / 'analysis.json'}")


def _expose_pip_cuda_libs():
    """Make pip-installed NVIDIA libs (mv doctor --install whisper-cuda) visible to CTranslate2."""
    import site
    roots = [Path(p) / "nvidia" for p in site.getsitepackages() + [site.getusersitepackages()]]
    for r in (r for r in roots if r.exists()):
        if os.name == "nt":
            for b in r.glob("*/bin"):
                os.add_dll_directory(str(b))
                os.environ["PATH"] = str(b) + os.pathsep + os.environ.get("PATH", "")
        else:
            import ctypes
            for so in sorted(r.glob("*/lib/lib*.so*")):
                if any(k in so.name for k in ("cublas", "cudnn")):
                    try:
                        ctypes.CDLL(str(so), mode=ctypes.RTLD_GLOBAL)
                    except OSError:
                        pass


def whisper_words(audio: Path, model: str, lang: str):
    from faster_whisper import WhisperModel
    prof = DR.load_profile()
    if model == "auto":
        model = prof.get("whisper_model", "medium")
    device = prof.get("whisper_device", "auto")
    if device != "cpu":
        _expose_pip_cuda_libs()
    print(f"[mv] whisper {model} on {device} (first run downloads the model) ...")
    try:
        wm = WhisperModel(model, device=device, compute_type="auto")
        segs, _ = wm.transcribe(str(audio), language=lang, word_timestamps=True, vad_filter=True)
        segs = list(segs)
    except (RuntimeError, OSError, ValueError) as e:  # missing CUDA libs etc. -> CPU fallback
        if device == "cpu":
            raise
        print(f"[mv] GPU whisper failed ({str(e)[:120]}) - falling back to CPU int8. Fix with: mv doctor")
        wm = WhisperModel(model if model != "large-v3" else "medium", device="cpu", compute_type="int8")
        segs, _ = wm.transcribe(str(audio), language=lang, word_timestamps=True, vad_filter=True)
    out = []
    for s in segs:
        out.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip(),
                    "words": [{"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)} for w in (s.words or [])]})
    return out


SKILL_DIR = Path(__file__).resolve().parent.parent
DEMOS = ["story", "blur", "lyric-poster", "lyric-styles", "pro", "genre-mv", "lyric-kinetic", "lyric-template"]
DEMO_ASSETS = {"singer_live": "bars", "A": "bars", "fans_light": "fractal", "B": "fractal",
               "memory_overlay": "photo", "C": "photo", "poster": "poster", "perf": "perf", "story": "fractal",
               "detail": "photo"}
# drum pulse + bass + a melody that never repeats inside 24 s (so `mv sync` has something unique to match)
DEMO_SONG = ("aevalsrc='0.55*sin(2*PI*220*t)*exp(-10*mod(t,0.5))+0.25*sin(2*PI*330*t)*exp(-6*mod(t+0.25,1))"
             "+0.2*sin(2*PI*t*440*pow(2,(mod(3*floor(t*2)*floor(t*2)+5*floor(t*2),13)-6)/12))*exp(-4*mod(t,0.5))'"
             ":s=44100:d=24")


def make_demo_asset(kind: str, dst: Path, title: str = "MÙA HÈ\nCỦA EM"):
    ff = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if kind == "bars":
        run(ff + ["-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=60", "-c:v", "libx264", "-preset", "ultrafast", str(dst)])
    elif kind == "fractal":
        run(ff + ["-f", "lavfi", "-i", "mandelbrot=s=1280x720:r=30", "-t", "40", "-c:v", "libx264", "-preset", "ultrafast", str(dst)])
    elif kind == "perf":  # performance camera: its own audio is the song played back 1.5 s after it started
        song = dst.parent.parent / "audio" / "song.mp3"
        run(ff + ["-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=40", "-i", str(song), "-filter_complex",
                  "[1:a]adelay=1500|1500,apad[a]", "-map", "0:v", "-map", "[a]", "-t", "40",
                  "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(dst)])
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
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", DEMO_SONG,
                 str(root / "audio" / "song.mp3")])
            if name == "lyric-template":  # the one-step lyric video: analyze -> auto (template) -> render
                cmd_analyze(argparse.Namespace(project=str(root), audio=str(root / "audio" / "song.mp3"), lyrics=False,
                                               model="medium", language="vi", sections=None))
                cmd_auto(argparse.Namespace(project=str(root), template="lv-kinetic", theme=None, format="9:16",
                                            audio=None, title="Mùa Hè Của Em", artist="Demo Artist", lang="en",
                                            lines=2, force=True))
            sb = yaml.safe_load((root / "storyboard.yaml").read_text(encoding="utf-8"))
            for sid in sb.get("sources") or {}:
                kind = DEMO_ASSETS.get(sid)
                if kind:
                    ext = ".png" if kind in ("photo", "poster") else ".mp4"
                    make_demo_asset(kind, root / "sources" / f"{sid}{ext}")
            if name != "lyric-template" and (sb.get("genre") or sb.get("lyric_beat") or any(sh.get("beat_fx") or sh.get("velocity") for sh in sb.get("shots") or [])):
                cmd_analyze(argparse.Namespace(project=str(root), audio=None, lyrics=False, model="medium",
                                               language="vi", sections=None))
            if "perf" in (sb.get("sources") or {}):
                cmd_sync(argparse.Namespace(project=str(root), source="perf"))
        cmd_review(argparse.Namespace(project=str(root)))
        cmd_render(argparse.Namespace(project=str(root), mode=a.mode, encoder=a.encoder, jobs=None, force=False))


def cmd_fonts(a):
    try:
        _cmd_fonts(a)
    except (RuntimeError, ValueError, OSError) as e:
        die(str(e))


def _cmd_fonts(a):
    act = a.action
    if act == "pack":
        LY.download_fonts()
        print(f"[mv] fonts in {LY.FONTS_DIR}: " + ", ".join(f for f in LY.FONT_PACK if LY.has_font(f)))
    elif act == "list":
        rows = FT.catalog(a.lang, a.tag)
        for r in rows:
            print(f"  {r['family']:<22} {r['category']:<24} {'italic ' if r['italic'] else '':7} [{r['scripts']}]  {r['tags']}")
        print(f"[mv] {len(rows)} fonts. Any Google Fonts family works too: mv fonts get \"Family:900i\"")
    elif act == "get":
        for spec in a.args:
            e = FT.ensure(spec)
            print(f"[mv] {spec:<24} -> {e['name']}  ({e['path'].name})")
    elif act == "check":
        text = a.text or ""
        if a.project:
            text += "".join(l.get("text", "") for l in Project(a.project).lyric_lines())
        for spec in a.args:
            e = FT.ensure(spec)
            miss = FT.missing_glyphs(e["path"], text)
            print(f"[mv] {spec:<24} {'OK - covers all characters' if not miss else 'MISSING: ' + ' '.join(miss)}")
    elif act == "preview":
        font_preview(a)


def font_preview(a):
    """Render the real lyric text in several candidate fonts over the project's poster/background -> refs/fonts_preview.jpg."""
    root = Path(a.args[0]) if a.args else Path(".")
    sb = yaml.safe_load((root / "storyboard.yaml").read_text(encoding="utf-8")) if (root / "storyboard.yaml").exists() else {}
    specs = [s.strip() for s in (a.fonts or "").split(",") if s.strip()]
    if not specs:
        die('give candidates: --fonts "Kanit:900i,Exo 2:900i,Archivo:900i@125"')
    typo = dict(sb.get("typo") or {})
    sample = a.text
    if not sample and (root / "storyboard.yaml").exists() and sb.get("lyrics_file"):
        ls = Project(root).lyric_lines()
        sample = ls[0]["text"] if ls else None
    sample = sample or sb.get("title") or "The quick brown fox"
    if typo.get("upper"):
        sample = sample.upper()
    W, row_h = 1080, 200
    H = even(150 + len(specs) * row_h + 40)
    out_dir = root / "build" / "fonts_preview"
    Renderer._sync_fonts(out_dir / "fonts")
    slants = []  # "Family:900 +0.2" = preview with a synthetic slant (typo.slant) for upright fonts
    for k, s in enumerate(specs):
        base, _, sl = s.partition(" +")
        specs[k] = base.strip()
        slants.append(float(sl) if sl else float(typo.get("slant", 0) or 0))
    entries = [FT.ensure(s) for s in specs]
    Renderer._sync_fonts(out_dir / "fonts")
    bg = Path(a.bg) if a.bg else None
    if not bg:
        for sid in (sb.get("sources") or {}):
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                if (root / "sources" / f"{sid}{ext}").exists():
                    bg = root / "sources" / f"{sid}{ext}"
                    break
            if bg:
                break
    label_font = "Be Vietnam Pro" if LY.has_font("Be Vietnam Pro") else "Arial"
    col = LY.ass_color(typo.get("color", "#FFFFFF"))
    ocol = LY.ass_color(typo.get("outline_color", "#000000"))
    bord = max(0, round(3 * float(typo.get("outline", 1.0))))
    shad = max(0, round(2 * float(typo.get("shadow", 1.0))))
    sp = typo.get("spacing", 0)
    ev = [f"Dialogue: 0,0:00:00.00,0:00:09.00,lab,,0,0,0,,{{\\an7\\pos(60,48)\\fs40}}Font preview · {LY._esc(sb.get('title', root.name))}"]
    for k, (spec, e) in enumerate(zip(specs, entries)):
        y = 150 + k * row_h
        miss = FT.missing_glyphs(e["path"], sample)
        status = "OK" if not miss else "missing " + " ".join(miss[:8])
        fs = max(40, min(104, int((W - 120) / max(1, len(sample)) / 0.56)))
        fax = f"\\fax{-slants[k]:.3f}" if slants[k] else ""
        label = spec + (f"  (slant {slants[k]})" if slants[k] else "")
        ev.append(f"Dialogue: 0,0:00:00.00,0:00:09.00,lab,,0,0,0,,{{\\an7\\pos(60,{y})}}{k + 1}. {label}   ·   {status}")
        ev.append(f"Dialogue: 0,0:00:00.00,0:00:09.00,s,,0,0,0,,{{\\an7\\q2\\pos(60,{y + 42})\\fn{e['name']}\\fs{fs}{fax}}}{LY._esc(sample)}")
    ass = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "ScaledBorderAndShadow: yes", "",
           "[V4+ Styles]", "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
           "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
           "MarginL, MarginR, MarginV, Encoding",
           f"Style: lab,{label_font},30,&H30FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,7,0,0,0,1",
           f"Style: s,{label_font},90,{col},{col},{ocol},&H78000000,0,0,0,0,100,100,{sp},0,1,{bord},{shad},7,0,0,0,1",
           "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text", *ev]
    (out_dir / "preview.ass").write_text("\n".join(ass) + "\n", encoding="utf-8-sig")
    if bg and bg.exists():
        inp = ["-loop", "1", "-i", str(bg.resolve())]
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=18,"
              f"eq=brightness=-0.32:saturation=1.1,subtitles=preview.ass:fontsdir=fonts")
    else:
        inp = ["-f", "lavfi", "-i", f"color=c=0x15151c:s={W}x{H}"]
        vf = "subtitles=preview.ass:fontsdir=fonts"
    out = root / "refs" / "fonts_preview.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inp, "-vf", vf, "-frames:v", "1", "-q:v", "2",
         str(out.resolve())], cwd=out_dir)
    print(f"[mv] wrote {out}  - open it and compare; set the winner as `font:` (and `display_font:`) in storyboard.yaml")


def cmd_palette(a):
    pal = FT.palette(Path(a.image), a.n)
    print("[mv] main tones (dark -> light): " + "  ".join(pal["main"]))
    print("[mv] vivid accents:              " + ("  ".join(pal["vivid"]) or "none (muted image - use white/black)"))
    print("     accent: one vivid colour (karaoke fill / glow / progress bar); typo.color / outline_color from main tones")


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
    weak = [l for l in out if l.get("match", 1) < 0.5]
    show = out if getattr(a, "verbose", False) else weak[:12]
    if not getattr(a, "verbose", False):
        print(f"[mv] {len(out)} lines, {len(weak)} weakly matched" + (" - spot-check these:" if weak else "")
              + " (--verbose lists every line)")
    for l in show:
        m = f"  (match {l['match']:.0%})" if "match" in l else ""
        print(f"     {fmt_t(l['start'])} - {fmt_t(l['end'])}  {l['text']}{m}")
    for l in out:
        l.pop("match", None)
    dst = root / "lyrics.yaml"
    dst.write_text("# generated by mv.py align - edit times freely; words = [word, start, end]\n" +
                   yaml.safe_dump({"lines": out}, allow_unicode=True, sort_keys=False, default_flow_style=None, width=200),
                   encoding="utf-8")
    print(f"[mv] wrote {dst}  (storyboard: lyrics_file: lyrics.yaml)")


# storyboard.md is read by the user: labels follow `lang:` in the storyboard (add a language by adding a dict here).
REVIEW_LABELS = {
    "en": dict(format="Format", duration="Duration", avg="avg", lyric="Lyrics", style="style", accent="accent",
               lines="lines", reading="Song reading", look="Overall look", plan="Technique proposals from the song's meaning",
               meaning="Meaning / emotion", rec="⭐ Recommended", why="Why it fits", other="Other option",
               wow="Wow moments (the shareable beats)", sources="Footage sources",
               src_head="| id | Status | Source | Note / rights |", have="✅ file ready", wait="⬇ to download",
               need="❓ to find", shots_head="| # | Time | Lyric / section | Intent | Technique | Layout | Layers | FX | → Transition |",
               soft="soft seam", hard="hard cut", alts="Alternatives per shot (pick to swap)",
               approve="> Approve: reply OK, or give shot id + option to change (e.g. `S03 -> option 2`).",
               check="Edit check (genre cutting grammar)", genre="Genre", preset="Style",
               platforms="Platform check", footage="Footage quality"),
    "vi": dict(format="Khung hình", duration="Thời lượng", avg="trung bình", lyric="Lyric", style="kiểu", accent="màu nhấn",
               lines="câu", reading="Đọc bài hát", look="Look tổng thể", plan="Đề xuất kỹ thuật theo ý nghĩa bài hát",
               meaning="Ý nghĩa / cảm xúc", rec="⭐ Đề xuất", why="Vì sao hợp", other="Phương án khác",
               wow="Khoảnh khắc 'wow' (điểm nhấn để viral)", sources="Nguồn footage",
               src_head="| id | Trạng thái | Nguồn | Ghi chú / quyền sử dụng |", have="✅ có file", wait="⬇ chờ tải",
               need="❓ cần tìm", shots_head="| # | Thời gian | Lời / đoạn | Ý đồ | Kỹ thuật | Bố cục | Lớp hình | FX | → Chuyển |",
               soft="viền mềm", hard="cắt cứng", alts="Phương án thay thế từng shot (chọn để đổi)",
               approve="> Duyệt: trả lời OK, hoặc ghi số shot + phương án muốn đổi (vd. `S03 -> phương án 2`).",
               check="Kiểm tra nhịp dựng (theo thể loại)", genre="Thể loại", preset="Phong cách",
               platforms="Kiểm tra theo nền tảng", footage="Chất lượng footage"),
}


def cmd_review(a):
    p = Project(a.project)
    p.validate()
    sb = p.sb
    T = REVIEW_LABELS.get(str(sb.get("lang", "en")).lower()[:2], REVIEW_LABELS["en"])
    s0, e1 = tsec(p.shots[0]["start"]), tsec(p.shots[-1]["end"])
    L = [f"# Storyboard - {sb.get('title', p.root.name)}", "",
         f"- {T['format']}: **{sb.get('format', '9:16')}** · {sb.get('fps', 30)} fps · Audio: `{sb.get('audio')}`",
         f"- {T['duration']}: **{fmt_t(e1 - s0)}** ({fmt_t(s0)} → {fmt_t(e1)}) · {len(p.shots)} shots · "
         f"{T['avg']} {(e1 - s0) / len(p.shots):.1f}s/shot", ""]
    if sb.get("genre") or sb.get("preset"):
        L[-1:] = [f"- {T['genre']}: **{sb.get('genre', '-')}** · {T['preset']}: **{sb.get('preset', '-')}**"
                  + (f" ({sb['theme']})" if sb.get("theme") else "")
                  + (f" · cut_lead {sb['cut_lead']}" if sb.get("cut_lead") else ""), ""]
    lines = p.lyric_lines()
    if lines or sb.get("lyric_style"):
        L += [f"- {T['lyric']}: {T['style']} **{sb.get('lyric_style', 'subtitle')}** · font `{sb.get('font', 'Be Vietnam Pro')}` / "
              f"`{sb.get('display_font', 'Anton')}` · {T['accent']} `{sb.get('accent', '#FFD24D')}` · {len(lines)} {T['lines']}", ""]
    if sb.get("concept"):
        L += ["## Concept", "", str(sb["concept"]).strip(), ""]
    if sb.get("song_reading"):
        L += [f"## {T['reading']}", "", str(sb["song_reading"]).strip(), ""]
    if sb.get("look"):
        L += [f"## {T['look']}", "", str(sb["look"]).strip(), ""]
    plan = sb.get("technique_plan") or []
    if plan:
        L += [f"## {T['plan']}", ""]
        for n, sec in enumerate(plan, 1):
            L.append(f"### {n}. {sec.get('section', '')}" + (f" - {sec['time']}" if sec.get("time") else ""))
            if sec.get("meaning"):
                L.append(f"- **{T['meaning']}:** {sec['meaning']}")
            if sec.get("recommend"):
                L.append(f"- **{T['rec']}:** {sec['recommend']}")
            if sec.get("why"):
                L.append(f"- **{T['why']}:** {sec['why']}")
            for o in sec.get("options") or []:
                L.append(f"- {T['other']}: {o}")
            L.append("")
    wow = sb.get("wow_moments") or []
    if wow:
        L += [f"## {T['wow']}", ""] + [f"- {w}" for w in wow] + [""]
    L += [f"## {T['sources']}", "", T["src_head"], "|---|---|---|---|"]
    for sid, info in p.sources.items():
        info = info or {}
        have = T["have"] if p.source_file(sid) else (T["wait"] if info.get("url") else T["need"])
        src = info.get("url") or info.get("path") or info.get("search") or ""
        if info.get("section"):
            src += f" `[{info['section']}]`"
        L.append(f"| `{sid}` | {have} | {src} | {info.get('note', '')} {('· ' + info['rights']) if info.get('rights') else ''} |")
    L += ["", "## Shot list", "", T["shots_head"], "|---|---|---|---|---|---|---|---|---|"]
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
            if ly.get("lipsync") not in (None, False):
                t += " lipsync"
            if p.gen_spec(ly.get("src")):
                t += f" gen:{p.gen_spec(ly.get('src'))}"
            lay.append(t)
        lyric = sh.get("lyric") or sh.get("caption") or sh.get("section", "")
        layout = sh.get("layout", "full")
        if layout in ("split_v", "split_h"):
            fv = sh.get("feather", DEFAULT_FEATHER)
            layout += f" ({T['soft']} {fv})" if fv else f" ({T['hard']})"
        fx = list(map(str, sh.get("fx") or [])) + [f"beat-{b}" for b in sh.get("beat_fx") or []]
        tech = ", ".join(f"`{t}`" for t in sh.get("technique") or [])
        if sh.get("lyric_style"):
            tech += f"<br>lyric: {sh['lyric_style']}"
        if sh.get("role") or sh.get("size"):
            tech += f"<br>{sh.get('role', '')} {sh.get('size', '')}".rstrip()
        L.append(f"| {sh['id']} | {fmt_t(tsec(sh['start']))}–{fmt_t(tsec(sh['end']))} | {lyric} | {sh.get('intent', '')} | "
                 f"{tech} | {layout} | {'<br>'.join(lay)} | {'+'.join(fx)} | {sh.get('transition', 'cut')} |")
    alts = [(sh["id"], a) for sh in p.shots for a in sh.get("alt") or []]
    if alts:
        L += ["", f"## {T['alts']}", ""] + [f"- **{i}:** {a}" for i, a in alts]
    if sb.get("genre") or any(sh.get("role") or sh.get("size") for sh in p.shots):
        res = EC.check(sb, p.shots, p.beats, p.downbeats, sb.get("lang", "en"))
        L += ["", f"## {T['check']}", ""] + EC.report_md(res)
    if sb.get("platforms"):
        pw = PL.check(sb, p.shots, e1 - s0, sb.get("lang", "en"))
        pl = PL.plan(sb["platforms"], e1 - s0)
        L += ["", f"## {T['platforms']}", "", f"- {', '.join(pl['platforms'])} · "
              + " · ".join(f"{f}: {', '.join(n)}" for f, n in pl["versions"].items())]
        L += [f"- ⚠ {w}" for w in pw] or ["- ✅"]
    fw = footage_warnings(p)
    if fw:
        L += ["", f"## {T['footage']}", ""] + [f"- ⚠ {w}" for w in fw]
    L += ["", T["approve"]]
    out = p.root / "storyboard.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    warns = [l[4:] for l in L if l.startswith("- ⚠ ")]
    print(f"[mv] wrote {out} - {len(p.shots)} shots, {fmt_t(e1 - s0)}, {len(p.sources)} sources"
          + (f", {len(warns)} warnings:" if warns else ", no warnings"))
    for w in warns[: (None if getattr(a, "verbose", False) else 8)]:
        print(f"  ⚠ {w}")
    if len(warns) > 8 and not getattr(a, "verbose", False):
        print(f"  ... {len(warns) - 8} more in storyboard.md")


def cmd_search(a):
    q = f"ytsearch{a.n}:{a.query}"
    r = run(venv_tool("yt_dlp") + ["--flat-playlist", "--no-warnings", "--print",
                                   "%(id)s | %(duration_string)s | %(channel)s | %(title)s | %(url)s", q])
    print(r.stdout.strip())


def _sheet_font() -> Path:
    f = LY.FONTS_DIR / "BeVietnamPro-SemiBold.ttf"
    return f if f.exists() else Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf"


def _save_picks(root: Path, updates: dict):
    f = root / "picks.yaml"
    cur = (yaml.safe_load(f.read_text(encoding="utf-8")) or {}) if f.exists() else {}
    cur.update(updates)
    f.write_text("# written by mv pick / mv ingest - merged over storyboard sources\n" +
                 yaml.safe_dump(cur, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")


def _embedder(model: str | None):
    """SigLIP 2 embedder, or None with an install hint (everything still works unranked)."""
    import match as MT
    try:
        return MT.Embedder(model or DR.load_profile().get("match_model"))
    except RuntimeError as e:
        print(f"[mv] {e}\n[mv] continuing without semantic ranking")
        return None


def _rank_and_scan(cands: list[dict], describe, emb, work: Path, deep: int = 0, avoid=None) -> list[dict]:
    """Order candidates by how well their thumbnail matches the description; for the best `deep` YouTube videos read
    the preview storyboard and find the matching moment (best_t + a suggested `section` to download)."""
    import match as MT
    work.mkdir(parents=True, exist_ok=True)
    for old in work.glob("th_*.jpg"):  # thumbs of an earlier search in this slot
        old.unlink()
    qv, nv = MT.query_vector(emb, describe, avoid)
    thumbs = [SRC.fetch_thumb(c, work / f"th_{i:03d}.jpg") for i, c in enumerate(cands)]
    have = [(c, t) for c, t in zip(cands, thumbs) if t]
    vecs = emb.images([t for _, t in have])
    sims = MT.dot_matrix([qv], vecs)[0]
    negs = MT.dot_matrix([nv], vecs)[0] if nv else [0.0] * len(vecs)
    for (c, t), sv, ng in zip(have, sims, negs):
        c["match"] = round(sv - 0.5 * ng, 4)
        c["thumb"] = str(t)
    ranked = sorted([c for c, _ in have], key=lambda c: c["match"], reverse=True) + [c for c, t in zip(cands, thumbs) if not t]
    for c in [c for c in ranked if c["provider"] == "youtube"][:deep]:
        try:
            info = c.get("_info") or SRC.ytdlp_json(c["url"])
            vid = re.sub(r"\W", "", str(info.get("id") or c["url"]))[-16:]
            tiles = MT.storyboard_tiles(info, work / f"sb_{vid}", lambda u: SRC._get(u, timeout=20))
            if not tiles:
                continue
            tv = emb.images([p for _, p in tiles])
            ts = MT.dot_matrix([qv], tv)[0]
            if nv:
                ts = [x - 0.5 * y for x, y in zip(ts, MT.dot_matrix([nv], tv)[0])]
            best_t, a0, b0 = MT.best_run([t for t, _ in tiles], ts)
            bi = max(range(len(ts)), key=lambda i: ts[i])
            c.update(best_t=best_t, section=f"{fmt_t(a0)}-{fmt_t(b0)}", thumb=str(tiles[bi][1]),
                     match=round(max(c.get("match", -1), ts[bi]), 4), deep=True)
        except Exception as e:
            print(f"[mv] deep scan skipped for {c['url']}: {str(e)[:80]}")
    for c in ranked:
        c.pop("_info", None)
    return sorted(ranked, key=lambda c: c.get("match", -9), reverse=True)


def _find_to_sheet(root: Path, slot: str, query: str | None, kind: str, provs, orient, n: int, describe=None,
                   emb=None, deep: int = 0, links: list[str] | None = None, avoid=None) -> list[dict]:
    cands, notes = SRC.find(query, kind, provs, orient, n) if query else ([], [])
    if links:
        more, n2 = SRC.from_links(links, n)
        cands += more
        notes += n2
    print(f"[mv] '{query or 'links'}' ({kind}) - " + " · ".join(notes))
    if not cands:
        return []
    work = root / "build" / "cand" / slot
    if emb is not None and (describe or query):
        cands = _rank_and_scan(cands, describe or query, emb, work / "rank", deep, avoid)
    for c in cands:
        c.pop("_info", None)
    sheet = root / "refs" / f"cand_{slot}.jpg"
    sheet.parent.mkdir(parents=True, exist_ok=True)
    made = SRC.contact_sheet(cands, sheet, work, _sheet_font())
    if made:
        cands = [c for c in cands if c.get("_sheet")]  # numbers on the sheet == candidate numbers
    cdir = root / "candidates"
    cdir.mkdir(exist_ok=True)
    (cdir / f"{slot}.json").write_text(json.dumps(cands, ensure_ascii=False, indent=1), encoding="utf-8")
    for i, c in enumerate(cands, 1):
        size = f"{c.get('w') or '?'}x{c.get('h') or '?'}"
        dur = f" {float(c['duration']):.0f}s" if c.get("duration") else ""
        m = f" match {c['match']:.3f}" if "match" in c else ""
        at = f" @ {fmt_t(c['best_t'])} -> section {c['section']}" if c.get("section") else ""
        print(f"  {i:2d}. [{c.get('site') or c['provider']}]{m} {size}{dur}  {str(c.get('title', ''))[:46]}  - "
              f"{c.get('creator', '')[:20]}{at}  | {c['license'][:32]}")
    print(f"[mv] contact sheet: {sheet if made else '(no thumbnails)'}  ·  pick with: mv pick {root} <source_id> {slot}:<n>")
    return cands


def _links(arg: str | None) -> list[str]:
    if not arg:
        return []
    f = Path(arg)
    txt = f.read_text(encoding="utf-8") if f.is_file() else arg
    return [x for x in re.split(r"[\s,]+", txt) if x.startswith("http")]


def cmd_find(a):
    provs = [x.strip() for x in a.providers.split(",")] if a.providers else None
    if provs and set(provs) - set(SRC.PROVIDERS):
        die(f"providers: {SRC.PROVIDERS}")
    if a.deep and provs is None:
        provs = SRC.default_providers(a.type) + ["youtube"]
    root = Path(a.project) if a.project else Path(".")
    slot = a.slot or re.sub(r"[^a-z0-9]+", "_", (a.query or "links").lower()).strip("_")[:30]
    emb = _embedder(a.model) if (a.rank or a.deep or a.describe) else None
    if not _find_to_sheet(root, slot, a.query, a.type, provs, a.orient, a.n, a.describe, emb, a.deep, _links(a.links),
                          a.avoid):
        die("no results - try other words (English works best), --type image, or other --providers")


def cmd_scout(a):
    """Every source with `search:` and no file / url yet: search, rank by its `look_for` (or note), deep-scan YouTube,
    one contact sheet per source + refs/scout.md. Nothing is downloaded until you pick (GATE 2)."""
    p = Project(a.project)
    provs = [x.strip() for x in a.providers.split(",")] if a.providers else SRC.default_providers("video") + ["youtube"]
    emb = _embedder(a.model)
    lines = ["# Scout - candidates per source", "", "Open each sheet, then: `mv pick <project> <source> <source>:<n>` "
             "(YouTube picks keep the suggested section, so only that part is downloaded).", ""]
    todo = [(sid, info or {}) for sid, info in p.sources.items()
            if (info or {}).get("search") and not (info or {}).get("url") and not p.source_file(sid)
            and (not a.only or sid in a.only.split(","))]
    if not todo:
        die("no source needs footage (add `search:` - and ideally `look_for:` - to sources without a file)")
    for sid, info in todo:
        queries = info["search"] if isinstance(info["search"], list) else [info["search"]]
        cands: list[dict] = []
        for q in queries:  # several phrasings widen the net; results are re-ranked together by the description
            seen = {c["url"] for c in cands}
            cands += [c for c in SRC.find(q, info.get("type", "video"), provs, info.get("orient") or a.orient, a.n)[0]
                      if c["url"] not in seen]
        describe = info.get("look_for") or info.get("note") or queries[0]
        if not cands:
            lines += [f"## {sid}", "", "- no results - rephrase `search:`", ""]
            continue
        work = p.root / "build" / "cand" / sid
        if emb is not None:
            cands = _rank_and_scan(cands, describe, emb, work / "rank", a.deep, info.get("avoid"))
        cands = cands[: a.keep]
        sheet = p.root / "refs" / f"cand_{sid}.jpg"
        sheet.parent.mkdir(parents=True, exist_ok=True)
        made = SRC.contact_sheet(cands, sheet, work, _sheet_font())
        if made:
            cands = [c for c in cands if c.get("_sheet")]
        (p.root / "candidates").mkdir(exist_ok=True)
        (p.root / "candidates" / f"{sid}.json").write_text(json.dumps(cands, ensure_ascii=False, indent=1), encoding="utf-8")
        lines += [f"## {sid} - {describe}", "", f"![{sid}](cand_{sid}.jpg)", ""]
        for i, c in enumerate(cands[:6], 1):
            at = f" · moment {fmt_t(c['best_t'])} (section {c['section']})" if c.get("section") else ""
            sc = f" · match {c['match']:.3f}" if "match" in c else ""
            lines.append(f"{i}. [{c.get('site') or c['provider']}] {str(c.get('title', ''))[:60]}{sc}{at} · {c['license'][:40]}")
        lines.append("")
        print(f"[mv] {sid}: {len(cands)} candidates -> {sheet}")
    (p.root / "refs" / "scout.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[mv] summary: {p.root / 'refs' / 'scout.md'} - look at the sheets, then mv pick (GATE 2 before mv fetch)")


def cmd_pick(a):
    root = Path(a.project)
    slot, _, num = a.candidate.rpartition(":")
    f = root / "candidates" / f"{slot or a.source}.json"
    if not f.exists():
        die(f"{f} not found - run mv find first")
    cands = json.loads(f.read_text(encoding="utf-8"))
    k = int(num) - 1
    if not 0 <= k < len(cands):
        die(f"candidate {num} out of range 1..{len(cands)}")
    c = cands[k]
    entry = {"url": c["url"], "provider": c["provider"], "kind": c["kind"], "page": c.get("page"),
             "title": c.get("title"), "creator": c.get("creator"), "rights": c["license"]}
    if a.section or c.get("section"):
        entry["section"] = a.section or c["section"]  # deep-scanned YouTube: download only the matching part
        print(f"[mv] section {entry['section']} (only this part is downloaded; `in:` stays in original video time)")
    _save_picks(root, {a.source: entry})
    print(f"[mv] {a.source} <- [{c['provider']}] {c.get('title', '')[:60]}  ({c['license'][:50]})")
    if c["provider"] in ("youtube", "web"):
        print("[mv] NOTE: this footage is normally copyrighted - confirm permission with the user before publishing")


def cmd_ingest(a):
    """Register the user's own clips/photos as sources and rank their best moments."""
    root = Path(a.project)
    folder = Path(a.folder)
    if not folder.is_dir():
        die(f"{folder} is not a folder")
    files = sorted(p for p in folder.rglob("*") if p.suffix.lower() in SRC.VIDEO_EXT + SRC.IMAGE_EXT)
    if not files:
        die("no video/image files found")
    picks, moments = {}, []
    work = root / "build" / "ingest"
    work.mkdir(parents=True, exist_ok=True)
    for n, fpath in enumerate(files, 1):
        sid = f"{a.prefix}{n}"
        picks[sid] = {"path": str(fpath.resolve()), "provider": "own", "rights": SRC.LICENSES["own"],
                      "title": fpath.name, "kind": "image" if fpath.suffix.lower() in SRC.IMAGE_EXT else "video"}
        if picks[sid]["kind"] == "image":
            moments.append({"src": sid, "in": 0, "score": 0.5, "file": fpath.name, "thumb": str(fpath)})
            continue
        print(f"[mv] scoring {fpath.name} ...")
        for sc in SRC.score_scenes(fpath):
            mid = (sc["start"] + sc["end"]) / 2
            th = work / f"{sid}_{int(mid * 10)}.jpg"
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{mid:.2f}", "-i", str(fpath), "-frames:v", "1",
                 "-vf", "scale=320:-2", str(th)])
            moments.append({"src": sid, "in": sc["start"], "end": sc["end"], **sc, "file": fpath.name, "thumb": str(th)})
    _save_picks(root, picks)
    moments.sort(key=lambda m: m["score"], reverse=True)
    best = moments[: a.top]
    (root / "candidates").mkdir(exist_ok=True)
    (root / "candidates" / "ingest.json").write_text(json.dumps(moments, ensure_ascii=False, indent=1), encoding="utf-8")
    sheet = root / "refs" / "ingest_best.jpg"
    sheet.parent.mkdir(exist_ok=True)
    SRC.contact_sheet(best, sheet, work / "sheet", _sheet_font(), cols=6)
    for i, m in enumerate(best, 1):
        extra = f"{m['start']:.1f}-{m['end']:.1f}s sharp {m['sharpness']:.0f} motion {m['motion']:.1f} faces {m['faces']}" \
            if "sharpness" in m else "photo"
        print(f"  {i:2d}. {m['src']:<8} in: {m['in']:<6} score {m['score']:.2f}  {extra}  ({m['file']})")
    print(f"[mv] {len(files)} files registered in picks.yaml as {a.prefix}1..{a.prefix}{len(files)} · best moments: {sheet}")


def _library(p: "Project", only: list[str] | None, work: Path) -> list[dict]:
    """Scenes to choose from: every source with a file (your clips from mv ingest, downloaded picks), split into scenes
    (mv ingest's scene list when present, else scene detection) with 3 sampled frames each."""
    import match as MT
    ing = p.root / "candidates" / "ingest.json"
    known: dict[str, list] = {}
    if ing.exists():
        for m in json.loads(ing.read_text(encoding="utf-8")):
            if "end" in m:
                known.setdefault(m["src"], []).append({"start": m["start"], "end": m["end"], "score": m.get("score", 0.5)})
    scenes = []
    for sid, info in p.sources.items():
        info = info or {}
        if info.get("gen") or str(sid).startswith("_scene") or (only and not any(sid == o or sid.startswith(o) for o in only)):
            continue
        f = p.source_file(sid)
        if f is None:
            continue
        if f.suffix.lower() in IMAGE_EXT:
            scenes.append({"src": sid, "start": 0.0, "end": 1e6, "image": True, "quality": 0.5, "frames": [(0.0, f)]})
            continue
        off = p.source_offset(sid)  # times in a downloaded section file + offset = original video time (`in:`)
        segs = known.get(sid)
        if segs is None:
            print(f"[mv] scenes in {f.name} ...")
            segs = SRC.score_scenes(f, max_scenes=80)
        for sc in segs:
            fr = [(t + off, MT.extract_frame(f, t, work / "frames" / f"{sid}_{int(t * 100):07d}.jpg"))
                  for t in MT.frame_times(float(sc["start"]), float(sc["end"]))]
            scenes.append({"src": sid, "start": float(sc["start"]) + off, "end": float(sc["end"]) + off,
                           "quality": float(sc.get("score", 0.5)), "frames": fr})
    return scenes


def cmd_match(a):
    """Choose a scene + in-point for every shot with `layers: auto` (or {src: auto}) by its `look_for` description."""
    import match as MT
    p = Project(a.project)
    raw = (yaml.safe_load((p.root / "storyboard.yaml").read_text(encoding="utf-8")) or {}).get("shots") or []
    auto_ids = {str(r.get("id") or f"S{i + 1:02d}") for i, r in enumerate(raw)
                if r.get("layers") == "auto" or (not r.get("layers") and r.get("look_for"))
                or any(isinstance(l, dict) and l.get("src") == "auto" for l in r.get("layers") or [] if r.get("layers") != "auto")}
    mf = p.root / "matches.yaml"
    if a.pick:  # quick switch: S03:2
        sid, _, k = a.pick.partition(":")
        data = yaml.safe_load(mf.read_text(encoding="utf-8")) if mf.exists() else None
        if not data or sid not in (data.get("shots") or {}):
            die(f"no match list for {sid} - run mv match first")
        data["shots"][sid]["use"] = int(k)
        mf.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
        print(f"[mv] {sid} -> candidate {k}")
        return
    targets = [sh for sh in p.shots if str(sh["id"]) in auto_ids]
    if not targets:
        die("no shot to match: give shots `layers: auto` (or a layer {src: auto}) and a `look_for:` description")
    work = p.build / "match"
    lib = _library(p, a.sources.split(",") if a.sources else None, work)
    if not lib:
        die("no footage to choose from - mv ingest <project> <folder> (your clips) or mv fetch the picked sources")
    emb = _embedder(a.model)
    if emb is None:
        die("mv match needs the matching model: mv doctor --install match")
    cache = MT.EmbCache(work / f"emb_{re.sub(r'[^a-z0-9]+', '_', emb.model_id.lower())}.json", emb)
    frames = [(i, t, f) for i, sc in enumerate(lib) for t, f in sc["frames"]]
    vecs = cache.images([f for _, _, f in frames])
    queries = []
    for sh in targets:
        q, av = MT.shot_query(sh)
        if not q:
            die(f"{sh['id']}: add `look_for:` (a concrete visual description, English works best)")
        queries.append(MT.query_vector(emb, q, av))
    S = MT.dot_matrix([q for q, _ in queries], vecs)
    cands: dict[str, list[dict]] = {}
    for qi, sh in enumerate(targets):
        nv = queries[qi][1]
        N = MT.dot_matrix([nv], vecs)[0] if nv else None
        lay = next((l for l in sh.get("layers") or [] if isinstance(l, dict)), {})
        need = (tsec(sh["end"]) - tsec(sh["start"])) * float(lay.get("speed", 1) or 1)
        per: dict[int, list] = {}
        for fi, (si, t, f) in enumerate(frames):
            per.setdefault(si, []).append((S[qi][fi], N[fi] if N else 0.0, t, f))
        out = []
        for si, fs in per.items():
            sc = lib[si]
            score = MT.score_scene([x[0] for x in fs], [x[1] for x in fs] if N else None, sc["quality"])
            if not sc.get("image") and sc["end"] - sc["start"] < need * 0.9:
                score -= 0.02  # too short for the shot: it would loop / freeze
            best = max(fs, key=lambda x: x[0] - 0.5 * x[1])
            out.append({"src": sc["src"], "in": 0.0 if sc.get("image") else MT.in_point(sc, best[2], need),
                        "scene": f"{fmt_t(sc['start'])}-{fmt_t(sc['end'])}" if not sc.get("image") else "photo",
                        "score": round(score, 4), "key": f"{sc['src']}@{sc['start']:.2f}", "image": bool(sc.get("image")),
                        "thumb": Path(best[3]).resolve().relative_to(p.root.resolve()).as_posix()
                        if Path(best[3]).resolve().is_relative_to(p.root.resolve()) else str(best[3])})
        cands[str(sh["id"])] = sorted(out, key=lambda c: c["score"], reverse=True)[: max(a.top, 1) * 3]
    chosen = MT.assign(targets, cands, reuse=a.reuse)
    shots_out = {}
    for sh in targets:
        sid = str(sh["id"])
        cs = cands[sid]
        k = chosen.get(sid, 0)
        keep = cs[: a.top]
        if k >= a.top:  # the assigned one was further down (others took the best): keep it in the list
            keep.append(cs[k])
            k = len(keep) - 1
        for c in keep:
            c.pop("key", None)
            if not c["image"]:
                c.pop("image")
        shots_out[sid] = {"look_for": MT.shot_query(sh)[0], "use": k + 1, "candidates": keep}
    mf.write_text("# written by mv match - `use:` picks the candidate (1 = best); or: mv match <project> --pick S03:2\n" +
                  yaml.safe_dump({"model": emb.model_id, "shots": shots_out}, allow_unicode=True, sort_keys=False, width=200),
                  encoding="utf-8")
    chosen_c = []
    for i, sh in enumerate(targets, 1):
        ent = shots_out[str(sh["id"])]
        c = ent["candidates"][ent["use"] - 1]
        chosen_c.append({"thumb": str(p.root / c["thumb"]) if not Path(c["thumb"]).is_absolute() else c["thumb"]})
        print(f"  {i:2d}. {sh['id']:<5} {c['src']:<10} in {c['in']:<7} score {c['score']:.3f}  {str(ent['look_for'])[:60]}")
    sheet = p.root / "refs" / "match_all.jpg"
    sheet.parent.mkdir(exist_ok=True)
    SRC.contact_sheet(chosen_c, sheet, work / "sheet", _sheet_font(), cols=6)
    for sh in targets if a.sheets else []:
        ent = shots_out[str(sh["id"])]
        SRC.contact_sheet([{"thumb": str(p.root / c["thumb"])} for c in ent["candidates"]],
                          p.root / "refs" / f"match_{sh['id']}.jpg", work / f"sheet_{sh['id']}", _sheet_font())
    print(f"[mv] wrote {mf} · chosen frames (numbered in shot order): {sheet}"
          + ("" if a.sheets else " · per-shot alternatives: add --sheets"))


def _out_video(p: "Project", mode: str, fmt: str | None = None) -> Path:
    fmt = fmt or str(p.sb.get("format", "9:16"))
    return p.out / f"{p.sb.get('slug') or p.root.name}_{mode}_{fmt.replace(':', 'x')}.mp4"


def cmd_proof(a):
    """One labelled frame per shot in one sheet: the cheapest way to look at a whole edit (instead of many frames)."""
    p = Project(a.project)
    p.validate()
    if a.format:
        p.sb["format"] = a.format
    video = _out_video(p, a.mode)
    if not video.exists():
        die(f"{video.name} not rendered yet - mv render {p.root} --mode {a.mode}" + (f" --format {a.format}" if a.format else ""))
    if video.stat().st_mtime < (p.root / "storyboard.yaml").stat().st_mtime:
        print("[mv] note: storyboard.yaml changed after this render - re-render to see the changes")
    lines = p.lyric_lines()
    s0, e1 = tsec(p.shots[0]["start"]), tsec(p.shots[-1]["end"])
    only = set(a.only.split(",")) if a.only else None
    sel = []
    for sh in p.shots:
        if only and sh["id"] not in only:
            continue
        a0, b0 = tsec(sh["start"]), tsec(sh["end"])
        ly = next((str(l["text"]) for l in lines if a0 <= float(l["start"]) < b0), None)
        sel.append({"id": sh["id"], "_s": a0, "_e": b0, "lyric": ly or sh.get("lyric"), "section": sh.get("section")})
    if not sel:
        die("no shots selected")
    W, H = FORMATS.get(str(p.sb.get("format", "9:16")), (1080, 1920))
    pages = AS.proof_sheet(video, sel, s0, e1 - s0, p.root / "refs" / ("proof.jpg" if not only else "proof_only.jpg"),
                           p.build / "proof", _sheet_font(), H > W)
    print(f"[mv] {len(sel)} shots -> " + ", ".join(str(x) for x in pages) + "  (open and look; frames are mid-shot)")


def cmd_status(a):
    """Compact state of a project and the next step - read this instead of re-reading the big files."""
    root = Path(a.project)
    L = [f"# {root.name}"]
    sbp = root / "storyboard.yaml"
    au = [f for f in (root / "audio").glob("*")] if (root / "audio").exists() else []
    L.append(f"audio: {', '.join(f.name for f in au) or 'MISSING (put the song in audio/)'}")
    an = root / "analysis.json"
    data = json.loads(an.read_text(encoding="utf-8")) if an.exists() else {}
    nb, bpm = len(data.get("beats") or []), data.get("tempo_bpm")
    L.append(f"analysis: {nb} beats, {bpm} bpm" if data else "analysis: not yet (mv analyze)")
    lf = root / "lyrics.yaml"
    nl = len((yaml.safe_load(lf.read_text(encoding="utf-8")) or {}).get("lines", [])) if lf.exists() else 0
    has_txt = (root / "lyrics.txt").exists()
    L.append(f"lyrics: {nl} timed lines" if nl else ("lyrics: lyrics.txt only (mv align)" if has_txt else "lyrics: none"))
    nxt = None
    if not au:
        nxt = "put the audio in audio/"
    elif not data:
        nxt = f"mv analyze {root} --lyrics"
    if not sbp.exists():
        L.append("storyboard: none")
        nxt = nxt or f"write storyboard.yaml (or mv auto {root} --plan plan.yaml / --template ...)"
        print("\n".join(L + [f"NEXT: {nxt}"]))
        return
    p = Project(root)
    sb = p.sb
    dur = tsec(p.shots[-1]["end"]) - tsec(p.shots[0]["start"])
    L.append(f"storyboard: {len(p.shots)} shots, {fmt_t(dur)}, format {sb.get('format', '9:16')}"
             + "".join(f", {k} {sb[k]}" for k in ("genre", "preset", "theme") if sb.get(k))
             + (f", platforms {sb['platforms']}" if sb.get("platforms") else ""))
    need, wait, have = [], [], 0
    for sid, info in p.sources.items():
        info = info or {}
        if info.get("gen") or p.source_file(sid):
            have += 1
        elif info.get("url"):
            wait.append(sid)
        else:
            need.append(sid)
    L.append(f"sources: {have} ready" + (f", to download: {', '.join(wait)}" if wait else "")
             + (f", to find: {', '.join(need)}" if need else ""))
    todo = [sh["id"] for sh in p.shots if str(sh.get("look_for", "")).startswith("TODO")]
    pending = [sh["id"] for sh in p.shots for ly in sh.get("layers") or []
               if isinstance(ly, dict) and ly.get("src") is None and "mv match" in str(ly.get("note", ""))]
    if todo:
        L.append(f"look_for TODO: {', '.join(todo[:10])}" + (" ..." if len(todo) > 10 else ""))
    if pending:
        L.append(f"auto shots not matched yet: {len(pending)}")
    warns = []
    if sb.get("genre") or any(sh.get("role") or sh.get("size") for sh in p.shots):
        warns += EC.check(sb, p.shots, p.beats, p.downbeats)["warnings"]
    warns += PL.check(sb, p.shots, dur)
    warns += footage_warnings(p)
    L.append(f"checks: {len(warns)} warnings" + (f" (first: {warns[0][:90]})" if warns else ""))
    sm = sbp.stat().st_mtime
    md = root / "storyboard.md"
    L.append(f"review: {'up to date' if md.exists() and md.stat().st_mtime >= sm else 'stale/missing (mv review)'}")
    outs = sorted(p.out.glob("*.mp4")) if p.out.exists() else []
    for f in outs:
        L.append(f"render: {f.name} ({'up to date' if f.stat().st_mtime >= sm else 'older than storyboard'})")
    if not outs:
        L.append("render: none")
    proof = root / "refs" / "proof.jpg"
    if proof.exists():
        L.append(f"proof: refs/proof.jpg ({'current' if outs and proof.stat().st_mtime >= max(f.stat().st_mtime for f in outs) else 'older than the render'})")
    if not nxt:
        if todo:
            nxt = "write `look_for` for the TODO shots (or a plan.yaml + mv auto --plan --force)"
        elif not md.exists() or md.stat().st_mtime < sm:
            nxt = f"mv review {root}, then show storyboard.md + proxy animatic (GATE 1)"
        elif need:
            nxt = f"find footage: mv scout {root} (or mv ingest your clips) -> GATE 2"
        elif wait:
            nxt = f"after the user approves the list: mv fetch {root}"
        elif pending:
            nxt = f"mv match {root}"
        elif not any("proxy" in f.name for f in outs) or any(f.stat().st_mtime < sm for f in outs):
            nxt = f"mv render {root} --mode proxy, then mv proof {root}"
        elif not any("final" in f.name for f in outs):
            nxt = f"look at mv proof {root}; when approved: mv render {root} --mode final (+ other --format / --cut versions)"
        else:
            nxt = "done - deliver out/*.mp4 and out/credits.txt"
    print("\n".join(L + [f"NEXT: {nxt}"]))


def cmd_context(a):
    genre, platforms, vtype, mood = a.genre, a.platforms, a.type, a.mood
    dur = None
    if a.project and (Path(a.project) / "storyboard.yaml").exists():
        p = Project(a.project)
        genre = genre or p.sb.get("genre")
        platforms = platforms or p.sb.get("platforms")
        dur = tsec(p.shots[-1]["end"]) - tsec(p.shots[0]["start"])
    hints = None
    if a.project and (Path(a.project) / "analysis.json").exists():
        hints = json.loads((Path(a.project) / "analysis.json").read_text(encoding="utf-8")).get("style")
    pt = None
    if platforms:
        try:
            pt = PL.plan_text(PL.plan(platforms, dur))
        except ValueError as e:
            die(str(e))
    out = AS.context(genre, platforms, vtype, mood or (hints or {}).get("mood"), load_presets(), EC.load_genres(), pt)
    if hints:
        m = hints.get("model") or {}
        out[1:1] = [f"Audio hints: {', '.join(g['genre'] for g in hints['genres'])} (heuristic"
                    + (f"; model: {', '.join(g['genre'] for g in m.get('genres', []))}, "
                       f"{', '.join(x for x, _ in m.get('moods', []))}" if m else "")
                    + f") · {hints['mood']} · {hints['why']} - confirm the genre with the lyrics, the artwork and the user", ""]
    print("\n".join(out))


RES_MSG = {
    "en": "{src} ({w}x{h}): enlarged up to {k:.1f}x in {ids} - looks soft on phones; use `layout: fit_blur`, a 4K or "
          "vertical source, or `upscale: true` on the layer",
    "vi": "{src} ({w}x{h}): bị phóng to tới {k:.1f} lần ở {ids} - sẽ mờ trên điện thoại; dùng `layout: fit_blur`, nguồn 4K "
          "hoặc quay dọc, hoặc `upscale: true` cho layer",
}


def footage_warnings(p: "Project", limit: float = 1.5) -> list[str]:
    """Sources enlarged too much for their slot at the final resolution (a 1080p landscape clip cropped to 9:16 is
    only 608 px wide). One line per source, worst factor first."""
    fmt = str(p.sb.get("format", "9:16"))
    W, H = FORMATS.get(fmt, (1080, 1920))
    sizes: dict = {}
    worst: dict = {}
    for sh in p.shots:
        layout = sh.get("layout", "full")
        if layout == "poster":
            continue
        slots = slots_for(layout, W, H, sh)
        base = [ly for ly in (sh.get("layers") or []) if isinstance(ly, dict) and not ly.get("blend")]
        for k, ly in enumerate(base[:len(slots)]):
            sid = ly.get("src")
            f = p.source_file(sid) if sid and not p.gen_spec(sid) else None
            if f is None:
                continue
            wh = sizes.setdefault(f, FG.probe_wh(f))
            zoom = 1 + float(ly.get("zoom_amount", 0.12)) if ly.get("zoom") else 1.0
            fac = FG.upscale_factor(wh, slots[k], zoom, contain=layout == "fit_blur")
            if ly.get("upscale"):
                fac /= 4
            if fac > limit:
                w0 = worst.setdefault(sid, {"k": 0, "ids": [], "wh": wh})
                w0["k"] = max(w0["k"], fac)
                w0["ids"].append(str(sh["id"]))
    T = RES_MSG.get(str(p.sb.get("lang", "en"))[:2], RES_MSG["en"])
    return [T.format(src=sid, w=v["wh"][0], h=v["wh"][1], k=v["k"], ids=", ".join(v["ids"][:6]) + (" ..." if len(v["ids"]) > 6 else ""))
            for sid, v in sorted(worst.items(), key=lambda x: -x[1]["k"])]


def _shot_at(p: "Project", offset: float):
    s0 = tsec(p.shots[0]["start"])

    def at(t: float) -> str:
        song = t + s0 + offset
        sh = next((x for x in p.shots if tsec(x["start"]) <= song < tsec(x["end"])), p.shots[-1])
        return str(sh["id"])
    return at


def _intended(p: "Project", offset: float):
    """Black / frozen stretches that the edit explains (dips, freezes, still images, static backgrounds)."""
    s0 = tsec(p.shots[0]["start"])

    def ok(kind: str, t0: float, t1: float) -> bool:
        a, b = t0 + s0 + offset, t1 + s0 + offset
        for i, sh in enumerate(p.shots):
            ss, se = tsec(sh["start"]), tsec(sh["end"])
            if se <= a - 1.0 or ss >= b + 1.0:
                continue
            tr = str(sh.get("transition", "cut"))
            prev = str(p.shots[i - 1].get("transition", "cut")) if i else "cut"
            if kind == "black" and (tr.startswith(("fadeblack", "flashblack")) or prev.startswith(("fadeblack", "flashblack"))):
                return True
            if kind == "frozen":
                for ly in sh.get("layers") or []:
                    if not isinstance(ly, dict):
                        continue
                    f = p.source_file(ly.get("src")) if ly.get("src") else None
                    if ly.get("freeze") or p.gen_spec(ly.get("src")) or f is None or \
                            (f.suffix.lower() in IMAGE_EXT and not ly.get("zoom")):
                        return True
        return False
    return ok


def _qa_file(p: "Project", f: Path) -> list[str]:
    m = re.search(r"_cut(\d+)-(\d+)_", f.name)
    offset = float(m.group(1)) - tsec(p.shots[0]["start"]) if m else 0.0
    expect = (float(m.group(2)) - float(m.group(1))) if m else tsec(p.shots[-1]["end"]) - tsec(p.shots[0]["start"])
    aspect = re.search(r"_(\d+x\d+)\.mp4$", f.name)
    fmt = aspect.group(1).replace("x", ":") if aspect else str(p.sb.get("format", "9:16"))
    max_sec = None
    if p.sb.get("platforms"):
        data = PL.load()
        lims = [data[k]["max_sec"] for k in PL.expand(p.sb["platforms"]) if data[k]["format"] == fmt]
        max_sec = min(lims) if lims else None
    res = DL.parse_scan(DL.scan(f))
    w = DL.qa_report(DL.probe(f), res, expect, _shot_at(p, offset), _intended(p, offset), max_sec)
    if m and abs(expect - round(expect)) > 0.6:
        pass
    print(f"[mv] {f.name}: {res['lufs']} LUFS, true peak {res['true_peak']} dBFS - "
          + (f"{len(w)} issue(s)" if w else "OK"))
    for x in w:
        print(f"  ⚠ {x}")
    return w


def cmd_qa(a):
    p = Project(a.project)
    files = [Path(a.file)] if a.file else sorted(f for f in p.out.glob(f"*_{a.mode}_*.mp4"))
    if not files:
        die(f"no {a.mode} renders in {p.out} - mv render {p.root} --mode {a.mode}")
    L = ["# QA", ""]
    for f in files:
        w = _qa_file(p, f)
        L += [f"## {f.name}", ""] + ([f"- ⚠ {x}" for x in w] or ["- ✅ OK"]) + [""]
    (p.out / "qa.md").write_text("\n".join(L), encoding="utf-8")
    print(f"[mv] wrote {p.out / 'qa.md'}")


def _write_srt(p: "Project", start: float | None = None, end: float | None = None, name: str | None = None) -> Path | None:
    lines = p.lyric_lines()
    if not lines:
        return None
    s0 = tsec(p.shots[0]["start"]) if start is None else start
    e1 = tsec(p.shots[-1]["end"]) if end is None else end
    p.out.mkdir(exist_ok=True)
    out = p.out / (name or f"{p.sb.get('slug') or p.root.name}.srt")
    out.write_text(DL.srt(lines, s0, e1), encoding="utf-8")
    return out


def cmd_srt(a):
    p = Project(a.project)
    a0 = b0 = None
    name = None
    if a.cut:
        x, _, y = a.cut.partition("-")
        a0, b0 = tsec(x), tsec(y)
        name = f"{p.sb.get('slug') or p.root.name}_cut{int(a0)}-{int(b0)}.srt"
    out = _write_srt(p, a0, b0, name)
    print(f"[mv] wrote {out}" if out else "[mv] no lyrics_file - nothing to export")


def cmd_thumbnail(a):
    """Best frame of the edit (sharp, exposed, colourful, a face; chorus favoured) + the title -> out/thumb_<aspect>.jpg.
    Frames come from the rendered shots (no lyrics burned in): render this format first."""
    p = Project(a.project)
    fmt = a.format or str(p.sb.get("format", "9:16"))
    mode = a.mode
    shots_dir = p.build / mode / "shots"
    W, H = FORMATS[fmt]
    files = [shots_dir / f"{i:03d}_{sh['id']}.mp4" for i, sh in enumerate(p.shots)]
    if not all(f.exists() for f in files):
        die(f"render the {fmt} {mode} version first: mv render {p.root} --mode {mode} --format {fmt}")
    sw, sh_ = FG.probe_wh(files[0])
    if sw and abs(sw / max(sh_, 1) - W / H) > 0.02:
        die(f"the {mode} shots are {sw}x{sh_}, not {fmt} - mv render {p.root} --mode {mode} --format {fmt}")
    work = p.build / "thumb"
    work.mkdir(parents=True, exist_ok=True)
    cands = []
    for i, sh in enumerate(p.shots):
        d = tsec(sh["end"]) - tsec(sh["start"])
        if a.at:
            t_song = tsec(a.at)
            if not tsec(sh["start"]) <= t_song < tsec(sh["end"]):
                continue
            times = [t_song - tsec(sh["start"])]
        else:
            times = [d * 0.5] if d < 2.5 else [d * 0.3, d * 0.7]
        for t in times:
            img = work / f"c_{i:03d}_{int(t * 100)}.jpg"
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(files[i]), "-frames:v", "1", "-q:v", "2", str(img)])
            score = DL.frame_score(img) + (0.08 if EC.canon(str(sh.get("section", ""))) in ("chorus", "drop") else 0)
            if i == 0 and len(p.shots) > 3:
                score -= 0.05  # the intro is rarely the best image
            cands.append({"thumb": str(img), "score": round(score, 3), "shot": sh["id"], "t": tsec(sh["start"]) + t})
    if not cands:
        die("no frame found (check --at)")
    cands.sort(key=lambda c: -c["score"])
    SRC.contact_sheet(cands[:8], p.root / "refs" / "thumb_candidates.jpg", work / "sheet", _sheet_font())
    best = cands[0]
    tc = p.sb.get("title_card") or {}
    title = a.title or tc.get("title") or p.sb.get("title") or p.root.name
    artist = tc.get("artist") or (p.sb.get("poster") or {}).get("artist") or ""
    vertical = H > W
    tw, th = (1280, 720) if not vertical else (1080, 1920)
    font = FT.resolve(p.sb.get("font"), "Be Vietnam Pro" if LY.has_font("Be Vietnam Pro") else "Arial")
    display = FT.resolve(p.sb.get("display_font"), "Anton" if LY.has_font("Anton") else font)
    Renderer._sync_fonts(work / "fonts")
    (work / "t.ass").write_text(DL.thumb_ass(tw, th, title, artist, display, font, p.sb.get("accent", "#FFD24D"), vertical),
                                encoding="utf-8-sig")
    ramp = "clip((Y/H-0.40)/0.60,0,1)" if not vertical else "clip((0.42-Y/H)/0.42,0,1)"  # soft dark fade behind the title
    shade = f"format=yuv444p,geq=lum='lum(X,Y)*(1-0.55*{ramp})':cb='cb(X,Y)':cr='cr(X,Y)'"
    out = p.out / f"thumb_{fmt.replace(':', 'x')}.jpg"
    p.out.mkdir(exist_ok=True)
    run(["ffmpeg", "-v", "error", "-y", "-i", str(Path(best["thumb"]).resolve()), "-vf",
         f"scale={tw}:{th}:force_original_aspect_ratio=increase:flags=lanczos,crop={tw}:{th},eq=saturation=1.12:contrast=1.05,"
         f"{shade},subtitles=t.ass:fontsdir=fonts", "-q:v", "2", str(out.resolve())], cwd=work)
    print(f"[mv] {out}  (frame {best['shot']} @ {fmt_t(best['t'])}, score {best['score']}) · other picks: "
          f"refs/thumb_candidates.jpg (use --at m:ss)")
    return out


def cmd_deliver(a):
    """Everything to publish, in one go: each platform version (full + short cut), SRT captions, thumbnails,
    credits + a description draft, and QA of every file -> out/deliver.md."""
    p = Project(a.project)
    p.validate()
    slug = p.sb.get("slug") or p.root.name
    s0, e1 = tsec(p.shots[0]["start"]), tsec(p.shots[-1]["end"])
    dur = e1 - s0
    if p.sb.get("platforms"):
        pl = PL.plan(p.sb["platforms"], dur)
        versions = list(pl["versions"])
        best = pl["best_cut_sec"] or 60
        want_short = dur > best * 1.2 and any(ASPECT_V(f) for f in versions)
    else:
        versions, best, want_short = [str(p.sb.get("format", "9:16"))], 60, False
    cut = a.cut or p.sb.get("short_cut")
    if want_short and not cut:
        win = DL.short_window(p.shots, min(best, 45), EC.canon)
        cut = f"{win[0]:.2f}-{win[1]:.2f}" if win else None
    made = []
    for fmt in versions:
        base = argparse.Namespace(project=a.project, mode=a.mode, encoder=a.encoder, jobs=None, force=False,
                                  format=fmt, cut=None, exact=False)
        cmd_render(base)
        made.append(_out_video(Project(a.project), a.mode, fmt))
        made.append(cmd_thumbnail(argparse.Namespace(project=a.project, format=fmt, mode=a.mode, at=None, title=None)))
        if cut and ASPECT_V(fmt):
            cmd_render(argparse.Namespace(**{**vars(base), "cut": cut}))
    cuts = sorted(p.out.glob(f"{slug}_cut*_{a.mode}_*.mp4"))
    made += [c for c in cuts if c not in made]
    srt = _write_srt(p)
    if srt:
        made.append(srt)
    for c in cuts:
        m = re.search(r"_cut(\d+)-(\d+)_", c.name)
        s2 = _write_srt(p, float(m.group(1)), float(m.group(2)), f"{slug}_cut{m.group(1)}-{m.group(2)}.srt") if m else None
        if s2 and s2 not in made:
            made.append(s2)
    cred = write_credits(p)
    tc = p.sb.get("title_card") or {}
    desc = p.out / "description.txt"
    lines = p.lyric_lines()
    desc.write_text("\n".join([f"{tc.get('title') or p.sb.get('title', slug)}" + (f" - {tc['artist']}" if tc.get("artist") else ""),
                               "", "(write 1-2 lines about the song here, in the audience's language; add hashtags)", "",
                               *(["Lyrics:", *[str(l["text"]) for l in lines], ""] if lines else []),
                               cred.read_text(encoding="utf-8")]), encoding="utf-8")
    made += [cred, desc]
    report = ["# Delivery - " + str(p.sb.get("title", slug)), ""]
    for f in [m for m in made if m and Path(m).suffix == ".mp4"]:
        w = _qa_file(p, Path(f))
        report += [f"- **{Path(f).name}**" + (" ✅" if not w else "")] + [f"  - ⚠ {x}" for x in w]
    report += ["", "Other files:"] + [f"- {Path(m).name}" for m in made if m and Path(m).suffix != ".mp4"]
    (p.out / "deliver.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"[mv] delivery ready in {p.out} - summary: {p.out / 'deliver.md'}")


def ASPECT_V(fmt: str) -> bool:
    w, h = FORMATS.get(fmt, (1, 1))
    return h > w


def cmd_stills(a):
    """Shot ideas from a few images: the most interesting details of each image (faces, texture, contrast) as
    numbered crops + ready-made `camera:` layers, so one poster becomes several different shots."""
    p = Project(a.project)
    ids = [x for x in (a.only.split(",") if a.only else p.sources) if p.source_file(x)
           and p.source_file(x).suffix.lower() in IMAGE_EXT]
    if not ids:
        die("no image sources (declare your poster / photos under sources:)")
    for sid in ids:
        f = p.source_file(sid)
        pts = FG.detail_points(f, a.n)
        work = p.build / "stills" / sid
        work.mkdir(parents=True, exist_ok=True)
        W, H = FG.probe_wh(f)
        cands = []
        for i, (x, y, z, why) in enumerate(pts, 1):
            cw, ch = int(W / z), int(H / z)
            cx, cy = int(min(max(x * W - cw / 2, 0), W - cw)), int(min(max(y * H - ch / 2, 0), H - ch))
            out = work / f"d{i}.jpg"
            run(["ffmpeg", "-v", "error", "-y", "-i", str(f), "-vf", f"crop={cw}:{ch}:{cx}:{cy},scale=320:-2",
                 "-frames:v", "1", str(out)])
            cands.append({"thumb": str(out)})
            print(f"  {i}. {sid} detail [{x:.2f}, {y:.2f}, {z:.1f}] ({why}) -> "
                  f"{{src: {sid}, camera: {{detail: [{x:.2f}, {y:.2f}, {z:.1f}]}}}}")
        sheet = p.root / "refs" / f"stills_{sid}.jpg"
        sheet.parent.mkdir(exist_ok=True)
        SRC.contact_sheet(cands, sheet, work / "sheet", _sheet_font())
        print(f"[mv] {sid}: {len(pts)} details -> {sheet}  (plus whole-frame moves: push, pull, pan-left/right/up/down, drift"
              + ("; `parallax: true` for 2.5D depth" if True else "") + ")")


def cmd_check(a):
    p = Project(a.project)
    p.validate()
    if a.genre:
        p.sb["genre"] = a.genre
    res = EC.check(p.sb, p.shots, p.beats, p.downbeats, p.sb.get("lang", "en"))
    if not p.beats:
        print("[mv] (no analysis.json - beat checks skipped; run: mv analyze <project>)")
    print("\n".join(EC.report_md(res)))
    for w in PL.check(p.sb, p.shots, tsec(p.shots[-1]["end"]) - tsec(p.shots[0]["start"]), p.sb.get("lang", "en")):
        print(f"- ⚠ {w}")
    for w in footage_warnings(p):
        print(f"- ⚠ {w}")


def cmd_genres(a):
    for k, g in EC.load_genres().items():
        asl = g.get("asl") or {}
        print(f"  {k:<8} {g.get('name', '')}")
        print(f"           verse {asl.get('verse')}s · chorus {asl.get('chorus')}s · min {g.get('min_shot')}s · "
              f"cut on {g.get('cut_on')} · presets: {', '.join(g.get('presets') or [])}")


def _pcm(f: Path, sr: int = 8000):
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                       capture_output=True)
    if r.returncode != 0 or not r.stdout:
        die(f"no audio track in {f.name} (lip-sync matching needs the clip's own sound)")
    return np.frombuffer(r.stdout, dtype=np.float32)


def _flux(x, hop: int = 80, n: int = 512, bands: int = 24):
    """Band-wise spectral flux at 100 frames/s (8 kHz input), z-scored per band."""
    import numpy as np
    frames = max(0, (len(x) - n) // hop)
    if frames < 50:
        die("audio too short to match (needs > 0.5 s)")
    out = []
    win = np.hanning(n).astype(np.float32)
    edges = np.unique(np.geomspace(2, n // 2, bands + 1).astype(int))
    for c in range(0, frames, 4000):  # chunked to keep memory small on long songs
        idx = np.arange(n)[None, :] + hop * np.arange(c, min(frames, c + 4000))[:, None]
        spec = np.abs(np.fft.rfft(x[idx] * win, axis=1))
        out.append(np.stack([spec[:, e0:e1].sum(1) for e0, e1 in zip(edges, edges[1:])], 1))
    lb = np.log1p(np.concatenate(out) * 10)
    fl = np.maximum(0, np.diff(lb, axis=0))
    return (fl - fl.mean(0)) / (fl.std(0) + 1e-6)


def audio_offset(song: Path, clip: Path) -> tuple[float, float]:
    """Offset (s) such that clip_time = song_time + offset, and a confidence ratio (best / runner-up peak)."""
    import numpy as np
    a, b = _flux(_pcm(song)), _flux(_pcm(clip))
    N = 1 << (len(a) + len(b)).bit_length()
    corr = np.fft.irfft((np.conj(np.fft.rfft(a, N, axis=0)) * np.fft.rfft(b, N, axis=0)).sum(1), N)
    lags = np.arange(N)
    lags[lags > N // 2] -= N
    ov = np.minimum(len(a), len(b) - lags) - np.maximum(0, -lags)
    need = min(500, int(0.5 * min(len(a), len(b))))
    score = np.where(ov >= need, corr / np.sqrt(np.maximum(ov, 1)), -np.inf)
    best = int(np.argmax(score))
    far = np.abs(lags - lags[best]) > 30
    second = float(np.max(np.where(far, score, -np.inf)))
    conf = float(score[best] / second) if second > 0 else 9.9
    frac = 0.0
    if 0 < best < N - 1 and np.isfinite(score[best - 1]) and np.isfinite(score[best + 1]):
        y0, y1, y2 = score[best - 1], score[best], score[best + 1]
        den = y0 - 2 * y1 + y2
        frac = float(0.5 * (y0 - y2) / den) if den else 0.0
    return float((lags[best] + frac) / 100.0), conf


def cmd_sync(a):
    p = Project(a.project)
    f = p.source_file(a.source)
    if f is None or f.suffix.lower() in IMAGE_EXT:
        die(f"source {a.source} has no video file yet (mv fetch / mv ingest first)")
    audio = p.root / str(p.sb.get("audio") or "")
    if not audio.is_file():
        die(f"song audio not found: {audio}")
    off, conf = audio_offset(audio, f)
    print(f"[mv] {a.source}: clip time = song time {'+' if off >= 0 else '-'} {abs(off):.2f} s  (confidence {conf:.2f})")
    if conf < 1.1:
        print("[mv] WARN: weak match - is this clip really shot to this song's playback? Check by eye in a proxy render.")
    picks = p.root / "picks.yaml"
    cur = (yaml.safe_load(picks.read_text(encoding="utf-8")) or {}) if picks.exists() else {}
    cur[a.source] = {**(cur.get(a.source) or {}), "sync": round(off, 3)}
    picks.write_text("# written by mv pick / mv ingest / mv sync - merged over storyboard sources\n" +
                     yaml.safe_dump(cur, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
    print(f"[mv] wrote sync: {off:.3f} to {picks}  - use layers like {{src: {a.source}, lipsync: true}}")


def _duration(f: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        die(f"cannot read duration of {f}")


def cmd_auto(a):
    """Lyric video in one step: lyrics.yaml + audio + a template preset -> storyboard.yaml (scenes change with the song)."""
    root = Path(a.project)
    sbp = root / "storyboard.yaml"
    if sbp.exists() and not a.force:
        die(f"{sbp} exists - pass --force to replace it (copy it first if you edited it)")
    presets = load_presets()
    plan = None
    if getattr(a, "plan", None):
        try:
            plan = AS.load_plan(Path(a.plan))
        except (OSError, ValueError) as e:
            die(str(e))
        a.template = a.template or plan.get("preset")
        a.genre = a.genre or plan.get("genre")
        a.format = plan.get("format", a.format)
    a.plan_data = plan
    if not a.template:
        die("give --template <preset> (or `preset:` in the plan)")
    pr = presets.get(a.template)
    if not pr:
        die(f"unknown template '{a.template}' - lyric templates: "
            + ", ".join(k for k, v in presets.items() if v.get("kind") == "lyric-template"))
    footage = pr.get("kind") != "lyric-template"
    if footage and not a.genre:
        a.genre = next((g for g, v in EC.load_genres().items() if a.template in (v.get("presets") or [])), "pop")
        print(f"[mv] footage MV: genre {a.genre} (set --genre to change)")
    audio = Path(a.audio) if a.audio else next((f for f in sorted((root / "audio").glob("*"))
                                                if f.suffix.lower() in (".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac")), None)
    if not audio or not audio.exists():
        die(f"no audio in {root / 'audio'} (or pass --audio)")
    lf = root / "lyrics.yaml"
    if not lf.exists() and not footage:
        die(f"{lf} not found - run mv align / mv lyrics fetch first")
    lines = sorted((yaml.safe_load(lf.read_text(encoding="utf-8")) or {}).get("lines", []), key=lambda l: float(l["start"])) \
        if lf.exists() else []
    if not lines and not footage:
        die("lyrics.yaml has no lines")
    dur = _duration(audio)
    an = root / "analysis.json"
    data = json.loads(an.read_text(encoding="utf-8")) if an.exists() else {}
    beats, secs = data.get("beats") or [], data.get("sections") or []
    if footage:
        return _auto_footage(a, root, audio, dur, lines, beats, secs)

    def snap(t):
        if not beats:
            return round(t, 3)
        b = min(beats, key=lambda x: abs(x - t))
        return round(b if abs(b - t) < 0.45 else t, 3)

    def label(ln):
        if ln.get("section"):
            return str(ln["section"]).lower()
        mid = (float(ln["start"]) + float(ln["end"])) / 2
        for x in secs:
            if x["start"] <= mid < x["end"]:
                return "chorus" if x.get("energy_rel", 0) > 0.8 else "verse"
        return "verse"

    groups: list[list[dict]] = []
    for ln in lines:
        if not groups or label(ln) != label(groups[-1][0]) or len(groups[-1]) >= a.lines:
            groups.append([ln])
        else:
            groups[-1].append(ln)
    first = float(lines[0]["start"])
    cuts, names = [0.0], []
    if first > 3.0:
        cuts.append(snap(first - 0.4))
        names.append("intro")
    for g, nxt in zip(groups, groups[1:] + [None]):
        names.append(label(g[0]))
        if nxt is not None:
            t = snap((float(g[-1]["end"]) + float(nxt[0]["start"])) / 2)
            if t - cuts[-1] >= 1.0:
                cuts.append(t)
            else:
                names.pop()
    cuts.append(round(dur, 3))
    names = names[:len(cuts) - 1]
    shots = [{"id": f"S{i + 1:02d}", "start": s, "end": e, "section": n}
             for i, (s, e, n) in enumerate(zip(cuts, cuts[1:], names))]
    sb = {"title": a.title or root.name, "preset": a.template, "lang": a.lang,
          "audio": audio.relative_to(root).as_posix() if audio.is_relative_to(root) else str(audio),
          "format": a.format, "lyrics_file": "lyrics.yaml"}
    if a.theme:
        sb["theme"] = a.theme
    if a.title or a.artist:
        sb["title_card"] = ({"artist": a.artist or "", "title": a.title or "", "style": "center", "start": 0.5,
                             "dur": round(min(5.0, first - 0.9), 2)} if first >= 3.0 else
                            {"artist": a.artist or "", "title": a.title or "", "style": "minimal", "start": 0.3, "dur": 4})
    sb["shots"] = shots
    sbp.write_text(f"# generated by mv auto --template {a.template} - edit freely: change sections, add `layers:` with your\n"
                   f"# own footage (shots without layers use the template's generated scenes), `theme:`, `palette:`.\n" +
                   yaml.safe_dump(sb, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
    print(f"[mv] wrote {sbp}: {len(shots)} scenes over {fmt_t(dur)} with template {a.template}"
          + ("" if beats else " (no analysis.json - cuts not snapped to beats; run mv analyze first for that)"))


def _auto_footage(a, root: Path, audio: Path, dur: float, lines: list, beats: list, secs: list):
    """Footage MV skeleton cut to the genre grammar: sections from lyrics (or energy), shots of the genre's average length
    per section (the last chorus faster), snapped to beats, every shot `layers: auto` + `look_for` to fill in."""
    g = EC.load_genres().get(a.genre)
    if not g:
        die(f"unknown genre '{a.genre}' - one of {', '.join(EC.load_genres())}")
    asl = g.get("asl") or {}

    def snap(t, tol=0.3):
        if not beats:
            return t
        b = min(beats, key=lambda x: abs(x - t))
        return b if abs(b - t) < tol else t

    blocks = []  # (start, end, section label, lyric lines)
    if lines:
        groups: list[list] = []  # consecutive lyric lines with the same section label
        for ln in lines:
            lab = str(ln.get("section") or "verse").lower()
            if groups and groups[-1][0] == lab:
                groups[-1][1].append(ln)
            else:
                groups.append([lab, [ln]])
        first = float(lines[0]["start"])
        if first > 2.5:
            blocks.append([0.0, first - 0.3, "intro", []])
        for i, (lab, lns) in enumerate(groups):
            start = blocks[-1][1] if blocks else 0.0
            end = dur if i == len(groups) - 1 else                 (float(lns[-1]["end"]) + float(groups[i + 1][1][0]["start"])) / 2  # midway into the gap
            blocks.append([start, end, lab, lns])
    else:
        for x in secs or [{"start": 0, "end": dur, "energy_rel": 0.6}]:
            e = x.get("energy_rel", 0.6)
            blocks.append([float(x["start"]), float(x["end"]), "chorus" if e > 0.8 else ("bridge" if e < 0.45 else "verse"), []])
        blocks[0][0], blocks[-1][1] = 0.0, dur
    for i in range(1, len(blocks)):  # section changes land on a beat
        blocks[i - 1][1] = blocks[i][0] = snap(blocks[i][0], 0.45)
    last_chorus = max((i for i, b in enumerate(blocks) if EC.canon(b[2]) in ("chorus", "drop")), default=-1)
    plan = getattr(a, "plan_data", None) or {}
    seen: dict[str, int] = {}
    last_of = {b[2]: i for i, b in enumerate(blocks)}
    shots = []
    for bi, (s, e, lab, lns) in enumerate(blocks):
        seen[lab] = seen.get(lab, 0) + 1
        sp = AS.section_plan(plan, lab, seen[lab], last_of[lab] == bi and seen[lab] > 1) if plan else {}
        rng = asl.get(EC.canon(lab) or "verse") or asl.get("verse") or [2, 4]
        target = float(sp.get("shot_len") or (rng[0] + rng[1]) / 2 * (0.8 if bi == last_chorus else 1.0))
        if bi == 0 and a.format == "9:16" and not sp.get("shot_len"):
            target = min(target, 2.5)  # vertical video: the hook lands inside the first 3 s
        n = max(1, round((e - s) / target))
        cuts = [s] + [snap(s + (e - s) * k / n) for k in range(1, n)] + [e]
        k_in, look_state = 0, {}
        for a0, b0 in zip(cuts, cuts[1:]):
            if b0 - a0 < 0.25:
                continue
            words = [str(l["text"]) for l in lns if float(l["start"]) < b0 and float(l["end"]) > a0]
            sh = {"id": f"S{len(shots) + 1:02d}", "start": round(a0, 3), "end": round(b0, 3), "section": lab,
                  "layers": "auto", "look_for": f"TODO concrete visual for: {words[0]}" if words else f"TODO {lab} visual"}
            if words:
                sh["lyric"] = words[0]
            if sp:
                AS.plan_shot(sh, sp, k_in, plan.get("performance"), look_state)
            k_in += 1
            shots.append(sh)
    for x, y in zip(shots, shots[1:]):
        x["end"] = y["start"]
    sb = {"title": a.title or root.name, "genre": a.genre, "preset": a.template, "lang": a.lang,
          "audio": audio.relative_to(root).as_posix() if audio.is_relative_to(root) else str(audio), "format": a.format}
    if lines:
        sb["lyrics_file"] = "lyrics.yaml"
    if a.title or a.artist:
        sb["title_card"] = {"artist": a.artist or "", "title": a.title or "", "start": 0.4, "dur": 3.5}
    if plan:  # everything except the per-section / per-shot parts goes to the storyboard top level
        for k, v in plan.items():
            if k not in ("sections", "shots", "performance"):
                sb[k] = v
        if plan.get("performance"):
            sb.setdefault("sources", {}).setdefault(plan["performance"], {"note": "performance (shot to playback): mv sync"})
        over = plan.get("shots") or {}
        for sh in shots:
            sh.update(over.get(sh["id"]) or {})
    sb["shots"] = shots
    todo = sum(1 for sh in shots if str(sh.get("look_for", "")).startswith("TODO"))
    src = f"plan {Path(a.plan).name}" if plan else f"--template {a.template} --genre {a.genre}"
    (root / "storyboard.yaml").write_text(
        f"# generated by mv auto ({src}): shots cut to the genre grammar.\n"
        + ("# Edit the plan and re-run with --force, or edit this file directly.\n" if plan else
           "# Next: replace every `look_for: TODO ...` with a concrete visual description (English works best;\n"
           "# a lyric is a metaphor - describe what the camera should SEE), add role/size, then: mv match <project>.\n")
        + yaml.safe_dump(sb, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
    print(f"[mv] wrote {root / 'storyboard.yaml'}: {len(shots)} shots ({a.genre}) over {fmt_t(dur)}"
          + (f" - {todo} shots still need `look_for`" if todo else "") + f" - next: mv match {root}")


def cmd_credits(a):
    p = Project(a.project)
    print(write_credits(p))


def write_credits(p: Project) -> Path:
    used = []
    for sh in p.shots:
        for ly in sh.get("layers") or []:
            if ly.get("src") and ly["src"] not in used:
                used.append(ly["src"])
    lines = [f"Credits - {p.sb.get('title', p.root.name)}", ""]
    for sid in used:
        s = p.sources.get(sid) or {}
        if s.get("provider") == "own" or not (s.get("url") or s.get("page")):
            continue
        lines.append(f"- {s.get('title') or sid} by {s.get('creator') or 'unknown'} ({s.get('provider', 'web')}) - "
                     f"{s.get('rights') or 'licence unknown'} - {s.get('page') or s.get('url')}")
    if len(lines) == 2:
        lines.append("(no third-party footage)")
    p.out.mkdir(exist_ok=True)
    out = p.out / "credits.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def cmd_lyrics(a):
    root = Path(a.project)
    dur = None
    sbp = root / "storyboard.yaml"
    sb = yaml.safe_load(sbp.read_text(encoding="utf-8")) if sbp.exists() else {}
    if sb.get("audio") and (root / sb["audio"]).exists():
        try:
            dur = float(_run_out(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                  str(root / sb["audio"])]))
        except ValueError:
            pass
    rec = SRC.lrclib(a.artist, a.title, a.album, dur)
    if not rec:
        die("no synced lyrics on LRCLIB - use `mv analyze --lyrics` + `mv align` instead")
    lines = SRC.parse_lrc(rec["syncedLyrics"], dur)
    print(f"[mv] LRCLIB: {rec.get('artistName')} - {rec.get('trackName')} ({rec.get('duration')}s), {len(lines)} lines")
    if dur and rec.get("duration") and abs(rec["duration"] - dur) > 3:
        print(f"[mv] WARN: LRCLIB track is {rec['duration']}s but your audio is {dur:.0f}s - another edit/version? "
              "Check the timing in a proxy render, or shift with song_start.")
    (root / "lyrics.txt").write_text("\n".join(l["text"] for l in lines) + "\n", encoding="utf-8")
    (root / "lyrics.yaml").write_text("# from LRCLIB (line timing; word timing is spread evenly)\n" +
                                      yaml.safe_dump({"lines": lines}, allow_unicode=True, sort_keys=False, width=200),
                                      encoding="utf-8")
    print(f"[mv] wrote lyrics.yaml + lyrics.txt  (storyboard: lyrics_file: lyrics.yaml). Lyrics are copyrighted - "
          "use them for the user's own edit only.")


def _run_out(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()


def cmd_fetch(a):
    p = Project(a.project)
    (p.root / "sources").mkdir(exist_ok=True)
    for sid, info in p.sources.items():
        info = info or {}
        if not info.get("url") or p.source_file(sid):
            continue
        if SRC.is_direct(info["url"], info.get("provider")):  # stock/CC file URL -> plain download
            print(f"[mv] downloading {sid} <- {info.get('provider', 'url')}")
            try:
                got = SRC.direct_download(info["url"], p.root / "sources" / sid, a.max_mb)
                print(f"     -> {got.name}")
            except Exception as e:
                print(f"[mv] WARN: failed to fetch {sid}: {e}")
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


def cmd_doctor(a):
    try:
        if a.use_python:
            return RT.use_python(a.use_python)
        if a.use_shared:
            return RT.use_shared()
        if a.remove_local_venv:
            return RT.remove_local_venv()
        if a.use_ffmpeg:
            return RT.use_ffmpeg(a.use_ffmpeg)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as e:
        die(str(e))
    if a.scan == "machine":  # read-only, only after the user agreed
        sc = RT.scan("machine")
        DR.save_section("reuse_scan", sc)
        print(json.dumps(sc, ensure_ascii=False, indent=1)) if a.json else RT.print_scan(sc)
        return
    if a.install:
        DR.install([x.strip() for x in a.install.split(",") if x.strip()])
    d = DR.build(run_bench=not a.quick)
    sc = RT.scan("project")
    d["reuse_scan"] = sc
    DR.save_section("reuse_scan", sc)
    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=1))
    else:
        DR.print_report(d)
        print()
        RT.print_scan(sc)
        print("\n(For tools installed elsewhere on this machine, ask the user before running: mv doctor --scan machine)")


def cmd_presets(a):
    pr = load_presets()
    for title, kind in (("Footage style presets (preset: <name>)", None),
                        ("Lyric-video templates (mv auto <p> --template <name>, or preset: <name>)", "lyric-template")):
        print(title)
        for k, v in pr.items():
            if v.get("kind") == kind:
                th = ", ".join(v.get("themes") or {})
                print(f"  {k:<18} {v.get('description', '')}" + (f"  [themes: {th}]" if th else ""))


def apply_cut(p: "Project", cut: str, snap: bool = True) -> tuple[float, float]:
    """Short version of the same edit (e.g. the chorus for TikTok / Reels / Shorts): keep the shots inside
    `m:ss-m:ss`, trim the first and last ones, shift in-points so the picture stays as edited. The cut points move to
    the nearest bar line (unless `--exact`) and the audio fades in / out, so the short version starts and ends musically."""
    a0, _, b0 = str(cut).partition("-")
    a0, b0 = tsec(a0), tsec(b0)
    song_end = tsec(p.shots[-1]["end"])
    if snap:
        bars = p.downbeats or p.beats[::4]
        a1, b1 = DL.snap_cut(a0, b0, bars)
        if (a1, b1) != (a0, b0):
            print(f"[mv] cut snapped to bars: {fmt_t(a0)}-{fmt_t(b0)} -> {fmt_t(a1)}-{fmt_t(b1)} (--exact keeps yours)")
        a0, b0 = a1, b1
    keep = [sh for sh in p.shots if tsec(sh["end"]) > a0 + 0.05 and tsec(sh["start"]) < b0 - 0.05]
    if b0 <= a0 or not keep:
        die(f"--cut {cut}: no shots in that range")
    first, last = keep[0], keep[-1]
    shift = a0 - tsec(first["start"])
    if shift > 0:
        for ly in first.get("layers") or []:
            if isinstance(ly, dict) and ly.get("src") and ly.get("lipsync") in (None, False):
                ly["in"] = round(tsec(ly.get("in", 0)) + shift * float(ly.get("speed", 1) or 1), 3)
        first["start"] = a0
    last["end"] = min(tsec(last["end"]), b0)
    last.pop("transition", None)
    p.shots[:] = keep
    p._resolve_lipsync()
    p.sb["slug"] = f"{p.sb.get('slug') or p.root.name}_cut{int(a0)}-{int(b0)}"
    if a0 > 0.05:
        p.sb["audio_fade_in"] = max(float(p.sb.get("audio_fade_in") or 0), 0.25)
    if b0 < song_end - 0.05:
        p.sb["audio_fade_out"] = max(float(p.sb.get("audio_fade_out") or 0), 1.2)
        p.sb["fade_out"] = max(float(p.sb.get("fade_out", 1.0) or 0), 0.8)
    print(f"[mv] cut {fmt_t(a0)}-{fmt_t(b0)}: {len(keep)} shots")
    return a0, b0


def cmd_platforms(a):
    names, dur = a.names, None
    if a.project:
        p = Project(a.project)
        names = names or p.sb.get("platforms")
        dur = tsec(p.shots[-1]["end"]) - tsec(p.shots[0]["start"])
    if not names:
        data = PL.load()
        print("| key | platform | format | size | max | best | hook | safe top/bottom/left/right |")
        for k, v in data.items():
            if k != "groups":
                print(f"| {k} | {v['name']} | {v['format']} | {v['size'][0]}x{v['size'][1]} | {v['max_sec']}s | "
                      f"{v['best_sec'][0]}-{v['best_sec'][1]}s | {v['hook_sec']}s | {'/'.join(f'{x:.0%}' for x in v['safe'])} |")
        print("groups: " + ", ".join(f"{g} = {'+'.join(ks)}" for g, ks in (data.get("groups") or {}).items()))
        print("[mv] plan for a set: mv platforms --for tiktok,youtube   (or set `platforms:` in the storyboard)")
        return
    try:
        print("\n".join(PL.plan_text(PL.plan(names, dur))))
    except ValueError as e:
        die(str(e))


def cmd_render(a):
    p = Project(a.project)
    if getattr(a, "format", None):
        p.sb["format"] = a.format
    if getattr(a, "cut", None):
        apply_cut(p, a.cut, snap=not getattr(a, "exact", False))
    p.validate()
    prof = DR.load_profile()
    jobs = a.jobs or prof.get("jobs") or max(1, (os.cpu_count() or 4) // 4)
    enc = a.encoder
    if enc == "auto":
        enc = prof.get("encoder", "libx264")
        if a.mode == "final":
            print(f"[mv] encoder auto -> {enc}" + ("" if DR.PROFILE.exists() else " (run `mv doctor` to detect GPU encoders)"))
    r = Renderer(p, a.mode, enc, jobs, a.force)
    lead = p.apply_cut_lead(r.fps)
    if lead:
        print(f"[mv] cut_lead: picture cuts {lead * 1000:.0f} ms before the beat")
    out = r.run_all()
    print(f"[mv] done -> {out}")
    if a.mode == "final":
        print(f"[mv] credits -> {write_credits(p)}  (paste into the video description)")


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
    s.add_argument("--lyrics", action="store_true"); s.add_argument("--model", default="auto")
    s.add_argument("--language", default="vi"); s.add_argument("--sections", type=int)
    s.add_argument("--verbose", action="store_true")
    s.add_argument("--genre-model", action="store_true", help="also run the AudioSet genre/mood model (~350 MB first use)")
    s.set_defaults(fn=cmd_analyze)
    s = sub.add_parser("review"); s.add_argument("project"); s.add_argument("--verbose", action="store_true")
    s.set_defaults(fn=cmd_review)
    s = sub.add_parser("proof", help="one labelled frame per shot in a single sheet")
    s.add_argument("project"); s.add_argument("--mode", choices=list(MODES), default="proxy")
    s.add_argument("--format", choices=list(FORMATS)); s.add_argument("--only", help="comma-separated shot ids")
    s.set_defaults(fn=cmd_proof)
    s = sub.add_parser("status", help="project state + next step"); s.add_argument("project"); s.set_defaults(fn=cmd_status)
    s = sub.add_parser("stills", help="detail crops + camera moves to make several shots from each image")
    s.add_argument("project"); s.add_argument("--only"); s.add_argument("-n", type=int, default=5); s.set_defaults(fn=cmd_stills)
    s = sub.add_parser("qa", help="check rendered files before publishing")
    s.add_argument("project"); s.add_argument("--mode", choices=list(MODES), default="final"); s.add_argument("--file")
    s.set_defaults(fn=cmd_qa)
    s = sub.add_parser("srt", help="lyrics as SubRip captions"); s.add_argument("project"); s.add_argument("--cut")
    s.set_defaults(fn=cmd_srt)
    s = sub.add_parser("thumbnail", help="best frame + title -> out/thumb_<aspect>.jpg")
    s.add_argument("project"); s.add_argument("--format", choices=list(FORMATS)); s.add_argument("--at")
    s.add_argument("--title"); s.add_argument("--mode", choices=list(MODES), default="final"); s.set_defaults(fn=cmd_thumbnail)
    s = sub.add_parser("deliver", help="all platform versions + short cut + srt + thumbnails + description + QA")
    s.add_argument("project"); s.add_argument("--mode", choices=list(MODES), default="final")
    s.add_argument("--encoder", default="auto"); s.add_argument("--cut", help="short version m:ss-m:ss (default: first chorus)")
    s.set_defaults(fn=cmd_deliver)
    s = sub.add_parser("context", help="planning digest for this project (instead of reading every reference)")
    s.add_argument("--project"); s.add_argument("--type", choices=["mv", "lyric", "poster"], default="mv")
    s.add_argument("--genre"); s.add_argument("--platforms"); s.add_argument("--mood"); s.set_defaults(fn=cmd_context)
    s = sub.add_parser("check", help="edit check against the genre's cutting grammar")
    s.add_argument("project"); s.add_argument("--genre"); s.set_defaults(fn=cmd_check)
    s = sub.add_parser("genres"); s.set_defaults(fn=cmd_genres)
    s = sub.add_parser("sync", help="audio-match a performance clip to the song -> picks.yaml sync offset")
    s.add_argument("project"); s.add_argument("source"); s.set_defaults(fn=cmd_sync)
    s = sub.add_parser("auto", help="lyric video storyboard from lyrics.yaml + a template")
    s.add_argument("project"); s.add_argument("--template"); s.add_argument("--theme")
    s.add_argument("--plan", help="plan.yaml: per-section look_for / role / size / fx -> every shot (reference/plan-template.yaml)")
    s.add_argument("--format", default="9:16", choices=list(FORMATS)); s.add_argument("--audio")
    s.add_argument("--title"); s.add_argument("--artist"); s.add_argument("--lang", default="en")
    s.add_argument("--lines", type=int, default=2, help="max lyric lines per scene (scene variety)")
    s.add_argument("--genre", help="footage presets: cutting grammar (default: the genre that lists the preset)")
    s.add_argument("--force", action="store_true"); s.set_defaults(fn=cmd_auto)
    s = sub.add_parser("fonts", help="pack | list | get | check | preview")
    s.add_argument("action", nargs="?", default="pack", choices=["pack", "list", "get", "check", "preview"])
    s.add_argument("args", nargs="*", help="font specs (get/check) or project (preview)")
    s.add_argument("--lang"); s.add_argument("--tag"); s.add_argument("--text"); s.add_argument("--project")
    s.add_argument("--fonts", help="comma-separated specs for preview"); s.add_argument("--bg", help="background image for preview")
    s.set_defaults(fn=cmd_fonts)
    s = sub.add_parser("palette"); s.add_argument("image"); s.add_argument("-n", type=int, default=8)
    s.set_defaults(fn=cmd_palette)
    s = sub.add_parser("find", help="licence-aware footage search with a numbered contact sheet")
    s.add_argument("query", nargs="?"); s.add_argument("--project"); s.add_argument("--slot", help="name for this search (e.g. the source id)")
    s.add_argument("--describe", help="visual description to rank by (default: the query)")
    s.add_argument("--avoid", help="what should NOT be in the picture (e.g. 'text, logo, watermark')")
    s.add_argument("--rank", action="store_true", help="order by semantic match (SigLIP 2, local, free)")
    s.add_argument("--deep", type=int, default=0, help="scan the top N YouTube results for the matching moment")
    s.add_argument("--links", help="file or space-separated URLs (TikTok, Facebook, Instagram, YouTube ...) to rank")
    s.add_argument("--model", help="matching model: base | large | a Hugging Face id")
    s.add_argument("--type", choices=["video", "image"], default="video")
    s.add_argument("--providers", help=",".join(SRC.PROVIDERS)); s.add_argument("--orient", choices=["portrait", "landscape"])
    s.add_argument("-n", type=int, default=8); s.set_defaults(fn=cmd_find)
    s = sub.add_parser("scout", help="search + rank + deep-scan candidates for every source with `search:`")
    s.add_argument("project"); s.add_argument("--providers"); s.add_argument("--orient", choices=["portrait", "landscape"])
    s.add_argument("-n", type=int, default=8, help="results per provider and phrasing")
    s.add_argument("--keep", type=int, default=12, help="candidates kept per source after ranking")
    s.add_argument("--deep", type=int, default=4); s.add_argument("--only", help="comma-separated source ids")
    s.add_argument("--model"); s.set_defaults(fn=cmd_scout)
    s = sub.add_parser("match", help="choose scenes from your footage for shots with `layers: auto`")
    s.add_argument("project"); s.add_argument("--sources", help="comma-separated source ids / prefixes to choose from")
    s.add_argument("--top", type=int, default=4, help="candidates kept per shot"); s.add_argument("--reuse", action="store_true")
    s.add_argument("--sheets", action="store_true", help="one contact sheet of alternatives per shot")
    s.add_argument("--pick", help="switch a shot to another candidate, e.g. S03:2"); s.add_argument("--model")
    s.set_defaults(fn=cmd_match)
    s = sub.add_parser("pick"); s.add_argument("project"); s.add_argument("source"); s.add_argument("candidate", help="slot:n")
    s.add_argument("--section", help="m:ss-m:ss (YouTube: download only this part)"); s.set_defaults(fn=cmd_pick)
    s = sub.add_parser("ingest", help="register your own clips/photos and rank their best moments")
    s.add_argument("project"); s.add_argument("folder"); s.add_argument("--prefix", default="own")
    s.add_argument("--top", type=int, default=24); s.set_defaults(fn=cmd_ingest)
    s = sub.add_parser("credits"); s.add_argument("project"); s.set_defaults(fn=cmd_credits)
    s = sub.add_parser("lyrics", help="synced lyrics from LRCLIB")
    s.add_argument("action", choices=["fetch"]); s.add_argument("project")
    s.add_argument("--artist", required=True); s.add_argument("--title", required=True); s.add_argument("--album")
    s.set_defaults(fn=cmd_lyrics)
    s = sub.add_parser("presets"); s.set_defaults(fn=cmd_presets)
    s = sub.add_parser("demo"); s.add_argument("name", nargs="?", default="story", choices=DEMOS + ["all"])
    s.add_argument("--dir", default="projects"); s.add_argument("--mode", choices=list(MODES), default="proxy")
    s.add_argument("--encoder", default="auto"); s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_demo)
    s = sub.add_parser("align"); s.add_argument("project"); s.add_argument("--start"); s.add_argument("--end")
    s.add_argument("--verbose", action="store_true")
    s.set_defaults(fn=cmd_align)
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("-n", type=int, default=10); s.set_defaults(fn=cmd_search)
    s = sub.add_parser("fetch"); s.add_argument("project"); s.add_argument("--max-height", type=int, default=1080)
    s.add_argument("--max-mb", type=float, default=300, help="skip direct downloads larger than this (0 = no limit)"); s.set_defaults(fn=cmd_fetch)
    s = sub.add_parser("sheet"); s.add_argument("project"); s.add_argument("source")
    s.add_argument("--every", type=float, default=2.0); s.add_argument("--cols", type=int, default=6)
    s.add_argument("--rows", type=int, default=6); s.set_defaults(fn=cmd_sheet)
    s = sub.add_parser("scenes"); s.add_argument("project"); s.add_argument("source"); s.set_defaults(fn=cmd_scenes)
    s = sub.add_parser("platforms", help="platform specs + a production plan (versions, sources, length, safe zones)")
    s.add_argument("--for", dest="names", help="tiktok,reels,facebook_reels,facebook_feed,shorts,youtube | all | vertical")
    s.add_argument("--project", help="use the storyboard's `platforms:` and the song length"); s.set_defaults(fn=cmd_platforms)
    s = sub.add_parser("render"); s.add_argument("project"); s.add_argument("--mode", choices=list(MODES), default="proxy")
    s.add_argument("--format", choices=list(FORMATS), help="render another aspect version of the same edit")
    s.add_argument("--cut", help="render only m:ss-m:ss (the short version for TikTok / Reels / Shorts)")
    s.add_argument("--exact", action="store_true", help="keep --cut points as given (default: snap to the nearest bar)")
    s.add_argument("--encoder", default="auto"); s.add_argument("--jobs", type=int); s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_render)
    s = sub.add_parser("doctor"); s.add_argument("--quick", action="store_true", help="skip the render benchmark")
    s.add_argument("--json", action="store_true"); s.add_argument("--install", help="comma-separated recommendation ids")
    s.add_argument("--scan", choices=["project", "machine"], default="project",
                   help="machine = read-only search for existing envs/FFmpeg/fonts/models (ask the user first)")
    s.add_argument("--use-python", help="reuse an existing complete Python environment (writes runtime.txt)")
    s.add_argument("--use-shared", action="store_true", help="use/create the shared runtime ~/.mv-maker/venv")
    s.add_argument("--remove-local-venv", action="store_true", help="delete this copy's .venv after switching runtime")
    s.add_argument("--use-ffmpeg", help="use this ffmpeg binary's folder for mv-maker only")
    s.set_defaults(fn=cmd_doctor)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
