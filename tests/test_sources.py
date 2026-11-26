import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "mv-maker" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sources


class _Response:
    def __init__(self, body: bytes, content_length: str | None = None):
        self._body = body
        self._read = False
        self.headers = {"Content-Length": content_length} if content_length is not None else {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, _size=-1):
        if self._read:
            return b""
        self._read = True
        return self._body


class SourceSearchTests(unittest.TestCase):
    def test_pexels_video_search_maps_license_and_orientation(self):
        payload = {
            "videos": [{
                "url": "https://pexels.test/video/1",
                "image": "https://pexels.test/thumb/1.jpg",
                "duration": 8,
                "user": {"name": "Creator"},
                "video_files": [
                    {"file_type": "video/mp4", "width": 1920, "height": 1080, "link": "https://cdn.test/1.mp4"},
                    {"file_type": "video/webm", "width": 1920, "height": 1080, "link": "https://cdn.test/1.webm"},
                ],
            }]
        }
        with patch.dict(os.environ, {"PEXELS_API_KEY": "test-key"}), patch.object(sources, "_json", return_value=payload) as get:
            result = sources.search_pexels("rain & neon", "video", "portrait", 3)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["provider"], "pexels")
        self.assertEqual(result[0]["license"], sources.LICENSES["pexels"])
        self.assertEqual(result[0]["creator"], "Creator")
        request_url, headers = get.call_args.args
        self.assertIn("query=rain%20%26%20neon", request_url)
        self.assertIn("orientation=portrait", request_url)
        self.assertEqual(headers["Authorization"], "test-key")

    def test_find_deduplicates_candidates_and_keeps_provider_errors(self):
        def good(_query, _kind, _orient, _n):
            return [
                {"provider": "fake", "title": "same.mp4", "url": "https://cdn.test/a.mp4"},
                {"provider": "fake", "title": "same.mp4", "url": "https://cdn.test/b.mp4"},
            ]

        def bad(_query, _kind, _orient, _n):
            raise RuntimeError("temporary provider outage")

        with patch.dict(sources.SEARCHERS, {"fake": good, "broken": bad}, clear=False):
            results, notes = sources.find("city", providers=["fake", "broken"], n=8)

        self.assertEqual([r["url"] for r in results], ["https://cdn.test/a.mp4"])
        self.assertEqual(notes[0], "fake: 1")
        self.assertIn("broken: skipped (temporary provider outage)", notes[1])


class SourceDownloadTests(unittest.TestCase):
    def test_direct_download_writes_extension_and_removes_partial_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "clip"
            response = _Response(b"media-bytes", "11")
            with patch.object(sources.urllib.request, "urlopen", return_value=response):
                result = sources.direct_download("https://cdn.test/clip.jpg?download=1", target, max_mb=1)

            self.assertEqual(result, target.with_suffix(".jpg"))
            self.assertEqual(result.read_bytes(), b"media-bytes")
            self.assertFalse(result.with_suffix(".jpg.part").exists())

    def test_direct_download_rejects_content_length_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "clip"
            response = _Response(b"too-large", str(2 * 2**20))
            with patch.object(sources.urllib.request, "urlopen", return_value=response):
                with self.assertRaisesRegex(RuntimeError, "file is 2 MB > limit 1 MB"):
                    sources.direct_download("https://cdn.test/clip.mp4", target, max_mb=1)

            self.assertFalse(target.with_suffix(".mp4").exists())
            self.assertFalse(target.with_suffix(".mp4.part").exists())

    def test_direct_download_cleans_partial_file_when_stream_crosses_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "clip"
            response = _Response(b"0123456789")
            with patch.object(sources.urllib.request, "urlopen", return_value=response):
                with self.assertRaisesRegex(RuntimeError, "download passed the 0 MB limit"):
                    sources.direct_download("https://cdn.test/clip.mp4", target, max_mb=0.000001)

            self.assertFalse(target.with_suffix(".mp4").exists())
            self.assertFalse(target.with_suffix(".mp4.part").exists())


if __name__ == "__main__":
    unittest.main()
