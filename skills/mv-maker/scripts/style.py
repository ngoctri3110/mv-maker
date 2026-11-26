"""Style hints from the audio: key / mode, brightness, drum weight, density, dynamics -> genre + mood guesses.

Heuristic and cheap (librosa, already a dependency). The agent combines them with the lyrics, the artwork and what
the user says - they are hints, not a verdict. Optional: an AudioSet classifier (AST via transformers) gives a
learned genre / mood reading with `mv analyze --genre-model` (downloads ~350 MB on first use)."""
from __future__ import annotations

KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
# Krumhansl-Kessler key profiles
MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


def _corr(a, b) -> float:
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = sum((x - ma) ** 2 for x in a) ** 0.5
    db = sum((y - mb) ** 2 for y in b) ** 0.5
    return num / (da * db) if da and db else 0.0


def estimate_key(chroma_mean: list[float]) -> tuple[str, str, float]:
    """(key, 'major'|'minor', confidence 0..1) from a 12-bin mean chroma vector."""
    best = ("C", "major", -1.0)
    for i in range(12):
        rot = chroma_mean[i:] + chroma_mean[:i]
        for mode, prof in (("major", MAJOR), ("minor", MINOR)):
            c = _corr(rot, prof)
            if c > best[2]:
                best = (KEYS[i], mode, c)
    return best[0], best[1], round(max(0.0, best[2]), 2)


def features(y, sr: int, tempo: float, onsets: list[float], dur: float) -> dict:
    import numpy as np
    import librosa
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1).tolist()
    key, mode, kconf = estimate_key(chroma)
    centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    flat = float(np.mean(librosa.feature.spectral_flatness(y=y)))
    harm, perc = librosa.effects.hpss(y)
    pe, he = float(np.sum(perc ** 2)), float(np.sum(harm ** 2))
    rms = librosa.feature.rms(y=y)[0]
    return {"tempo": round(float(tempo), 1), "key": key, "mode": mode, "key_conf": kconf,
            "brightness_hz": round(centroid), "noisiness": round(flat, 4),
            "drums": round(pe / max(pe + he, 1e-9), 3), "onset_rate": round(len(onsets) / max(dur, 1e-3), 2),
            "dynamics": round(float(np.std(rms) / max(np.mean(rms), 1e-9)), 3)}


def _band(v: float, lo: float, hi: float, soft: float) -> float:
    """1 inside [lo, hi], falling linearly to 0 at `soft` outside."""
    if lo <= v <= hi:
        return 1.0
    d = lo - v if v < lo else v - hi
    return max(0.0, 1 - d / soft)


def guess(f: dict) -> dict:
    """Genre candidates (keys of genres.yaml) with scores and the reasons, plus a mood reading."""
    t = f["tempo"]
    half = t / 2 if t > 140 else t  # trap / drum & bass are often felt at half time
    dbl = t * 2 if t < 80 else t
    drums, bright, onset, minor = f["drums"], f["brightness_hz"], f["onset_rate"], f["mode"] == "minor"
    noisy = f["noisiness"]
    s = {
        "ballad": 0.4 * _band(t, 56, 92, 20) + 0.35 * _band(drums, 0, 0.28, 0.15) + 0.25 * _band(onset, 0, 2.2, 1.5),
        "indie": 0.35 * _band(t, 70, 118, 20) + 0.35 * _band(drums, 0.1, 0.35, 0.15) + 0.3 * _band(bright, 900, 2300, 800),
        "rnb": 0.35 * _band(t, 60, 105, 15) + 0.25 * _band(drums, 0.25, 0.5, 0.15) + 0.2 * minor
        + 0.2 * _band(bright, 1100, 2600, 700),
        "pop": 0.35 * _band(dbl, 95, 132, 15) + 0.3 * _band(drums, 0.3, 0.55, 0.15) + 0.2 * (not minor)
        + 0.15 * _band(bright, 1800, 3400, 900),
        "kpop": 0.3 * _band(t, 108, 140, 12) + 0.3 * _band(drums, 0.42, 0.7, 0.15) + 0.2 * _band(bright, 2300, 4200, 900)
        + 0.2 * _band(f["dynamics"], 0.35, 1.2, 0.2),
        "rap": 0.35 * max(_band(t, 78, 102, 10), _band(half, 68, 88, 8)) + 0.35 * _band(drums, 0.45, 0.85, 0.15)
        + 0.3 * _band(onset, 2.5, 8, 1.5),
        "edm": 0.35 * max(_band(t, 118, 132, 6), _band(t, 138, 152, 6)) + 0.35 * _band(drums, 0.5, 0.9, 0.15)
        + 0.3 * _band(f["dynamics"], 0.45, 1.5, 0.25),
        "rock": 0.3 * _band(t, 100, 180, 20) + 0.3 * _band(noisy, 0.02, 0.2, 0.02) + 0.4 * _band(bright, 2600, 5000, 900),
    }
    ranked = sorted(s.items(), key=lambda kv: -kv[1])
    energy = "high" if drums > 0.45 and t > 105 else ("low" if drums < 0.25 or t < 80 else "medium")
    mood = {("minor", "low"): "melancholic, intimate", ("minor", "medium"): "moody, bittersweet",
            ("minor", "high"): "intense, dark, driving", ("major", "low"): "warm, tender",
            ("major", "medium"): "bright, hopeful", ("major", "high"): "euphoric, upbeat"}[(f["mode"], energy)]
    why = (f"{f['tempo']} bpm, {f['key']} {f['mode']}, drums {f['drums']:.0%} of the energy, brightness "
           f"{f['brightness_hz']} Hz, {f['onset_rate']} onsets/s")
    if ranked[0][1] - ranked[1][1] < 0.06:  # e.g. K-pop vs EDM look alike on these features: ask, don't guess
        why += f"; {ranked[0][0]} vs {ranked[1][0]} is a close call - ask the user"
    return {"genres": [{"genre": g, "score": round(v, 2)} for g, v in ranked[:3]], "energy": energy, "mood": mood,
            "why": why}


# ----------------------------------------------------------------------------------------------- optional classifier
AST_MODEL = "MIT/ast-finetuned-audioset-10-10-0.4593"
AUDIOSET_TO_GENRE = {
    "Pop music": "pop", "Hip hop music": "rap", "Rock music": "rock", "Punk rock": "rock", "Grunge": "rock",
    "Heavy metal": "rock", "Rock and roll": "rock", "Electronic music": "edm", "House music": "edm", "Techno": "edm",
    "Dubstep": "edm", "Drum and bass": "edm", "Electronic dance music": "edm", "Trance music": "edm",
    "Electronica": "edm", "Rhythm and blues": "rnb", "Soul music": "rnb", "Funk": "rnb", "Folk music": "indie",
    "Independent music": "indie", "Country": "indie", "Ambient music": "indie", "Jazz": "rnb",
}
AUDIOSET_MOODS = {"Happy music", "Sad music", "Tender music", "Exciting music", "Angry music", "Scary music",
                  "Funny music"}


def classify(y, sr: int, windows: list[tuple[float, float]]) -> dict:
    """AudioSet tags (AST) averaged over a few 10 s windows -> genre votes + mood tags. Needs torch + transformers."""
    try:
        from transformers import pipeline
        import librosa
        import numpy as np
    except ImportError as e:
        raise RuntimeError("the genre model needs PyTorch + transformers: mv doctor --install match") from e
    clf = pipeline("audio-classification", model=AST_MODEL, top_k=40)
    y16 = librosa.resample(y, orig_sr=sr, target_sr=16000)
    scores: dict[str, float] = {}
    for a, b in windows:
        seg = y16[int(a * 16000):int(b * 16000)]
        if len(seg) < 16000:
            continue
        for r in clf({"raw": np.asarray(seg, dtype=np.float32), "sampling_rate": 16000}):
            scores[r["label"]] = scores.get(r["label"], 0) + r["score"] / len(windows)
    return interpret(scores)


def interpret(scores: dict[str, float]) -> dict:
    votes: dict[str, float] = {}
    for lab, v in scores.items():
        g = AUDIOSET_TO_GENRE.get(lab)
        if g:
            votes[g] = votes.get(g, 0) + v
    moods = sorted(((lab, round(v, 3)) for lab, v in scores.items() if lab in AUDIOSET_MOODS), key=lambda x: -x[1])
    if votes.get("pop") and any(m in ("Sad music", "Tender music") and v > 0.1 for m, v in moods):
        votes["ballad"] = votes.get("ballad", 0) + votes["pop"] * 0.8  # a sad / tender pop song is cut like a ballad
    ranked = sorted(votes.items(), key=lambda kv: -kv[1])
    top = sorted(((lab, round(v, 3)) for lab, v in scores.items()), key=lambda x: -x[1])[:6]
    return {"genres": [{"genre": g, "score": round(v, 3)} for g, v in ranked[:3]], "moods": moods[:3], "tags": top}
