"""Generated backgrounds for lyric videos - no footage needed.

A source with `gen: "<kind>:<colours>"` renders procedurally with FFmpeg:
  solid:#c            flat colour
  gradient:#a,#b[,#c] slowly drifting gradient
  blocks:#a,#b,#c     bold colour blocks that swap layout every 2 s (minimal / pop templates)
  smoke:#base,#tint   drifting fog / smoke clouds (cinematic, dark, ballad)
  particles:#base,#dot  floating dust + bokeh rising slowly (dreamy, night, glow)
  paper:#c            paper texture with gentle drift (cozy, handwritten, paper cut-out)
  grunge:#base,#tint  dark scratchy texture with flicker (punk, rock, rap)
  crt:#base,#tint     scanlines + rolling bar + glow (retro, synthwave)
Colours may be `$1` `$2` `$3` (the palette) or `$a` (accent). Textures are cached PNGs in build/<mode>/gen.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

KINDS = {"solid", "gradient", "blocks", "smoke", "particles", "paper", "grunge", "crt"}
DEFAULTS = {
    "solid": ["#111118"], "gradient": ["#1a1a2e", "#3a1c71", "#d76d77"], "blocks": ["#F2C14E", "#1D3557", "#E63946"],
    "smoke": ["#0d0d12", "#8a96c8"], "particles": ["#0b0b1a", "#ffd9a0"], "paper": ["#efe6d2"],
    "grunge": ["#121212", "#b8b0a0"], "crt": ["#050a08", "#40ff9a"],
}
# deterministic per-pixel hash noise for geq (static pattern, unlike random())
HASH = "st(0,sin(X*12.9898+Y*78.233)*43758.5453);ld(0)-floor(ld(0))"


def parse(spec: str, palette: list[str] | None = None, accent: str | None = None) -> tuple[str, list[str]]:
    kind, _, rest = str(spec).partition(":")
    kind = kind.strip()
    if kind not in KINDS:
        raise ValueError(f"unknown gen kind '{kind}' - one of {sorted(KINDS)}")
    pal = list(palette or [])
    cols = []
    for c in [c.strip() for c in rest.split(",") if c.strip()]:
        if c.startswith("$"):
            key = c[1:]
            if key == "a":
                c = accent or "#FFD24D"
            elif key.isdigit() and 0 < int(key) <= len(pal):
                c = pal[int(key) - 1]
            else:
                raise ValueError(f"gen colour '{c}': palette has {len(pal)} colours")
        cols.append(c)
    d = DEFAULTS[kind]
    cols += d[len(cols):]
    return kind, cols


def _hex(c: str) -> str:
    return "0x" + c.lstrip("#")


def _rgb(c: str) -> tuple[float, float, float]:
    h = c.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _texture(cache: Path, name: str, w: int, h: int, vf: str) -> Path:
    """Render one grayscale texture PNG (cached by name + size)."""
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / f"{name}_{w}x{h}.png"
    if not out.exists():
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                            f"nullsrc=s={w}x{h}:d=1:r=1", "-vf", vf, "-frames:v", "1", str(out)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"texture {name} failed: {r.stderr[-400:]}")
    return out


def _tile(lab: str) -> str:
    """Mirror-tile a WxH texture to 2Wx2H so `scroll` wraps without visible seams."""
    return (f"split=2[{lab}_ta][{lab}_tb];[{lab}_tb]hflip[{lab}_tc];[{lab}_ta][{lab}_tc]hstack[{lab}_tr];"
            f"[{lab}_tr]split=2[{lab}_td][{lab}_te];[{lab}_te]vflip[{lab}_tf];[{lab}_td][{lab}_tf]vstack")


def build(spec: str, w: int, h: int, fps: int, need: float, cache: Path, lab: str,
          palette: list[str] | None = None, accent: str | None = None) -> tuple[list[str], list[str]]:
    """-> (ffmpeg input args, filter_complex statements). The last statement ends in [lab] (gbrp, w x h)."""
    kind, c = parse(spec, palette, accent)
    t = f"{need:.3f}"
    base = ["-f", "lavfi", "-t", t, "-i", f"color=c={_hex(c[0])}:s={w}x{h}:r={fps}"]

    def tex_input(name, tw, th, vf):
        png = _texture(cache, name, tw, th, vf)
        return ["-loop", "1", "-framerate", str(fps), "-t", t, "-i", str(png)]

    if kind == "solid":
        return base, [f"[IN0]format=gbrp[{lab}]"]
    if kind == "gradient":
        cols = "".join(f":c{i}={_hex(x)}" for i, x in enumerate(c[:8]))
        return (["-f", "lavfi", "-t", t, "-i", f"gradients=s={w}x{h}{cols}:nb_colors={len(c)}:x0={w // 4}:y0=0:"
                                                f"x1={w * 3 // 4}:y1={h}:speed=0.004:rate={fps}"],
                [f"[IN0]format=gbrp[{lab}]"])
    if kind == "blocks":
        a, b, d = c[0], c[1], c[2]
        sw = f"lt(mod(t,4),2)"
        return base, [f"[IN0]drawbox=x='if({sw},0,iw*0.45)':y=0:w=iw*0.55:h='if({sw},ih*0.62,ih*0.5)':"
                      f"color={_hex(b)}:t=fill,"
                      f"drawbox=x=0:y='if({sw},ih*0.62,ih*0.5)':w=iw:h=ih:color={_hex(d)}:t=fill,"
                      f"drawbox=x='if({sw},iw*0.08,iw*0.06)':y='if({sw},ih*0.06,ih*0.56)':w=iw*0.12:h=iw*0.12:"
                      f"color={_hex(a)}:t=fill,format=gbrp[{lab}]"]
    tw, th = max(2, w // 2) // 2 * 2, max(2, h // 2) // 2 * 2
    if kind == "smoke":
        r, g, bb = _rgb(c[1])
        sw_, sh_ = max(4, w // 40) // 2 * 2, max(4, h // 40) // 2 * 2  # low-res noise -> soft clouds
        args = base + tex_input("smoke", sw_, sh_, f"format=gray,geq=lum='255*({HASH})',scale={w}:{h}:flags=bicubic,"
                                f"gblur=sigma={max(8, w // 14)},normalize")
        return args, [f"[IN1]format=gray,{_tile(lab)},split[{lab}_s1][{lab}_s2]",
                      f"[{lab}_s1]scroll=h=0.0006:v=0.00015,crop={w}:{h}:0:0[{lab}_sa]",
                      f"[{lab}_s2]scroll=h=-0.0004:v=0.00025,crop={w}:{h}:{w // 2}:{h // 3}[{lab}_sb]",
                      f"[{lab}_sa][{lab}_sb]blend=all_mode=average,normalize,curves=all='0/0 0.45/0.12 1/0.85',format=gbrp,"
                      f"colorchannelmixer=rr={r:.3f}:gg={g:.3f}:bb={bb:.3f}[{lab}_sm]",
                      f"[IN0]format=gbrp[{lab}_bg]", f"[{lab}_bg][{lab}_sm]blend=all_mode=screen:all_opacity=0.85[{lab}]"]
    if kind == "particles":
        r, g, bb = _rgb(c[1])
        args = base + tex_input("dust", tw, th, f"format=gray,geq=lum='255*gt({HASH},0.9975)',scale={tw * 2}:{th * 2}:"
                                f"flags=bilinear,gblur=sigma=2,lutyuv=y='min(255,val*6)',scale={tw}:{th}")
        args += tex_input("bokeh", tw, th, f"format=gray,geq=lum='255*gt({HASH},0.985)',scale={tw}:{th}:flags=bilinear,"
                          f"gblur=sigma={max(4, tw // 50)},lutyuv=y='min(255,val*3)'")
        mix = f"colorchannelmixer=rr={r:.3f}:gg={g:.3f}:bb={bb:.3f}"
        return args, [f"[IN1]format=gray,scale={w}:{h},scroll=v=0.0016,format=gbrp,{mix}[{lab}_pd]",
                      f"[IN2]format=gray,scale={w}:{h},scroll=v=0.0006:h=0.0002,format=gbrp,{mix}[{lab}_pk]",
                      f"[IN0]vignette=PI/4,format=gbrp[{lab}_bg]",
                      f"[{lab}_bg][{lab}_pk]blend=all_mode=screen:all_opacity=0.7[{lab}_b1]",
                      f"[{lab}_b1][{lab}_pd]blend=all_mode=screen:all_opacity=0.9[{lab}]"]
    if kind == "paper":
        args = base + tex_input("fibre", tw, th, f"format=gray,geq=lum='128+60*({HASH})-30',gblur=sigma=0.7")
        return args, [f"[IN1]format=gray,scale={w}:{h},format=gbrp[{lab}_tx]",
                      f"[IN0]format=gbrp[{lab}_bg]",
                      f"[{lab}_bg][{lab}_tx]blend=all_mode=overlay:all_opacity=0.35,format=yuv444p,vignette=PI/5,"
                      f"crop=w=iw*0.96:h=ih*0.96:x='(iw-ow)/2+iw*0.006*sin(t*0.7)':y='(ih-oh)/2+ih*0.004*sin(t*0.5)',"
                      f"scale={w}:{h},format=gbrp[{lab}]"]
    if kind == "grunge":
        r, g, bb = _rgb(c[1])
        args = base + tex_input("scratch", tw, th, "format=gray,geq=lum='255*max(gt(st(0,sin(X*12.9898+floor(Y/97)*78.233)*43758.5453);"
                                "ld(0)-floor(ld(0)),0.993),gt(st(1,sin(X*4.1+Y*91.7)*13758.5);ld(1)-floor(ld(1)),0.997))',"
                                "gblur=sigma=0.6,lutyuv=y='min(255,val*2.5)'")
        args += tex_input("blotch", max(2, tw // 24) // 2 * 2, max(2, th // 24) // 2 * 2,
                          f"format=gray,geq=lum='255*({HASH})'")
        mix = f"colorchannelmixer=rr={r:.3f}:gg={g:.3f}:bb={bb:.3f}"
        return args, [f"[IN1]format=gray,{_tile(lab)},scale={w}:{h},scroll=v=0.01,format=gbrp,{mix}[{lab}_gs]",
                      f"[IN2]format=gray,scale={w}:{h}:flags=bicubic,gblur=sigma={max(10, w // 30)},normalize,format=gbrp,{mix}[{lab}_gb]",
                      f"[IN0]format=gbrp[{lab}_bg]",
                      f"[{lab}_bg][{lab}_gb]blend=all_mode=screen:all_opacity=0.35[{lab}_b1]",
                      f"[{lab}_b1][{lab}_gs]blend=all_mode=screen:all_opacity=0.5,"
                      f"format=yuv444p,eq=brightness='0.03*sin(t*31)*gt(sin(t*3.1),0.6)':eval=frame,vignette=PI/3.5,format=gbrp[{lab}]"]
    if kind == "crt":
        line = max(3, h // 220)
        args = ["-f", "lavfi", "-t", t, "-i", f"gradients=s={w}x{h}:c0={_hex(c[1])}:c1={_hex(c[0])}:nb_colors=2:"
                f"type=radial:x0={w // 2}:y0={h // 2}:x1={w // 2}:y1=0:speed=0:rate={fps}"]
        return args, [f"[IN0]format=yuv444p,eq=brightness=-0.2:saturation=1.2,"
                      f"drawgrid=w=iw:h={line}:t={max(1, line // 2)}:color=black@0.55,"
                      f"drawbox=x=0:y='mod(t*{h // 5},{h * 1.4:.0f})-{h // 5}':w=iw:h={h // 6}:color=white@0.06:t=fill,"
                      f"eq=brightness='0.015*sin(t*50)':eval=frame,vignette=PI/3,format=gbrp[{lab}]"]
    raise ValueError(kind)
