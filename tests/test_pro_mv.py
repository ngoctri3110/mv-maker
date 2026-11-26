import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "mv-maker" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import editcheck  # noqa: E402
import gen  # noqa: E402
import lyrics  # noqa: E402
import mv  # noqa: E402


def make_project(root: Path, storyboard: dict, picks: dict | None = None) -> "mv.Project":
    (root / "storyboard.yaml").write_text(yaml.safe_dump(storyboard, allow_unicode=True), encoding="utf-8")
    if picks:
        (root / "picks.yaml").write_text(yaml.safe_dump(picks), encoding="utf-8")
    return mv.Project(root)


class GenTests(unittest.TestCase):
    def test_parse_resolves_palette_and_accent_and_defaults(self):
        kind, cols = gen.parse("smoke:$2,$a", ["#000000", "#112233"], "#ff0000")
        self.assertEqual(kind, "smoke")
        self.assertEqual(cols, ["#112233", "#ff0000"])
        self.assertEqual(gen.parse("particles:")[1], gen.DEFAULTS["particles"])

    def test_parse_rejects_unknown_kind_and_missing_palette_slot(self):
        with self.assertRaises(ValueError):
            gen.parse("lava:#fff")
        with self.assertRaises(ValueError):
            gen.parse("smoke:$3", ["#000000"])

    def test_build_uses_unique_labels_and_input_placeholders(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(gen, "_texture", return_value=Path(tmp) / "t.png"):
            args, stmts = gen.build("particles:#000000,#ffffff", 540, 960, 24, 2.0, Path(tmp), "S1l0g")
        graph = ";".join(stmts)
        self.assertEqual(args.count("-i"), 3)
        self.assertIn("[IN1]", graph)
        self.assertTrue(stmts[-1].endswith("[S1l0g]"))
        self.assertIn("format=gbrp", graph)


class EditCheckTests(unittest.TestCase):
    def shots(self):
        return [
            {"id": "S01", "start": 0, "end": 2, "section": "verse", "role": "performance", "size": "medium",
             "layers": [{"src": "perf"}]},
            {"id": "S02", "start": 2, "end": 4, "section": "verse", "role": "performance", "size": "medium",
             "layers": [{"src": "perf"}]},
            {"id": "S03", "start": 4, "end": 12, "section": "chorus", "role": "narrative", "layers": [{"src": "story"}]},
            {"id": "S04", "start": 12, "end": 20, "section": "chorus", "role": "narrative", "layers": [{"src": "story2"}]},
        ]

    def test_canon_maps_loose_section_names(self):
        self.assertEqual(editcheck.canon("Pre-Chorus"), "pre")
        self.assertEqual(editcheck.canon("Hook 2"), "chorus")
        self.assertEqual(editcheck.canon("Rap verse"), "verse")
        self.assertIsNone(editcheck.canon("instrumental"))

    def test_flags_jump_cut_slow_chorus_and_low_performance(self):
        res = editcheck.check({"genre": "pop", "format": "16:9"}, self.shots())
        text = "\n".join(res["warnings"])
        self.assertIn("S01->S02", text)              # same source, same size
        self.assertIn("chorus: average shot 8.0s", text)
        self.assertIn("performance is 0%", text)
        self.assertEqual(res["stats"][0]["perf"], 1.0)

    def test_vietnamese_messages_and_unknown_genre(self):
        res = editcheck.check({"genre": "polka"}, self.shots(), lang="vi")
        self.assertIn("không có thể loại", res["warnings"][0])

    def test_off_beat_cuts_are_reported(self):
        res = editcheck.check({}, self.shots(), beats=[0, 2.0, 4.3, 12.0])
        self.assertTrue(any("S03 (0.30s)" in w for w in res["warnings"]))


class ProjectFeatureTests(unittest.TestCase):
    def test_lipsync_follows_song_time_and_cut_lead_keeps_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            sb = {"sources": {"perf": {"note": "x"}}, "song_start": 1.0, "cut_lead": "2f",
                  "shots": [{"id": "A", "start": 0, "end": 2, "layers": [{"src": "perf", "lipsync": True}]},
                            {"id": "B", "start": 2, "end": 4, "layers": [{"src": "perf", "lipsync": True}]}]}
            p = make_project(Path(tmp), sb, picks={"perf": {"sync": 1.5}})
            self.assertEqual(p.shots[1]["layers"][0]["in"], 4.5)      # 2 + song_start 1 + sync 1.5
            lead = p.apply_cut_lead(25)
            self.assertAlmostEqual(lead, 0.08)
            self.assertAlmostEqual(mv.tsec(p.shots[1]["start"]), 1.92)
            self.assertAlmostEqual(p.shots[1]["layers"][0]["in"], 4.42)
            self.assertEqual(mv.tsec(p.shots[0]["start"]), 0)         # first start / last end never move
            self.assertEqual(mv.tsec(p.shots[1]["end"]), 4)

    def test_lipsync_rejects_speed_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            sb = {"sources": {"perf": {}}, "shots": [
                {"id": "A", "start": 0, "end": 2, "layers": [{"src": "perf", "lipsync": True, "speed": 0.5}]}]}
            with self.assertRaises(SystemExit):
                make_project(Path(tmp), sb).validate()

    def test_template_preset_fills_empty_shots_with_cycling_scenes_and_theme(self):
        with tempfile.TemporaryDirectory() as tmp:
            sb = {"preset": "lv-kinetic", "theme": "ocean", "shots": [
                {"id": "A", "start": 0, "end": 2, "section": "verse"},
                {"id": "B", "start": 2, "end": 4, "section": "chorus"},
                {"id": "C", "start": 4, "end": 6, "section": "pre-chorus", "layers": [{"src": "own"}]}],
                "sources": {"own": {"note": "user clip"}}}
            p = make_project(Path(tmp), sb)
            p.validate()
            self.assertEqual(p.sb["palette"][0], "#021b2e")              # theme beats preset palette
            self.assertEqual(p.shots[0]["layers"][0]["src"], "_scene1")
            self.assertEqual(p.shots[1]["layers"][0]["src"], "_scene2")
            self.assertEqual(p.shots[1]["lyric_style"], "stack")           # chorus section extra
            self.assertNotIn("lyric_style", p.shots[2])                    # pre-chorus is not chorus
            self.assertEqual(p.shots[2]["layers"][0]["src"], "own")       # user layers are kept
            self.assertIn("gen", p.sources["_scene1"])

    def test_role_and_size_are_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            sb = {"sources": {}, "shots": [{"id": "A", "start": 0, "end": 2, "role": "dance"}]}
            with self.assertRaises(SystemExit):
                make_project(Path(tmp), sb).validate()

    def test_generated_source_renders_through_add_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font = root / "f.ttf"
            font.write_bytes(b"x")
            sb = {"format": "9:16", "font_file": str(font), "palette": ["#101010", "#ff0000"],
                  "sources": {"bg": {"gen": "smoke:$1,$2"}},
                  "shots": [{"id": "S01", "start": 0, "end": 2, "layers": [{"src": "bg"}]}]}
            p = make_project(root, sb)
            with patch.object(mv, "run"), patch.object(gen, "_texture", return_value=root / "t.png"):
                r = mv.Renderer(p, mode="proxy", encoder="libx264", jobs=1, force=True)
                r.render_shot(0)
            graph = (root / "build" / "proxy" / "shots" / "000_S01.filter").read_text(encoding="utf-8")
            self.assertNotIn("[IN", graph)
            self.assertIn("[1:v]", graph)
            self.assertIn("S01l0g", graph)


class LyricStyleTests(unittest.TestCase):
    line = {"start": 1.0, "end": 3.0, "text": "Mãi mãi mùa hè của em", "emph": "hè"}

    def events(self, style, typo=None):
        aw = lyrics.AssWriter(1080, 1920, "Be Vietnam Pro", "Anton", "#FFD24D", 0, 10, typo)
        aw.lyrics([dict(self.line)], lambda t: style, lead=0.3)
        return aw

    def test_new_styles_emit_events_with_their_ass_style(self):
        for style, ass in (("grunge", ",grunge,"), ("paper", ",paper,"), ("marker", ",marker,"), ("stagger", ",stagbig,")):
            aw = self.events(style)
            self.assertTrue(any(ass in e for e in aw.events), style)

    def test_stagger_uses_emph_word_and_lead(self):
        aw = self.events("stagger")
        big = [e for e in aw.events if ",stagbig," in e][0]
        self.assertTrue(big.rstrip().endswith("HÈ"))

    def test_lyric_lead_moves_line_start(self):
        aw = self.events("subtitle")
        self.assertIn("0:00:00.70", aw.events[0])

    def test_paper_style_uses_opaque_box_and_typo_size_scales(self):
        small = self.events("paper")
        big = self.events("paper", {"size": 1.5})
        st = [s for s in small.styles if s.startswith("Style: paper,")][0]
        self.assertEqual(st.split(",")[15], "3")                       # BorderStyle 3
        fs = lambda aw: int([s for s in aw.styles if s.startswith("Style: lyric,")][0].split(",")[2])
        self.assertGreater(fs(big), fs(small))

    def test_title_card_styles(self):
        aw = lyrics.AssWriter(1080, 1920, "Be Vietnam Pro", "Anton", "#FFD24D", 0, 10)
        aw.title_card({"artist": "Artist", "title": "Song"}, 0.5, 4)
        aw.title_card({"text": "The end"}, 7, 9.5, kind="end")
        text = "\n".join(aw.events)
        self.assertIn("ARTIST", text)
        self.assertIn("“Song”", text)
        self.assertIn("The end", text)


class AudioSyncTests(unittest.TestCase):
    def test_audio_offset_finds_known_delay(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not installed")
        rng = np.random.default_rng(3)
        sr = 8000
        song = np.zeros(sr * 20, dtype=np.float32)
        for t in rng.uniform(0, 19.5, 120):  # random clicks + tones = unique onsets
            i = int(t * sr)
            n = np.arange(800)
            song[i:i + 800] += np.sin(2 * np.pi * rng.uniform(200, 2000) * n / sr) * np.exp(-n / 200)
        clip = np.concatenate([np.zeros(int(2.3 * sr), dtype=np.float32), song[: sr * 12]])
        with patch.object(mv, "_pcm", side_effect=[song, clip]):
            off, conf = mv.audio_offset(Path("song"), Path("clip"))
        self.assertAlmostEqual(off, 2.3, delta=0.02)
        self.assertGreater(conf, 1.1)


if __name__ == "__main__":
    unittest.main()
