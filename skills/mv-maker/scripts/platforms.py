"""Platform planning: what TikTok / Reels / Facebook / Shorts / YouTube need, merged into one production plan
(versions to render, master format, source footage to look for, length, safe zones, hook, loudness) and checks.
Pure Python + PyYAML; numbers live in reference/platforms.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml

FILE = Path(__file__).resolve().parent.parent / "reference" / "platforms.yaml"
ASPECT = {"9:16": 9 / 16, "4:5": 4 / 5, "1:1": 1.0, "16:9": 16 / 9}

MSG = {
    "en": {
        "unknown": "unknown platform '{p}' - one of {names}",
        "long": "{name}: the video is {d:.0f}s, longer than {mx:.0f}s - render a cut (e.g. the hook/chorus) for it",
        "best": "{name}: {d:.0f}s is outside the {lo}-{hi}s range that performs best - consider a shorter cut",
        "format": "{name} wants {want}; this storyboard is {have} - render that version too: mv render <p> --format {want}",
        "area": "lyric_area {area} reaches into {name}'s UI ({side}) - move it inside the safe zone",
        "hook": "{name}: the first shot lasts {d:.1f}s - viewers decide within {h}s, open on the strongest image",
    },
    "vi": {
        "unknown": "không có nền tảng '{p}' - chọn một trong {names}",
        "long": "{name}: video dài {d:.0f}s, vượt giới hạn {mx:.0f}s - render bản cắt (vd. đoạn hook/điệp khúc) cho nền tảng này",
        "best": "{name}: {d:.0f}s nằm ngoài khoảng {lo}-{hi}s hiệu quả nhất - cân nhắc bản ngắn hơn",
        "format": "{name} cần {want}; storyboard đang là {have} - render thêm bản đó: mv render <p> --format {want}",
        "area": "lyric_area {area} lấn vào vùng giao diện của {name} ({side}) - dời vào vùng an toàn",
        "hook": "{name}: shot đầu dài {d:.1f}s - người xem quyết định trong {h}s, mở bằng hình mạnh nhất",
    },
}


def load() -> dict:
    return yaml.safe_load(FILE.read_text(encoding="utf-8")) or {}


def expand(names) -> list[str]:
    """'all' / 'vertical' / 'meta' groups and comma strings -> platform keys (order kept, no duplicates)."""
    data = load()
    groups = data.get("groups") or {}
    if isinstance(names, str):
        names = [x.strip() for x in names.split(",") if x.strip()]
    out: list[str] = []
    for n in names or []:
        for k in groups.get(n, [n]):
            if k not in data or k == "groups":
                raise ValueError(MSG["en"]["unknown"].format(p=k, names=", ".join(x for x in data if x != "groups")))
            if k not in out:
                out.append(k)
    return out


def safe_zone(names, fmt: str) -> list[float] | None:
    """Union (max per side) of the safe margins of the platforms that use this aspect ratio."""
    data = load()
    zs = [data[k]["safe"] for k in expand(names) if data[k]["format"] == fmt]
    return [max(z[i] for z in zs) for i in range(4)] if zs else None


def plan(names, duration: float | None = None) -> dict:
    data = load()
    keys = expand(names)
    ps = [dict(data[k], key=k) for k in keys]
    versions: dict[str, list[str]] = {}
    for p in ps:
        versions.setdefault(p["format"], []).append(p["name"])
    fmts = list(versions)
    tallest = min(fmts, key=lambda f: ASPECT[f])
    widest = max(fmts, key=lambda f: ASPECT[f])
    if len(fmts) == 1:
        source = (f"{fmts[0]} sources at >= {max(p['size'][1] for p in ps)}p fill the frame; "
                  + ("landscape 16:9 footage also works but is cropped to the centre third - keep subjects centred "
                     "(`focus:`) or use `layout: fit_blur`" if ASPECT[fmts[0]] < 1 else "portrait clips need fit_blur"))
    else:
        source = (f"several aspect ratios ({', '.join(fmts)}): prefer landscape 4K (3840x2160) or at least 1080p "
                  f"footage with the subject in the centre third, so one source crops to every version; "
                  f"portrait-only clips work for {tallest} but need `fit_blur` in {widest}")
    vertical = [p for p in ps if ASPECT[p["format"]] < 1]
    max_v = min((p["max_sec"] for p in vertical), default=None)
    best_hi = min((p["best_sec"][1] for p in ps), default=None)
    out = {
        "platforms": [p["name"] for p in ps],
        "versions": versions,
        "master": widest if len(fmts) > 1 else fmts[0],
        "source": source,
        "max_vertical_sec": max_v,
        "best_cut_sec": best_hi,
        "hook_sec": min(p["hook_sec"] for p in ps),
        "loudness": max(p["loudness"] for p in ps),
        "safe": {f: safe_zone(keys, f) for f in fmts},
        "notes": {p["name"]: " ".join(str(p.get("notes", "")).split()) for p in ps},
    }
    if duration:
        out["duration"] = duration
        out["needs_cut"] = [p["name"] for p in ps if duration > p["max_sec"]]
    return out


def plan_text(pl: dict) -> list[str]:
    L = [f"Platforms: {', '.join(pl['platforms'])}", "", "Versions to render:"]
    for f, names in pl["versions"].items():
        L.append(f"  {f:<5} -> {', '.join(names)}   (mv render <p> --format {f})")
    L += ["", f"Edit master: {pl['master']}  (storyboard `format:`; other versions re-frame the same edit)",
          f"Source footage: {pl['source']}"]
    if pl.get("duration"):
        L.append(f"Length: the song edit is {pl['duration']:.0f}s"
                 + (f"; too long for {', '.join(pl['needs_cut'])} - plan a hook cut" if pl.get("needs_cut") else ""))
    if pl.get("max_vertical_sec"):
        L.append(f"Vertical limit: {pl['max_vertical_sec']}s · best-performing cut: <= {pl['best_cut_sec']}s "
                 "(plan which section is the short version: usually the first chorus)")
    L.append(f"Hook: strongest image / line within the first {pl['hook_sec']}s")
    for f, z in pl["safe"].items():
        if z:
            L.append(f"Safe zone {f}: keep text/faces out of top {z[0]:.0%}, bottom {z[1]:.0%}, left {z[2]:.0%}, "
                     f"right {z[3]:.0%} (lyrics are placed inside it automatically)")
    L.append(f"Loudness: platforms normalise to about {pl['loudness']} LUFS - leave a finished master alone; set "
             "`loudness:` only for a mix that is far too quiet / loud")
    L += ["", "Platform notes:"] + [f"  {k}: {v}" for k, v in pl["notes"].items()]
    return L


def check(sb: dict, shots: list, duration: float, lang: str = "en") -> list[str]:
    T = MSG.get(str(lang or "en")[:2], MSG["en"])
    names = sb.get("platforms")
    if not names:
        return []
    try:
        keys = expand(names)
    except ValueError as e:
        return [str(e)]
    data = load()
    fmt = str(sb.get("format", "9:16"))
    out = []
    first = (float(shots[0]["end"]) - float(shots[0]["start"])) if shots else 0
    for k in keys:
        p = data[k]
        if p["format"] != fmt:
            out.append(T["format"].format(name=p["name"], want=p["format"], have=fmt))
            continue
        if duration > p["max_sec"]:
            out.append(T["long"].format(name=p["name"], d=duration, mx=p["max_sec"]))
        elif not p["best_sec"][0] <= duration <= p["best_sec"][1] * 1.5:
            out.append(T["best"].format(name=p["name"], d=duration, lo=p["best_sec"][0], hi=p["best_sec"][1]))
        if first > p["hook_sec"] + 1.2 and not sb.get("title_card"):
            out.append(T["hook"].format(name=p["name"], d=first, h=p["hook_sec"]))
        ar = sb.get("lyric_area")
        if ar:
            t, b, l, r = p["safe"]
            for side, bad in (("top", ar[1] < t), ("bottom", ar[3] > 1 - b), ("left", ar[0] < l), ("right", ar[2] > 1 - r)):
                if bad:
                    out.append(T["area"].format(area=ar, name=p["name"], side=side))
                    break
    return out
