import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

import yaml

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "mv-maker" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import mv


class FfmpegGraphTests(unittest.TestCase):
    def test_fx_filters_keep_screen_style_effects_in_rgb(self):
        filters = mv.fx_filters(["glow", "leak:0.25"], "fx", w=640, h=360, fps=24)
        graph = ";".join(filters)
        self.assertIn("format=gbrp", graph)
        self.assertIn("blend=all_mode=screen", graph)

    def test_render_shot_writes_split_graph_and_ffmpeg_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            font = root / "test.ttf"
            font.write_bytes(b"synthetic-font")
            storyboard = {
                "title": "Graph test",
                "format": "16:9",
                "font_file": str(font),
                "sources": {
                    "top": {"note": "top placeholder"},
                    "bottom": {"note": "bottom placeholder"},
                },
                "shots": [{
                    "id": "S01",
                    "start": 0,
                    "end": 2,
                    "layout": "split_v",
                    "layers": [{"src": "top"}, {"src": "bottom", "fx": ["glow"]}],
                }],
            }
            (root / "storyboard.yaml").write_text(yaml.safe_dump(storyboard), encoding="utf-8")
            project = mv.Project(root)
            commands = []

            def fake_run(command, cwd=None, quiet=True):
                commands.append((command, cwd))
                return None

            with patch.object(mv, "run", side_effect=fake_run):
                renderer = mv.Renderer(project, mode="proxy", encoder="libx264", jobs=1, force=True)
                output = renderer.render_shot(0)

            graph_path = root / "build" / "proxy" / "shots" / "000_S01.filter"
            graph = graph_path.read_text(encoding="utf-8")
            self.assertEqual(output.name, "000_S01.mp4")
            self.assertIn("maskedmerge", graph)
            self.assertIn("format=gbrp", graph)
            self.assertIn("blend=all_mode=screen", graph)
            self.assertTrue(any("-/filter_complex" in command for command, _ in commands))


if __name__ == "__main__":
    unittest.main()
