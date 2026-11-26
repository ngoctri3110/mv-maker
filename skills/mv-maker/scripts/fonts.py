"""Font catalogue + on-demand Google Fonts downloader, glyph-coverage check, font specimen and palette tools.

Font spec syntax used everywhere (storyboard `font`, `display_font`, `poster.title_font`, CLI):
    "Family"            regular (or the family's only style)
    "Family:800"        weight 800
    "Family:900i"       weight 900 italic
    "Archivo:900i@125"  + width axis (fonts with a wdth axis only)
Downloads static TTF instances (libass renders static fonts reliably) into fonts/gf/ (git-ignored, cached).
"""
from __future__ import annotations

import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
FONTS_DIR = SKILL_DIR / "fonts"
GF_DIR = FONTS_DIR / "gf"
INDEX = GF_DIR / "index.json"

# scripts: latin, vietnamese, cyrillic, greek, thai, japanese, korean, chinese-simplified, chinese-traditional,
# arabic, devanagari. Tags describe the look/mood so an agent can match a poster or a song.
# These are hints - `check` verifies real glyph coverage after download.
CATALOG = [
    # --- clean sans
    ("Be Vietnam Pro", "sans", "clean modern readable neutral default", "latin vietnamese", True),
    ("Inter", "sans", "clean neutral ui minimal", "latin vietnamese cyrillic greek", True),
    ("Montserrat", "sans geometric", "pop fashion bold clean", "latin vietnamese cyrillic", True),
    ("Plus Jakarta Sans", "sans", "modern friendly startup", "latin vietnamese", True),
    ("Lexend", "sans", "readable wide-ish friendly", "latin vietnamese", False),
    ("Roboto", "sans", "neutral universal", "latin vietnamese cyrillic greek", True),
    ("Noto Sans", "sans", "universal fallback neutral", "latin vietnamese cyrillic greek", True),
    ("Josefin Sans", "sans geometric", "elegant vintage fashion thin", "latin vietnamese", True),
    ("Nunito", "sans rounded", "soft cute friendly", "latin vietnamese cyrillic", True),
    ("Quicksand", "sans rounded", "soft light pastel cute", "latin vietnamese", False),
    # --- heavy / condensed display
    ("Anton", "display condensed", "poster impact heavy hook uppercase", "latin vietnamese", False),
    ("Oswald", "display condensed", "news sporty strong uppercase", "latin vietnamese cyrillic", False),
    ("Barlow Condensed", "display condensed", "sporty street urban athletic", "latin vietnamese", True),
    ("Big Shoulders Display", "display condensed", "industrial city bold", "latin vietnamese", False),
    ("Bebas Neue", "display condensed", "cinematic poster uppercase", "latin", False),
    ("Bungee", "display blocky", "street signage hiphop urban", "latin vietnamese", False),
    ("Paytone One", "display rounded heavy", "fun youthful playful", "latin vietnamese", False),
    # --- wide / speed / tech
    ("Kanit", "sans heavy italic", "speed sporty cars luxury hype bold italic", "latin vietnamese thai", True),
    ("Exo 2", "techno", "futuristic racing edm speed italic", "latin vietnamese cyrillic", True),
    ("Saira", "techno", "racing sport motorsport italic", "latin vietnamese", True),
    ("Chakra Petch", "techno square", "gaming cyber esports", "latin vietnamese thai", True),
    ("Archivo", "grotesk variable-width", "editorial wide speed (use @125) bold italic", "latin vietnamese", True),
    ("Encode Sans Expanded", "wide", "luxury minimal wide", "latin vietnamese", False),
    ("Unbounded", "wide display", "y2k hype bold modern wide", "latin vietnamese cyrillic", False),
    ("Michroma", "wide techno", "luxury car minimal wide", "latin", False),
    ("Orbitron", "techno", "sci-fi space futuristic", "latin", False),
    # --- serif
    ("Playfair Display", "serif high-contrast", "elegant romantic fashion luxury", "latin vietnamese cyrillic", True),
    ("Cormorant Garamond", "serif", "classic poetic ballad delicate", "latin vietnamese cyrillic", True),
    ("Lora", "serif", "warm storytelling book", "latin vietnamese cyrillic", True),
    ("Prata", "serif didone", "elegant editorial vogue", "latin vietnamese cyrillic", False),
    ("Noto Serif", "serif", "universal classic", "latin vietnamese cyrillic greek", True),
    # --- script / handwriting
    ("Dancing Script", "script", "love sweet romantic", "latin vietnamese", False),
    ("Pacifico", "script retro", "summer surf fun", "latin vietnamese cyrillic", False),
    ("Great Vibes", "calligraphy", "wedding romantic luxury", "latin vietnamese cyrillic", False),
    ("Caveat", "handwriting", "diary casual acoustic", "latin cyrillic", False),
    ("Patrick Hand", "handwriting", "notes cute school", "latin vietnamese", False),
    ("Sedgwick Ave Display", "graffiti", "street hiphop rap", "latin vietnamese", False),
    ("Permanent Marker", "marker", "street raw diy", "latin", False),
    # --- retro / fun
    ("Lobster", "retro script bold", "retro diner 50s", "latin vietnamese cyrillic", False),
    ("Bangers", "comic", "comic loud fun", "latin vietnamese", False),
    ("Press Start 2P", "pixel", "8-bit gaming retro", "latin cyrillic greek", False),
    ("VT323", "terminal", "retro computer glitch", "latin vietnamese", False),
    ("Monoton", "neon lines", "80s neon retro disco", "latin", False),
    ("Righteous", "retro", "70s groovy", "latin", False),
    # --- other scripts
    ("Noto Sans JP", "sans", "japanese neutral", "japanese latin", False),
    ("M PLUS Rounded 1c", "sans rounded", "japanese cute soft", "japanese latin vietnamese", False),
    ("Dela Gothic One", "display heavy", "japanese poster bold", "japanese latin vietnamese", False),
    ("Noto Serif JP", "serif", "japanese elegant", "japanese latin", False),
    ("Noto Sans KR", "sans", "korean neutral", "korean latin", False),
    ("Black Han Sans", "display heavy", "korean poster bold", "korean latin", False),
    ("Do Hyeon", "display", "korean playful", "korean latin", False),
    ("Noto Sans SC", "sans", "chinese simplified neutral", "chinese-simplified latin", False),
    ("ZCOOL KuaiLe", "display rounded", "chinese playful", "chinese-simplified latin", False),
    ("Ma Shan Zheng", "brush", "chinese calligraphy", "chinese-simplified latin", False),
    ("Noto Sans TC", "sans", "chinese traditional neutral", "chinese-traditional latin", False),
    ("Prompt", "sans", "thai modern", "thai latin vietnamese", True),
    ("Mitr", "sans rounded", "thai friendly", "thai latin vietnamese", False),
    ("Noto Sans Arabic", "sans", "arabic neutral", "arabic latin", False),
    ("Cairo", "sans", "arabic modern", "arabic latin", False),
    ("Hind", "sans", "devanagari neutral", "devanagari latin", False),
    ("Noto Sans Devanagari", "sans", "devanagari universal", "devanagari latin", False),
]
LANG_SAMPLE = {"vietnamese": "ạếữđ", "thai": "กข", "cyrillic": "Жя", "greek": "Ωλ", "japanese": "あア", "korean": "한글",
               "chinese-simplified": "爱你", "chinese-traditional": "愛妳", "arabic": "حب", "devanagari": "प्य"}


def catalog(lang: str | None = None, tag: str | None = None) -> list[dict]:
    out = []
    for fam, cat, tags, scripts, ital in CATALOG:
        d = {"family": fam, "category": cat, "tags": tags, "scripts": scripts, "italic": ital}
        if lang and lang not in scripts.split():
            continue
        if tag and not all(t in f"{cat} {tags}" for t in tag.lower().split()):
            continue
        out.append(d)
    return out


def parse_spec(spec: str) -> tuple[str, int, bool, int | None]:
    m = re.fullmatch(r"\s*([^:@]+?)\s*(?::(\d{3})(i?))?\s*(?:@(\d{2,3}))?\s*", str(spec))
    if not m:
        raise ValueError(f"bad font spec '{spec}' (use 'Family', 'Family:800', 'Family:900i', 'Family:900i@125')")
    fam, w, i, wd = m.groups()
    return fam, int(w) if w else 400, bool(i), int(wd) if wd else None


def _slug(fam, w, i, wd) -> str:
    return f"{re.sub(r'[^A-Za-z0-9]', '', fam)}-{w}{'i' if i else ''}{f'-w{wd}' if wd else ''}"


def _index() -> dict:
    try:
        return json.loads(INDEX.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _names(path: Path) -> dict:
    from fontTools.ttLib import TTFont
    f = TTFont(str(path), lazy=True)
    n = f["name"]
    return {"full": n.getDebugName(4), "family": n.getDebugName(1), "sub": n.getDebugName(2)}


def ensure(spec: str) -> dict:
    """Download (once) a static TTF for the spec; returns {file, name (ASS/libass name), spec}."""
    fam, w, i, wd = parse_spec(spec)
    key = _slug(fam, w, i, wd)
    idx = _index()
    if key in idx and (GF_DIR / idx[key]["file"]).exists():
        return {**idx[key], "path": GF_DIR / idx[key]["file"]}
    GF_DIR.mkdir(parents=True, exist_ok=True)
    axes, vals = [], []
    if i:
        axes.append("ital"); vals.append("1")
    if wd:
        axes.append("wdth"); vals.append(str(wd))
    axes.append("wght"); vals.append(str(w))
    queries = [f"{fam}:{','.join(axes)}@{','.join(vals)}", fam]  # fall back to the default style
    css = None
    for q in queries:
        url = "https://fonts.googleapis.com/css2?family=" + urllib.parse.quote(q, safe=":,@")
        try:
            css = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "mv-maker"}), timeout=30).read().decode()
            if q == fam and (w != 400 or i or wd):
                print(f"[mv] note: '{spec}' style not available, using the default style of {fam}")
            break
        except urllib.error.HTTPError:
            continue
    if not css:
        raise RuntimeError(f"Google Fonts has no family '{fam}' (check spelling at https://fonts.google.com)")
    ttf = re.search(r"url\((https://[^)]+\.ttf)\)", css)
    if not ttf:
        raise RuntimeError(f"no TTF offered for '{spec}'")
    dst = GF_DIR / f"{key}.ttf"
    dst.write_bytes(urllib.request.urlopen(urllib.request.Request(ttf.group(1), headers={"User-Agent": "mv-maker"}), timeout=60).read())
    nm = _names(dst)
    entry = {"file": dst.name, "name": nm["full"], "family": nm["family"], "spec": spec}
    idx[key] = entry
    INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
    return {**entry, "path": dst}


def resolve(spec: str | None, fallback: str) -> str:
    """Storyboard font value -> libass font name. Plain names of installed/system fonts pass through."""
    if not spec:
        return fallback
    s = str(spec)
    fam = parse_spec(s)[0] if re.fullmatch(r"[^:@]+(:\d{3}i?)?(@\d+)?", s) else s
    known = any(c[0].lower() == fam.lower() for c in CATALOG)
    if ":" in s or "@" in s or known:
        try:
            return ensure(s)["name"]
        except Exception as e:  # offline etc.
            print(f"[mv] WARN: font '{s}' unavailable ({e}); using {fallback}")
            return fallback
    return s


def missing_glyphs(font_name_or_path, text: str) -> list[str]:
    from fontTools.ttLib import TTFont
    p = Path(font_name_or_path)
    if not p.exists():
        hit = next((GF_DIR / e["file"] for e in _index().values() if e["name"] == font_name_or_path), None)
        if not hit:
            return []
        p = hit
    cmap = TTFont(str(p), lazy=True).getBestCmap()
    return sorted({ch for ch in text if not ch.isspace() and ord(ch) not in cmap})


def palette(image: Path, n: int = 8) -> dict:
    """Image colours via FFmpeg palettegen: `main` (overall tones) and `vivid` (saturated, bright = accent candidates)."""
    import colorsys
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(image), "-vf",
                        "scale=240:-1,palettegen=max_colors=32:reserve_transparent=0:stats_mode=full",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    data, cols = r.stdout, []
    for k in range(0, len(data) - 2, 3):
        c = (data[k], data[k + 1], data[k + 2])
        if c not in cols:
            cols.append(c)
    hexs = lambda cs: ["#%02X%02X%02X" % c for c in cs]
    def score(c):
        h, s, v = colorsys.rgb_to_hsv(*(x / 255 for x in c))
        return s * v
    vivid = [c for c in sorted(cols, key=score, reverse=True) if score(c) > 0.18]
    picked = []
    for c in vivid:  # keep distinct hues
        h = colorsys.rgb_to_hsv(*(x / 255 for x in c))[0]
        if all(min(abs(h - colorsys.rgb_to_hsv(*(x / 255 for x in p))[0]), 1 - abs(h - colorsys.rgb_to_hsv(*(x / 255 for x in p))[0])) > 0.06 for p in picked):
            picked.append(c)
    main = sorted(cols, key=lambda c: sum(c))[:: max(1, len(cols) // n)][:n]
    return {"main": hexs(main), "vivid": hexs(picked[:6])}
