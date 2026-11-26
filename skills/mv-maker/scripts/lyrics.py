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
LYRIC_STYLES = {"subtitle", "karaoke", "word", "typewriter", "stack", "neon", "scroll"}


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


class AssWriter:
    def __init__(self, W: int, H: int, font: str, display_font: str, accent: str, s0: float, t_end: float):
        self.W, self.H, self.s0, self.t_end = W, H, s0, t_end
        self.base = min(W, H)
        self.vertical = H > W
        self.font, self.display, self.accent = font, display_font, accent
        self.mv = int(H * (0.22 if self.vertical else 0.08))  # 9:16 keeps text above TikTok/Reels UI
        self.events: list[str] = []
        bord, shad = max(1, H // 400), max(1, H // 640)
        b = self.base
        white, black, shadow = "&H00FFFFFF", "&H00000000", "&H78000000"
        acc = ass_color(accent)
        self.styles = [
            self._style("lyric", font, b * 0.066, white, "&H000000FF", black, shadow, -1, 2, self.mv, bord, shad),
            self._style("title", font, b * 0.10, white, "&H000000FF", black, shadow, -1, 5, 0, bord, shad),
            self._style("credit", font, b * 0.035, white, "&H000000FF", black, shadow, 0, 1, int(H * 0.05), bord, shad),
            self._style("karaoke", font, b * 0.066, acc, white, black, shadow, -1, 5, 0, bord, shad),
            self._style("neon", font, b * 0.07, white, white, acc, "&H00000000", -1, 5, 0, max(2, H // 300), 0),
            self._style("big", display_font, b * 0.13, white, white, black, "&H96000000", 0, 5, 0, bord, shad * 2),
            self._style("scroll", font, b * (0.056 if self.vertical else 0.05), white, white, "&H64000000",
                        "&H00000000", -1, 7, 0, 1, 0),
            self._style("scrollk", font, b * (0.056 if self.vertical else 0.05), acc, white, "&H64000000",
                        "&H00000000", -1, 7, 0, 1, 0),
            self._style("ptitle", font, b * 0.058, white, white, "&H64000000", shadow, -1, 8, 0, 1, shad),
            self._style("partist", font, b * 0.04, "&H40FFFFFF", white, "&H64000000", shadow, 0, 8, 0, 1, 0),
        ]

    @staticmethod
    def _style(name, font, size, prim, sec, outl, back, bold, align, marg_v, bord, shad) -> str:
        return (f"Style: {name},{font},{int(size)},{prim},{sec},{outl},{back},{bold},0,0,0,100,100,0,0,1,"
                f"{bord},{shad},{align},0,0,{marg_v},1")

    def _ts(self, x: float) -> str:
        x = max(0.0, x - self.s0)
        hh, r = divmod(x, 3600)
        mm, ss = divmod(r, 60)
        return f"{int(hh)}:{int(mm):02d}:{ss:05.2f}"

    def add(self, start, end, style, text, layer=0, ml=0, mr=0):
        if end <= self.s0 or start >= self.t_end or end <= start:
            return
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
        if style == "stack":
            return (int(W * 0.08), int(H * 0.26), int(W * 0.92), int(H * 0.70))
        if style == "scroll":
            return (int(W * 0.08), int(H * 0.52), int(W * 0.92), H - self.mv) if self.vertical else \
                   (int(W * 0.08), int(H * 0.60), int(W * 0.92), int(H * 0.94))
        return (int(W * 0.08), H - self.mv - int(H * 0.12), int(W * 0.92), H - self.mv)

    def lyrics(self, lines: list[dict], style_for, area=None, align=None, highlight="line",
               anim="fade", lead=0.15):
        if not lines:
            return
        lines = sorted(lines, key=lambda l: float(l["start"]))
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
        big = self.base * 0.13
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

    def _scroll(self, lines, idx, ar, align, highlight):
        x0, y0, x1, y1 = ar
        fs = self.base * (0.056 if self.vertical else 0.05)
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
