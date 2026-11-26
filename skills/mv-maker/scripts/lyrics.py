"""Lyric engine for mv.py: font pack, ASS lyric styles, poster-player geometry, lyric/whisper alignment."""
from __future__ import annotations

import difflib
import re
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
FONTS_DIR = SKILL_DIR / "fonts"
GF = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
# All OFL licensed, all with Vietnamese glyphs.
FONT_PACK = {
    "Be Vietnam Pro": ["bevietnampro/BeVietnamPro-Regular.ttf", "bevietnampro/BeVietnamPro-SemiBold.ttf",
                       "bevietnampro/BeVietnamPro-Bold.ttf", "bevietnampro/BeVietnamPro-ExtraBold.ttf"],
    "Anton": ["anton/Anton-Regular.ttf"],
    "Montserrat": ["montserrat/Montserrat%5Bwght%5D.ttf"],
    "Playfair Display": ["playfairdisplay/PlayfairDisplay%5Bwght%5D.ttf"],
    "Dancing Script": ["dancingscript/DancingScript%5Bwght%5D.ttf"],
    "Pacifico": ["pacifico/Pacifico-Regular.ttf"],
}
LYRIC_STYLES = {"subtitle", "karaoke", "word", "typewriter", "stack", "neon", "scroll",
                "grunge", "paper", "marker", "stagger"}


def font_files(family: str) -> list[Path]:
    return [FONTS_DIR / urllib.parse.unquote(p.rsplit("/", 1)[1]) for p in FONT_PACK.get(family, [])]


def has_font(family: str) -> bool:
    files = font_files(family)
    return bool(files) and all(f.exists() for f in files)


def download_fonts() -> None:
    FONTS_DIR.mkdir(exist_ok=True)
    for fam, paths in FONT_PACK.items():
        for p, dst in zip(paths, font_files(fam)):
            if dst.exists():
                continue
            req = urllib.request.Request(GF + p, headers={"User-Agent": "mv-maker"})
            with urllib.request.urlopen(req, timeout=60) as r:
                dst.write_bytes(r.read())
        print(f"[mv] font ok: {fam}")


def ass_color(hexstr: str, alpha: int = 0) -> str:
    h = hexstr.lstrip("#")
    return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def ff_color(hexstr: str) -> str:
    return "0x" + hexstr.lstrip("#")


def _even(n: float) -> int:
    return max(2, int(round(n)) // 2 * 2)


def poster_geom(W: int, H: int) -> dict:
    """Layout of the 'poster player' lyric video: cover card, title, artist, visualizer, progress bar, lyric area."""
    if H >= W * 1.2:  # vertical: stacked
        cw, ch = _even(W * 0.70), _even(H * 0.33)
        cx, cy = (W - cw) // 2, int(H * 0.07)
        tx, ty = W // 2, cy + ch + int(H * 0.02)
        ay = ty + int(H * 0.036)
        vis = (int(W * 0.12), ay + int(H * 0.034), _even(W * 0.76), _even(H * 0.026))
        bar = (int(W * 0.12), vis[1] + vis[3] + int(H * 0.006), _even(W * 0.76), max(4, _even(H / 320)))
        lyr = (int(W * 0.07), bar[1] + int(H * 0.04), int(W * 0.93), int(H * 0.82))
        align = "center"
    else:  # landscape / square: card left, lyrics right
        ch = _even(H * 0.56)
        cw = ch
        cx, cy = int(W * 0.07), int(H * 0.09)
        tx, ty = cx + cw // 2, cy + ch + int(H * 0.035)
        ay = ty + int(H * 0.065)
        vis = (cx, ay + int(H * 0.06), cw, _even(H * 0.05))
        bar = (cx, vis[1] + vis[3] + int(H * 0.012), cw, max(4, _even(H / 220)))
        lyr = (int(W * 0.50), int(H * 0.12), int(W * 0.95), int(H * 0.88))
        align = "left"
    return {"card": (cx, cy, cw, ch), "title": (tx, ty), "artist": (tx, ay), "vis": vis, "bar": bar,
            "lyr": lyr, "align": align}


def wrap_words(words: list[str], max_chars: int) -> list[list[int]]:
    """Greedy wrap -> list of rows, each a list of word indices."""
    rows, cur, n = [], [], 0
    for i, w in enumerate(words):
        if cur and n + 1 + len(w) > max_chars:
            rows.append(cur)
            cur, n = [], 0
        cur.append(i)
        n += len(w) + (1 if n else 0)
    if cur:
        rows.append(cur)
    return rows


def word_times(ln: dict) -> list[tuple[str, float, float]]:
    """(word, start, end) for a lyric line; spreads evenly by length when no word timing exists."""
    ws = ln.get("words")
    if ws:
        return [(str(w[0]), float(w[1]), float(w[2])) for w in ws]
    words = str(ln["text"]).split()
    s, e = float(ln["start"]), float(ln["end"])
    total = sum(len(w) + 1 for w in words) or 1
    out, t = [], s
    for w in words:
        d = (e - s) * (len(w) + 1) / total
        out.append((w, t, t + d))
        t += d
    return out


def _esc(t: str) -> str:
    return str(t).replace("{", "(").replace("}", ")").replace("\n", "\\N")


TYPO_STYLES = {"lyric", "karaoke", "neon", "big", "scroll", "scrollk", "title", "ptitle", "grunge", "paper", "marker",
               "stag", "stagbig", "tc_artist", "tc_title"}


class AssWriter:
    def __init__(self, W: int, H: int, font: str, display_font: str, accent: str, s0: float, t_end: float,
                 typo: dict | None = None, title_font: str | None = None, artist_font: str | None = None,
                 safe: list | None = None):
        self.W, self.H, self.s0, self.t_end = W, H, s0, t_end
        self.base = min(W, H)
        self.lb = self.base * float((typo or {}).get("size", 1.0))  # lyric size (typo.size scales every lyric style)
        self.vertical = H > W
        self.font, self.display, self.accent = font, display_font, accent
        self.mv = int(H * (0.22 if self.vertical else 0.08))  # 9:16 keeps text above TikTok/Reels UI
        # platform safe zone [top, bottom, left, right] (storyboard `platforms:`): lyrics stay clear of the app's UI
        st, sbm, sl, sr = safe or (0, 0, 0, 0)
        self.mv = max(self.mv, int(H * (sbm + 0.02)))
        self.top = max(0.26, st + 0.02)
        self.sx0, self.sx1 = int(W * max(0.08, sl + 0.01)), int(W * min(0.92, 1 - sr - 0.01))
        self.events: list[str] = []
        t = self.typo = dict(typo or {})
        # typo: colour / outline_color / outline / shadow / spacing / slant / upper / bold (poster-matched lettering)
        om, sm = float(t.get("outline", 1.0)), float(t.get("shadow", 1.0))
        bord, shad = max(0, round(H / 400 * om)), max(0, round(H / 640 * sm))
        sp = round(float(t.get("spacing", 0)) * self.base / 1080, 1)
        bold = 0 if t.get("bold") is False else -1
        b = self.lb
        white = ass_color(t.get("color", "#FFFFFF"))
        black = ass_color(t.get("outline_color", "#000000"))
        shadow = ass_color(t.get("shadow_color", "#000000"), 0x78)
        acc = ass_color(accent)
        slant = float(t.get("slant", 0))  # >0 leans forward like italic; uses ASS \fax shear
        self.pre = f"\\fax{-slant:.3f}" if slant else ""
        st = self._style
        self.styles = [
            st("lyric", font, b * 0.066, white, "&H000000FF", black, shadow, bold, 2, self.mv, bord, shad, sp),
            st("title", font, self.base * 0.10, white, "&H000000FF", black, shadow, bold, 5, 0, bord, shad, sp),
            st("credit", font, self.base * 0.035, "&H00FFFFFF", "&H000000FF", "&H00000000", shadow, 0, 1, int(H * 0.05), 1, 1, 0),
            st("karaoke", font, b * 0.066, acc, white, black, shadow, bold, 5, 0, bord, shad, sp),
            st("neon", font, b * 0.07, white, white, acc, "&H00000000", bold, 5, 0, max(2, H // 300), 0, sp),
            st("big", display_font, b * 0.13, white, white, black, ass_color(t.get("shadow_color", "#000000"), 0x96),
               0, 5, 0, bord, shad * 2, sp),
            st("scroll", font, b * (0.056 if self.vertical else 0.05), white, white, "&H64000000",
               "&H00000000", bold, 7, 0, 1, 0, sp),
            st("scrollk", font, b * (0.056 if self.vertical else 0.05), acc, white, "&H64000000",
               "&H00000000", bold, 7, 0, 1, 0, sp),
            st("ptitle", title_font or font, self.base * 0.058, white, white, "&H64000000", shadow, bold, 8, 0, 1, shad, sp),
            st("partist", artist_font or font, self.base * 0.04, "&H40FFFFFF", white, "&H64000000", shadow, 0, 8, 0, 1, 0, 0),
            st("grunge", display_font, b * 0.105, white, white, "&H00101010", ass_color("#000000", 0x60), 0, 5, 0,
               max(2, round(bord * 1.4)), shad, sp),
            # BorderStyle 3 = opaque box behind each row: the outline colour is the paper strip
            st("paper", font, b * 0.068, ass_color(t.get("paper_text", "#1A1A1A")), white,
               ass_color(t.get("paper", "#F4EDE0")), ass_color("#000000", 0x90), bold, 5, 0,
               max(4, round(H / 130)), max(2, round(H / 400)), sp, border_style=3),
            st("marker", font, b * 0.066, white, white, acc, ass_color("#000000", 0x80), bold, 5, 0,
               max(5, round(H / 110)), 0, sp),
            st("stag", font, b * 0.064, white, white, black, shadow, bold, 5, 0, bord, shad, sp),
            st("stagbig", display_font, b * 0.15, acc, acc, black, shadow, 0, 5, 0, bord, shad * 2, sp),
            st("tc_artist", font, self.base * 0.034, white, white, black, shadow, bold, 1, 0, max(1, bord // 2), shad,
               round(self.base * 0.006, 1)),
            st("tc_title", display_font, self.base * 0.07, white, white, black, shadow, 0, 1, 0, bord, shad, sp),
        ]

    @staticmethod
    def _style(name, font, size, prim, sec, outl, back, bold, align, marg_v, bord, shad, spacing=0,
               border_style=1) -> str:
        return (f"Style: {name},{font},{int(size)},{prim},{sec},{outl},{back},{bold},0,0,0,100,100,{spacing},0,"
                f"{border_style},{bord},{shad},{align},0,0,{marg_v},1")

    def _ts(self, x: float) -> str:
        x = max(0.0, x - self.s0)
        hh, r = divmod(x, 3600)
        mm, ss = divmod(r, 60)
        return f"{int(hh)}:{int(mm):02d}:{ss:05.2f}"

    def add(self, start, end, style, text, layer=0, ml=0, mr=0):
        if end <= self.s0 or start >= self.t_end or end <= start:
            return
        if self.pre and style in TYPO_STYLES:  # poster-style slant on every lyric/title event
            text = "{" + self.pre + text[1:] if text.startswith("{") else "{" + self.pre + "}" + text
        self.events.append(f"Dialogue: {layer},{self._ts(start)},{self._ts(end)},{style},,{ml},{mr},0,,{text}")

    def write(self, path: Path) -> None:
        head = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {self.W}", f"PlayResY: {self.H}",
                "WrapStyle: 0", "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
                "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
                "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding", *self.styles, "", "[Events]",
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
        path.write_text("\n".join(head + self.events) + "\n", encoding="utf-8-sig")

    # ------------------------------------------------------------------ simple captions (shot captions)
    def caption(self, start, end, style, anim, text):
        W, H = self.W, self.H
        tag = ""
        if anim == "pop":
            tag = "{\\fad(80,160)\\fscx72\\fscy72\\t(0,180,\\fscx100\\fscy100)}"
        elif anim == "rise":
            x = W // 2
            y = H // 2 if style == "title" else H - self.mv
            an = "\\an5" if style == "title" else "\\an2"
            tag = f"{{{an}\\move({x},{y + H // 40},{x},{y},0,320)\\fad(200,200)}}"
        elif anim != "none":
            tag = "{\\fad(180,180)}"
        m = int(W * 0.08)
        self.add(start, end, style, tag + _esc(text), ml=m, mr=m)

    # ------------------------------------------------------------------ lyric lines
    def default_area(self, style: str) -> tuple[int, int, int, int]:
        W, H = self.W, self.H
        if style in ("stack", "grunge", "paper", "stagger", "marker"):
            return (self.sx0, int(H * self.top), self.sx1, min(int(H * 0.70), H - self.mv))
        if style == "scroll":
            return (self.sx0, int(H * 0.52), self.sx1, H - self.mv) if self.vertical else \
                   (self.sx0, int(H * 0.60), self.sx1, min(int(H * 0.94), H - self.mv))
        return (self.sx0, H - self.mv - int(H * 0.12), self.sx1, H - self.mv)

    def lyrics(self, lines: list[dict], style_for, area=None, align=None, highlight="line",
               anim="fade", lead=0.15):
        if not lines:
            return
        lines = sorted(lines, key=lambda l: float(l["start"]))
        if self.typo.get("upper"):
            lines = [dict(l, text=str(l["text"]).upper(),
                          words=[[str(w[0]).upper(), w[1], w[2]] for w in l.get("words") or []] or None) for l in lines]
        for i, ln in enumerate(lines):  # display window: hold until the next line when the gap is short
            s, e = float(ln["start"]), float(ln["end"])
            nxt = float(lines[i + 1]["start"]) if i + 1 < len(lines) else None
            if nxt is not None and nxt - e < 1.5:
                ln["_end"] = nxt - lead - 0.02
            else:
                ln["_end"] = max(e + 0.6, s + 1.2) if nxt is None else min(max(e + 0.6, s + 1.2), nxt - lead - 0.02)
            ln["_start"] = s - lead
        scroll_idx = []
        for i, ln in enumerate(lines):
            st = style_for(float(ln["start"]))
            ar = area or self.default_area(st)
            if st == "scroll":
                scroll_idx.append(i)
            elif st == "karaoke":
                self._karaoke(ln, ar)
            elif st == "word":
                self._reveal(ln, ar, per_char=False)
            elif st == "typewriter":
                self._reveal(ln, ar, per_char=True)
            elif st == "stack":
                self._stack(ln, ar)
            elif st == "neon":
                self._neon(ln, ar)
            elif st == "grunge":
                self._grunge(ln, ar, i)
            elif st == "paper":
                self._paper(ln, ar, i)
            elif st == "marker":
                self._marker(ln, ar)
            elif st == "stagger":
                self._stagger(ln, ar, i)
            else:
                self._subtitle(ln, ar, anim)
        if scroll_idx:
            ar = area or self.default_area("scroll")
            al = align or ("center" if self.vertical else "left")
            self._scroll(lines, scroll_idx, ar, al, highlight)

    def _pos(self, ar, an=5):
        x0, y0, x1, y1 = ar
        return f"\\an{an}\\pos({(x0 + x1) // 2},{(y0 + y1) // 2})", x0, self.W - x1

    def _subtitle(self, ln, ar, anim):
        pos, ml, mr = self._pos(ar)
        a = {"pop": "\\fad(80,160)\\fscx72\\fscy72\\t(0,180,\\fscx100\\fscy100)", "none": ""}.get(anim, "\\fad(180,180)")
        if anim == "rise":
            x0, y0, x1, y1 = ar
            cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
            pos, a = f"\\an5\\move({cx},{cy + self.H // 40},{cx},{cy},0,320)", "\\fad(200,200)"
        text = _esc(ln["text"])
        if ln.get("sub"):
            text += f"\\N{{\\fs{int(self.base * 0.042)}\\b0\\alpha&H30&}}{_esc(ln['sub'])}"
        self.add(ln["_start"], ln["_end"], "lyric", f"{{{pos}{a}}}{text}", ml=ml, mr=mr)

    def _karaoke(self, ln, ar):
        pos, ml, mr = self._pos(ar)
        wt = word_times(ln)
        lead = max(0.0, wt[0][1] - ln["_start"])
        parts = [f"{{{pos}\\fad(120,180)\\k{int(lead * 100)}}}"]
        for i, (w, s, e) in enumerate(wt):
            nxt = wt[i + 1][1] if i + 1 < len(wt) else e
            parts.append(f"{{\\kf{max(1, int((max(e, nxt) - s) * 100))}}}{_esc(w)} ")
        self.add(ln["_start"], ln["_end"], "karaoke", "".join(parts).rstrip(), ml=ml, mr=mr)

    def _reveal(self, ln, ar, per_char):
        pos, ml, mr = self._pos(ar)
        t0 = ln["_start"]
        parts = [f"{{{pos}\\fad(0,180)}}"]
        for w, s, e in word_times(ln):
            if per_char:
                step = min(0.07, max(0.02, (e - s) / max(1, len(w))))
                for k, ch in enumerate(w):
                    ms = int((s - t0 + k * step) * 1000)
                    parts.append(f"{{\\alpha&HFF&\\t({ms},{ms + 40},\\alpha&H00&)}}{_esc(ch)}")
                parts.append(" ")
            else:
                ms = int((s - t0) * 1000)
                parts.append(f"{{\\alpha&HFF&\\t({ms},{ms + 180},\\alpha&H00&)}}{_esc(w)} ")
        self.add(t0, ln["_end"], "lyric", "".join(parts).rstrip(), ml=ml, mr=mr)

    def _neon(self, ln, ar):
        pos, ml, mr = self._pos(ar)
        acc = ass_color(self.accent)
        flick = "\\alpha&HFF&\\t(0,60,\\alpha&H00&)\\t(60,110,\\alpha&HA0&)\\t(110,170,\\alpha&H00&)"
        txt = _esc(ln["text"])
        glow = f"{{{pos}{flick}\\fad(0,200)\\bord{max(4, self.H // 160)}\\blur{max(6, self.H // 110)}\\3c{acc}\\1a&HFF&}}"
        core = f"{{{pos}{flick}\\fad(0,200)\\blur1\\3c{acc}}}"
        self.add(ln["_start"], ln["_end"], "neon", glow + txt, layer=0, ml=ml, mr=mr)
        self.add(ln["_start"], ln["_end"], "neon", core + txt, layer=1, ml=ml, mr=mr)

    def _stack(self, ln, ar):
        x0, y0, x1, y1 = ar
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        big = self.lb * 0.13
        wt = [(w.upper(), s, e) for w, s, e in word_times(ln)]
        rows = wrap_words([w for w, _, _ in wt], max(4, int((x1 - x0) / (big * 0.48))))
        sizes = []
        for r in rows:
            n = len(" ".join(wt[i][0] for i in r))
            sizes.append(big * (1.18 if n <= 6 else (0.78 if n > 11 else 1.0)))
        total = sum(s * 1.02 for s in sizes)
        y = cy - total / 2
        longest = max(range(len(rows)), key=lambda k: max(len(wt[i][0]) for i in rows[k]))
        acc = ass_color(self.accent)
        for k, r in enumerate(rows):
            yy = int(y + sizes[k] * 0.51)
            y += sizes[k] * 1.02
            color = f"\\c{acc}" if k == longest and len(rows) > 1 else ""
            tag = (f"{{\\an5\\pos({cx},{yy})\\fs{int(sizes[k])}{color}\\fscx130\\fscy130"
                   f"\\t(0,140,\\fscx100\\fscy100)\\fad(60,160)}}")
            self.add(wt[r[0]][1] - 0.05, ln["_end"], "big", tag + _esc(" ".join(wt[i][0] for i in r)))

    def _rows(self, ln, ar, size, upper=False):
        """Word timing + greedy rows sized for the area (display fonts run ~0.5 em per character)."""
        x0, _, x1, _ = ar
        wt = [((w.upper() if upper else w), s, e) for w, s, e in word_times(ln)]
        rows = wrap_words([w for w, _, _ in wt], max(4, int((x1 - x0) / (size * 0.5))))
        return wt, rows

    def _grunge(self, ln, ar, n):
        """Distressed punk/rock lettering: rows tilt and jolt in, words slam in as sung, accent misprint ghost."""
        x0, y0, x1, y1 = ar
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        size = self.lb * 0.105
        wt, rows = self._rows(ln, ar, size, upper=True)
        lh = size * 1.05
        y = cy - lh * len(rows) / 2 + lh / 2
        acc = ass_color(self.accent)
        off = max(2, int(self.base / 160))
        for k, r in enumerate(rows):
            rot = ((n * 3 + k * 5) % 7 - 3) * 1.1  # deterministic tilt, -3.3..3.3 degrees
            yy = int(y + k * lh)
            t0 = max(ln["_start"], wt[r[0]][1] - 0.05)
            words = []
            for i in r:
                ms = max(0, int((wt[i][1] - t0) * 1000))
                words.append(f"{{\\alpha&HFF&\\t({ms},{ms + 40},\\alpha&H00&)}}{_esc(wt[i][0])}")
            body = " ".join(words)
            anim = "\\fscx112\\fscy112\\t(0,90,\\fscx100\\fscy100)\\fad(0,140)"
            main = f"{{\\an5\\frz{rot:.1f}\\move({cx + off * 3},{yy - off * 2},{cx},{yy},0,90){anim}\\blur0.6}}"
            ghost = (f"{{\\an5\\frz{rot:.1f}\\pos({cx + off},{yy + off}){anim}\\1c{acc}\\1a&H60&\\bord0\\shad0"
                     f"\\blur1.5}}")
            self.add(t0, ln["_end"], "grunge", ghost + body, layer=0)
            self.add(t0, ln["_end"], "grunge", main + body, layer=1)

    def _paper(self, ln, ar, n):
        """Cut-out paper strips: each row on its own tilted strip, popping in; the longest row on an accent strip."""
        x0, y0, x1, y1 = ar
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        size = self.lb * 0.068
        wt, rows = self._rows(ln, ar, size * 1.15)
        lh = size * 1.75
        y = cy - lh * len(rows) / 2 + lh / 2
        longest = max(range(len(rows)), key=lambda k: len(" ".join(wt[i][0] for i in rows[k])))
        for k, r in enumerate(rows):
            rot = 2.4 if (n + k) % 2 else -2.0
            dx = int(self.base * 0.03) * (1 if (n + k) % 2 else -1)
            yy = int(y + k * lh)
            t0 = max(ln["_start"], wt[r[0]][1] - 0.12)
            col = f"\\3c{ass_color(self.accent)}" if k == longest and len(rows) > 1 else ""
            tag = (f"{{\\an5\\pos({cx + dx},{yy})\\frz{rot}{col}\\fscx60\\fscy60"
                   f"\\t(0,160,\\fscx106\\fscy106)\\t(160,240,\\fscx100\\fscy100)\\fad(40,160)}}")
            self.add(t0, ln["_end"], "paper", tag + _esc(" ".join(wt[i][0] for i in r)), layer=k)

    def _marker(self, ln, ar):
        """Highlighter pen: each word gets a thick accent marker stroke (and dark ink) the moment it is sung."""
        pos, ml, mr = self._pos(ar)
        t0 = ln["_start"]
        ink = ass_color(self.typo.get("marker_ink", "#141414"))
        plain = ass_color(self.typo.get("color", "#FFFFFF"))  # reset per word: an earlier \t would carry over
        parts = [f"{{{pos}\\fad(120,180)}}"]
        for w, s, e in word_times(ln):
            ms = max(0, int((s - t0) * 1000))
            parts.append(f"{{\\1c{plain}\\3a&HFF&\\t({ms},{ms + 110},\\3a&H00&\\1c{ink})}}{_esc(w)} ")
        self.add(t0, ln["_end"], "marker", "".join(parts).rstrip(), ml=ml, mr=mr)

    def _stagger(self, ln, ar, n):
        """Kinetic layout: the key word huge in the display font, the rest small around it; lines alternate
        left / right / centre and slide in. Key word = `emph:` on the lyric line, else the longest word."""
        x0, y0, x1, y1 = ar
        wt = word_times(ln)
        words = [w for w, _, _ in wt]
        emph = str(ln.get("emph") or "").strip().lower()
        k = next((i for i, w in enumerate(words) if w.lower().strip(",.!?") == emph), None) if emph else None
        if k is None:
            k = max(range(len(words)), key=lambda i: len(words[i].strip(",.!?")))
        side = n % 3  # 0 left, 1 right, 2 centre
        an, x = {0: (4, x0), 1: (6, x1), 2: (5, (x0 + x1) // 2)}[side]
        slide = int(self.W * 0.06) * (-1 if side == 0 else (1 if side == 1 else 0))
        big = self.lb * 0.15
        bigsize = big * min(1.0, (x1 - x0) / max(1.0, len(words[k]) * big * 0.5))
        small = self.lb * 0.064
        before, after = " ".join(words[:k]), " ".join(words[k + 1:])
        cy = (y0 + y1) // 2 + int((y1 - y0) * (-0.12 if n % 2 else 0.1))
        rows = []
        if before:
            rows.append(("stag", before, small, wt[0][1]))
        rows.append(("stagbig", words[k].upper(), bigsize, wt[k][1]))
        if after:
            rows.append(("stag", after, small, wt[k + 1][1]))
        total = sum(sz * 1.05 for _, _, sz, _ in rows)
        y = cy - total / 2
        for style, text, sz, t in rows:
            yy = int(y + sz * 0.52)
            y += sz * 1.05
            t0 = max(ln["_start"], t - 0.08)
            pop = "\\fscx125\\fscy125\\t(0,150,\\fscx100\\fscy100)" if style == "stagbig" else ""
            tag = f"{{\\an{an}\\move({x + slide},{yy},{x},{yy},0,220){pop}\\fs{int(sz)}\\fad(90,160)}}"
            self.add(t0, ln["_end"], style, tag + _esc(text))

    # ------------------------------------------------------------------ title / end cards (official-MV style)
    def title_card(self, card: dict, start: float, end: float, kind: str = "title"):
        """Artist + song title as in official music videos. style: official (lower-left, letter-spaced artist,
        "Title" in the display font) | center (centred, cinematic) | minimal (small, top-left)."""
        W, H = self.W, self.H
        style = card.get("style", "center" if kind == "end" else "official")
        artist, title, sub = str(card.get("artist", "")), str(card.get("title", "")), str(card.get("sub", ""))
        if kind == "end":
            title, artist, sub = str(card.get("text", title)), str(card.get("sub", "")), ""
        fade = "\\fad(500,600)"
        if style == "center":
            cx, cy = W // 2, H // 2
            if artist:
                grow = f"\\t(0,{int((end - start) * 1000)},\\fsp{round(self.base * 0.012, 1)})"
                self.add(start, end, "tc_artist",
                         f"{{\\an2\\pos({cx},{cy - int(self.base * 0.05)}){fade}{grow}}}{_esc(artist.upper())}")
            self.add(start, end, "tc_title", f"{{\\an8\\pos({cx},{cy - int(self.base * 0.03)}){fade}\\fs{int(self.base * 0.11)}}}{_esc(title)}")
            return
        if style == "minimal":
            x, y = int(W * 0.06), int(H * 0.06)
            text = _esc(artist.upper()) + (f"\\N{{\\b0}}{_esc(title)}" if title else "")
            self.add(start, end, "tc_artist", f"{{\\an7\\pos({x},{y}){fade}}}{text}")
            return
        x = int(W * 0.07)
        # above the lyric zone (which moves up when a platform's safe zone is larger)
        yb = int(min(H * (0.60 if self.vertical else 0.76), H - self.mv - H * 0.20))
        rise = int(H * 0.012)
        q = f"\u201c{title}\u201d" if title and kind == "title" else title
        self.add(start, end, "tc_title", f"{{\\an1\\move({x},{yb + rise},{x},{yb},0,600){fade}}}{_esc(q)}")
        if artist:
            ya = yb - int(self.base * 0.085)
            self.add(start, end, "tc_artist",
                     f"{{\\an1\\move({x},{ya + rise},{x},{ya},0,600){fade}}}{_esc(artist.upper())}")
        if sub:
            self.add(start, end, "credit", f"{{\\an7\\pos({x},{yb + int(self.base * 0.012)}){fade}}}{_esc(sub)}")

    def _scroll(self, lines, idx, ar, align, highlight):
        x0, y0, x1, y1 = ar
        fs = self.lb * (0.056 if self.vertical else 0.05)
        lh, gap = fs * 1.3, fs * 0.6
        maxc = max(8, int((x1 - x0) / (fs * 0.52)))
        wts = [word_times(l) for l in lines]
        rows = [wrap_words([w for w, _, _ in wt], maxc) for wt in wts]
        hts = [len(r) * lh + gap for r in rows]
        anchor = y0 + (y1 - y0) * 0.26  # current line sits high; previous line scrolls out above, next lines below
        x, an = (x0, 7) if align == "left" else ((x0 + x1) // 2, 8)
        clip = f"\\clip({x0},{y0},{x1},{y1})"

        def body(i, karaoke, t_start):
            wt, out = wts[i], []
            if karaoke:
                lead = max(0.0, wt[0][1] - t_start)
                out.append(f"{{\\k{int(lead * 100)}}}")
            for r_i, row in enumerate(rows[i]):
                for j, wi in enumerate(row):
                    w, s, e = wt[wi]
                    if karaoke:
                        nxt = wt[wi + 1][1] if wi + 1 < len(wt) else e
                        out.append(f"{{\\kf{max(1, int((max(e, nxt) - s) * 100))}}}")
                    out.append(_esc(w) + (" " if j < len(row) - 1 else ""))
                if r_i < len(rows[i]) - 1:
                    out.append("\\N")
            return "".join(out)

        for k in idx:
            st = float(lines[k]["start"]) - 0.25
            en = float(lines[k + 1]["start"]) - 0.25 if k + 1 < len(lines) else lines[k]["_end"] + 1.2
            ys, y = {k: anchor}, anchor
            for i in range(k + 1, len(lines)):
                y += hts[i - 1]
                if y > y1:
                    break
                ys[i] = y
            y = anchor
            for i in range(k - 1, -1, -1):
                y -= hts[i]
                ys[i] = y
                if y + hts[i] < y0:
                    break
            shift = int(hts[k - 1]) if k > 0 else 0
            for i, yy in ys.items():
                cur, prev = i == k, i == k - 1
                if cur:
                    al = "\\alpha&H70&\\t(0,280,\\alpha&H00&)" if k > 0 else "\\fad(250,0)"
                elif prev:
                    al = "\\alpha&H00&\\t(0,280,\\alpha&H80&)"
                else:
                    al = "\\alpha&H80&" if abs(i - k) == 1 else "\\alpha&HB4&"
                    if k == 0:
                        al += "\\fad(250,0)"
                move = f"\\move({x},{int(yy) + shift},{x},{int(yy)},0,280)" if k > 0 else f"\\pos({x},{int(yy)})"
                kar = cur and highlight == "karaoke"
                style = "scrollk" if kar else "scroll"
                tag = f"{{\\an{an}\\q2{clip}{move}{al}{'' if cur else chr(92) + 'b0'}}}"
                self.add(st, en, style, tag + body(i, kar, st))


# ---------------------------------------------------------------------- lyrics.txt + alignment
def _norm(w: str) -> str:
    w = unicodedata.normalize("NFD", w.lower()).replace("đ", "d")
    w = "".join(c for c in w if unicodedata.category(c) != "Mn").replace("đ", "d")
    return re.sub(r"[^\w]", "", w)


def parse_lyrics_txt(text: str) -> list[dict]:
    """One lyric line per text line. `[Chorus]`-style headers set the section; `a | b` adds a sub-line (translation)."""
    out, section = [], ""
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("[") and s.endswith("]"):
            section = s[1:-1]
            continue
        main, _, sub = s.partition("|")
        d = {"text": main.strip(), "section": section}
        if sub.strip():
            d["sub"] = sub.strip()
        out.append(d)
    return out


def align_lines(lines: list[dict], segments: list[dict]) -> tuple[list[dict], float]:
    """Map the user's lyric words onto Whisper word timings (order-preserving diff). Returns (lines, match ratio)."""
    uw = [(li, w) for li, ln in enumerate(lines) for w in ln["text"].split()]
    ww = []
    for seg in segments:
        words = seg.get("words") or []
        if words:
            ww += [(_norm(w["w"]), float(w["s"]), float(w["e"])) for w in words if _norm(w["w"])]
        else:
            toks = seg["text"].split()
            d = (seg["end"] - seg["start"]) / max(1, len(toks))
            ww += [(_norm(t), seg["start"] + k * d, seg["start"] + (k + 1) * d) for k, t in enumerate(toks)]
    times: list = [None] * len(uw)
    matched = 0
    sm = difflib.SequenceMatcher(None, [_norm(w) for _, w in uw], [w[0] for w in ww], autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                times[i1 + k] = ww[j1 + k][1:]
            matched += i2 - i1
        elif op == "replace":
            s, e = ww[j1][1], ww[j2 - 1][2]
            n = i2 - i1
            for k in range(n):  # spread the misheard span across the user's words
                times[i1 + k] = (s + (e - s) * k / n, s + (e - s) * (k + 1) / n)
    known = [k for k, t in enumerate(times) if t]
    if not known:
        raise ValueError("no lyric words matched the transcription")
    for k in range(len(times)):  # interpolate words Whisper missed entirely
        if times[k]:
            continue
        prev = max((j for j in known if j < k), default=None)
        nxt = min((j for j in known if j > k), default=None)
        if prev is None:
            t = times[nxt][0] - 0.35 * (nxt - k)
            times[k] = (t, t + 0.3)
        elif nxt is None:
            t = times[prev][1] + 0.35 * (k - prev - 1)
            times[k] = (t, t + 0.3)
        else:
            a, b = times[prev][1], times[nxt][0]
            span = (b - a) / (nxt - prev)
            times[k] = (a + span * (k - prev - 1), a + span * (k - prev))
    out = [dict(ln, words=[]) for ln in lines]
    for (li, w), (s, e) in zip(uw, times):
        out[li]["words"].append([w, round(s, 2), round(e, 2)])
    for ln in out:
        ln["start"], ln["end"] = ln["words"][0][1], ln["words"][-1][2]
    return out, matched / max(1, len(uw))
