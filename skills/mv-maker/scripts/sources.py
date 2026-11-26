"""Footage sourcing for mv-maker: licence-aware stock search (Pexels, Pixabay, Wikimedia Commons, Openverse, YouTube),
candidate contact sheets, picks, direct downloads, own-footage ingest with scene scoring, credits, and synced lyrics
from LRCLIB. Network calls send only the search terms and a generic User-Agent."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

UA = "mv-maker/0.7.0 (+https://github.com/ngoctri3110/mv-maker)"
VIDEO_EXT = (".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi")
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
PROVIDERS = ["pexels", "pixabay", "commons", "openverse", "youtube"]
LICENSES = {
    "pexels": "Pexels License (free to use, no attribution required; credit appreciated)",
    "pixabay": "Pixabay Content License (free to use, no attribution required)",
    "youtube": "UNKNOWN - YouTube content is usually copyrighted; get permission",
    "web": "UNKNOWN - social-media clips (TikTok, Facebook, Instagram ...) are copyrighted; get permission",
    "own": "user's own footage",
}


def _get(url: str, headers: dict | None = None, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _json(url: str, headers: dict | None = None) -> dict:
    return json.loads(_get(url, headers).decode("utf-8"))


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


# ----------------------------------------------------------------------------------------------- search providers
def search_pexels(q: str, kind: str, orient: str | None, n: int) -> list[dict]:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        raise RuntimeError("PEXELS_API_KEY not set (free key: https://www.pexels.com/api/)")
    o = f"&orientation={orient}" if orient else ""
    out = []
    if kind == "video":
        d = _json(f"https://api.pexels.com/videos/search?query={urllib.parse.quote(q)}&per_page={n}{o}", {"Authorization": key})
        for v in d.get("videos", []):
            files = sorted((f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("height")),
                           key=lambda f: abs(max(f["width"], f["height"]) - 1920))
            if not files:
                continue
            out.append({"provider": "pexels", "kind": "video", "url": files[0]["link"], "page": v.get("url"),
                        "thumb": v.get("image"), "w": files[0]["width"], "h": files[0]["height"], "duration": v.get("duration"),
                        "title": q, "creator": (v.get("user") or {}).get("name", ""), "license": LICENSES["pexels"]})
    else:
        d = _json(f"https://api.pexels.com/v1/search?query={urllib.parse.quote(q)}&per_page={n}{o}", {"Authorization": key})
        for p in d.get("photos", []):
            src = p.get("src", {})
            out.append({"provider": "pexels", "kind": "image", "url": src.get("original"), "page": p.get("url"),
                        "thumb": src.get("medium") or src.get("tiny"), "w": p.get("width"), "h": p.get("height"),
                        "title": p.get("alt") or q, "creator": p.get("photographer", ""), "license": LICENSES["pexels"]})
    return out


def search_pixabay(q: str, kind: str, orient: str | None, n: int) -> list[dict]:
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        raise RuntimeError("PIXABAY_API_KEY not set (free key: https://pixabay.com/api/docs/)")
    out = []
    n = max(3, min(n, 200))
    if kind == "video":
        d = _json(f"https://pixabay.com/api/videos/?key={key}&q={urllib.parse.quote(q)}&per_page={n}")
        for h in d.get("hits", []):
            vs = h.get("videos", {})
            best = vs.get("large") if (vs.get("large") or {}).get("url") else vs.get("medium", {})
            if not best.get("url"):
                continue
            if orient == "portrait" and best.get("width", 0) > best.get("height", 0):
                continue
            out.append({"provider": "pixabay", "kind": "video", "url": best["url"], "page": h.get("pageURL"),
                        "thumb": best.get("thumbnail"), "w": best.get("width"), "h": best.get("height"),
                        "duration": h.get("duration"), "title": h.get("tags", q), "creator": h.get("user", ""),
                        "license": LICENSES["pixabay"]})
    else:
        o = {"portrait": "vertical", "landscape": "horizontal"}.get(orient or "", "all")
        d = _json(f"https://pixabay.com/api/?key={key}&q={urllib.parse.quote(q)}&image_type=photo&orientation={o}&per_page={n}")
        for h in d.get("hits", []):
            out.append({"provider": "pixabay", "kind": "image", "url": h.get("largeImageURL"), "page": h.get("pageURL"),
                        "thumb": h.get("webformatURL"), "w": h.get("imageWidth"), "h": h.get("imageHeight"),
                        "title": h.get("tags", q), "creator": h.get("user", ""), "license": LICENSES["pixabay"]})
    return out


def search_commons(q: str, kind: str, orient: str | None, n: int) -> list[dict]:
    ft = "video" if kind == "video" else "bitmap"
    prop = ("prop=videoinfo&viprop=url|size|mime|extmetadata|derivatives&viurlwidth=320" if kind == "video"
            else "prop=imageinfo&iiprop=url|size|mime|extmetadata&iiurlwidth=320")
    url = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search&gsrnamespace=6"
           f"&gsrlimit={n}&gsrsearch={urllib.parse.quote(f'filetype:{ft} {q}')}&{prop}")
    pages = (_json(url).get("query") or {}).get("pages", {})
    out = []
    for p in pages.values():
        ii = (p.get("videoinfo") or p.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata") or {}
        lic = (md.get("LicenseShortName") or {}).get("value", "see page")
        w, h = ii.get("width") or 0, ii.get("height") or 0
        if orient == "portrait" and w > h or orient == "landscape" and h > w:
            continue
        file_url = ii.get("url")
        ders = [d for d in ii.get("derivatives") or [] if d.get("src") and "video" in str(d.get("type", ""))
                and d.get("height") and d["src"] != file_url]
        if ders:  # use a ≤1080p transcode instead of a (possibly multi-GB) 4K original
            small = [d for d in ders if min(d["width"], d["height"]) <= 1080]
            best = max(small, key=lambda d: d["height"] * d["width"]) if small else min(ders, key=lambda d: d["height"])
            file_url, w, h = best["src"], best["width"], best["height"]
        thumb = ii.get("thumburl") or ""
        if kind == "image" and max(w, h) > 2600 and "/320px-" in thumb:  # Commons-scaled copy, plenty for 1080p/4K
            file_url = thumb.replace("/320px-", "/2160px-")
        out.append({"provider": "commons", "kind": kind, "url": file_url, "page": ii.get("descriptionurl"),
                    "thumb": ii.get("thumburl"), "w": w, "h": h, "duration": ii.get("duration"),
                    "title": p.get("title", "").replace("File:", ""), "creator": _strip_html((md.get("Artist") or {}).get("value", "")),
                    "license": f"{lic} (Wikimedia Commons - follow the licence terms, attribution usually required)"})
    return out


def search_openverse(q: str, kind: str, orient: str | None, n: int) -> list[dict]:
    if kind == "video":
        raise RuntimeError("Openverse has images and audio only")
    o = {"portrait": "tall", "landscape": "wide"}.get(orient or "", "")
    d = _json(f"https://api.openverse.org/v1/images/?q={urllib.parse.quote(q)}&page_size={n}" + (f"&aspect_ratio={o}" if o else ""))
    out = []
    for r in d.get("results", []):
        lic = f"CC {str(r.get('license', '')).upper()} {r.get('license_version', '')}".strip()
        out.append({"provider": "openverse", "kind": "image", "url": r.get("url"), "page": r.get("foreign_landing_url"),
                    "thumb": r.get("thumbnail"), "w": r.get("width"), "h": r.get("height"), "title": r.get("title") or q,
                    "creator": r.get("creator") or "", "license": f"{lic} (attribution required unless CC0/PDM)"})
    return out


def search_youtube(q: str, kind: str, orient: str | None, n: int) -> list[dict]:
    if kind != "video":
        raise RuntimeError("YouTube search is for videos")
    r = subprocess.run([sys.executable, "-m", "yt_dlp", "--flat-playlist", "--no-warnings", "-J", f"ytsearch{n}:{q}"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-300:])
    out = []
    for e in json.loads(r.stdout).get("entries", []):
        vid = e.get("id")
        out.append({"provider": "youtube", "kind": "video", "url": f"https://www.youtube.com/watch?v={vid}",
                    "page": f"https://www.youtube.com/watch?v={vid}", "thumb": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
                    "duration": e.get("duration"), "title": e.get("title", ""), "creator": e.get("channel") or e.get("uploader") or "",
                    "license": LICENSES["youtube"]})
    return out


def ytdlp_json(url: str, flat: bool = False, timeout: int = 90) -> dict:
    """Metadata only (title, thumbnail, duration, formats incl. storyboards) - never downloads the video."""
    cmd = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--skip-download", "-J"] + (["--flat-playlist"] if flat else [])
    r = subprocess.run(cmd + [url], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-300:])
    return json.loads(r.stdout)


def from_links(links: list[str], n: int = 8) -> tuple[list[dict], list[str]]:
    """Candidates from links the user pasted (TikTok, Facebook, Instagram, Vimeo, X, YouTube ... anything yt-dlp opens).
    A profile / hashtag / playlist page expands to its first n videos when yt-dlp supports it. Metadata only."""
    out, notes = [], []
    for link in links:
        try:
            info = ytdlp_json(link, flat=True)
            entries = [e.get("url") or e.get("webpage_url") for e in (info.get("entries") or [])][:n]
            urls = entries or [link]
            for u in urls:
                v = ytdlp_json(u) if entries else info  # a single video already came back with full metadata
                host = urllib.parse.urlparse(v.get("webpage_url") or u).netloc.replace("www.", "")
                prov = "youtube" if "youtu" in host else "web"
                out.append({"provider": prov, "kind": "video", "url": v.get("webpage_url") or u,
                            "page": v.get("webpage_url") or u, "thumb": v.get("thumbnail"),
                            "duration": v.get("duration"), "title": v.get("title") or v.get("description", "")[:60],
                            "creator": v.get("uploader") or v.get("channel") or host, "site": host,
                            "license": LICENSES[prov], "_info": v if prov == "youtube" else None})
            notes.append(f"{link[:40]}: {len(urls)}")
        except Exception as e:
            notes.append(f"{link[:40]}: skipped ({str(e)[:80]})")
    return out, notes


def fetch_thumb(c: dict, dst: Path) -> Path | None:
    """Local copy of a candidate's thumbnail (URL or path) for ranking / contact sheets."""
    if dst.exists():
        return dst
    try:
        if c.get("thumb") and Path(str(c["thumb"])).exists():
            shutil.copy(c["thumb"], dst)
        elif c.get("thumb"):
            dst.write_bytes(_get(c["thumb"], timeout=20))
        else:
            return None
        return dst
    except Exception:
        return None


SEARCHERS = {"pexels": search_pexels, "pixabay": search_pixabay, "commons": search_commons,
             "openverse": search_openverse, "youtube": search_youtube}


def default_providers(kind: str) -> list[str]:
    ps = [p for p, env in (("pexels", "PEXELS_API_KEY"), ("pixabay", "PIXABAY_API_KEY")) if os.environ.get(env)]
    ps += ["commons"] + (["openverse"] if kind == "image" else [])
    return ps


def find(query: str, kind: str = "video", providers: list[str] | None = None, orient: str | None = None,
         n: int = 8) -> tuple[list[dict], list[str]]:
    results, notes = [], []
    for p in providers or default_providers(kind):
        try:
            key = lambda r: (r["provider"], Path(str(r.get("title", ""))).stem.lower())
            got, seen = [], {key(r) for r in results}
            for r in SEARCHERS[p](query, kind, orient, n):  # drop duplicates (same file in several formats)
                if key(r) not in seen and r.get("url"):
                    seen.add(key(r))
                    got.append(r)
            results += got[:n]
            notes.append(f"{p}: {len(got[:n])}")
        except Exception as e:  # keep other providers going
            notes.append(f"{p}: skipped ({str(e)[:90]})")
    return results, notes


def contact_sheet(cands: list[dict], out_jpg: Path, work: Path, font: Path, cols: int = 4) -> Path | None:
    """Numbered thumbnail grid so the agent (and user) can look at candidates before picking.
    `thumb` may be a URL or a local image path. Number n on the sheet = candidate n."""
    work.mkdir(parents=True, exist_ok=True)
    for f in list(work.glob("t_*.jpg")) + list(work.glob("raw_*")):
        f.unlink()
    shutil.copy(font, work / "_f.ttf")
    ok = 0
    for i, c in enumerate(cands, 1):
        if not c.get("thumb"):
            continue
        try:
            raw = work / f"raw_{i:02d}"
            if Path(str(c["thumb"])).exists():
                shutil.copy(c["thumb"], raw)
            else:
                raw.write_bytes(_get(c["thumb"], timeout=20))
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-vf",
                            "scale=320:240:force_original_aspect_ratio=decrease,pad=320:240:(ow-iw)/2:(oh-ih)/2:color=0x202020",
                            "-frames:v", "1", str(work / f"t_{ok + 1:02d}.jpg")], check=True)
            raw.unlink()
            c["_sheet"] = ok + 1
            ok += 1
        except Exception:
            continue
    if not ok:
        return None
    rows = -(-ok // cols)
    (work / "_n.txt").write_text("%{eif:n+1:d}", encoding="utf-8", newline="\n")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "1", "-i", "t_%02d.jpg", "-vf",
                    "drawtext=fontfile=_f.ttf:textfile=_n.txt:x=8:y=6:fontsize=34:fontcolor=yellow:box=1:boxcolor=black@0.6,"
                    f"tile={cols}x{rows}:padding=4:color=0x101010", "-frames:v", "1", str(Path(out_jpg).resolve())],
                   check=True, cwd=work)
    return out_jpg


def direct_download(url: str, dst_noext: Path, max_mb: float = 300) -> Path:
    """Download a media file; refuses files larger than max_mb (0 = no limit) so a 4K original can't fill the disk."""
    ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if ext not in VIDEO_EXT + IMAGE_EXT:
        ext = ".mp4"
    dst = dst_noext.with_suffix(ext)
    tmp = dst.with_suffix(ext + ".part")
    limit = max_mb * 2**20 if max_mb else None
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            size = int(r.headers.get("Content-Length") or 0)
            if limit and size > limit:
                raise RuntimeError(f"file is {size / 2**20:.0f} MB > limit {max_mb:.0f} MB - pick a shorter/smaller "
                                   "candidate or rerun with --max-mb 0")
            got = 0
            with open(tmp, "wb") as f:
                while chunk := r.read(1 << 20):
                    got += len(chunk)
                    if limit and got > limit:
                        raise RuntimeError(f"download passed the {max_mb:.0f} MB limit - stopped")
                    f.write(chunk)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(dst)
    return dst


def is_direct(url: str, provider: str | None) -> bool:
    return provider in ("pexels", "pixabay", "commons", "openverse") or \
        Path(urllib.parse.urlparse(url).path).suffix.lower() in VIDEO_EXT + IMAGE_EXT


# ----------------------------------------------------------------------------------------------- own footage
def score_scenes(video: Path, max_scenes: int = 40) -> list[dict]:
    """Scene cuts + per-scene quality: sharpness (Laplacian), motion, brightness, faces (Haar). Higher score = better."""
    import cv2
    from scenedetect import AdaptiveDetector, detect
    scenes = [(s.get_seconds(), e.get_seconds()) for s, e in detect(str(video), AdaptiveDetector())]
    cap = cv2.VideoCapture(str(video))
    dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / max(1.0, cap.get(cv2.CAP_PROP_FPS) or 30)
    if not scenes:
        step = 4.0
        scenes = [(t, min(dur, t + step)) for t in [i * step for i in range(int(dur // step) + 1)] if min(dur, t + step) - t > 0.8]
    face = None  # Haar face detector exists in OpenCV 4 only; without it the face term is simply 0
    if hasattr(cv2, "CascadeClassifier") and hasattr(cv2, "data"):
        face = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    out = []
    for s, e in scenes[:max_scenes]:
        if e - s < 0.6:
            continue
        vals, prev, motion, faces = [], None, [], 0
        for t in (s + (e - s) * k for k in (0.25, 0.5, 0.75)):
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, fr = cap.read()
            if not ok:
                continue
            g = cv2.cvtColor(cv2.resize(fr, (480, int(480 * fr.shape[0] / fr.shape[1]))), cv2.COLOR_BGR2GRAY)
            vals.append((cv2.Laplacian(g, cv2.CV_64F).var(), g.mean()))
            if prev is not None:
                motion.append(float(cv2.absdiff(g, prev).mean()))
            prev = g
            if face is not None:
                faces = max(faces, len(face.detectMultiScale(g, 1.2, 5, minSize=(40, 40))))
        if not vals:
            continue
        sharp = sum(v[0] for v in vals) / len(vals)
        bright = sum(v[1] for v in vals) / len(vals)
        mot = sum(motion) / len(motion) if motion else 0.0
        expo = 1.0 - min(1.0, abs(bright - 120) / 120)  # penalise very dark / blown-out
        score = min(1.0, sharp / 400) * 0.45 + expo * 0.25 + min(1.0, mot / 25) * 0.15 + min(1, faces) * 0.15
        out.append({"start": round(s, 2), "end": round(e, 2), "sharpness": round(sharp, 1), "brightness": round(bright, 1),
                    "motion": round(mot, 2), "faces": faces, "score": round(score, 3)})
    cap.release()
    return out


# ----------------------------------------------------------------------------------------------- synced lyrics
def lrclib(artist: str, title: str, album: str | None = None, duration: float | None = None) -> dict | None:
    """Synced (LRC) lyrics from LRCLIB (free, no key). Returns the best record or None."""
    qs = {"artist_name": artist, "track_name": title}
    if album:
        qs["album_name"] = album
    if duration:
        qs["duration"] = str(int(round(duration)))
    try:
        rec = _json("https://lrclib.net/api/get?" + urllib.parse.urlencode(qs))
        if rec.get("syncedLyrics"):
            return rec
    except Exception:
        pass
    try:
        hits = _json("https://lrclib.net/api/search?" + urllib.parse.urlencode({"track_name": title, "artist_name": artist}))
    except Exception:
        return None
    hits = [h for h in hits if h.get("syncedLyrics")]
    if duration:
        hits.sort(key=lambda h: abs((h.get("duration") or 0) - duration))
    return hits[0] if hits else None


def parse_lrc(lrc: str, song_end: float | None = None) -> list[dict]:
    rows = []
    for line in lrc.splitlines():
        stamps = re.findall(r"\[(\d+):(\d+(?:\.\d+)?)\]", line)
        text = re.sub(r"\[[^\]]*\]", "", line).strip()
        for m, s in stamps:
            rows.append((int(m) * 60 + float(s), text))
    rows.sort()
    out = []
    for i, (t, text) in enumerate(rows):
        if not text:
            continue
        nxt = next((rows[j][0] for j in range(i + 1, len(rows))), song_end or t + 4)
        out.append({"start": round(t, 2), "end": round(min(nxt - 0.05, t + 8), 2), "text": text})
    return out
