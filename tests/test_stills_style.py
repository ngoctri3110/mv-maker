import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "mv-maker" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import footage  # noqa: E402
import mv  # noqa: E402
import style  # noqa: E402


class StyleTests(unittest.TestCase):
    def test_key_estimate_finds_a_minor_and_c_major(self):
        a_minor = [0.0] * 12
        for k, v in ((9, 1.0), (0, 0.8), (4, 0.8), (2, 0.4), (7, 0.3), (5, 0.3)):   # A, C, E strongest
            a_minor[k] = v
        self.assertEqual(style.estimate_key(a_minor)[:2], ("A", "minor"))
        c_major = [1.0, 0, 0.5, 0, 0.8, 0.5, 0, 0.9, 0, 0.4, 0, 0.3]
        self.assertEqual(style.estimate_key(c_major)[:2], ("C", "major"))

    def test_guess_ranks_typical_profiles(self):
        edm = {"tempo": 128, "key": "A", "mode": "minor", "key_conf": 0.7, "brightness_hz": 2800, "noisiness": 0.01,
               "drums": 0.78, "onset_rate": 4.5, "dynamics": 0.7}
        ballad = {"tempo": 72, "key": "C", "mode": "major", "key_conf": 0.8, "brightness_hz": 1200, "noisiness": 0.005,
                  "drums": 0.12, "onset_rate": 1.2, "dynamics": 0.3}
        rap = {"tempo": 90, "key": "F", "mode": "minor", "key_conf": 0.5, "brightness_hz": 2000, "noisiness": 0.01,
               "drums": 0.66, "onset_rate": 5.0, "dynamics": 0.4}
        self.assertEqual(style.guess(edm)["genres"][0]["genre"], "edm")
        self.assertEqual(style.guess(ballad)["genres"][0]["genre"], "ballad")
        self.assertEqual(style.guess(ballad)["mood"], "warm, tender")
        self.assertEqual(style.guess(rap)["genres"][0]["genre"], "rap")
        close = dict(edm, drums=0.6)                                         # K-pop and EDM overlap here
        self.assertIn("close call", style.guess(close)["why"])

    def test_interpret_maps_audioset_tags_and_sad_pop_to_ballad(self):
        r = style.interpret({"Pop music": 0.6, "Sad music": 0.3, "Rock music": 0.05, "Speech": 0.4})
        self.assertEqual(r["genres"][0]["genre"], "pop")
        self.assertIn("ballad", [g["genre"] for g in r["genres"]])
        self.assertEqual(r["moods"][0][0], "Sad music")


class CameraTests(unittest.TestCase):
    def test_camera_paths(self):
        self.assertEqual(mv.camera_path({"camera": "pan-left"})[:2], ([0.64, 0.5, 1.3], [0.36, 0.5, 1.3]))
        self.assertEqual(mv.camera_path({"camera": {"detail": [0.3, 0.2]}})[1], [0.3, 0.2, 2.0])
        self.assertEqual(mv.camera_path({"zoom": "out"})[:2], ([0.5, 0.5, 1.12], [0.5, 0.5, 1.0]))   # legacy zoom
        self.assertIsNone(mv.camera_path({}))
        with self.assertRaises(SystemExit):
            mv.camera_path({"camera": "orbit"})

    def test_detail_anchors_the_crop_on_the_target_and_starts_near_it(self):
        ly = {"camera": {"detail": [0.9, 0.7, 2.4]}}
        self.assertEqual(mv.camera_focus(ly), [0.9, 0.7])                    # edge details stay reachable in 9:16
        start = mv.camera_path(ly)[0]
        self.assertGreater(start[0], 0.7)                                    # a short shot already reads as the detail
        self.assertEqual(mv.camera_focus({"camera": {"from": [0.2, 0.5, 1.5], "to": [0.4, 0.5, 1.5]}}), [0.3, 0.5])
        self.assertIsNone(mv.camera_focus({"zoom": "in"}))

    def test_zoompan_keeps_the_window_inside_and_eases(self):
        z = mv.camera_zoompan(([0.5, 0.5, 1.0], [0.9, 0.1, 2.0], True), 540, 960, 72, 24)
        self.assertIn("max(0,min(iw-iw/zoom,", z)
        self.assertIn("*(3-2*", z)                                           # smoothstep
        fg = mv.camera_zoompan(([0.5, 0.5, 1.0], [0.5, 0.5, 1.1], False), 540, 960, 72, 24, zscale=2.0)
        self.assertIn("z='1.0+(0.2000)", fg)                                 # parallax foreground zooms 2x

    def test_parallax_builds_two_zoom_layers_with_a_depth_matte(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "f.ttf").write_bytes(b"x")
            (root / "p.png").write_bytes(b"x")
            sb = {"format": "9:16", "font_file": str(root / "f.ttf"), "sources": {"p": {"path": "p.png"}},
                  "shots": [{"id": "S1", "start": 0, "end": 3, "layers": [{"src": "p", "parallax": True}]}]}
            (root / "storyboard.yaml").write_text(yaml.safe_dump(sb), encoding="utf-8")
            p = mv.Project(root)
            with patch.object(mv, "run"), patch.object(footage, "depth_mask", side_effect=lambda f, d, s=0.35: d), \
                    patch.object(footage, "file_key", side_effect=str):
                mv.Renderer(p, mode="proxy", encoder="libx264", jobs=1, force=True).render_shot(0)
            g = (root / "build" / "proxy" / "shots" / "000_S1.filter").read_text(encoding="utf-8")
            self.assertIn("alphamerge", g)
            self.assertEqual(g.count("zoompan"), 3)                          # background, foreground, matte
            self.assertIn("[1:v]format=gray", g)                             # the matte is the second input


class StillsTests(unittest.TestCase):
    def test_detail_points_prefers_busy_areas_away_from_borders(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("OpenCV not installed")
        with tempfile.TemporaryDirectory() as tmp:
            img = np.full((600, 900, 3), 120, np.uint8)
            img[250:350, 550:650] = np.random.default_rng(1).integers(0, 255, (100, 100, 3), dtype=np.uint8)  # texture
            f = Path(tmp) / "x.png"
            cv2.imwrite(str(f), img)
            pts = footage.detail_points(f, 3)
        x, y, z, why = pts[0]
        self.assertAlmostEqual(x, 0.67, delta=0.1)
        self.assertAlmostEqual(y, 0.5, delta=0.12)
        self.assertEqual(why, "detail")


if __name__ == "__main__":
    unittest.main()
