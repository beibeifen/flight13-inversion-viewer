from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HUD_ROOT = REPO_ROOT / "app" / "hud" / "assets"

REPLACEMENTS = {
    "vehicle-models.json": {
        ("source", "blend_file"): "external-model/Starship Block 3 V4.blend",
    },
    "hud-visual-cues.json": {
        ("sources", "coverage_csv"): (
            "visualizations/03_state_reconstruction/attitude_full_timeline_coverage_1hz/"
            "Flight13_attitude_full_timeline_coverage_1hz.csv"
        ),
        ("sources", "attitude_pilot"): (
            "visualizations/03_state_reconstruction/attitude_pilot/"
            "Flight13_attitude_pilot.json"
        ),
        ("sources", "material_pilot"): (
            "visualizations/03_state_reconstruction/attitude_material_pilot/"
            "Flight13_attitude_material_pilot.json"
        ),
        ("sources", "joint_search"): (
            "visualizations/03_state_reconstruction/attitude_joint_3d_pilot/"
            "Flight13_joint_3d_search.json"
        ),
        ("sources", "near_axis_anchors"): "tools/near_axis_projection_anchors.json",
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replace machine-local HUD metadata paths with portable provenance labels."
    )
    parser.add_argument("--hud-root", type=Path, default=DEFAULT_HUD_ROOT)
    args = parser.parse_args()

    hud_root = args.hud_root.resolve()
    for file_name, replacements in REPLACEMENTS.items():
        path = hud_root / file_name
        data = json.loads(path.read_text(encoding="utf-8"))
        for keys, value in replacements.items():
            target = data
            for key in keys[:-1]:
                target = target[key]
            target[keys[-1]] = value
        path.write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        print(f"sanitized {path}")


if __name__ == "__main__":
    main()
