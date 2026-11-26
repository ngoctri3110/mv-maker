import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "mv-maker" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import footage  # noqa: E402
import lyrics  # noqa: E402
import mv  # noqa: E402


def project(root: Path, sb: dict) -> "mv.Project":
    (root / "storyboard.yaml").write_text(yaml.safe_dump(sb), encoding="utf-8")
    return mv.Project(root)


class ColorTests(unittest.TestCase):
    def test_match_filter_brightens_dark_and_removes_cast(self):
        f = footage.match_filter({"r": 0.2, "g": 0.2, "b": 0.35, "y": 0.2}, 0.45, 0.6)
        self.assertIn("eq=gamma=", f)
        gamma = float(f.split("eq=gamma=")[1].split(",")[0])
        self.assertGreater(gamma, 1.0)                                  # brighter
        bb = float(f.split("bb=")[1])
        self.assertLess(bb, 1.0)                                        # less blue
        self.assertIsNone(footage.match_filter({"r": 0.4, "g": 0.4, "b": 0.4, "y": 0.45}, 0.45))

    def test_lut_is_copied_next_to_the_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "look.cube").write_text("LUT_3D_SIZE 2\n", encoding="utf-8")
            filt, amt = footage.lut_filter("look.cube@0.7", root / "build" / "luts", root)
            self.assertTrue(filt.startswith("lut3d=file=luts/"))
            self.assertEqual(amt, 0.7)
            self.assertEqual(len(list((root / "build" / "luts").glob("*.cube"))), 1)
        graph = ";".join(mv.fx_filters([("__raw__", "lut3d=file=luts/x.cube", 0.5)], "L", 540, 960))
        self.assertIn("blend=all_mode=normal:all_opacity=0.5", graph)


class TrackTests(unittest.TestCase):
    def test_smooth_track_limits_pan_speed_and_fills_gaps(self):
        pts = [(0.0, 0.1, 0.5, 1), (0.25, 0.9, 0.5, 1), (2.0, 0.9, 0.5, 1)]
        tr = footage.smooth_track(pts, 2.0, 0.25, max_speed=0.35)
        xs = [x for _, x, _ in tr]
        self.assertEqual(len(tr), 9)
        self.assertTrue(all(abs(b - a) <= 0.35 * 0.25 + 1e-6 for a, b in zip(xs, xs[1:])))

    def test_track_expr_is_piecewise_in_output_time(self):
        e = footage.track_expr([(0.0, 0.2, 0.5), (2.0, 0.6, 0.5)], 0, speed=2.0)
        self.assertIn("lt(t,1.000)", e)                                  # 2 s of source at 2x = 1 s on screen
        self.assertTrue(e.endswith("0.6000)"))

    def test_upscale_factor(self):
        self.assertAlmostEqual(footage.upscale_factor((1920, 1080), (1080, 1920)), 1.78)
        self.assertAlmostEqual(footage.upscale_factor((1920, 1080), (1080, 1920), contain=True), 0.56)


class RenderGraphTests(unittest.TestCase):
    def render(self, sb, i=0, files=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        font = root / "f.ttf"
        font.write_bytes(b"x")
        sb = {"format": "9:16", "font_file": str(font), **sb}
        for name in files or []:
            (root / name).write_bytes(b"x")
        p = project(root, sb)
        p.beats = [0.5 * k for k in range(40)]
        with patch.object(mv, "run"), patch.object(footage, "stabilize_pass", return_value=True), \
                patch.object(footage, "file_key", side_effect=lambda f: str(f)):
            r = mv.Renderer(p, mode="proxy", encoder="libx264", jobs=1, force=True)
            r.render_shot(i)
        return (root / "build" / "proxy" / "shots" / f"{i:03d}_{p.shots[i]['id']}.filter").read_text(encoding="utf-8")

    def test_new_transitions_on_both_sides_of_the_cut(self):
        shots = [{"id": "A", "start": 0, "end": 2, "layers": [{"src": "x"}], "transition": "spin:0.4"},
                 {"id": "B", "start": 2, "end": 4, "layers": [{"src": "x"}], "transition": "burn"}]
        g0 = self.render({"sources": {"x": {}}, "shots": shots}, 0)
        self.assertIn("rotate=a=", g0)
        self.assertIn("zoompan", g0)
        g1 = self.render({"sources": {"x": {}}, "shots": shots}, 1)
        self.assertIn("rotate=a='-0.45", g1)                             # incoming half of the spin
        self.assertIn("all_expr='A+(255-A)*B/255*", g1)                  # outgoing film burn
        self.assertNotIn("(t-", g1.split("all_expr=")[1].split("'")[1])  # blend expressions use T
        self.assertEqual(mv.parse_transition("strobe"), ("flash", "flash", 0.08))

    def test_velocity_stabilize_track_and_finishing(self):
        shots = [{"id": "A", "start": 0, "end": 3, "velocity": True,
                  "layers": [{"src": "v", "fx": ["stabilize", "denoise"]}], "fx": ["halation", "flare", "dust", "weave", "lens"]}]
        g = self.render({"sources": {"v": {"path": "v.mp4"}}, "shots": shots}, 0, files=["v.mp4"])
        self.assertIn("vidstabtransform=input=stab/", g)
        self.assertIn("hqdn3d", g)
        self.assertGreater(g.count("if(lt(T,"), 6)                       # beat ramp -> nested setpts segments
        for k in ("lenscorrection", "lutyuv=y='if(gt(val,251)", "sigmaV=1.5", "colorchannelmixer=rr=1:gg=0.35"):
            self.assertIn(k, g)

    def test_focus_auto_builds_a_moving_crop(self):
        shots = [{"id": "A", "start": 0, "end": 2, "layers": [{"src": "v", "focus": "auto"}]}]
        with patch.object(footage, "track_subject", return_value=[(0.0, 0.2, 0.5), (2.0, 0.7, 0.5)]):
            g = self.render({"sources": {"v": {"path": "v.mp4"}}, "shots": shots}, 0, files=["v.mp4"])
        self.assertIn("in_w*(if(lt(t,2.000)", g)


class LyricBeatTests(unittest.TestCase):
    def test_beat_react_adds_pulses_inside_shown_lines_only(self):
        aw = lyrics.AssWriter(1080, 1920, "Be Vietnam Pro", "Anton", "#FFD24D", 0, 10)
        aw.lyrics([{"start": 1.0, "end": 3.0, "text": "một hai ba"}], lambda t: "subtitle")
        aw.caption(0, 5, "credit", "fade", "credit line")
        aw.beat_react([0.2, 1.5, 2.0, 2.5, 9.0])
        lyric = [e for e in aw.events if ",lyric," in e][0]
        self.assertEqual(lyric.count("fscx108"), 3)
        self.assertNotIn("fscx108", [e for e in aw.events if ",credit," in e][0])


class FootageCheckTests(unittest.TestCase):
    def test_low_resolution_sources_are_reported_once_per_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.mp4").write_bytes(b"x")
            p = project(root, {"sources": {"a": {"path": "a.mp4"}}, "shots": [
                {"id": "S1", "start": 0, "end": 2, "layers": [{"src": "a"}]},
                {"id": "S2", "start": 2, "end": 4, "layers": [{"src": "a"}], "layout": "fit_blur"},
                {"id": "S3", "start": 4, "end": 6, "layers": [{"src": "a", "upscale": True}]}]})
            with patch.object(footage, "probe_wh", return_value=(1280, 720)):
                w = mv.footage_warnings(p)
        self.assertEqual(len(w), 1)
        self.assertIn("a (1280x720)", w[0])
        self.assertIn("S1", w[0])
        self.assertNotIn("S2", w[0])                                       # fit_blur shows the whole frame
        self.assertNotIn("S3", w[0])                                       # upscaled


if __name__ == "__main__":
    unittest.main()
