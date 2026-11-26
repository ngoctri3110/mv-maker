"""Edit check: compare a storyboard's cutting against the editing grammar of its genre (reference/genres.yaml).

Pure Python (PyYAML only) so `mv check` / `mv review` run anywhere. Findings are advice, never errors:
average shot length per section, performance / story balance, jump cuts, shot-size variety, cuts off the beat,
the 3-second hook on vertical video and the energy build into the last chorus.
"""
from __future__ import annotations

from pathlib import Path

import yaml

GENRES_FILE = Path(__file__).resolve().parent.parent / "reference" / "genres.yaml"
ROLES = {"performance", "narrative", "broll", "concept"}
SIZES = {"ews", "wide", "full", "medium", "mcu", "close", "ecu", "insert", "aerial", "pov"}
# shot sizes grouped by how far the camera is - two cuts in the same group from one source read as a jump cut
SIZE_GROUP = {"ews": 0, "aerial": 0, "wide": 0, "full": 1, "medium": 2, "mcu": 2, "pov": 2, "close": 3, "ecu": 4,
              "insert": 4}
CANON = [("pre", ("pre", "build", "lift", "riser", "tiền")), ("drop", ("drop",)),
         ("chorus", ("chorus", "hook", "refrain", "post", "điệp")), ("verse", ("verse", "rap", "phiên", "đoạn")),
         ("bridge", ("bridge", "break", "cầu")), ("intro", ("intro", "mở", "open")),
         ("outro", ("outro", "end", "kết", "close"))]

MSG = {
    "en": {
        "asl_slow": "{sec}: average shot {asl:.1f}s is slower than {genre} ({lo}-{hi}s) - cut more often or add cutaways",
        "asl_fast": "{sec}: average shot {asl:.1f}s is faster than {genre} ({lo}-{hi}s) - let shots breathe",
        "short": "{ids}: shorter than {min}s - reads as a strobe; keep only as a deliberate burst",
        "perf_low": "{sec}: performance is {p:.0%} of the time, {genre} usually {lo:.0%}-{hi:.0%} - show the artist more",
        "perf_high": "{sec}: performance is {p:.0%} of the time, {genre} usually {lo:.0%}-{hi:.0%} - cut away to story / b-roll",
        "jump": "{a}->{b}: same source and same shot size - a jump cut; change size/angle or put a cutaway between",
        "nosize": "{sec}: every shot is '{size}' - vary wide / medium / close to keep the eye moving",
        "offbeat": "cuts off the beat (> {tol:.2f}s): {ids} - snap to analysis.json beats",
        "offbar": "{n} cuts land between downbeats in {genre} ({cut_on}) - e.g. {ids}; big changes belong on the bar",
        "hook": "first shot is {d:.1f}s on vertical video - open on the hook (strongest image / line) within 3s",
        "arc": "last chorus averages {b:.1f}s/shot vs first chorus {a:.1f}s - cut the final chorus faster to build energy",
        "nogenre": "unknown genre '{genre}' - one of {names}",
        "ok": "no issues - the cutting fits {genre}",
        "stats": "| Section | Shots | Avg shot | {genre} range | Performance |",
    },
    "vi": {
        "asl_slow": "{sec}: shot trung bình {asl:.1f}s chậm hơn chuẩn {genre} ({lo}-{hi}s) - cắt dày hơn hoặc chèn cutaway",
        "asl_fast": "{sec}: shot trung bình {asl:.1f}s nhanh hơn chuẩn {genre} ({lo}-{hi}s) - để shot thở hơn",
        "short": "{ids}: ngắn hơn {min}s - nhìn như chớp nháy; chỉ giữ nếu là cú dồn có chủ đích",
        "perf_low": "{sec}: performance chiếm {p:.0%} thời lượng, {genre} thường {lo:.0%}-{hi:.0%} - cho ca sĩ xuất hiện nhiều hơn",
        "perf_high": "{sec}: performance chiếm {p:.0%} thời lượng, {genre} thường {lo:.0%}-{hi:.0%} - cắt sang câu chuyện / b-roll",
        "jump": "{a}->{b}: cùng nguồn, cùng cỡ cảnh - lỗi jump cut; đổi cỡ cảnh/góc máy hoặc chèn cutaway ở giữa",
        "nosize": "{sec}: mọi shot đều '{size}' - xen toàn / trung / cận để mắt người xem chuyển động",
        "offbeat": "cắt lệch beat (> {tol:.2f}s): {ids} - kéo về beat trong analysis.json",
        "offbar": "{n} điểm cắt rơi giữa các phách mạnh với {genre} ({cut_on}) - vd. {ids}; thay đổi lớn nên ở đầu ô nhịp",
        "hook": "shot đầu dài {d:.1f}s trên video dọc - mở bằng hook (hình/câu mạnh nhất) trong 3 giây đầu",
        "arc": "điệp khúc cuối trung bình {b:.1f}s/shot so với điệp khúc đầu {a:.1f}s - cắt điệp khúc cuối nhanh hơn để dồn cảm xúc",
        "nogenre": "không có thể loại '{genre}' - chọn một trong {names}",
        "ok": "không có vấn đề - nhịp dựng hợp {genre}",
        "stats": "| Đoạn | Số shot | Shot TB | Chuẩn {genre} | Performance |",
    },
}


def tsec(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    sec = 0.0
    for part in str(v).strip().split(":"):
        sec = sec * 60 + float(part)
    return sec


def load_genres() -> dict:
    return yaml.safe_load(GENRES_FILE.read_text(encoding="utf-8")) or {}


def canon(section) -> str | None:
    s = str(section or "").lower()
    for key, words in CANON:
        if any(w in s for w in words):
            return key
    return None


def _groups(shots: list) -> list[tuple[str, str, list]]:
    """Consecutive shots with the same section label -> [(label, canonical, shots)]."""
    out: list = []
    for sh in shots:
        lab = str(sh.get("section") or "").strip()
        if out and out[-1][0] == lab:
            out[-1][2].append(sh)
        else:
            out.append((lab, canon(lab), [sh]))
    return out


def check(sb: dict, shots: list, beats: list[float] | None = None, downbeats: list[float] | None = None,
          lang: str = "en") -> dict:
    """-> {genre, stats: [rows], warnings: [str]}. Shots must have start/end (song time)."""
    T = MSG.get(str(lang or "en")[:2], MSG["en"])
    genres = load_genres()
    gname = str(sb.get("genre") or "").lower()
    warnings: list[str] = []
    prof = genres.get(gname) if gname else None
    if gname and not prof:
        warnings.append(T["nogenre"].format(genre=gname, names=", ".join(genres)))
    label = (prof or {}).get("name", gname or "-").split("/")[0].strip()
    asl_tab = (prof or {}).get("asl") or {}
    perf_tab = (prof or {}).get("performance") or {}
    stats = []
    chorus_asl = []
    for lab, key, grp in _groups(shots):
        durs = [tsec(s["end"]) - tsec(s["start"]) for s in grp]
        total = sum(durs)
        asl = total / len(grp)
        rng = asl_tab.get(key) or (asl_tab.get("chorus") if key == "drop" else None)
        roled = [(s, d) for s, d in zip(grp, durs) if s.get("role")]
        perf = None
        if len(grp) >= 2 and roled and len(roled) * 2 >= len(grp):
            perf = sum(d for s, d in roled if s.get("role") == "performance") / max(1e-6, sum(d for _, d in roled))
        stats.append({"section": lab or "-", "canon": key, "shots": len(grp), "asl": asl, "range": rng, "perf": perf})
        if key == "chorus" or key == "drop":
            chorus_asl.append(asl)
        name = lab or key or "-"
        if rng and len(grp) >= 2 or (rng and total > rng[1] * 1.6):
            if asl > rng[1] * 1.1:
                warnings.append(T["asl_slow"].format(sec=name, asl=asl, genre=label, lo=rng[0], hi=rng[1]))
            elif asl < rng[0] * 0.9:
                warnings.append(T["asl_fast"].format(sec=name, asl=asl, genre=label, lo=rng[0], hi=rng[1]))
        pr = perf_tab.get(key) or (perf_tab.get("chorus") if key == "drop" else None)
        if pr and perf is not None:
            if perf < pr[0] - 0.05:
                warnings.append(T["perf_low"].format(sec=name, p=perf, genre=label, lo=pr[0], hi=pr[1]))
            elif perf > pr[1] + 0.05:
                warnings.append(T["perf_high"].format(sec=name, p=perf, genre=label, lo=pr[0], hi=pr[1]))
        sizes = [s.get("size") for s in grp if s.get("size")]
        if len(sizes) >= 3 and len(sizes) == len(grp) and len(set(sizes)) == 1:
            warnings.append(T["nosize"].format(sec=name, size=sizes[0]))
    if prof:
        short = [s["id"] for s in shots if tsec(s["end"]) - tsec(s["start"]) < float(prof.get("min_shot", 0)) - 1e-6]
        if short:
            warnings.append(T["short"].format(ids=", ".join(short[:8]) + (" ..." if len(short) > 8 else ""),
                                              min=prof.get("min_shot")))
    for a, b in zip(shots, shots[1:]):
        la = [ly for ly in a.get("layers") or [] if not ly.get("blend")]
        lb = [ly for ly in b.get("layers") or [] if not ly.get("blend")]
        if not la or not lb or la[0].get("src") != lb[0].get("src") or not la[0].get("src"):
            continue
        if str(la[0]["src"]).startswith("_scene") or la[0].get("gen"):  # generated backgrounds never jump
            continue
        if str(a.get("transition", "cut")).split(":")[0] not in ("cut", "", "none"):
            continue
        sa, sz = a.get("size"), b.get("size")
        same = (sa and sz and SIZE_GROUP.get(sa) == SIZE_GROUP.get(sz)) or (not sa and not sz)
        if same and (a.get("layout", "full") == b.get("layout", "full") == "full"):
            warnings.append(T["jump"].format(a=a["id"], b=b["id"]))
    cuts = [(s["id"], tsec(s["start"])) for s in shots[1:]]
    if beats and cuts:
        tol = 0.07
        off = [(i, min(abs(t - x) for x in beats)) for i, t in cuts]
        bad = [f"{i} ({d:.2f}s)" for i, d in off if d > tol]
        if bad:
            warnings.append(T["offbeat"].format(tol=tol, ids=", ".join(bad[:8]) + (" ..." if len(bad) > 8 else "")))
        if prof and prof.get("cut_on") in ("downbeat", "phrase") and downbeats:
            sec_starts = {tsec(g[2][0]["start"]) for g in _groups(shots)}
            mid = [i for i, t in cuts if t in sec_starts and min(abs(t - x) for x in downbeats) > tol]
            if mid:
                warnings.append(T["offbar"].format(n=len(mid), genre=label, cut_on=prof["cut_on"], ids=", ".join(mid[:6])))
    vertical = str(sb.get("format", "9:16")) == "9:16"
    if vertical and shots:
        d0 = tsec(shots[0]["end"]) - tsec(shots[0]["start"])
        if d0 > 3.0 and not sb.get("lyric_style") == "scroll":
            warnings.append(T["hook"].format(d=d0))
    if len(chorus_asl) >= 2 and chorus_asl[-1] > chorus_asl[0] * 1.1:
        warnings.append(T["arc"].format(a=chorus_asl[0], b=chorus_asl[-1]))
    return {"genre": gname, "label": label, "stats": stats, "warnings": warnings, "T": T}


def report_md(res: dict) -> list[str]:
    """Markdown block for storyboard.md / `mv check`."""
    T = res["T"]
    L = [T["stats"].format(genre=res["label"]), "|---|---|---|---|---|"]
    for r in res["stats"]:
        rng = f"{r['range'][0]}-{r['range'][1]}s" if r["range"] else "-"
        perf = f"{r['perf']:.0%}" if r["perf"] is not None else "-"
        L.append(f"| {r['section']} | {r['shots']} | {r['asl']:.1f}s | {rng} | {perf} |")
    L.append("")
    if res["warnings"]:
        L += [f"- ⚠ {w}" for w in res["warnings"]]
    else:
        L.append(f"- ✅ {T['ok'].format(genre=res['label'])}")
    return L
