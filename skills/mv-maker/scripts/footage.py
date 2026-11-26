"""Footage quality helpers for the renderer: colour matching across sources, subject-tracking reframe, stabilisation
pre-pass, resolution checks, AI upscale and person mattes (the last two are optional, heavy tools - lazy).

Pure Python + FFmpeg for colour / resolution; OpenCV (already a dependency) for tracking. Results are cached in the
build folder so a re-render costs nothing."""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

_FILTERS: set[str] | None = None


def ffmpeg_filters() -> set[str]:
    global _FILTERS
    if _FILTERS is None:
        try:
            out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
            _FILTERS = {ln.split()[1] for ln in out.splitlines() if len(ln.split()) > 2 and ln.startswith(" ")}
        except OSError:
            _FILTERS = set()
    return _FILTERS


def key(*parts) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:16]


def file_key(f: Path) -> str:
    st = f.stat()
    return f"{f.resolve()}|{st.st_mtime_ns}|{st.st_size}"


class Cache:
    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def get(self, k, fn):
        if k not in self.data:
            self.data[k] = fn()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data), encoding="utf-8")
        return self.data[k]


# ----------------------------------------------------------------------------------------------- 1. colour match
def _rgb_frames(f: Path, times: list[float], w: int = 48, h: int = 27) -> list[bytes]:
    out = []
    for t in times:
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.2f}", "-i", str(f), "-frames:v", "1",
                            "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
        if r.returncode == 0 and len(r.stdout) == w * h * 3:
            out.append(r.stdout)
    return out


def color_stats(f: Path, start: float, dur: float, image: bool = False) -> dict | None:
    """Average R/G/B and median luma (0..1) of the part of the clip a shot uses (3 small frames)."""
    times = [0.0] if image else [start + dur * k for k in (0.2, 0.5, 0.8)]
    frames = _rgb_frames(f, times)
    if not frames:
        return None
    r = g = b = 0.0
    lum = []
    n = 0
    for fr in frames:
        for i in range(0, len(fr), 3):
            R, G, B = fr[i], fr[i + 1], fr[i + 2]
            r += R
            g += G
            b += B
            lum.append(0.2126 * R + 0.7152 * G + 0.0722 * B)
            n += 1
    lum.sort()
    return {"r": r / n / 255, "g": g / n / 255, "b": b / n / 255, "y": lum[len(lum) // 2] / 255}


def match_filter(st: dict, target_y: float, strength: float = 0.6) -> str | None:
    """Gentle normalisation towards the edit's common exposure and a neutral white balance:
    gamma moves the mid-tones (no clipping), channel gains remove casts. `strength` 0..1 keeps intentional looks."""
    if not st or strength <= 0:
        return None
    y = min(max(st["y"], 0.03), 0.97)
    gamma = math.log(min(max(target_y, 0.05), 0.95)) / math.log(y)
    gamma = 1 + (min(max(gamma, 0.65), 1.5) - 1) * strength
    m = (st["r"] + st["g"] + st["b"]) / 3 or 1e-3
    gains = []
    for c in ("r", "g", "b"):
        gn = m / max(st[c], 1e-3)
        gains.append(1 + (min(max(gn, 0.8), 1.25) - 1) * strength)
    if abs(gamma - 1) < 0.03 and all(abs(x - 1) < 0.02 for x in gains):
        return None
    # eq gamma > 1 brightens; our gamma maps y -> target, so invert for eq
    return (f"eq=gamma={1 / gamma:.3f},"
            f"colorchannelmixer=rr={gains[0]:.3f}:gg={gains[1]:.3f}:bb={gains[2]:.3f}")


def lut_filter(spec: str, lut_dir: Path, root: Path) -> tuple[str, Path]:
    """`lut:<file.cube>[@strength]` -> (filter, copied lut) - the LUT is copied next to the graph (no path escaping)."""
    path, _, amt = spec.partition("@")
    src = Path(path)
    if not src.is_absolute():
        src = root / path
    if not src.exists():
        raise FileNotFoundError(f"LUT not found: {src}")
    lut_dir.mkdir(parents=True, exist_ok=True)
    dst = lut_dir / f"{key(file_key(src))}{src.suffix.lower()}"
    if not dst.exists():
        shutil.copy(src, dst)
    return f"lut3d=file=luts/{dst.name}:interp=tetrahedral", float(amt) if amt else 1.0


# ----------------------------------------------------------------------------------------------- 2. subject tracking
def track_subject(f: Path, start: float, dur: float, step: float = 0.25) -> list[tuple[float, float, float]]:
    """Subject centre over time -> [(t_from_start, x, y)] in 0..1, smoothed. Faces first (frontal + profile), else the
    centre of motion, else the frame centre. Used to slide a 9:16 crop window through 16:9 footage."""
    import cv2
    cap = cv2.VideoCapture(str(f))
    cascades = []
    if hasattr(cv2, "data") and hasattr(cv2, "CascadeClassifier"):  # some OpenCV builds lack Haar: motion only
        for n in ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml"):
            c = cv2.CascadeClassifier(cv2.data.haarcascades + n)
            if not c.empty():
                cascades.append(c)
    pts, prev = [], None
    t = 0.0
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    stepf = max(1, round(step * fps))
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)  # one seek, then read forward: seeks snap to keyframes
    while t <= dur + 1e-6:
        ok, fr = cap.read()
        if not ok:
            break
        for _ in range(stepf - 1):
            cap.grab()
        h0, w0 = fr.shape[:2]
        sm = cv2.resize(fr, (320, max(2, int(320 * h0 / w0))))
        g = cv2.cvtColor(sm, cv2.COLOR_BGR2GRAY)
        H, W = g.shape
        best = None
        for c in cascades:
            for (x, y, w, h) in c.detectMultiScale(g, 1.15, 4, minSize=(18, 18)):
                if best is None or w * h > best[2] * best[3]:
                    best = (x, y, w, h)
        if best is not None:
            x, y, w, h = best
            pts.append((t, (x + w / 2) / W, (y + h / 2) / H, 1.0))
        elif prev is not None:
            d = cv2.absdiff(g, prev)
            _, m = cv2.threshold(cv2.GaussianBlur(d, (9, 9), 0), 18, 255, cv2.THRESH_BINARY)
            mo = cv2.moments(m)
            if mo["m00"] > 255 * W * H * 0.004:
                pts.append((t, mo["m10"] / mo["m00"] / W, mo["m01"] / mo["m00"] / H, 0.5))
        prev = g
        t += step
    cap.release()
    return smooth_track(pts, dur, step)


def smooth_track(pts: list[tuple], dur: float, step: float = 0.25, max_speed: float = 0.35) -> list[tuple]:
    """Fill gaps, moving-average, and limit pan speed (fraction of the frame per second) - a calm operator, not a jitter."""
    if not pts:
        return [(0.0, 0.5, 0.5), (round(dur, 2), 0.5, 0.5)]
    times = [round(i * step, 3) for i in range(int(dur / step) + 1)]
    out = []
    for tt in times:
        near = [(abs(p[0] - tt), p) for p in pts]
        d, p = min(near)
        out.append([tt, p[1], p[2]])
    for k in (1, 2):  # x, y moving average over ~1 s
        vals = [o[k] for o in out]
        r = max(1, int(0.5 / step))
        sm = [sum(vals[max(0, i - r):i + r + 1]) / len(vals[max(0, i - r):i + r + 1]) for i in range(len(vals))]
        lim = max_speed * step
        for i in range(1, len(sm)):
            sm[i] = min(max(sm[i], sm[i - 1] - lim), sm[i - 1] + lim)
        for o, v in zip(out, sm):
            o[k] = round(min(max(v, 0.0), 1.0), 4)
    return [tuple(o) for o in out]


def track_expr(track: list[tuple], axis: int, speed: float = 1.0, max_keys: int = 24) -> str:
    """Piecewise-linear expression of output time t (setpts already applied) -> anchor 0..1 for crop x or y."""
    pts = [(t / max(speed, 1e-3), v) for t, *vs in track for v in [vs[axis]]]
    if len(pts) > max_keys:  # keep the expression small
        stepk = (len(pts) - 1) / (max_keys - 1)
        pts = [pts[round(i * stepk)] for i in range(max_keys)]
    if len(pts) == 1:
        return f"{pts[0][1]:.4f}"
    e = f"{pts[-1][1]:.4f}"
    for (t0, v0), (t1, v1) in zip(reversed(pts[:-1]), reversed(pts[1:])):
        e = f"if(lt(t,{t1:.3f}),{v0:.4f}+({v1 - v0:.4f})*(t-{t0:.3f})/{max(t1 - t0, 1e-3):.3f},{e})"
    return e


# ----------------------------------------------------------------------------------------------- 3. stabilise
def stabilize_pass(f: Path, start: float, dur: float, out_trf: Path, shakiness: int = 6) -> bool:
    """vidstab detect pass on exactly the part the shot uses (cached .trf). False when FFmpeg lacks vidstab."""
    if "vidstabdetect" not in ffmpeg_filters():
        return False
    if not out_trf.exists():
        out_trf.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(f),
                            "-vf", f"vidstabdetect=shakiness={shakiness}:accuracy=15:result={out_trf.name}", "-f", "null",
                            "-"], cwd=out_trf.parent, capture_output=True, text=True)
        if r.returncode != 0:
            return False
    return True


# ----------------------------------------------------------------------------------------------- 4. resolution check
def probe_wh(f: Path) -> tuple[int, int]:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(f)], capture_output=True, text=True)
    try:
        w, h = (int(x) for x in r.stdout.strip().split(",")[:2])
        return w, h
    except ValueError:
        return 0, 0


def upscale_factor(src_wh: tuple[int, int], slot_wh: tuple[int, int], zoom: float = 1.0, contain: bool = False) -> float:
    """How much the source is enlarged to fill the slot (cover crop) - > 1.5 looks soft on a phone."""
    sw, sh = src_wh
    if not sw or not sh:
        return 1.0
    w, h = slot_wh
    k = (min if contain else max)(w / sw, h / sh)
    return round(k * zoom, 2)


# ----------------------------------------------------------------------------------------------- 10. AI upscale
def realesrgan_bin(skill_dir: Path) -> Path | None:
    env = os.environ.get("MV_REALESRGAN")
    cands = [Path(env)] if env else []
    exe = "realesrgan-ncnn-vulkan.exe" if os.name == "nt" else "realesrgan-ncnn-vulkan"
    cands += [p / exe for p in (skill_dir / "tools" / "realesrgan").rglob("*") if p.is_dir()] if (skill_dir / "tools").exists() else []
    cands += [skill_dir / "tools" / "realesrgan" / exe]
    w = shutil.which("realesrgan-ncnn-vulkan")
    if w:
        cands.append(Path(w))
    return next((c for c in cands if c.exists()), None)


def upscale_clip(binary: Path, f: Path, start: float, dur: float, fps: float, dst: Path, scale: int = 2,
                 image: bool = False) -> Path:
    """Real-ESRGAN (ncnn/Vulkan) on the part of the clip the shot uses -> dst (cached). Frames in, frames out."""
    if dst.exists():
        return dst
    work = dst.with_suffix("")
    if work.exists():
        shutil.rmtree(work)
    (work / "in").mkdir(parents=True)
    (work / "out").mkdir()
    model = ["-n", "realesrgan-x4plus", "-s", "4"]  # the photo-real model; the renderer scales the result to the slot
    if image:
        subprocess.run([str(binary), "-i", str(f), "-o", str(dst), *model], check=True)
        return dst
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(f),
                    "-vf", f"fps={fps}", str(work / "in" / "%06d.png")], check=True)
    subprocess.run([str(binary), "-i", str(work / "in"), "-o", str(work / "out"), *model, "-f", "png"], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(fps), "-i", str(work / "out" / "%06d.png"),
                    "-c:v", "libx264", "-crf", "14", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(dst)], check=True)
    shutil.rmtree(work)
    return dst


# ----------------------------------------------------------------------------------------------- 9. person matte
def person_matte(video: Path, dst: Path, fps: int, w: int, h: int, threshold: float = 0.5) -> Path:
    """Grey matte video (white = person) from a rendered shot with MediaPipe selfie segmentation -> text-behind-subject."""
    if dst.exists() and dst.stat().st_mtime >= video.stat().st_mtime:
        return dst
    import numpy as np
    seg = _segmenter()
    rd = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-vf", f"fps={fps},scale={w}:{h}", "-"], stdout=subprocess.PIPE)
    wr = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}",
                           "-r", str(fps), "-i", "-", "-vf", "gblur=sigma=1.5", "-c:v", "libx264", "-crf", "12",
                           "-pix_fmt", "yuv420p", str(dst)], stdin=subprocess.PIPE)
    n = w * h * 3
    while True:
        buf = rd.stdout.read(n)
        if len(buf) < n:
            break
        frame = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        m = seg(frame)
        wr.stdin.write((np.clip((m - threshold) * 4 + 0.5, 0, 1) * 255).astype(np.uint8).tobytes())
    wr.stdin.close()
    rd.wait()
    wr.wait()
    return dst


def _segmenter():
    """MediaPipe selfie segmentation (legacy `solutions` API, bundled model) -> fn(rgb uint8 HxWx3) -> float mask."""
    try:
        import mediapipe as mp
    except ImportError as e:
        raise RuntimeError("text-behind-subject needs MediaPipe: mv doctor --install segment (~40 MB)") from e
    sol = getattr(getattr(mp, "solutions", None), "selfie_segmentation", None)
    if sol is None:
        raise RuntimeError("this MediaPipe build has no selfie_segmentation - install mediapipe==0.10.14 "
                           "(mv doctor --install segment)")
    model = sol.SelfieSegmentation(model_selection=1)
    return lambda rgb: model.process(rgb).segmentation_mask


# ----------------------------------------------------------------------------------------------- stills: details + depth
def detail_points(img: Path, n: int = 5) -> list[tuple[float, float, float, str]]:
    """Interesting places to push into on a still: faces first, then the busiest / most contrasted grid cells
    (texture, text, eyes, objects), spread out. -> [(x, y, zoom, reason)] in 0..1."""
    import cv2
    import numpy as np
    im = cv2.imread(str(img))
    if im is None:
        return [(0.5, 0.5, 1.6, "centre")]
    h0, w0 = im.shape[:2]
    sc = 480 / max(h0, w0)
    sm = cv2.resize(im, (max(2, int(w0 * sc)), max(2, int(h0 * sc))))
    g = cv2.cvtColor(sm, cv2.COLOR_BGR2GRAY)
    H, W = g.shape
    out = []
    if hasattr(cv2, "CascadeClassifier") and hasattr(cv2, "data"):
        c = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if not c.empty():
            for (x, y, fw, fh) in sorted(c.detectMultiScale(g, 1.1, 5, minSize=(20, 20)), key=lambda r: -r[2] * r[3])[:2]:
                out.append(((x + fw / 2) / W, (y + fh / 2) / H, round(min(3.0, max(1.6, 0.35 * W / fw)), 1), "face"))
    lap = np.abs(cv2.Laplacian(g, cv2.CV_64F))
    lab = cv2.cvtColor(sm, cv2.COLOR_BGR2LAB).astype(np.float64)
    sal = lap / (lap.mean() + 1e-6) + np.linalg.norm(lab - lab.reshape(-1, 3).mean(0), axis=2) / 40
    gx, gy = 6, 8 if H > W else 6
    cells = []
    for i in range(gx):
        for j in range(gy):
            a = sal[j * H // gy:(j + 1) * H // gy, i * W // gx:(i + 1) * W // gx]
            edge = i in (0, gx - 1) or j in (0, gy - 1)  # frame borders / lettering edges are rarely the subject
            cells.append((float(a.mean()) * (0.6 if edge else 1.0), (i + 0.5) / gx, (j + 0.5) / gy))
    for score, x, y in sorted(cells, reverse=True):
        if len(out) >= n:
            break
        if all(abs(x - ox) > 0.22 or abs(y - oy) > 0.22 for ox, oy, _, _ in out):
            out.append((round(x, 2), round(y, 2), 2.0, "detail"))
    return [(round(x, 2), round(y, 2), z, why) for x, y, z, why in out[:n]] or [(0.5, 0.5, 1.6, "centre")]


DEPTH_MODEL = "depth-anything/Depth-Anything-V2-Small-hf"


def depth_mask(img: Path, dst: Path, fg_share: float = 0.35) -> Path:
    """Foreground matte (white = near) from a monocular depth model, feathered; cached. For `parallax: true`."""
    if dst.exists() and dst.stat().st_mtime >= img.stat().st_mtime:
        return dst
    try:
        from transformers import pipeline
        from PIL import Image, ImageFilter
        import numpy as np
    except ImportError as e:
        raise RuntimeError("parallax needs PyTorch + transformers: mv doctor --install match "
                           "(the depth model, ~100 MB, downloads on first use)") from e
    im = Image.open(img).convert("RGB")
    depth = np.asarray(pipeline("depth-estimation", model=DEPTH_MODEL)(im)["depth"], dtype=np.float32)  # bright = near
    thr = float(np.percentile(depth, 100 * (1 - fg_share)))
    m = Image.fromarray(((depth >= thr) * 255).astype(np.uint8)).resize(im.size)
    dst.parent.mkdir(parents=True, exist_ok=True)
    m.filter(ImageFilter.GaussianBlur(radius=max(2, im.size[0] // 250))).save(dst)
    return dst
