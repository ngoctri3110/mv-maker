import argparse
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import yaml

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "mv-maker" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import assist  # noqa: E402
import lyrics  # noqa: E402
import mv  # noqa: E402


def run(fn, args) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn(args)
    return buf.getvalue()


class PlanTests(unittest.TestCase):
    plan = {"sections": {"chorus": {"look_for": ["a", "b"], "role": ["performance", "narrative"], "size": ["close", "wide"]},
                         "chorus@last": {"shot_len": 0.8}, "verse": {"look_for": "v"}}}

    def test_section_plan_merges_generic_then_specific(self):
        sp = assist.section_plan(self.plan, "chorus", 2, True)
        self.assertEqual(sp["shot_len"], 0.8)
        self.assertEqual(sp["look_for"], ["a", "b"])
        self.assertNotIn("shot_len", assist.section_plan(self.plan, "chorus", 1, False))
        self.assertEqual(assist.section_plan(self.plan, "hook", 1, False)["look_for"], ["a", "b"])   # hook -> chorus

    def test_plan_shot_uses_performance_clip_and_cycles_looks_over_other_shots(self):
        sp, state = self.plan["sections"]["chorus"], {}
        shots = [assist.plan_shot({"id": f"S{i}"}, sp, i, "perf", state) for i in range(4)]
        self.assertEqual(shots[0]["layers"], [{"src": "perf", "lipsync": True}])
        self.assertEqual([s.get("look_for") for s in shots], [None, "a", None, "b"])
        self.assertEqual([s["size"] for s in shots], ["close", "wide", "close", "wide"])

    def test_auto_with_plan_writes_full_storyboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "audio").mkdir()
            (root / "audio" / "song.mp3").write_bytes(b"x")
            lines = [{"start": 4, "end": 8, "text": "verse", "section": "Verse"},
                     {"start": 9, "end": 15, "text": "chorus one", "section": "Chorus"},
                     {"start": 16, "end": 23, "text": "chorus two", "section": "Chorus"}]
            (root / "lyrics.yaml").write_text(yaml.safe_dump({"lines": lines}), encoding="utf-8")
            plan = {"genre": "pop", "preset": "pop-bright", "platforms": ["tiktok"], "performance": "perf",
                    "sections": {"verse": {"look_for": "street"}, "chorus": {"role": ["performance", "narrative"],
                                                                             "look_for": ["beach"], "beat_fx": ["zoom"]}},
                    "shots": {"S01": {"look_for": "fixed intro"}}}
            (root / "plan.yaml").write_text(yaml.safe_dump(plan), encoding="utf-8")
            args = argparse.Namespace(project=str(root), template=None, theme=None, format="9:16", audio=None, title=None,
                                      artist=None, lang="en", lines=2, force=True, genre=None, plan=str(root / "plan.yaml"))
            with patch.object(mv, "_duration", return_value=24.0):
                run(mv.cmd_auto, args)
            sb = yaml.safe_load((root / "storyboard.yaml").read_text(encoding="utf-8"))
            self.assertEqual((sb["preset"], sb["genre"], sb["platforms"]), ("pop-bright", "pop", ["tiktok"]))
            self.assertIn("perf", sb["sources"])
            self.assertEqual(sb["shots"][0]["look_for"], "fixed intro")
            ch = [s for s in sb["shots"] if s["section"] == "chorus"]
            self.assertTrue(all(s["beat_fx"] == ["zoom"] for s in ch))
            self.assertTrue(any(s.get("layers") == [{"src": "perf", "lipsync": True}] for s in ch))
            self.assertFalse(any(str(s.get("look_for", "")).startswith("TODO") for s in sb["shots"][1:]))
            mv.Project(root).validate()
            status = run(mv.cmd_status, argparse.Namespace(project=str(root)))
            self.assertIn("to find: perf", status)
            self.assertIn("NEXT:", status)


class DigestTests(unittest.TestCase):
    def test_context_is_short_and_specific(self):
        out = run(mv.cmd_context, argparse.Namespace(project=None, type="mv", genre="rock", platforms="tiktok",
                                                     mood="nostalgia"))
        self.assertIn("Genre rock", out)
        self.assertIn("rock-grunge", out)
        self.assertNotIn("lv-kinetic", out)                 # lyric templates are not listed for an MV
        self.assertIn("C-SPLIT-SOFT =", out)                 # mood picks explained
        self.assertIn("Platform plan", out)
        self.assertLess(len(out), 6000)                      # ~1.5k tokens, not the whole reference set
        lyr = run(mv.cmd_context, argparse.Namespace(project=None, type="lyric", genre=None, platforms=None, mood=None))
        self.assertIn("lv-grunge", lyr)

    def test_align_reports_per_line_match(self):
        user = [{"text": "xin chao ban"}, {"text": "hoan toan khac"}]
        segs = [{"text": "", "start": 0, "end": 3, "words": [
            {"w": "xin", "s": 0, "e": 0.5}, {"w": "chao", "s": 0.5, "e": 1}, {"w": "ban", "s": 1, "e": 1.5},
            {"w": "zzz", "s": 2, "e": 2.5}, {"w": "yyy", "s": 2.5, "e": 3}]}]
        out, _ = lyrics.align_lines(user, segs)
        self.assertEqual(out[0]["match"], 1.0)
        self.assertEqual(out[1]["match"], 0.0)


class ProofTests(unittest.TestCase):
    def test_proof_sheet_labels_every_shot_in_one_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font = root / "f.ttf"
            font.write_bytes(b"x")
            calls = []

            def fake(cmd, check=True, cwd=None):
                calls.append(cmd)
                if "tile=" in " ".join(cmd):
                    Path(cmd[-1]).write_bytes(b"jpg")

            shots = [{"id": f"S{i}", "_s": i * 2.0, "_e": i * 2.0 + 2, "lyric": "câu hát"} for i in range(10)]
            with patch.object(assist.subprocess, "run", side_effect=fake):
                pages = assist.proof_sheet(root / "v.mp4", shots, 0.0, 20.0, root / "refs" / "proof.jpg",
                                           root / "work", font, vertical=True)
            self.assertEqual(len(pages), 1)
            self.assertEqual(len(calls), 11)                                  # 10 frames + 1 tile
            self.assertIn("-ss", calls[3])
            self.assertEqual(calls[3][calls[3].index("-ss") + 1], "7.00")      # middle of shot 3
            label = (root / "work" / "l009.txt").read_text(encoding="utf-8")
            self.assertTrue(label.startswith("S9  0:18.0"))


if __name__ == "__main__":
    unittest.main()
