import sys
import tempfile
import unittest
from pathlib import Path

import yaml

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "mv-maker" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import lyrics  # noqa: E402
import mv  # noqa: E402
import platforms  # noqa: E402


class PlatformPlanTests(unittest.TestCase):
    def test_groups_expand_without_duplicates(self):
        self.assertEqual(platforms.expand("vertical,tiktok"), ["tiktok", "reels", "facebook_reels", "shorts"])
        with self.assertRaises(ValueError):
            platforms.expand(["myspace"])

    def test_plan_groups_versions_and_prefers_landscape_master_for_mixed_formats(self):
        pl = platforms.plan(["tiktok", "reels", "youtube"], duration=240)
        self.assertEqual(pl["versions"], {"9:16": ["TikTok", "Instagram Reels"], "16:9": ["YouTube video"]})
        self.assertEqual(pl["master"], "16:9")
        self.assertIn("landscape 4K", pl["source"])
        self.assertEqual(pl["needs_cut"], ["Instagram Reels"])               # 240 s > 180 s
        self.assertEqual(pl["safe"]["9:16"], [0.14, 0.35, 0.06, 0.14])        # strictest side of each
        self.assertTrue(any("Versions to render" in l for l in platforms.plan_text(pl)))

    def test_check_flags_format_length_hook_and_unsafe_lyric_area(self):
        sb = {"platforms": ["reels", "youtube"], "format": "9:16", "lyric_area": [0.05, 0.5, 0.95, 0.9]}
        shots = [{"start": 0, "end": 5}, {"start": 5, "end": 200}]
        text = "\n".join(platforms.check(sb, shots, 200.0))
        self.assertIn("wants 16:9", text)
        self.assertIn("longer than 180s", text)
        self.assertIn("first shot lasts 5.0s", text)
        self.assertIn("lyric_area", text)
        vi = platforms.check(sb, shots, 200.0, lang="vi")
        self.assertTrue(any("vượt giới hạn" in w for w in vi))


class SafeZoneLyricTests(unittest.TestCase):
    def test_safe_zone_lifts_lyrics_and_narrows_margins(self):
        plain = lyrics.AssWriter(1080, 1920, "Be Vietnam Pro", "Anton", "#FFD24D", 0, 10)
        reels = lyrics.AssWriter(1080, 1920, "Be Vietnam Pro", "Anton", "#FFD24D", 0, 10,
                                 safe=platforms.safe_zone(["reels"], "9:16"))
        a, b = plain.default_area("subtitle"), reels.default_area("subtitle")
        self.assertLessEqual(b[3], 1920 * (1 - 0.35))                          # above the Reels caption area
        self.assertLess(b[3], a[3])
        self.assertLess(b[2], a[2])                                            # clear of the right button column


class CutRenderTests(unittest.TestCase):
    def test_apply_cut_keeps_range_trims_and_shifts_in_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sb = {"slug": "song", "sources": {"a": {}, "perf": {"sync": 1.0}}, "shots": [
                {"id": "S1", "start": 0, "end": 10, "layers": [{"src": "a", "in": 2}]},
                {"id": "S2", "start": 10, "end": 20, "layers": [{"src": "a", "in": 30, "speed": 0.5}], "transition": "flash"},
                {"id": "S3", "start": 20, "end": 30, "layers": [{"src": "perf", "lipsync": True}], "transition": "flash"},
                {"id": "S4", "start": 30, "end": 40, "layers": [{"src": "a", "in": 50}]}]}
            (root / "storyboard.yaml").write_text(yaml.safe_dump(sb), encoding="utf-8")
            p = mv.Project(root)
            mv.apply_cut(p, "0:14-0:25")
            p.validate()
            self.assertEqual([s["id"] for s in p.shots], ["S2", "S3"])
            self.assertEqual(p.shots[0]["start"], 14.0)
            self.assertEqual(p.shots[0]["layers"][0]["in"], 32.0)             # 4 s later at half speed = 2 s of source
            self.assertEqual(p.shots[1]["end"], 25.0)
            self.assertNotIn("transition", p.shots[1])
            self.assertEqual(p.shots[1]["layers"][0]["in"], 21.0)             # lip-sync still follows the song
            self.assertEqual(p.sb["slug"], "song_cut14-25")


if __name__ == "__main__":
    unittest.main()
