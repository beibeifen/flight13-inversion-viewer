from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "runtime" / "source-hud.zip"
FRAME_RE = re.compile(r"pts_\d{4}p000\.jpg$")
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def collect_frames(source_root: Path) -> list[tuple[str, Path]]:
    frames: list[tuple[str, Path]] = []
    for side in ("left", "right"):
        side_root = source_root / side
        if not side_root.is_dir():
            raise FileNotFoundError(f"Missing HUD side directory: {side_root}")
        for path in sorted(side_root.iterdir(), key=lambda item: item.name):
            if path.is_file() and FRAME_RE.fullmatch(path.name):
                frames.append((f"{side}/{path.name}", path))
    if not frames:
        raise FileNotFoundError(f"No HUD frames found below {source_root}")
    return frames


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a deterministic optional ZIP of Flight 13 HUD source frames."
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
        help="Directory containing left/ and right/ JPEG frames.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    output = args.output.resolve()
    manifest_path = output.with_suffix(".manifest.json")
    frames = collect_frames(source_root)
    output.parent.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, str | int]] = []
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
        strict_timestamps=True,
    ) as archive:
        for archive_name, path in frames:
            body = path.read_bytes()
            info = zipfile.ZipInfo(archive_name, ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, body, compresslevel=6)
            entries.append(
                {
                    "path": archive_name,
                    "bytes": len(body),
                    "sha256": sha256_bytes(body),
                }
            )

    counts = {
        side: sum(1 for entry in entries if str(entry["path"]).startswith(f"{side}/"))
        for side in ("left", "right")
    }
    archive_body = output.read_bytes()
    manifest = {
        "schema": "flight13-source-hud-manifest-v1",
        "archive_name": output.name,
        "archive_bytes": len(archive_body),
        "archive_sha256": sha256_bytes(archive_body),
        "frame_counts": counts,
        "frames": entries,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "archive": str(output),
                "bytes": len(archive_body),
                "sha256": manifest["archive_sha256"],
                "frame_counts": counts,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
