import sys
import tempfile
import unittest
from pathlib import Path

import yaml


SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "mv-maker" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import lyrics  # noqa: E402
import mv  # noqa: E402


class LyricsTests(unittest.TestCase):
    def test_parse_lyrics_txt_preserves_sections_and_translation(self):
        lines = lyrics.parse_lyrics_txt(
            "# comment\n[Chorus]\nXin chào | Hello\n\nMột câu"
        )
        self.assertEqual(lines[0], {"text": "Xin chào", "section": "Chorus", "sub": "Hello"})
        self.assertEqual(lines[1], {"text": "Một câu", "section": "Chorus"})

    def test_align_lines_maps_words_and_reports_match_ratio(self):
        user = [{"text": "xin chao", "section": "Verse"}]
        segments = [{
            "text": "xin chao",
            "start": 1.0,
            "end": 2.0,
            "words": [
                {"w": "xin", "s": 1.0, "e": 1.4},
                {"w": "chao", "s": 1.4, "e": 2.0},
            ],
        }]
        aligned, ratio = lyrics.align_lines(user, segments)
        self.assertEqual(ratio, 1.0)
        self.assertEqual(aligned[0]["start"], 1.0)
        self.assertEqual(aligned[0]["end"], 2.0)
        self.assertEqual(aligned[0]["words"][1], ["chao", 1.4, 2.0])


class RendererContractTests(unittest.TestCase):
    def test_time_and_transition_parsers(self):
        self.assertAlmostEqual(mv.tsec("1:02.5"), 62.5)
        self.assertEqual(mv.parse_transition("cut"), ("cut", "cut", 0.0))
        self.assertEqual(mv.parse_transition("dissolve:0.75"), ("xfade", "fade", 0.75))
        self.assertEqual(mv.parse_transition("flash"), ("flash", "flash", 0.25))

    def test_project_validation_accepts_contiguous_storyboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            storyboard = {
                "title": "Test",
                "format": "9:16",
                "sources": {"clip": {"note": "synthetic"}},
                "shots": [
                    {"id": "S01", "start": 0, "end": 1, "layers": [{"src": "clip"}]},
                    {"id": "S02", "start": 1, "end": 2, "layers": [{"src": "clip"}]},
                ],
            }
            (root / "storyboard.yaml").write_text(yaml.safe_dump(storyboard), encoding="utf-8")
            project = mv.Project(root)
            project.validate()
            self.assertEqual([shot["id"] for shot in project.shots], ["S01", "S02"])


if __name__ == "__main__":
    unittest.main()
