"""Token-lean helpers for the agent: one proof sheet instead of many frames, a compact planning digest instead of whole
reference files, plan.yaml -> shots expansion. Plain Python + PyYAML + FFmpeg (no mv.py import: no cycles)."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import yaml

REF = Path(__file__).resolve().parent.parent / "reference"


def _t(sec: float) -> str:
    m, s = divmod(max(0.0, sec), 60)
    return f"{int(m)}:{s:04.1f}"


# ----------------------------------------------------------------------------------------------- proof sheet
def proof_sheet(video: Path, shots: list[dict], s0: float, duration: float, out: Path, work: Path, font: Path,
                vertical: bool, per_page: int = 24) -> list[Path]:
    """One frame from the middle of every shot, labelled `S07 1:23.4 lyric...`, tiled into as few images as possible.
    Returns the page paths (refs/proof.jpg, refs/proof_2.jpg ...)."""
    tw, th = (180, 320) if vertical else (320, 180)
    cols = 8 if vertical else 4
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    shutil.copy(font, work / "_f.ttf")
    pages: list[Path] = []
    for p0 in range(0, len(shots), per_page):
        chunk = shots[p0:p0 + per_page]
        for k, sh in enumerate(chunk):
            a, b = float(sh["_s"]), float(sh["_e"])
            t = min(max(0.0, (a + b) / 2 - s0), max(0.0, duration - 0.05))
            lab = str(sh.get("lyric") or sh.get("section") or "")[:20]
            (work / f"l{k:03d}.txt").write_text(f"{sh['id']}  {_t(a)}\n{lab}", encoding="utf-8", newline="\n")
            fs = 13
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-vf",
                            f"scale={tw}:{th},drawtext=fontfile=_f.ttf:textfile=l{k:03d}.txt:fontsize={fs}:"
                            f"fontcolor=yellow:line_spacing=2:x=4:y=4:box=1:boxcolor=black@0.6:boxborderw=3",
                            f"f{k:03d}.jpg"], check=True, cwd=work)
        rows = -(-len(chunk) // cols)
        name = out if not pages else out.with_name(f"{out.stem}_{len(pages) + 1}{out.suffix}")
        name.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "1", "-i", "f%03d.jpg", "-vf",
                        f"tile={min(cols, len(chunk))}x{rows}:padding=3:color=0x101010", "-frames:v", "1", "-q:v", "4",
                        str(name.resolve())], check=True, cwd=work)
        for f in work.glob("f*.jpg"):
            f.unlink()
        pages.append(name)
    return pages


# ----------------------------------------------------------------------------------------------- planning digest
def _md_tables(text: str) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        if line.startswith("|") and not re.match(r"^\|[-| ]+\|$", line):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows


def technique_index() -> dict[str, str]:
    """ID -> 'Name: when to use' from techniques.md tables (compact)."""
    out = {}
    for r in _md_tables((REF / "techniques.md").read_text(encoding="utf-8")):
        if r and re.match(r"^[A-Z]-[A-Z0-9-]+$", r[0]) and len(r) >= 3:
            out[r[0]] = f"{r[1]}: {r[2]}"[:110]
    return out


def mood_picks(mood: str) -> list[tuple[str, str]]:
    text = (REF / "techniques.md").read_text(encoding="utf-8")
    sec = text.split("## Mood → quick picks", 1)[-1].split("##", 1)[0]
    words = [w for w in re.split(r"[\s,/]+", mood.lower()) if len(w) > 2]
    rows = [r for r in _md_tables(sec)[1:] if len(r) >= 2]
    hit = [(r[0], r[1]) for r in rows if any(w in r[0].lower() for w in words)]
    return hit or [(r[0], r[1]) for r in rows]


def context(genre: str | None, platforms, vtype: str, mood: str | None, presets: dict, genres: dict,
            plan_text: list[str] | None) -> list[str]:
    """Only what this project needs: genre grammar, fitting presets/templates, mood picks with technique meanings,
    platform plan, the storyboard fields to use. ~1-1.5k tokens instead of reading every reference file."""
    L = [f"# Context - type {vtype}" + (f" · genre {genre}" if genre else "") + (f" · mood {mood}" if mood else ""), ""]
    if genre and genre in genres:
        g = genres[genre]
        L.append(f"## Genre {genre}: {g.get('name', '')}")
        L.append(f"shot length (s) per section: " + ", ".join(f"{k} {v[0]}-{v[1]}" for k, v in (g.get("asl") or {}).items()))
        if g.get("performance"):
            L.append("performance share: " + ", ".join(f"{k} {v[0]:.0%}-{v[1]:.0%}" for k, v in g["performance"].items()))
        L += [f"min shot {g.get('min_shot')}s · cut on {g.get('cut_on')} · last chorus fastest · change `size` on every cut "
              "from the same source · `cut_lead: 1f` for beat-driven songs", ""]
    want = "lyric-template" if vtype == "lyric" else None
    names = (genres.get(genre, {}).get("presets") or []) if genre and vtype == "mv" else []
    L.append("## Presets" if vtype != "lyric" else "## Lyric-video templates (mv auto --template)")
    for k, v in presets.items():
        if v.get("kind") == want and (not names or k in names or vtype == "lyric"):
            th = f" [themes: {', '.join(v.get('themes') or {})}]" if v.get("themes") else ""
            L.append(f"- {k}: {v.get('description', '')}{th}")
    L.append("")
    if mood:
        idx = technique_index()
        L.append(f"## Mood picks ({mood})")
        ids = []
        for feel, picks in mood_picks(mood)[:3]:
            L.append(f"- {feel}: {picks}")
            ids += re.findall(r"[A-Z]-[A-Z0-9-]+", picks)
        for i in dict.fromkeys(ids):
            if i in idx:
                L.append(f"  - {i} = {idx[i]}")
        L.append("")
    if plan_text:
        L += ["## Platform plan"] + plan_text[:12] + [""]
    L.append("## Storyboard fields to use")
    if vtype == "mv":
        L += ["shots: {id, start, end, section, role: performance|narrative|broll, size: wide|medium|close|ecu|insert,",
              "  layers: auto + look_for: '<concrete picture>' (mv match) | [{src, in, lipsync: true, fx, zoom}],",
              "  layout: full|split_v|split_h|pip|fit_blur, fx: [grade:<g>, ...], transition, beat_fx: [zoom|flash|shake]}",
              "top: genre, preset, platforms, format, title_card {artist, title}, end_card, cut_lead, lyrics_file, lyric_style",
              "fast path: write plan.yaml per section -> mv auto <p> --plan plan.yaml (reference/plan-template.yaml)"]
    elif vtype == "lyric":
        L += ["mv auto <p> --template lv-<look> [--theme t] writes the storyboard; tweak: palette, accent, font, typo.size,",
              "lyric_style per section (subtitle karaoke word typewriter stack neon scroll grunge paper marker stagger),",
              "lyric_lead 0.25-0.4, visualizer {type: bars|wave}, layers with user footage on some shots"]
    else:
        L += ["layout: poster, poster {title, artist, visualizer: wave|bars|none}, lyric_style: scroll, lyric_highlight: karaoke,",
              "accent from the cover (mv palette), format 9:16 (card on top) or 16:9 (card left)"]
    L.append("Full references only when needed: storyboard-schema.md, techniques.md, lyrics.md, genres.md, matching.md.")
    return L


# ----------------------------------------------------------------------------------------------- plan.yaml
PLAN_SHOT_KEYS = ("fx", "beat_fx", "beat_every", "beat_zoom", "beat_flash", "lyric_style", "layout", "transition",
                  "caption_anim", "feather", "ratio", "technique", "avoid")


def section_plan(plan: dict, label: str, occurrence: int, is_last: bool) -> dict:
    """Plan for one song section: `chorus@last` / `chorus@2` beat `chorus`; canonical names (hook -> chorus) match."""
    import editcheck as EC
    secs = plan.get("sections") or {}
    keys = [f"{label}@last" if is_last else None, f"{label}@{occurrence}", label]
    ck = EC.canon(label)
    if ck and ck != label:
        keys += [f"{ck}@last" if is_last else None, f"{ck}@{occurrence}", ck]
    merged: dict = {}
    for k in reversed([k for k in keys if k]):
        if k in secs:
            merged.update(secs[k] or {})
    return merged


def cycle(v, i: int):
    if isinstance(v, list):
        return v[i % len(v)] if v else None
    return v


def plan_shot(sh: dict, sp: dict, i: int, performance_src: str | None, state: dict | None = None) -> dict:
    """Fill one shot from its section plan: role / size cycle per shot; look_for cycles over the shots that need
    footage (performance shots use the lip-synced clip), so a section's descriptions are not repeated early."""
    state = state if state is not None else {}
    role = cycle(sp.get("role"), i)
    if role:
        sh["role"] = role
    size = cycle(sp.get("size"), i)
    if size:
        sh["size"] = size
    if role == "performance" and performance_src:
        sh["layers"] = [{"src": performance_src, "lipsync": True}]
        sh.pop("look_for", None)
    else:
        look = cycle(sp.get("look_for"), state.get("look", 0))
        if look:
            sh["look_for"] = look
            state["look"] = state.get("look", 0) + 1
    for k in PLAN_SHOT_KEYS:
        if k in sp:
            sh[k] = sp[k]
    return sh


def load_plan(path: Path) -> dict:
    plan = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(plan.get("sections"), dict) or not plan["sections"]:
        raise ValueError(f"{path}: needs `sections:` (intro / verse / chorus ... -> look_for, role, size, fx)")
    return plan
