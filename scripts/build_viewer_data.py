from __future__ import annotations

import argparse
import base64
import csv
import gzip
import hashlib
import json
import math
import os
import sys
from array import array
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "app" / "viewer-data.json"
TRACKER_ALIGNMENT_CANDIDATE_S = 2.56
VIDEO_TPLUS_ZERO_PTS_S = 7.0
UINT16_NULL = 65535
UINT8_NULL = 255


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def number(value: str | None, digits: int = 6) -> float | None:
    if value is None or value == "":
        return None
    parsed = float(value)
    if not math.isfinite(parsed):
        return None
    return round(parsed, digits)


def boolean(value: str | None) -> bool:
    return str(value).strip().lower() == "true"


def quantize_u16(value: str | None) -> int:
    parsed = number(value)
    if parsed is None:
        return UINT16_NULL
    return max(0, min(UINT16_NULL - 1, round(parsed * (UINT16_NULL - 1))))


def quantize_u8(value: str | None) -> int:
    parsed = number(value)
    if parsed is None:
        return UINT8_NULL
    return max(0, min(UINT8_NULL - 1, round(parsed * (UINT8_NULL - 1))))


def count_u8(value: str | None) -> int:
    if value is None or value == "":
        return UINT8_NULL
    return max(0, min(UINT8_NULL - 1, int(value)))


def encode_array(values: list[int], typecode: str) -> str:
    packed = array(typecode, values)
    if sys.byteorder != "little" and packed.itemsize > 1:
        packed.byteswap()
    return base64.b64encode(packed.tobytes()).decode("ascii")


def read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def build_trajectory(path: Path) -> dict[str, Any]:
    columns = [
        "tplus_s",
        "file_pts_s",
        "tracker_source_met_s",
        "ecef_x_m",
        "ecef_y_m",
        "ecef_z_m",
        "latitude_deg",
        "longitude_deg",
        "ellipsoid_altitude_km",
        "ecef_vx_mps",
        "ecef_vy_mps",
        "ecef_vz_mps",
        "ecef_ax_mps2",
        "ecef_ay_mps2",
        "ecef_az_mps2",
        "ecef_speed_kmh",
        "east_velocity_mps",
        "north_velocity_mps",
        "vertical_velocity_mps",
        "ground_speed_kmh",
        "heading_deg",
        "flight_path_angle_deg",
        "distance_from_pad_km",
        "phase_label",
        "derivative_quality_code",
    ]
    rows: list[list[Any]] = []
    for row in read_csv(path):
        rows.append(
            [
                number(row["mission_time_s"], 3),
                number(row["file_pts_s"], 3),
                number(row["tracker_source_met_s"], 3),
                number(row["ecef_x_m"], 3),
                number(row["ecef_y_m"], 3),
                number(row["ecef_z_m"], 3),
                number(row["latitude_deg"], 6),
                number(row["longitude_deg"], 6),
                number(row["ellipsoid_altitude_km"], 4),
                number(row["ecef_vx_mps"], 3),
                number(row["ecef_vy_mps"], 3),
                number(row["ecef_vz_mps"], 3),
                number(row["ecef_ax_mps2"], 6),
                number(row["ecef_ay_mps2"], 6),
                number(row["ecef_az_mps2"], 6),
                number(row["ecef_speed_kmh"], 2),
                number(row["east_velocity_mps"], 3),
                number(row["north_velocity_mps"], 3),
                number(row["vertical_velocity_mps"], 3),
                number(row["ground_speed_kmh"], 2),
                number(row["heading_deg"], 3),
                number(row["flight_path_angle_deg"], 3),
                number(row["great_circle_distance_from_pad_km"], 3),
                row["phase_label"],
                row["derivative_quality_code"],
            ]
        )
    return {"columns": columns, "rows": rows}


def build_fixes(path: Path) -> dict[str, Any]:
    columns = [
        "record_index",
        "aligned_tplus_s",
        "wall_tplus_s",
        "source_met_s",
        "video_pts_s",
        "latitude_deg",
        "longitude_deg",
        "source_altitude_m",
        "trajectory_version",
        "phase_label",
        "segment_id",
        "source_role",
        "gap_class",
        "dt_previous_s",
    ]
    rows: list[list[Any]] = []
    previous_met: float | None = None
    for row in read_csv(path):
        source_met = float(row["source_mission_time_s"])
        aligned = source_met + TRACKER_ALIGNMENT_CANDIDATE_S
        delta = None if previous_met is None else source_met - previous_met
        if delta is None:
            gap_class = "first"
        elif delta > 30.1:
            gap_class = "hard_220s"
        elif delta > 10.5:
            gap_class = "minor_20s"
        else:
            gap_class = "normal"
        rows.append(
            [
                int(row["record_index"]),
                round(aligned, 3),
                number(row["wall_offset_from_launch_epoch_s"], 3),
                round(source_met, 3),
                round(aligned + VIDEO_TPLUS_ZERO_PTS_S, 3),
                number(row["latitude_deg"], 6),
                number(row["longitude_deg"], 6),
                number(row["source_altitude_m"], 1),
                int(row["trajectory_version"]),
                row["phase_label"],
                row["raw_segment_id"],
                row["source_role"],
                gap_class,
                None if delta is None else round(delta, 3),
            ]
        )
        previous_met = source_met
    return {"columns": columns, "rows": rows}


def build_tracker_intervals(path: Path, summary_path: Path, validation_path: Path) -> dict[str, Any]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    expected_validation = "PASS_AS_RAW_ENDPOINT_INTERVAL_AVERAGE_KINEMATICS_WITH_EXPLICIT_TIME_BASES"
    if validation.get("status") != expected_validation or validation.get("error_count") != 0:
        raise ValueError(f"Tracker interval source is not independently validated: {validation.get('status')}")

    columns = [
        "interval_id",
        "segment_id",
        "left_record_index",
        "right_record_index",
        "start_tplus_s",
        "end_tplus_s",
        "mid_tplus_s",
        "dt_source_s",
        "dt_wall_s",
        "time_basis_difference_ms",
        "mid_latitude_deg",
        "mid_longitude_deg",
        "mid_altitude_km",
        "mid_ecef_x_m",
        "mid_ecef_y_m",
        "mid_ecef_z_m",
        "avg_ecef_vx_mps",
        "avg_ecef_vy_mps",
        "avg_ecef_vz_mps",
        "avg_ecef_speed_kmh",
        "avg_ground_speed_kmh",
        "avg_climb_rate_mps",
        "avg_heading_deg",
        "avg_east_mps",
        "avg_north_mps",
        "wall_avg_ecef_vx_mps",
        "wall_avg_ecef_vy_mps",
        "wall_avg_ecef_vz_mps",
        "wall_avg_ecef_speed_kmh",
        "wall_avg_ground_speed_kmh",
        "wall_avg_climb_rate_mps",
        "interval_horizontal_displacement_km",
        "segment_cumulative_horizontal_start_km",
        "segment_cumulative_horizontal_end_km",
        "future_conditioned",
        "result_level",
    ]
    rows: list[list[Any]] = []
    current_segment: str | None = None
    segment_cumulative_km = 0.0
    previous_end_tplus: float | None = None

    for row in read_csv(path):
        if row["instantaneous_navigation_state"].lower() != "false":
            raise ValueError(f"Unexpected instantaneous-state claim in {row['kinematics_interval_id']}")
        if row["future_conditioned"].lower() != "true" or row["smoothing_used"].lower() != "false":
            raise ValueError(f"Unexpected interval semantics in {row['kinematics_interval_id']}")

        segment_id = row["raw_segment_id"]
        if segment_id != current_segment:
            current_segment = segment_id
            segment_cumulative_km = 0.0
            previous_end_tplus = None

        start_tplus = float(row["left_source_mission_time_s"]) + TRACKER_ALIGNMENT_CANDIDATE_S
        end_tplus = float(row["right_source_mission_time_s"]) + TRACKER_ALIGNMENT_CANDIDATE_S
        mid_tplus = float(row["mid_source_mission_time_s"]) + TRACKER_ALIGNMENT_CANDIDATE_S
        dt_source = float(row["dt_source_s"])
        dt_wall = float(row["dt_wall_s"])
        east = float(row["source_avg_enu_east_mps"])
        north = float(row["source_avg_enu_north_mps"])
        up = float(row["source_avg_enu_up_mps"])
        wall_east = float(row["wall_avg_enu_east_mps"])
        wall_north = float(row["wall_avg_enu_north_mps"])
        wall_up = float(row["wall_avg_enu_up_mps"])
        ground_speed = math.hypot(east, north)
        wall_ground_speed = math.hypot(wall_east, wall_north)
        heading = None if ground_speed < 1e-9 else math.degrees(math.atan2(east, north)) % 360.0
        horizontal_displacement_km = ground_speed * dt_source / 1000.0
        cumulative_start = segment_cumulative_km
        segment_cumulative_km += horizontal_displacement_km

        if end_tplus <= start_tplus or abs(mid_tplus - (start_tplus + end_tplus) / 2.0) > 1e-6:
            raise ValueError(f"Invalid tracker interval time geometry in {row['kinematics_interval_id']}")
        if previous_end_tplus is not None and abs(start_tplus - previous_end_tplus) > 1e-6:
            raise ValueError(f"Non-contiguous interval inside {segment_id}: {row['kinematics_interval_id']}")
        previous_end_tplus = end_tplus

        rows.append(
            [
                row["kinematics_interval_id"],
                segment_id,
                int(row["left_record_index"]),
                int(row["right_record_index"]),
                round(start_tplus, 3),
                round(end_tplus, 3),
                round(mid_tplus, 3),
                round(dt_source, 3),
                round(dt_wall, 3),
                round((dt_source - dt_wall) * 1000.0, 3),
                number(row["mid_geodetic_latitude_deg"], 6),
                number(row["mid_geodetic_longitude_deg"], 6),
                number(str(float(row["mid_geodetic_altitude_m"]) / 1000.0), 4),
                number(row["mid_ecef_x_m"], 3),
                number(row["mid_ecef_y_m"], 3),
                number(row["mid_ecef_z_m"], 3),
                number(row["source_avg_ecef_vx_mps"], 3),
                number(row["source_avg_ecef_vy_mps"], 3),
                number(row["source_avg_ecef_vz_mps"], 3),
                number(str(float(row["source_avg_ecef_speed_mps"]) * 3.6), 2),
                round(ground_speed * 3.6, 2),
                round(up, 3),
                None if heading is None else round(heading, 3),
                round(east, 3),
                round(north, 3),
                number(row["wall_avg_ecef_vx_mps"], 3),
                number(row["wall_avg_ecef_vy_mps"], 3),
                number(row["wall_avg_ecef_vz_mps"], 3),
                number(str(float(row["wall_avg_ecef_speed_mps"]) * 3.6), 2),
                round(wall_ground_speed * 3.6, 2),
                round(wall_up, 3),
                round(horizontal_displacement_km, 4),
                round(cumulative_start, 4),
                round(segment_cumulative_km, 4),
                True,
                row["result_level"],
            ]
        )

    expected_rows = int(validation["recomputed_facts"]["interval_rows"])
    if len(rows) != expected_rows:
        raise ValueError(f"Tracker interval row count mismatch: expected {expected_rows}, found {len(rows)}")
    return {
        "columns": columns,
        "rows": rows,
        "source_semantics": "source-MET endpoint displacement rate between two saved raw fixes; wall time is a separate diagnostic alternative; no blending; no smoothing",
        "source_validation_status": validation["status"],
        "source_validation_checks": validation["check_count"],
        "source_summary_status": summary["status"],
        "hard_gaps_crossed": 0,
        "viewer_added_fields": [
            "source and wall ECEF XYZ endpoint displacement-rate components",
            "horizontal ENU speed and heading from validated east/north components",
            "interval horizontal tangent-plane displacement",
            "segment cumulative horizontal tangent-plane path reset at each raw segment",
        ],
    }


def build_telemetry(path: Path) -> dict[str, Any]:
    columns = [
        "tplus_s",
        "file_pts_s",
        "source_frame_index",
        "source_level",
        "window_id",
        "sample_rate_hz",
        "broadcast_clock_s",
        "layout",
        "vehicle_identity",
        "trajectory_object",
        "speed_kmh",
        "altitude_km",
        "speed_raw",
        "altitude_raw",
        "speed_confidence",
        "altitude_confidence",
        "altitude_display_status",
        "usable_speed",
        "usable_altitude",
        "review_status",
        "qc_flags",
    ]
    rows: list[list[Any]] = []
    for row in read_csv(path):
        rows.append(
            [
                number(row["measurement_time_s"], 3),
                number(row["file_pts_s"], 3),
                int(row["source_frame_index"]),
                row["source_level"],
                row["window_id"],
                number(row["sample_rate_hz"], 3),
                number(row["broadcast_clock_s"], 3),
                row["layout"],
                row["vehicle_identity"],
                row["trajectory_object"],
                number(row["speed_kmh"], 3),
                number(row["altitude_km"], 3),
                row["speed_raw"],
                row["altitude_raw"],
                number(row["speed_confidence"], 4),
                number(row["altitude_confidence"], 4),
                row["altitude_display_status"],
                boolean(row["usable_for_speed_inversion"]),
                boolean(row["usable_for_altitude_inversion"]),
                row["review_status"],
                row["qc_flags"],
            ]
        )
    return {"columns": columns, "rows": rows}


def build_object_telemetry(path: Path) -> dict[str, Any]:
    field_map = {
        "integrated_stack.speed_kmh": "stack_speed",
        "integrated_stack.altitude_km": "stack_altitude",
        "starship.speed_kmh": "starship_speed",
        "starship.altitude_km": "starship_altitude",
        "super_heavy.speed_kmh": "super_heavy_speed",
        "super_heavy.altitude_km": "super_heavy_altitude",
    }
    samples: dict[float, dict[str, Any]] = {}
    for row in read_csv(path):
        if row["source_product"] != "L1_1HZ" or not boolean(row["canonical_coverage_field"]):
            continue
        prefix = field_map.get(row["object_field"])
        if prefix is None:
            continue
        tplus = float(row["measurement_time_s"])
        sample = samples.setdefault(
            tplus,
            {
                "tplus_s": round(tplus, 3),
                "file_pts_s": number(row["file_pts_s"], 3),
                "source_frame_index": int(row["source_frame_index"]),
                "layout": row["layout_from_source"],
                "qc_flags": row["qc_flags_from_source"],
                "review_status": row["review_status_from_source"],
            },
        )
        sample[f"{prefix}_value"] = number(row["mode_gated_value"], 3)
        sample[f"{prefix}_raw"] = row["mode_gated_raw"]
        sample[f"{prefix}_confidence"] = number(row["mode_gated_confidence"], 4)
        sample[f"{prefix}_status"] = row["mode_gate_status"]
        sample[f"{prefix}_source"] = row["mode_gated_value_source"]

    prefixes = [
        "stack_speed",
        "stack_altitude",
        "starship_speed",
        "starship_altitude",
        "super_heavy_speed",
        "super_heavy_altitude",
    ]
    columns = ["tplus_s", "file_pts_s", "source_frame_index", "layout", "qc_flags", "review_status"]
    for prefix in prefixes:
        columns.extend([f"{prefix}_value", f"{prefix}_raw", f"{prefix}_confidence", f"{prefix}_status", f"{prefix}_source"])
    rows = [[sample.get(column) for column in columns] for _, sample in sorted(samples.items())]
    return {
        "columns": columns,
        "rows": rows,
        "source_semantics": "L1 canonical object fields from mode-gated numeric re-audit; no interpolation",
    }


def build_ring(path: Path) -> dict[str, Any]:
    mode_labels: list[str] = []
    mode_codes: dict[str, int] = {}

    def mode_code(label: str) -> int:
        if label not in mode_codes:
            mode_codes[label] = len(mode_labels)
            mode_labels.append(label)
        return mode_codes[label]

    left_mode: list[int] = []
    right_mode: list[int] = []
    left_confidence: list[int] = []
    right_confidence: list[int] = []
    left_bright: list[int] = []
    right_bright: list[int] = []
    booster_level: list[int] = []
    ship_level: list[int] = []
    booster_count: list[int] = []
    ship_count: list[int] = []
    frame_count = 0

    for expected_frame, row in enumerate(read_csv(path)):
        frame = int(row["source_frame_index"])
        if frame != expected_frame:
            raise ValueError(f"Ring table frame discontinuity: expected {expected_frame}, found {frame}")
        left_mode.append(mode_code(row["left_outer_mode"]))
        right_mode.append(mode_code(row["right_outer_mode"]))
        left_confidence.append(quantize_u8(row["left_mode_confidence"]))
        right_confidence.append(quantize_u8(row["right_mode_confidence"]))
        left_bright.append(quantize_u16(row["left_outer_bright_fraction"]))
        right_bright.append(quantize_u16(row["right_outer_bright_fraction"]))
        booster_level.append(quantize_u16(row["booster_relative_graphic_level_candidate"]))
        ship_level.append(quantize_u16(row["ship_relative_graphic_level_candidate"]))
        booster_count.append(count_u8(row["booster_active_engine_count_candidate"]))
        ship_count.append(count_u8(row["ship_active_engine_count_candidate"]))
        frame_count += 1

    return {
        "encoding": "little-endian typed arrays; base64",
        "length": frame_count,
        "fps": 30,
        "tplus_zero_frame": 210,
        "null_u16": UINT16_NULL,
        "null_u8": UINT8_NULL,
        "mode_labels": mode_labels,
        "arrays": {
            "left_mode_u8": encode_array(left_mode, "B"),
            "right_mode_u8": encode_array(right_mode, "B"),
            "left_confidence_u8": encode_array(left_confidence, "B"),
            "right_confidence_u8": encode_array(right_confidence, "B"),
            "left_bright_fraction_u16": encode_array(left_bright, "H"),
            "right_bright_fraction_u16": encode_array(right_bright, "H"),
            "booster_relative_level_u16": encode_array(booster_level, "H"),
            "ship_relative_level_u16": encode_array(ship_level, "H"),
            "booster_active_count_u8": encode_array(booster_count, "B"),
            "ship_active_count_u8": encode_array(ship_count, "B"),
        },
    }


def build_mass_schedule(path: Path) -> dict[str, Any]:
    """Pack only the saved icon schedule needed by the interactive scenario ledger.

    The cumulative icon-seconds are a mode-gated broadcast-derived candidate.  They
    are deliberately kept separate from thrust, Isp and mass assumptions, which
    remain editable in the viewer.
    """
    columns = [
        "tplus_s",
        "booster_active_count_candidate",
        "ship_active_count_candidate",
        "booster_engine_seconds_cumulative",
        "ship_engine_seconds_cumulative",
        "booster_full_second_eligible",
        "ship_full_second_eligible",
    ]
    rows: list[list[Any]] = []
    for row in read_csv(path):
        # The saved cumulative columns include the current one-second bin.  The
        # viewer reports state *at* nominal T+, so subtract that bin and expose
        # the cumulative icon-seconds at the bin start.  This keeps T+0 at the
        # full-load scenario instead of silently consuming the first second.
        booster_cumulative = number(row["booster_engine_seconds_cumulative"], 6)
        ship_cumulative = number(row["ship_engine_seconds_cumulative"], 6)
        booster_bin = number(row["booster_engine_seconds_in_bin"], 6)
        ship_bin = number(row["ship_engine_seconds_in_bin"], 6)
        booster_to_tplus = (
            round(max(0.0, booster_cumulative - booster_bin), 6)
            if booster_cumulative is not None and booster_bin is not None
            else None
        )
        ship_to_tplus = (
            round(max(0.0, ship_cumulative - ship_bin), 6)
            if ship_cumulative is not None and ship_bin is not None
            else None
        )
        rows.append(
            [
                number(row["nominal_tplus_s"], 3),
                number(row["booster_active_engine_count_candidate_at_anchor"], 0),
                number(row["ship_active_engine_count_candidate_at_anchor"], 0),
                booster_to_tplus,
                ship_to_tplus,
                boolean(row["booster_full_second_eligible"]),
                boolean(row["ship_full_second_eligible"]),
            ]
        )
    return {
        "columns": columns,
        "rows": rows,
        "semantics": "mode-gated broadcast icon-state candidate; cumulative values are evaluated at the nominal T+ bin start and use persistent-event gating that may be future-conditioned",
        "physical_engine_state_recovered": False,
        "physical_mass_recovered": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the compact Flight 13 timeline-viewer data bundle.")
    parser.add_argument(
        "--source-root",
        "--project-root",
        dest="source_root",
        type=Path,
        help="Research workspace containing data_processed/ and data_raw/. "
        "Defaults to FLIGHT13_SOURCE_ROOT.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    source_root_arg = args.source_root or os.environ.get("FLIGHT13_SOURCE_ROOT")
    if not source_root_arg:
        parser.error("--source-root or FLIGHT13_SOURCE_ROOT is required")
    project_root = Path(source_root_arg).resolve()
    output_path = args.output.resolve()
    paths = {
        "trajectory": project_root / "data_processed/flight13/public_tracker_trajectory_v1/Flight13_public_tracker_trajectory_v1.csv",
        "fixes": project_root / "data_processed/flight13/learning_evidence_3d_v0/Flight13_evidence_3d_raw_fixes_v0.csv",
        "telemetry": project_root / "data_processed/flight13/telemetry_fused_l1_l2_v1/Flight13_telemetry_fused_l1_l2_observations.csv",
        "telemetry_objects": project_root / "data_processed/flight13/video_observation_master_v1/numeric_mode_reaudit_v1/Flight13_numeric_mode_reaudit_long_v1.csv",
        "tracker_intervals": project_root / "data_processed/flight13/learning_kinematics_m2_v1/Flight13_learning_kinematics_m2_interval_average_v1.csv",
        "tracker_intervals_summary": project_root / "data_processed/flight13/learning_kinematics_m2_v1/Flight13_learning_kinematics_m2_v1_summary.json",
        "tracker_intervals_validation": project_root / "data_processed/flight13/learning_kinematics_m2_v1/validation.json",
        "ring": project_root / "data_processed/flight13/video_observation_master_v1/engine_propellant_observation_v1/Flight13_engine_propellant_observation_30hz_v1.csv",
        "mass_schedule": project_root / "data_processed/flight13/learning_baseline_v1/Flight13_learning_timeline_v1.csv",
        "video_manifest": project_root / "data_raw/flight13/Flight13_video_manifest.json",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing source files:\n" + "\n".join(missing))

    video_manifest = json.loads(paths["video_manifest"].read_text(encoding="utf-8"))
    bundle = {
        "schema_version": "flight13-timeline-viewer-data-v1.5",
        "interpretation": {
            "raw_tracker_is_truth": False,
            "dense_trajectory_is_observation": False,
            "ring_level_is_propellant_percentage": False,
            "tracker_and_hud_independent": False,
            "interval_kinematics_is_instantaneous_navigation_state": False,
            "interval_cumulative_horizontal_path_is_geodesic_downrange": False,
            "hud_body_axes_are_registered_to_ecef_or_enu": False,
            "engine_icon_is_physical_thrust_state": False,
            "mass_scenario_is_physical_mass_recovery": False,
        },
        "coordinate_systems": {
            "ecef": {
                "name": "WGS84 Earth-centered Earth-fixed",
                "semi_major_axis_m": 6378137.0,
                "inverse_flattening": 298.257223563,
                "x_axis": "equator at longitude 0 degrees",
                "y_axis": "equator at longitude 90 degrees east",
                "z_axis": "north pole",
                "velocity_semantics": "relative to the rotating Earth; not airspeed",
                "source_datum_caveat": "the reconstruction uses WGS84 geometry, but the public tracker datum and upstream filtering are not independently documented",
                "viewer_globe_geometry": "spherical display approximation only; screen coordinates are not ECEF",
            },
            "enu": {
                "name": "local East-North-Up",
                "origin": "geodetic midpoint of each allowed raw-fix interval",
                "axes": "E east, N north, U outward along the WGS84 ellipsoid normal",
                "scope": "one interval at a time; the basis rotates with location",
            },
            "hud_body": {
                "name": "HUD model body-axis display convention",
                "x_body": "nose/longitudinal; browser model +Y",
                "y_body": "right-handed transverse completion; browser model -Z",
                "z_body": "heatshield/belly side; browser model -X",
                "registration_to_ecef": "unresolved; the HUD renderer/camera-to-local-navigation transform has not been calibrated",
                "claim": "display candidate only, not physical attitude",
            },
        },
        "time": {
            "viewer_tplus_min_s": 0.0,
            "viewer_tplus_max_s": 3923.0,
            "video_tplus_zero_pts_s": VIDEO_TPLUS_ZERO_PTS_S,
            "video_fps": 30,
            "tracker_source_met_to_viewer_tplus_candidate_s": TRACKER_ALIGNMENT_CANDIDATE_S,
            "tracker_alignment_status": "candidate; absolute time not calibrated; channel delay confounded",
            "video_time_calibration_uncertainty_s": 0.5,
        },
        "video": {
            "route": "/video/flight13.mp4",
            "runtime_asset": "media/Flight13_web_720p.mp4",
            "reference_source": {
                "file_name": video_manifest["file"],
                "size_bytes": video_manifest["size_bytes"],
                "sha256": video_manifest["sha256"],
                "duration_s": video_manifest["duration_s"],
                "codec": video_manifest["video"]["codec"],
                "width": video_manifest["video"]["width"],
                "height": video_manifest["video"]["height"],
            },
            "runtime_asset_note": "The server may use a separately encoded 720p proxy; runtime bytes are reported by /health.json, not by this source manifest.",
        },
        "source_paths": {
            key: path.relative_to(project_root).as_posix() for key, path in paths.items()
        },
        "source_sha256": {key: sha256_file(path) for key, path in paths.items()},
        "trajectory": build_trajectory(paths["trajectory"]),
        "fixes": build_fixes(paths["fixes"]),
        "tracker_intervals": build_tracker_intervals(
            paths["tracker_intervals"],
            paths["tracker_intervals_summary"],
            paths["tracker_intervals_validation"],
        ),
        "telemetry": build_telemetry(paths["telemetry"]),
        "telemetry_objects": build_object_telemetry(paths["telemetry_objects"]),
        "ring": build_ring(paths["ring"]),
        "mass_schedule": build_mass_schedule(paths["mass_schedule"]),
    }

    encoded = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(encoded)
    gzip_path = output_path.with_suffix(output_path.suffix + ".gz")
    gzip_path.write_bytes(gzip.compress(encoded, compresslevel=6, mtime=0))
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(output_path),
                "bytes": len(encoded),
                "gzip_output": str(gzip_path),
                "gzip_bytes": gzip_path.stat().st_size,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
