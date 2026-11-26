"""Delivery helpers: clean short-cut points, output QA (black / frozen frames, A/V sync, loudness, specs), SRT export,
thumbnail frame scoring and title layout. FFmpeg + PyYAML; OpenCV only for thumbnail scoring."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def _ts(sec: float, sep: str = ",") -> str:
    sec = max(0.0, sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}{sep}{int(round((s - int(s)) * 1000)) % 1000:03d}"


# ----------------------------------------------------------------------------------------------- 1. clean cut points
def snap_cut(a0: float, b0: float, bars: list[float], tol: float = 1.5) -> tuple[float, float]:
    """Move a short version's start / end onto the nearest bar line (downbeat) within `tol` seconds, so the music
    starts and ends on a phrase instead of mid-bar."""
    def near(t):
        cands = [b for b in bars if abs(b - t) <= tol]
        return min(cands, key=lambda b: abs(b - t)) if cands else t
    a, b = near(a0), near(b0)
    return (round(a, 3), round(b, 3)) if b - a > 3 else (a0, b0)


def short_window(shots: list[dict], target: float, canon) -> tuple[float, float] | None:
    """Default short version: start where the first chorus / hook / drop starts, run about `target` seconds."""
    first = next((s for s in shots if canon(str(s.get("section", ""))) in ("chorus", "drop")), None)
    if first is None:
        return None
    a = float(first["start"])
    end_song = float(shots[-1]["end"])
    return a, min(end_song, a + target)


# ----------------------------------------------------------------------------------------------- 2. QA
def probe(video: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration,size,bit_rate:stream=codec_type,codec_name,width,height,pix_fmt,r_frame_rate,duration",
                        "-of", "json", str(video)], capture_output=True, text=True)
    return json.loads(r.stdout or "{}")


def scan(video: Path) -> str:
    """One decode pass: black frames, frozen frames, EBU R128 loudness + true peak (log text to parse)."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video),
                        "-vf", "blackdetect=d=0.25:pix_th=0.10,freezedetect=n=0.003:d=0.8",
                        "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.stderr


def parse_scan(log: str) -> dict:
    black = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", log)]
    fs = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", log)]
    fe = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", log)]
    frozen = list(zip(fs, fe + [None] * (len(fs) - len(fe))))
    summary = log.rsplit("Summary:", 1)[-1] if "Summary:" in log else ""
    i = re.search(r"I:\s+(-?[\d.]+) LUFS", summary)
    tp = re.search(r"True peak:\s+Peak:\s+(-?[\d.]+|-inf) dBFS", summary, re.S)
    lra = re.search(r"LRA:\s+([\d.]+) LU", summary)
    return {"black": black, "frozen": frozen,
            "lufs": float(i.group(1)) if i else None,
            "true_peak": (float(tp.group(1)) if tp and tp.group(1) != "-inf" else None),
            "lra": float(lra.group(1)) if lra else None}


def qa_report(info: dict, scan_res: dict, expect_dur: float, shot_at, intended, max_sec: float | None = None) -> list[str]:
    """Warnings for one output. `shot_at(t)` -> shot id, `intended(kind, t0, t1)` -> True when an effect explains it."""
    w = []
    streams = info.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    dur = float((info.get("format") or {}).get("duration") or 0)
    if abs(dur - expect_dur) > 0.25:
        w.append(f"duration {dur:.2f}s, expected {expect_dur:.2f}s")
    if a is None:
        w.append("no audio track")
    elif v.get("duration") and a.get("duration") and abs(float(v["duration"]) - float(a["duration"])) > 0.15:
        w.append(f"audio {float(a['duration']):.2f}s vs video {float(v['duration']):.2f}s - check sync")
    if v and (v.get("codec_name") != "h264" or v.get("pix_fmt") != "yuv420p"):
        w.append(f"video is {v.get('codec_name')}/{v.get('pix_fmt')} - platforms expect h264/yuv420p")
    if max_sec and dur > max_sec:
        w.append(f"{dur:.0f}s is over the platform limit ({max_sec:.0f}s) - deliver a short cut")
    for t0, t1 in scan_res["black"]:
        if t0 < 1.0 and t1 < 1.6 or t1 > dur - 1.2 or intended("black", t0, t1):
            continue
        w.append(f"black {t0:.2f}-{t1:.2f}s ({shot_at(t0)}) - empty slot, missing footage or a too-long dip")
    for t0, t1 in scan_res["frozen"]:
        end = t1 if t1 is not None else dur
        if intended("frozen", t0, end) or any(b0 - 0.1 <= t0 and end <= b1 + 0.1 for b0, b1 in scan_res["black"]):
            continue  # a black stretch is also "frozen" - report it once
        w.append(f"frozen picture {t0:.2f}-{end:.2f}s ({shot_at(t0)}) - source too short / looping or a still without zoom")
    if scan_res["true_peak"] is not None and scan_res["true_peak"] > -0.5:
        w.append(f"true peak {scan_res['true_peak']:.1f} dBFS - may clip after platform encoding (set `loudness:` to limit)")
    if scan_res["lufs"] is not None and scan_res["lufs"] < -20:
        w.append(f"quiet: {scan_res['lufs']:.1f} LUFS (platforms aim near -14) - set `loudness: -14`")
    return w


# ----------------------------------------------------------------------------------------------- 3. SRT
def srt(lines: list[dict], start: float, end: float) -> str:
    """Lyric lines inside [start, end) as SubRip, times relative to `start` (closed captions on YouTube / Facebook)."""
    out, n = [], 0
    for ln in sorted(lines, key=lambda l: float(l["start"])):
        a, b = float(ln["start"]), float(ln["end"])
        if b <= start or a >= end:
            continue
        n += 1
        text = str(ln["text"]) + (f"\n{ln['sub']}" if ln.get("sub") else "")
        out.append(f"{n}\n{_ts(a - start)} --> {_ts(min(b, end) - start)}\n{text}\n")
    return "\n".join(out)


# ----------------------------------------------------------------------------------------------- 4. thumbnails
def frame_score(img_path: Path) -> float:
    """Sharp, well exposed, colourful, ideally with a face: what makes a thumbnail stop the scroll."""
    import cv2
    im = cv2.imread(str(img_path))
    if im is None:
        return 0.0
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    sharp = min(1.0, cv2.Laplacian(g, cv2.CV_64F).var() / 500)
    expo = 1.0 - min(1.0, abs(float(g.mean()) - 125) / 125)
    contrast = min(1.0, float(g.std()) / 64)
    b, gr, r = [im[:, :, k].astype(float) for k in range(3)]
    rg, yb = abs(r - gr), abs(0.5 * (r + gr) - b)
    colour = min(1.0, ((rg.std() ** 2 + yb.std() ** 2) ** 0.5 + 0.3 * (rg.mean() ** 2 + yb.mean() ** 2) ** 0.5) / 90)
    faces = 0
    if hasattr(cv2, "CascadeClassifier") and hasattr(cv2, "data"):
        c = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if not c.empty():
            faces = len(c.detectMultiScale(cv2.resize(g, (320, int(320 * g.shape[0] / g.shape[1]))), 1.15, 5, minSize=(24, 24)))
    return round(0.35 * sharp + 0.2 * expo + 0.15 * contrast + 0.15 * colour + 0.15 * min(1, faces), 4)


def thumb_ass(W: int, H: int, title: str, artist: str, display: str, font: str, accent: str, vertical: bool) -> str:
    """Title layout: YouTube - big title lower-left over a dark fade; vertical cover - title in the upper safe area."""
    def col(h):
        h = h.lstrip("#")
        return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()
    base = min(W, H)
    t_fs = int(base * (0.13 if not vertical else 0.12))
    a_fs = int(base * 0.045)
    bord = max(3, base // 160)
    if vertical:
        x, y, an = W // 2, int(H * 0.22), 8
        ya = y - int(a_fs * 1.6)
    else:
        x, y, an = int(W * 0.05), int(H * 0.90), 1
        ya = y - int(t_fs * 1.15)
    esc = lambda s: str(s).replace("{", "(").replace("}", ")").replace("\n", "\\N")
    ev = [f"Dialogue: 0,0:00:00.00,0:00:05.00,t,,0,0,0,,{{\\an{an}\\pos({x},{y})\\q2}}{esc(title.upper())}"]
    if artist:
        ev.append(f"Dialogue: 0,0:00:00.00,0:00:05.00,a,,0,0,0,,{{\\an{an}\\pos({x},{ya})}}{esc(artist.upper())}")
    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0",
        "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, "
        "MarginV, Encoding",
        f"Style: t,{display},{t_fs},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,{bord},{bord},{an},0,0,0,1",
        f"Style: a,{font},{a_fs},{col(accent)},&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,{base // 200},0,1,"
        f"{max(2, bord // 2)},{bord // 2},{an},0,0,0,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text", *ev, ""])
