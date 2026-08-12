from __future__ import annotations

import argparse
import gzip
import json
import mimetypes
import os
import re
import sysconfig
import threading
import webbrowser
import zipfile
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


SOURCE_CHECKOUT_ROOT = Path(__file__).resolve().parents[2]


def default_app_dir() -> Path:
    configured = os.environ.get("FLIGHT13_VIEWER_APP_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    checkout_app = SOURCE_CHECKOUT_ROOT / "app"
    if checkout_app.is_dir():
        return checkout_app
    return Path(sysconfig.get_path("data")) / "share" / "flight13-viewer" / "app"


APP_DIR = default_app_dir()
DEFAULT_RUNTIME_ROOT = (
    SOURCE_CHECKOUT_ROOT if (SOURCE_CHECKOUT_ROOT / "app").is_dir() else Path.cwd()
)


def default_video_path() -> Path:
    configured = os.environ.get("FLIGHT13_VIEWER_VIDEO_PATH")
    if configured:
        return Path(configured).expanduser().resolve()

    candidates = (
        DEFAULT_RUNTIME_ROOT / "media" / "Flight13_web_720p.mp4",
        DEFAULT_RUNTIME_ROOT / "media" / "Flight13_launch_to_splashdown_1080p.mp4",
        DEFAULT_RUNTIME_ROOT.parent
        / "data_raw"
        / "flight13"
        / "Flight13_launch_to_splashdown_1080p.mp4",
    )
    return next((path for path in candidates if path.is_file()), candidates[0])


DEFAULT_VIDEO_PATH = default_video_path()
DEFAULT_SOURCE_HUD_ARCHIVE = DEFAULT_RUNTIME_ROOT / "runtime" / "source-hud.zip"

HUD_ASSET_NAMES = (
    "vehicle-models.json",
)


def build_static_routes(app_dir: Path) -> dict[str, Path]:
    hud_dir = app_dir / "hud"
    hud_asset_dir = hud_dir / "assets"
    return {
        "/": app_dir / "index.html",
        "/index.html": app_dir / "index.html",
        "/viewer-data.json": app_dir / "viewer-data.json",
        "/assets/app.css": app_dir / "assets" / "app.css",
        "/assets/theme.js": app_dir / "assets" / "theme.js",
        "/assets/app.js": app_dir / "assets" / "app.js",
        "/vendor/three/three.module.js": (
            app_dir / "vendor" / "three" / "three.module.js"
        ),
        "/vendor/three/LICENSE": app_dir / "vendor" / "three" / "LICENSE",
        "/hud/index.html": hud_dir / "index.html",
        **{
            f"/hud/assets/{name}": hud_asset_dir / name
            for name in HUD_ASSET_NAMES
        },
    }


HUD_DIR = APP_DIR / "hud"
HUD_ASSET_DIR = HUD_DIR / "assets"
STATIC_ROUTES = build_static_routes(APP_DIR)

VIDEO_ROUTE = "/video/flight13.mp4"
HEALTH_ROUTE = "/health.json"
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")
SOURCE_HUD_ROUTE_RE = re.compile(
    r"/source-hud/(?P<side>left|right)/(?P<filename>pts_\d{4}p000\.jpg)$"
)
SOURCE_HUD_FILE_RE = re.compile(r"pts_\d{4}p000\.jpg$")
CHUNK_SIZE = 1024 * 1024
STATIC_CHUNK_SIZE = 64 * 1024
MAX_RANGE_RESPONSE_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class SourceHudStore:
    directory: Path | None = None
    archive: Path | None = None

    @property
    def backend(self) -> str:
        if self.directory is not None and self.directory.is_dir():
            return "directory"
        if self.archive is not None and self.archive.is_file():
            return "zip"
        return "missing"

    def counts(self) -> dict[str, int]:
        counts = {"left": 0, "right": 0}
        if self.backend == "directory":
            assert self.directory is not None
            for side in counts:
                side_dir = self.directory / side
                if side_dir.is_dir():
                    counts[side] = sum(
                        1
                        for path in side_dir.iterdir()
                        if path.is_file()
                        and SOURCE_HUD_FILE_RE.fullmatch(path.name) is not None
                    )
        elif self.backend == "zip":
            assert self.archive is not None
            with zipfile.ZipFile(self.archive) as source:
                for name in source.namelist():
                    parts = name.replace("\\", "/").split("/")
                    if (
                        len(parts) == 2
                        and parts[0] in counts
                        and SOURCE_HUD_FILE_RE.fullmatch(parts[1]) is not None
                    ):
                        counts[parts[0]] += 1
        return counts

    def read(self, side: str, filename: str) -> bytes | None:
        if self.backend == "directory":
            assert self.directory is not None
            path = self.directory / side / filename
            return path.read_bytes() if path.is_file() else None
        if self.backend == "zip":
            assert self.archive is not None
            try:
                with zipfile.ZipFile(self.archive) as source:
                    return source.read(f"{side}/{filename}")
            except KeyError:
                return None
        return None


VIDEO_PATH = DEFAULT_VIDEO_PATH
SOURCE_HUD_STORE = SourceHudStore(archive=DEFAULT_SOURCE_HUD_ARCHIVE)
ALLOW_MISSING_VIDEO = False


class ViewerServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class ViewerHandler(BaseHTTPRequestHandler):
    server_version = "Flight13Viewer/2.0"

    def do_HEAD(self) -> None:
        self._dispatch(send_body=False)

    def do_GET(self) -> None:
        self._dispatch(send_body=True)

    def _dispatch(self, *, send_body: bool) -> None:
        route = urlsplit(self.path).path
        if route == VIDEO_ROUTE:
            self._serve_video(send_body=send_body)
            return
        if route == HEALTH_ROUTE:
            self._serve_health(send_body=send_body)
            return
        source_hud_match = SOURCE_HUD_ROUTE_RE.fullmatch(route)
        if source_hud_match is not None:
            self._serve_source_hud(source_hud_match, send_body=send_body)
            return
        static_path = STATIC_ROUTES.get(route)
        if static_path is not None:
            self._serve_static(static_path, send_body=send_body)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Unknown viewer route")

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")

    def _serve_static(self, path: Path, *, send_body: bool) -> None:
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, f"Missing viewer file: {path.name}")
            return

        response_path = path
        content_encoding: str | None = None
        if (
            path.name == "viewer-data.json"
            and "gzip" in self.headers.get("Accept-Encoding", "")
            and path.with_suffix(path.suffix + ".gz").is_file()
        ):
            response_path = path.with_suffix(path.suffix + ".gz")
            content_encoding = "gzip"

        size = response_path.stat().st_size
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix == ".json":
            content_type = "application/json; charset=utf-8"
        elif path.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        elif path.suffix == ".js":
            content_type = "text/javascript; charset=utf-8"
        elif path.suffix == ".css":
            content_type = "text/css; charset=utf-8"

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-cache")
        if content_encoding is not None:
            self.send_header("Content-Encoding", content_encoding)
            self.send_header("Vary", "Accept-Encoding")
        if path.suffix == ".html":
            script_sources = "'self'"
            frame_ancestors = "'none'"
            if path == HUD_DIR / "index.html":
                script_sources += " 'unsafe-inline'"
                frame_ancestors = "'self'"
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; media-src 'self'; "
                f"style-src 'self' 'unsafe-inline'; script-src {script_sources}; "
                "connect-src 'self'; object-src 'none'; base-uri 'none'; "
                f"frame-ancestors {frame_ancestors}",
            )
        self._security_headers()
        self.end_headers()
        if send_body:
            try:
                with response_path.open("rb") as source:
                    while chunk := source.read(STATIC_CHUNK_SIZE):
                        self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                return

    def _serve_source_hud(self, match: re.Match[str], *, send_body: bool) -> None:
        side = match.group("side")
        filename = match.group("filename")
        body = SOURCE_HUD_STORE.read(side, filename)
        if body is None:
            self.send_error(HTTPStatus.NOT_FOUND, "HUD source frame is unavailable")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self._security_headers()
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def _serve_health(self, *, send_body: bool) -> None:
        source_counts = SOURCE_HUD_STORE.counts()
        resources: dict[str, bool | int | str] = {
            "parent_index": (APP_DIR / "index.html").is_file(),
            "viewer_data": (APP_DIR / "viewer-data.json").is_file(),
            "app_css": (APP_DIR / "assets" / "app.css").is_file(),
            "app_js": (APP_DIR / "assets" / "app.js").is_file(),
            "source_video": VIDEO_PATH.is_file(),
            "source_video_optional": ALLOW_MISSING_VIDEO,
            "hud_index": (HUD_DIR / "index.html").is_file(),
            "hud_asset_whitelist_complete": all(
                (HUD_ASSET_DIR / name).is_file() for name in HUD_ASSET_NAMES
            ),
            "source_hud_backend": SOURCE_HUD_STORE.backend,
            "source_hud_left_frames": source_counts["left"],
            "source_hud_right_frames": source_counts["right"],
        }
        required = (
            bool(resources["parent_index"])
            and bool(resources["viewer_data"])
            and bool(resources["app_css"])
            and bool(resources["app_js"])
            and bool(resources["hud_index"])
            and bool(resources["hud_asset_whitelist_complete"])
            and (bool(resources["source_video"]) or ALLOW_MISSING_VIDEO)
        )
        payload = {
            "schema": "flight13-viewer-health-v2",
            "status": "ok" if required else "degraded",
            "resources": resources,
            "routes": {
                "static_route_count": len(STATIC_ROUTES),
                "hud_asset_route_count": len(HUD_ASSET_NAMES),
                "video_range_requests": True,
                "video_range_cap_bytes": MAX_RANGE_RESPONSE_BYTES,
                "source_hud_pattern": "/source-hud/(left|right)/pts_NNNNp000.jpg",
            },
        }
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        self.send_response(HTTPStatus.OK if required else HTTPStatus.SERVICE_UNAVAILABLE)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def _serve_video(self, *, send_body: bool) -> None:
        if not VIDEO_PATH.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Source video is unavailable")
            return
        size = VIDEO_PATH.stat().st_size
        range_header = self.headers.get("Range")
        start = 0
        end = size - 1
        status = HTTPStatus.OK

        if range_header:
            match = RANGE_RE.fullmatch(range_header.strip())
            if match is None or "," in range_header:
                self._range_not_satisfiable(size)
                return
            start_text, end_text = match.groups()
            if not start_text and not end_text:
                self._range_not_satisfiable(size)
                return
            if start_text:
                start = int(start_text)
                requested_end = int(end_text) if end_text else size - 1
                if start >= size or requested_end < start:
                    self._range_not_satisfiable(size)
                    return
                end = min(requested_end, size - 1, start + MAX_RANGE_RESPONSE_BYTES - 1)
            else:
                suffix = int(end_text)
                if suffix <= 0:
                    self._range_not_satisfiable(size)
                    return
                suffix = min(suffix, size, MAX_RANGE_RESPONSE_BYTES)
                start = size - suffix
                end = size - 1
            status = HTTPStatus.PARTIAL_CONTENT

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "private, max-age=3600")
        self._security_headers()
        self.end_headers()
        if not send_body:
            return

        try:
            with VIDEO_PATH.open("rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining:
                    chunk = handle.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    def _range_not_satisfiable(self, size: int) -> None:
        self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
        self.send_header("Content-Range", f"bytes */{size}")
        self.send_header("Content-Length", "0")
        self._security_headers()
        self.end_headers()

    def log_message(self, format_string: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {format_string % args}")


def configure_runtime(
    *,
    video_path: Path,
    app_dir: Path | None = None,
    source_hud_root: Path | None = None,
    source_hud_archive: Path | None = None,
    allow_missing_video: bool = False,
) -> None:
    global APP_DIR, HUD_DIR, HUD_ASSET_DIR, STATIC_ROUTES
    global VIDEO_PATH, SOURCE_HUD_STORE, ALLOW_MISSING_VIDEO
    if app_dir is not None:
        APP_DIR = app_dir.expanduser().resolve()
        HUD_DIR = APP_DIR / "hud"
        HUD_ASSET_DIR = HUD_DIR / "assets"
        STATIC_ROUTES = build_static_routes(APP_DIR)
    VIDEO_PATH = video_path.resolve()
    SOURCE_HUD_STORE = SourceHudStore(
        directory=source_hud_root.resolve() if source_hud_root else None,
        archive=source_hud_archive.resolve() if source_hud_archive else None,
    )
    ALLOW_MISSING_VIDEO = allow_missing_video


def ensure_gzip_bundle() -> None:
    source = APP_DIR / "viewer-data.json"
    target = APP_DIR / "viewer-data.json.gz"
    if not source.is_file():
        return
    if target.is_file() and target.stat().st_mtime_ns >= source.stat().st_mtime_ns:
        return
    try:
        target.write_bytes(gzip.compress(source.read_bytes(), compresslevel=6, mtime=0))
    except OSError:
        # Installed assets may be read-only; the uncompressed JSON remains valid.
        return


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serve the read-only Flight 13 synchronized timeline viewer."
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address; use 0.0.0.0 only behind a firewall or reverse proxy.",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--app-dir",
        type=Path,
        default=APP_DIR,
        help="Viewer asset directory. Defaults to the source checkout, installed share data, "
        "or FLIGHT13_VIEWER_APP_DIR.",
    )
    parser.add_argument("--video-path", type=Path, default=DEFAULT_VIDEO_PATH)
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument("--source-hud-root", type=Path)
    source_group.add_argument(
        "--source-hud-archive", type=Path, default=DEFAULT_SOURCE_HUD_ARCHIVE
    )
    parser.add_argument(
        "--allow-missing-video",
        action="store_true",
        help="Start in data-only mode when the local MP4 is unavailable.",
    )
    parser.add_argument(
        "--no-open", action="store_true", help="Do not open the default browser."
    )
    args = parser.parse_args()

    archive = args.source_hud_archive
    if archive is not None and not archive.is_file():
        archive = None
    configure_runtime(
        app_dir=args.app_dir,
        video_path=args.video_path,
        source_hud_root=args.source_hud_root,
        source_hud_archive=archive,
        allow_missing_video=args.allow_missing_video,
    )
    ensure_gzip_bundle()

    missing = [path for path in STATIC_ROUTES.values() if not path.is_file()]
    if not VIDEO_PATH.is_file() and not ALLOW_MISSING_VIDEO:
        missing.append(VIDEO_PATH)
    if missing:
        missing_lines = "\n".join(f"  - {path}" for path in missing)
        raise SystemExit(
            "Flight 13 查看器缺少启动文件：\n"
            f"{missing_lines}\n\n"
            "把视频复制到 media 目录，或使用：\n"
            '  flight13-viewer --video-path "D:\\path\\to\\Flight13.mp4"\n'
            "只检查页面可使用：\n"
            "  flight13-viewer --allow-missing-video"
        )

    try:
        server = ViewerServer((args.host, args.port), ViewerHandler)
    except OSError as error:
        raise SystemExit(
            f"无法监听 {args.host}:{args.port}：{error}\n"
            "该端口可能已有查看器在运行；可直接访问 "
            f"http://127.0.0.1:{args.port}/，或用 --port 指定其他端口。"
        ) from None
    actual_port = server.server_address[1]
    display_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    url = f"http://{display_host}:{actual_port}/"
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    source_counts = SOURCE_HUD_STORE.counts()
    print(f"Flight 13 viewer: {url}")
    print(
        "HUD source frames: "
        f"backend={SOURCE_HUD_STORE.backend}, left={source_counts['left']}, "
        f"right={source_counts['right']}"
    )
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
