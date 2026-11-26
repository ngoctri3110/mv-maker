"""Semantic matching without a real model: a fake embedder maps words to fixed directions."""
import argparse
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "mv-maker" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import match  # noqa: E402
import mv  # noqa: E402

WORDS = ["beach", "rain", "city", "door", "text"]


def vec_for(text: str) -> list[float]:
    v = [1.0 if w in text.lower() else 0.0 for w in WORDS] + [0.3]
    n = sum(x * x for x in v) ** 0.5
    return [x / n for x in v]


class FakeEmbedder:
    model_id = "fake/siglip"

    def __init__(self):
        self.image_calls = 0

    def images(self, paths):
        self.image_calls += len(paths)
        return [vec_for(Path(p).name) for p in paths]

    def texts(self, texts):
        return [vec_for(t) for t in texts]


class MatchCoreTests(unittest.TestCase):
    def test_assign_avoids_reuse_and_neighbours(self):
        shots = [{"id": "A"}, {"id": "B"}, {"id": "C"}]
        c = lambda key, sc: {"key": key, "score": sc}
        cands = {"A": [c("x", 0.9), c("y", 0.5)], "B": [c("x", 0.8), c("z", 0.4)], "C": [c("x", 0.7), c("y", 0.6)]}
        got = match.assign(shots, cands)
        self.assertEqual(got, {"A": 0, "B": 1, "C": 1})
        # reuse allowed, but never in neighbouring shots
        got = match.assign(shots, cands, reuse=True)
        self.assertEqual(got["A"], 0)
        self.assertEqual(got["C"], 0)
        self.assertEqual(got["B"], 1)

    def test_in_point_puts_best_frame_a_third_in_and_stays_inside(self):
        self.assertEqual(match.in_point({"start": 10, "end": 30}, 20.0, 3.0), 18.95)
        self.assertEqual(match.in_point({"start": 10, "end": 12}, 11.0, 3.0), 10.0)    # scene too short: its start
        self.assertEqual(match.in_point({"start": 10, "end": 14}, 13.9, 3.0), 11.0)    # clamped to fit

    def test_score_prefers_strong_frame_and_penalises_avoid(self):
        self.assertGreater(match.score_scene([0.1, 0.4, 0.1], None), match.score_scene([0.2, 0.2, 0.2], None))
        self.assertLess(match.score_scene([0.4], [0.4]), match.score_scene([0.4], [0.0]))

    def test_best_run_extends_over_near_best_tiles(self):
        best, a, b = match.best_run([0, 2, 4, 6, 8], [0.1, 0.30, 0.31, 0.305, 0.1], pad=1.0)
        self.assertEqual(best, 4)
        self.assertEqual((a, b), (1.0, 8.0))

    def test_storyboard_tiles_times_without_downloading_video(self):
        info = {"duration": 30, "formats": [
            {"format_id": "sb2", "width": 48, "height": 27, "columns": 2, "rows": 2,
             "fragments": [{"url": "u0", "duration": 20}, {"url": "u1", "duration": 20}]},
            {"format_id": "sb0", "width": 160, "height": 90, "columns": 2, "rows": 2,
             "fragments": [{"url": "big0", "duration": 20}, {"url": "big1", "duration": 20}]},
            {"format_id": "18", "url": "video"}]}
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            got_urls = []

            def fake_run(cmd, check=True):
                stem = Path(cmd[-1]).name.split("_%")[0]
                for k in range(1, 5):
                    (work / f"{stem}_{k:02d}.jpg").write_bytes(b"x")

            with patch.object(match.subprocess, "run", side_effect=fake_run):
                tiles = match.storyboard_tiles(info, work, lambda u: got_urls.append(u) or b"img")
        self.assertEqual(got_urls, ["big0", "big1"])                   # largest storyboard
        self.assertEqual([t for t, _ in tiles], [0.0, 5.0, 10.0, 15.0, 20.0, 25.0])  # 30 s video: later tiles dropped


class ProjectAutoTests(unittest.TestCase):
    def test_auto_layers_resolve_from_matches_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sb = {"sources": {"own1": {"path": "a.mp4"}, "own2": {"path": "b.jpg"}}, "shots": [
                {"id": "S01", "start": 0, "end": 2, "layers": "auto", "look_for": "beach"},
                {"id": "S02", "start": 2, "end": 4, "look_for": "rain"},
                {"id": "S03", "start": 4, "end": 6, "layers": [{"src": "auto", "fx": ["bw"]}]}]}
            (root / "storyboard.yaml").write_text(yaml.safe_dump(sb), encoding="utf-8")
            (root / "matches.yaml").write_text(yaml.safe_dump({"shots": {
                "S01": {"use": 2, "candidates": [{"src": "own1", "in": 1.0}, {"src": "own1", "in": 9.5}]},
                "S02": {"use": 1, "candidates": [{"src": "own2", "in": 0, "image": True}]}}}), encoding="utf-8")
            p = mv.Project(root)
            p.validate()
            self.assertEqual(p.shots[0]["layers"][0], {"src": "own1", "in": 9.5})
            self.assertEqual(p.shots[1]["layers"][0]["zoom"], "in")       # photo -> Ken Burns
            self.assertIsNone(p.shots[2]["layers"][0]["src"])            # not matched yet -> placeholder card
            self.assertIn("mv match", p.shots[2]["layers"][0]["note"])
            self.assertEqual(p.shots[2]["layers"][0]["fx"], ["bw"])


class CommandTests(unittest.TestCase):
    def test_cmd_match_writes_choices_without_reusing_scenes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frames = root / "build" / "match" / "frames"
            frames.mkdir(parents=True)
            lib = []
            for i, (src, word) in enumerate([("own1", "beach"), ("own1", "rain"), ("own2", "city"), ("own2", "beach")]):
                fr = []
                for t in (0.2, 0.5, 0.8):
                    f = frames / f"{src}_{i}_{word}_{t}.jpg"
                    f.write_bytes(b"x")
                    fr.append((i * 10 + t * 10, f))
                lib.append({"src": src, "start": i * 10.0, "end": i * 10 + 10.0, "quality": 0.5, "frames": fr})
            sb = {"sources": {"own1": {"path": "a.mp4"}, "own2": {"path": "b.mp4"}}, "shots": [
                {"id": "S01", "start": 0, "end": 2, "layers": "auto", "look_for": "a beach at sunset"},
                {"id": "S02", "start": 2, "end": 4, "layers": "auto", "look_for": ["beach waves", "sunny beach"]},
                {"id": "S03", "start": 4, "end": 6, "layers": "auto", "look_for": "rain on a window", "avoid": "text"}]}
            (root / "storyboard.yaml").write_text(yaml.safe_dump(sb), encoding="utf-8")
            fake = FakeEmbedder()
            args = argparse.Namespace(project=str(root), pick=None, sources=None, model=None, top=3, reuse=False,
                                      sheets=False)
            with patch.object(mv, "_library", return_value=lib), patch.object(mv, "_embedder", return_value=fake), \
                    patch.object(mv.SRC, "contact_sheet"):
                mv.cmd_match(args)
                calls = fake.image_calls
                mv.cmd_match(args)                       # second run: every frame embedding comes from the cache
            self.assertEqual(fake.image_calls, calls)
            m = yaml.safe_load((root / "matches.yaml").read_text(encoding="utf-8"))["shots"]
            pick = lambda s: m[s]["candidates"][m[s]["use"] - 1]
            beach = {pick("S01")["src"] + str(pick("S01")["in"]), pick("S02")["src"] + str(pick("S02")["in"])}
            self.assertEqual(len(beach), 2)                                    # two beach shots, two different scenes
            self.assertEqual(pick("S03")["src"], "own1")
            self.assertGreaterEqual(pick("S03")["in"], 10.0)                   # the rain scene
            p = mv.Project(root)
            self.assertEqual(p.shots[2]["layers"][0]["src"], "own1")
            mv.cmd_match(argparse.Namespace(**{**vars(args), "pick": "S03:2"}))
            self.assertEqual(yaml.safe_load((root / "matches.yaml").read_text(encoding="utf-8"))["shots"]["S03"]["use"], 2)

    def test_rank_and_deep_scan_orders_candidates_and_suggests_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            th = []
            for name in ("city_thumb.jpg", "beach_thumb.jpg"):
                (root / name).write_bytes(b"x")
                th.append(str(root / name))
            cands = [{"provider": "pexels", "url": "u1", "thumb": th[0], "license": "x"},
                     {"provider": "youtube", "url": "https://youtu.be/abc", "thumb": th[1], "license": "x",
                      "_info": {"id": "abc"}}]
            tiles = []
            for t, w in ((0, "city"), (5, "beach"), (10, "beach"), (15, "door")):
                f = root / f"tile_{t}_{w}.jpg"
                f.write_bytes(b"x")
                tiles.append((float(t), f))
            with patch.object(match, "storyboard_tiles", return_value=tiles):
                out = mv._rank_and_scan(cands, "beach", FakeEmbedder(), root / "rank", deep=1)
            self.assertEqual(out[0]["url"], "https://youtu.be/abc")
            self.assertTrue(out[0]["deep"])
            self.assertEqual(out[0]["best_t"], 5.0)
            self.assertEqual(out[0]["section"], "0:02.00-0:16.00")
            self.assertNotIn("_info", out[0])

    def test_auto_footage_cuts_to_genre_grammar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "audio").mkdir()
            (root / "audio" / "song.mp3").write_bytes(b"x")
            lines = [{"start": 4, "end": 7, "text": "verse line one", "section": "Verse"},
                     {"start": 8, "end": 11, "text": "verse line two", "section": "Verse"},
                     {"start": 12, "end": 15, "text": "chorus line", "section": "Chorus"},
                     {"start": 16, "end": 19, "text": "bridge line", "section": "Bridge"},
                     {"start": 20, "end": 23, "text": "last chorus", "section": "Chorus"}]
            (root / "lyrics.yaml").write_text(yaml.safe_dump({"lines": lines}), encoding="utf-8")
            args = argparse.Namespace(project=str(root), template="pop-bright", theme=None, format="9:16", audio=None,
                                      title="Song", artist="Artist", lang="vi", lines=2, force=True, genre=None)
            with patch.object(mv, "_duration", return_value=24.0):
                mv.cmd_auto(args)
            sb = yaml.safe_load((root / "storyboard.yaml").read_text(encoding="utf-8"))
            self.assertEqual(sb["genre"], "pop")
            shots = sb["shots"]
            self.assertEqual(shots[0]["section"], "intro")
            self.assertEqual(shots[-1]["end"], 24.0)
            self.assertTrue(all(s["layers"] == "auto" and s["look_for"] for s in shots))
            for x, y in zip(shots, shots[1:]):
                self.assertEqual(x["end"], y["start"])
            dur = lambda s: s["end"] - s["start"]
            first = [dur(s) for s in shots if s["section"] == "chorus" and s["start"] < 16]
            last = [dur(s) for s in shots if s["section"] == "chorus" and s["start"] >= 16]
            self.assertLess(sum(last) / len(last), sum(first) / len(first) + 1e-6)
            mv.Project(root).validate()


if __name__ == "__main__":
    unittest.main()
