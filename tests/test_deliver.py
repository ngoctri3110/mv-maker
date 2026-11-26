import sys
import tempfile
import unittest
from pathlib import Path

import yaml

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "mv-maker" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import deliver  # noqa: E402
import editcheck  # noqa: E402
import mv  # noqa: E402

LOG = """
[blackdetect @ 0x1] black_start:4 black_end:5.5 black_duration:1.5
[freezedetect @ 0x2] lavfi.freezedetect.freeze_start: 4
[freezedetect @ 0x2] lavfi.freezedetect.freeze_end: 5.5
[freezedetect @ 0x2] lavfi.freezedetect.freeze_start: 6
[freezedetect @ 0x2] lavfi.freezedetect.freeze_end: 8.5
[Parsed_ebur128_0 @ 0x3] Summary:

  Integrated loudness:
    I:         -21.8 LUFS
    Threshold: -32.1 LUFS

  Loudness range:
    LRA:         3.0 LU

  True peak:
    Peak:       -0.2 dBFS
"""
INFO = {"format": {"duration": "12.0"}, "streams": [
    {"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p", "duration": "12.0"},
    {"codec_type": "audio", "codec_name": "aac", "duration": "11.6"}]}


class DeliverTests(unittest.TestCase):
    def test_parse_scan_reads_black_frozen_and_loudness(self):
        r = deliver.parse_scan(LOG)
        self.assertEqual(r["black"], [(4.0, 5.5)])
        self.assertEqual(r["frozen"], [(4.0, 5.5), (6.0, 8.5)])
        self.assertEqual((r["lufs"], r["true_peak"], r["lra"]), (-21.8, -0.2, 3.0))

    def test_qa_report_flags_real_problems_once_and_skips_intended(self):
        r = deliver.parse_scan(LOG)
        w = deliver.qa_report(INFO, r, 11.0, lambda t: "S04", lambda k, a, b: False, max_sec=10)
        text = "\n".join(w)
        for k in ("duration 12.00s", "audio 11.60s vs video 12.00s", "over the platform limit", "black 4.00-5.50s (S04)",
                  "frozen picture 6.00-8.50s", "true peak -0.2", "quiet: -21.8"):
            self.assertIn(k, text)
        self.assertEqual(text.count("frozen picture"), 1)                 # the black stretch is not reported twice
        w2 = deliver.qa_report(INFO, r, 12.0, lambda t: "S04", lambda k, a, b: True)
        self.assertFalse(any("black" in x or "frozen" in x for x in w2))

    def test_snap_cut_and_short_window(self):
        self.assertEqual(deliver.snap_cut(9.3, 16.6, [0, 2.1, 4.2, 8.5, 10.6, 16.8]), (8.5, 16.8))
        self.assertEqual(deliver.snap_cut(9.3, 16.6, [30.0]), (9.3, 16.6))       # nothing near: unchanged
        shots = [{"start": 0, "end": 8, "section": "verse"}, {"start": 8, "end": 30, "section": "Hook"},
                 {"start": 30, "end": 200, "section": "chorus"}]
        self.assertEqual(deliver.short_window(shots, 45, editcheck.canon), (8.0, 53.0))

    def test_srt_is_relative_to_the_window(self):
        lines = [{"start": 1.0, "end": 2.5, "text": "một"}, {"start": 10.0, "end": 12.0, "text": "hai", "sub": "two"}]
        out = deliver.srt(lines, 9.0, 20.0)
        self.assertEqual(out, "1\n00:00:01,000 --> 00:00:03,000\nhai\ntwo\n")

    def test_thumb_ass_places_title_by_orientation(self):
        h = deliver.thumb_ass(1280, 720, "Song", "Artist", "Anton", "Be Vietnam Pro", "#FF0000", False)
        v = deliver.thumb_ass(1080, 1920, "Song", "Artist", "Anton", "Be Vietnam Pro", "#FF0000", True)
        self.assertIn("\\an1\\pos(64,648)", h)                             # lower-left on YouTube
        self.assertIn("\\an8\\pos(540,422)", v)                            # upper safe area on a vertical cover
        self.assertIn("SONG", h)


class CutAudioTests(unittest.TestCase):
    def test_cut_snaps_to_bars_and_fades_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sb = {"sources": {"a": {}}, "shots": [{"id": f"S{i}", "start": i * 4, "end": i * 4 + 4,
                                                   "layers": [{"src": "a", "in": i}]} for i in range(10)]}
            (root / "storyboard.yaml").write_text(yaml.safe_dump(sb), encoding="utf-8")
            p = mv.Project(root)
            p.downbeats = [2.0 * k for k in range(21)]
            a0, b0 = mv.apply_cut(p, "0:09.3-0:16.7")
            self.assertEqual((a0, b0), (10.0, 16.0))
            self.assertEqual(p.sb["audio_fade_in"], 0.25)
            self.assertEqual(p.sb["audio_fade_out"], 1.2)
            p2 = mv.Project(root)
            self.assertEqual(mv.apply_cut(p2, "0:09.3-0:16.7", snap=False), (9.3, 16.7))


if __name__ == "__main__":
    unittest.main()
