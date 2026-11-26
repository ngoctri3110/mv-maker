"""Semantic footage matching: pick the scenes (own clips, downloaded sources, online candidates) that look like a text
description, with a free local vision-language model (Google SigLIP 2, multilingual, via Hugging Face transformers).

Heavy deps (torch, transformers, Pillow) are imported lazily inside Embedder - install with `mv doctor --install match`.
Everything else here is plain Python so the planning / assignment logic is testable without a model.

Pipeline (mv match):  library scenes -> 3 frames each -> image embeddings (cached)
                      shot `look_for` text -> text embedding -> similarity per frame
                      -> best frame = in-point, scene score -> global greedy assignment (no reuse, no adjacent repeats)
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path

MODELS = {  # alias -> Hugging Face id (download size is approximate)
    "base": "google/siglip2-base-patch16-224",        # ~1.5 GB, good on CPU
    "large": "google/siglip2-so400m-patch14-384",     # ~4.5 GB, best quality, wants a GPU
}
FRAME_POS = (0.2, 0.5, 0.8)  # where inside a scene frames are sampled


# ----------------------------------------------------------------------------------------------- embedding backend
class Embedder:
    """SigLIP 2 image/text embeddings (L2-normalised). First use downloads the model to the Hugging Face cache."""

    def __init__(self, model: str | None = None, device: str | None = None):
        try:
            import torch
            from transformers import AutoModel, AutoProcessor
        except ImportError as e:  # pragma: no cover - depends on the machine
            raise RuntimeError("semantic matching needs PyTorch + transformers: run `mv doctor --install match` "
                               f"(~1-2 GB with the model) - {e}") from e
        self.torch = torch
        self.model_id = MODELS.get(model or "base", model or MODELS["base"])
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.dtype = torch.float16 if self.device == "cuda" else torch.float32
        print(f"[mv] loading {self.model_id} on {self.device} (first run downloads it) ...")
        self.model = AutoModel.from_pretrained(self.model_id, torch_dtype=self.dtype).to(self.device).eval()
        self.proc = AutoProcessor.from_pretrained(self.model_id)

    def _to(self, inp):
        return {k: (v.to(self.device, self.dtype) if v.is_floating_point() else v.to(self.device)) for k, v in inp.items()}

    @staticmethod
    def _norm(f):
        return (f / f.norm(dim=-1, keepdim=True)).float().cpu().tolist()

    def images(self, paths: list[Path], batch: int = 16) -> list[list[float]]:
        from PIL import Image
        out = []
        for i in range(0, len(paths), batch):
            ims = [Image.open(p).convert("RGB") for p in paths[i:i + batch]]
            with self.torch.no_grad():
                out += self._norm(self.model.get_image_features(**self._to(self.proc(images=ims, return_tensors="pt"))))
        return out

    def texts(self, texts: list[str]) -> list[list[float]]:
        # SigLIP was trained on lower-cased text padded to 64 tokens
        inp = self.proc(text=[t.lower() for t in texts], padding="max_length", max_length=64, truncation=True,
                        return_tensors="pt")
        with self.torch.no_grad():
            return self._norm(self.model.get_text_features(**self._to(inp)))


class EmbCache:
    """Image embeddings cached per model in build/match/emb_<model>.json (key = file + mtime + model)."""

    def __init__(self, path: Path, emb):
        self.path, self.emb = path, emb
        self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    @staticmethod
    def key(p: Path) -> str:
        st = p.stat()
        return hashlib.sha1(f"{p.resolve()}|{st.st_mtime_ns}|{st.st_size}".encode()).hexdigest()[:20]

    def images(self, paths: list[Path]) -> list[list[float]]:
        keys = [self.key(p) for p in paths]
        todo = [(k, p) for k, p in zip(keys, paths) if k not in self.data]
        if todo:
            print(f"[mv] embedding {len(todo)} frames ...")
            for (k, _), v in zip(todo, self.emb.images([p for _, p in todo])):
                self.data[k] = [round(x, 5) for x in v]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data), encoding="utf-8")
        return [self.data[k] for k in keys]


# ----------------------------------------------------------------------------------------------- vector maths
def dot_matrix(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    """a (n x d) . b (m x d)^T -> n x m (numpy when available)."""
    if not a or not b:
        return [[] for _ in a]
    try:
        import numpy as np
        return (np.asarray(a, dtype=np.float32) @ np.asarray(b, dtype=np.float32).T).tolist()
    except ImportError:
        return [[sum(x * y for x, y in zip(r, c)) for c in b] for r in a]


def mean_vec(vs: list[list[float]]) -> list[float]:
    m = [sum(col) / len(vs) for col in zip(*vs)]
    n = math.sqrt(sum(x * x for x in m)) or 1.0
    return [x / n for x in m]


def query_vector(emb, look_for, avoid=None) -> tuple[list[float], list[float] | None]:
    """`look_for` may be a string or a list (several phrasings are averaged - more robust than one)."""
    qs = [look_for] if isinstance(look_for, str) else [str(x) for x in look_for]
    vec = mean_vec(emb.texts(qs))
    neg = None
    if avoid:
        neg = mean_vec(emb.texts([avoid] if isinstance(avoid, str) else [str(x) for x in avoid]))
    return vec, neg


# ----------------------------------------------------------------------------------------------- frames
def frame_times(start: float, end: float) -> list[float]:
    return [round(start + (end - start) * k, 2) for k in FRAME_POS]


def extract_frame(video: Path, t: float, dst: Path, width: int = 384) -> Path:
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={width}:-2", str(dst)], check=True)
    return dst


# ----------------------------------------------------------------------------------------------- scoring + assignment
def score_scene(frame_sims: list[float], neg_sims: list[float] | None, quality: float = 0.5) -> float:
    """Best frame counts most (one strong moment is enough to cut to), the scene average breaks ties."""
    s = [x - 0.5 * n for x, n in zip(frame_sims, neg_sims)] if neg_sims else list(frame_sims)
    return round(0.7 * max(s) + 0.3 * sum(s) / len(s) + 0.01 * quality, 5)


def in_point(scene: dict, best_t: float, need: float) -> float:
    """Start so the best frame sits ~1/3 into the shot, kept inside the scene when the scene is long enough."""
    s, e = float(scene["start"]), float(scene["end"])
    t = best_t - need * 0.35
    if e - s >= need:
        t = min(max(t, s), e - need)
    else:
        t = s
    return round(max(0.0, t), 2)


def assign(shots: list[dict], cands: dict[str, list[dict]], reuse: bool = False) -> dict[str, int]:
    """Global greedy: highest-scoring (shot, scene) pairs first; a scene is used once (unless reuse) and never in two
    neighbouring shots. cands[shot_id] = candidates sorted best-first, each with `key` (scene id) and `score`.
    Returns shot_id -> index into its candidate list."""
    order = {s["id"]: i for i, s in enumerate(shots)}
    pairs = sorted(((c["score"], sid, k) for sid, cs in cands.items() for k, c in enumerate(cs)), reverse=True)
    chosen: dict[str, int] = {}
    used: dict[str, list[int]] = {}
    for score, sid, k in pairs:
        if sid in chosen:
            continue
        key = cands[sid][k]["key"]
        pos = order[sid]
        where = used.get(key, [])
        if where and (not reuse or any(abs(p - pos) <= 1 for p in where)):
            continue
        chosen[sid] = k
        used.setdefault(key, []).append(pos)
    for sid, cs in cands.items():  # everything taken: fall back to the best one
        if sid not in chosen and cs:
            chosen[sid] = 0
    return chosen


def shot_query(sh: dict) -> tuple[object | None, object | None]:
    """look_for (preferred: concrete English visual description written by the agent) or intent / lyric as fallback."""
    q = sh.get("look_for") or " ".join(str(sh[k]) for k in ("intent", "lyric") if sh.get(k)) or None
    return q, sh.get("avoid")


# ----------------------------------------------------------------------------------------------- online moments
def best_run(times: list[float], sims: list[float], pad: float = 3.0, keep: float = 0.015) -> tuple[float, float, float]:
    """Best tile time and the contiguous run of near-best tiles around it -> (best_t, section_start, section_end)."""
    if not times:
        return 0.0, 0.0, 0.0
    b = max(range(len(sims)), key=lambda i: sims[i])
    lo = hi = b
    while lo > 0 and sims[lo - 1] >= sims[b] - keep:
        lo -= 1
    while hi < len(sims) - 1 and sims[hi + 1] >= sims[b] - keep:
        hi += 1
    return times[b], max(0.0, times[lo] - pad), times[hi] + pad * 2


def storyboard_tiles(info: dict, work: Path, get, max_frags: int = 40) -> list[tuple[float, Path]]:
    """YouTube storyboard sprites (the hover-preview thumbnails) -> [(time, tile.jpg)] without downloading the video.
    `info` = yt-dlp -J output; `get(url) -> bytes`."""
    sbs = [f for f in info.get("formats") or [] if str(f.get("format_id", "")).startswith("sb") and f.get("fragments")]
    if not sbs:
        return []
    sb = max(sbs, key=lambda f: (f.get("width") or 0) * (f.get("height") or 0))
    cols, rows = int(sb.get("columns") or 5), int(sb.get("rows") or 5)
    frags = sb["fragments"]
    starts, t = [], 0.0
    for fr in frags:
        starts.append(t)
        t += float(fr.get("duration") or 0)
    idx = list(range(len(frags)))
    if len(idx) > max_frags:  # long video: spread the budget evenly
        idx = sorted({round(i * (len(frags) - 1) / (max_frags - 1)) for i in range(max_frags)})
    work.mkdir(parents=True, exist_ok=True)
    out = []
    for i in idx:
        fr = frags[i]
        sprite = work / f"sb_{i:03d}.jpg"
        try:
            if not sprite.exists():
                sprite.write_bytes(get(fr["url"]))
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(sprite), "-vf", f"untile={cols}x{rows}",
                            str(work / f"sb_{i:03d}_%02d.jpg")], check=True)
        except Exception:
            continue
        per = float(fr.get("duration") or 0) / (cols * rows)
        for k in range(cols * rows):
            tile = work / f"sb_{i:03d}_{k + 1:02d}.jpg"
            tt = starts[i] + k * per
            if tile.exists() and (not info.get("duration") or tt < float(info["duration"])):
                out.append((round(tt, 2), tile))
    return out
