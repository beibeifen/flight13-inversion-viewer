from __future__ import annotations

import gzip
import http.client
import json
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from flight13_viewer import server as viewer_server  # noqa: E402


class ServerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        temp_root = Path(cls.temp.name)
        cls.video = temp_root / "sample.mp4"
        cls.video.write_bytes(bytes(range(256)) * 32768)
        archive = temp_root / "source-hud.zip"
        with zipfile.ZipFile(archive, "w") as target:
            target.writestr("left/pts_0000p000.jpg", b"left-jpeg")
            target.writestr("right/pts_0430p000.jpg", b"right-jpeg")
        viewer_server.configure_runtime(
            app_dir=REPO_ROOT / "app",
            video_path=cls.video,
            source_hud_archive=archive,
        )
        viewer_server.ensure_gzip_bundle()
        cls.httpd = viewer_server.ViewerServer(
            ("127.0.0.1", 0), viewer_server.ViewerHandler
        )
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=3)
        cls.temp.cleanup()

    def request(
        self, method: str, path: str, headers: dict[str, str] | None = None
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        body = response.read()
        response_headers = {key.lower(): value for key, value in response.getheaders()}
        connection.close()
        return response.status, response_headers, body

    def test_main_page_and_assets(self) -> None:
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["content-type"])
        self.assertIn("script-src 'self'", headers["content-security-policy"])
        self.assertIn(b"/assets/app.js", body)
        for route in (
            "/assets/app.css",
            "/assets/theme.js",
            "/assets/app.js",
            "/vendor/three/three.module.js",
            "/vendor/three/LICENSE",
        ):
            self.assertEqual(self.request("GET", route)[0], 200)

    def test_json_gzip(self) -> None:
        status, headers, body = self.request(
            "GET", "/viewer-data.json", {"Accept-Encoding": "gzip"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("content-encoding"), "gzip")
        parsed = json.loads(gzip.decompress(body))
        self.assertEqual(
            parsed["schema_version"],
            "flight13-timeline-viewer-data-v1.5-public-demo",
        )

    def test_health_reports_runtime_resources(self) -> None:
        status, _, body = self.request("GET", "/health.json")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["schema"], "flight13-viewer-health-v2")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["resources"]["source_hud_backend"], "zip")
        self.assertEqual(payload["resources"]["source_hud_left_frames"], 1)
        self.assertEqual(payload["resources"]["source_hud_right_frames"], 1)

    def test_source_hud_zip_route_is_whitelisted(self) -> None:
        status, headers, body = self.request(
            "GET", "/source-hud/left/pts_0000p000.jpg"
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "image/jpeg")
        self.assertEqual(body, b"left-jpeg")
        self.assertEqual(self.request("GET", "/source-hud/left/../../secret")[0], 404)

    def test_video_ranges_are_bounded(self) -> None:
        status, headers, body = self.request(
            "GET", "/video/flight13.mp4", {"Range": "bytes=256-1023"}
        )
        self.assertEqual(status, 206)
        self.assertEqual(headers["content-range"], f"bytes 256-1023/{self.video.stat().st_size}")
        self.assertEqual(body, self.video.read_bytes()[256:1024])

        status, headers, body = self.request(
            "GET", "/video/flight13.mp4", {"Range": "bytes=0-"}
        )
        self.assertEqual(status, 206)
        self.assertEqual(len(body), viewer_server.MAX_RANGE_RESPONSE_BYTES)
        self.assertTrue(headers["content-range"].startswith("bytes 0-4194303/"))

    def test_invalid_range_and_unknown_route(self) -> None:
        self.assertEqual(
            self.request(
                "GET", "/video/flight13.mp4", {"Range": "bytes=999999999-"}
            )[0],
            416,
        )
        self.assertEqual(self.request("GET", "/not-a-route")[0], 404)


class LocalLauncherContractTests(unittest.TestCase):
    def test_windows_launcher_is_zero_install_and_autodetects_workspace_video(self) -> None:
        launcher = (REPO_ROOT / "start-viewer.ps1").read_text(encoding="utf-8-sig")
        wrapper = (REPO_ROOT / "start-viewer.cmd").read_text(encoding="utf-8-sig")
        self.assertIn('Get-Command python', launcher)
        self.assertIn('data_raw\\flight13\\Flight13_launch_to_splashdown_1080p.mp4', launcher)
        self.assertIn('$env:PYTHONPATH', launcher)
        self.assertIn('--source-hud-archive', launcher)
        self.assertIn('$DataOnly = $true', launcher)
        self.assertIn('if ($DataOnly) { $null }', launcher)
        self.assertIn('start-viewer.ps1', wrapper)


if __name__ == "__main__":
    unittest.main()
