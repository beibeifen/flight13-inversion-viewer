from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import math
from array import array
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
T_MAX = 3923
FPS = 30
PTS_ZERO = 7
RING_LENGTH = (T_MAX + PTS_ZERO) * FPS + 1
NULL_U8 = 255
NULL_U16 = 65535
MODE_LABELS = [
    "outside_flight_scope_unassigned",
    "mode_transition_or_not_visible",
    "booster_engine_array",
    "ship_engine_array",
    "speed_numeric",
    "altitude_numeric",
    "attitude_globe",
]


def table(columns: list[str], rows: list[list[Any]], **metadata: Any) -> dict[str, Any]:
    return {"columns": columns, "rows": rows, **metadata}


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def trajectory_state(t: float) -> tuple[float, float, float]:
    if t <= 520:
        progress = smoothstep(t / 520)
        latitude = 25.997 - 8.6 * progress
        longitude = -97.158 + 16.0 * progress
        altitude = 185.0 * progress
    else:
        progress = smoothstep((t - 520) / (T_MAX - 520))
        latitude = 17.397 - 34.9 * progress
        longitude = -81.158 + 187.9 * progress
        altitude = 185.0 * (1.0 - progress)
    return latitude, longitude, max(0.05, altitude)


def ecef(latitude: float, longitude: float, altitude_km: float) -> tuple[float, float, float]:
    radius = 6_378_137.0 + altitude_km * 1000.0
    lat = math.radians(latitude)
    lon = math.radians(longitude)
    return (
        radius * math.cos(lat) * math.cos(lon),
        radius * math.cos(lat) * math.sin(lon),
        radius * math.sin(lat),
    )


def build_trajectory() -> dict[str, Any]:
    columns = [
        "tplus_s", "file_pts_s", "tracker_source_met_s", "ecef_x_m", "ecef_y_m",
        "ecef_z_m", "latitude_deg", "longitude_deg", "ellipsoid_altitude_km",
        "ecef_vx_mps", "ecef_vy_mps", "ecef_vz_mps",
        "ecef_ax_mps2", "ecef_ay_mps2", "ecef_az_mps2", "ecef_speed_kmh",
        "east_velocity_mps", "north_velocity_mps", "vertical_velocity_mps",
        "ground_speed_kmh", "heading_deg", "flight_path_angle_deg",
        "distance_from_pad_km", "phase_label", "derivative_quality_code",
    ]
    positions = {t: trajectory_state(t) for t in range(T_MAX + 1)}
    ecef_positions = {t: ecef(*position) for t, position in positions.items()}
    rows: list[list[Any]] = []
    pad_lat, pad_lon, _ = positions[0]
    for t in range(T_MAX + 1):
        left = positions[max(0, t - 1)]
        right = positions[min(T_MAX, t + 1)]
        dt = 1 if t in {0, T_MAX} else 2
        left_ecef = ecef_positions[max(0, t - 1)]
        center_ecef = ecef_positions[t]
        right_ecef = ecef_positions[min(T_MAX, t + 1)]
        velocity = tuple((right_ecef[i] - left_ecef[i]) / dt for i in range(3))
        if t == 0:
            second_difference = (
                ecef_positions[0], ecef_positions[1], ecef_positions[2]
            )
        elif t == T_MAX:
            second_difference = (
                ecef_positions[T_MAX - 2],
                ecef_positions[T_MAX - 1],
                ecef_positions[T_MAX],
            )
        else:
            second_difference = (left_ecef, center_ecef, right_ecef)
        acceleration = tuple(
            second_difference[2][i]
            - 2 * second_difference[1][i]
            + second_difference[0][i]
            for i in range(3)
        )
        speed = math.sqrt(sum(component * component for component in velocity))
        lat, lon, altitude = positions[t]
        dlat = math.radians(right[0] - left[0])
        dlon = math.radians(right[1] - left[1])
        north = dlat * 6_371_000 / dt
        east = dlon * 6_371_000 * math.cos(math.radians(lat)) / dt
        up = (right[2] - left[2]) * 1000 / dt
        ground = math.hypot(east, north)
        heading = (math.degrees(math.atan2(east, north)) + 360) % 360
        gamma = math.degrees(math.atan2(up, max(ground, 1e-9)))
        pad_dlat = math.radians(lat - pad_lat)
        pad_dlon = math.radians(lon - pad_lon)
        a = math.sin(pad_dlat / 2) ** 2 + math.cos(math.radians(pad_lat)) * math.cos(math.radians(lat)) * math.sin(pad_dlon / 2) ** 2
        distance = 2 * 6_371 * math.asin(min(1.0, math.sqrt(a)))
        x, y, z = ecef(lat, lon, altitude)
        rows.append([
            float(t), float(t + PTS_ZERO), float(t), round(x, 3), round(y, 3), round(z, 3),
            round(lat, 6), round(lon, 6), round(altitude, 4),
            round(velocity[0], 3), round(velocity[1], 3), round(velocity[2], 3),
            round(acceleration[0], 6), round(acceleration[1], 6), round(acceleration[2], 6),
            round(speed * 3.6, 2), round(east, 3), round(north, 3), round(up, 3),
            round(ground * 3.6, 2), round(heading, 3), round(gamma, 3), round(distance, 3),
            "synthetic_ascent" if t < 520 else "synthetic_coast_and_entry", "synthetic_demo",
        ])
    return table(columns, rows, source_semantics="synthetic demonstrator; not Flight 13 observation")


def build_fixes(trajectory: dict[str, Any]) -> dict[str, Any]:
    columns = [
        "record_index", "aligned_tplus_s", "wall_tplus_s", "source_met_s", "video_pts_s",
        "latitude_deg", "longitude_deg", "source_altitude_m", "trajectory_version",
        "phase_label", "segment_id", "source_role", "gap_class", "dt_previous_s",
    ]
    lookup = {int(row[0]): row for row in trajectory["rows"]}
    times = list(range(0, T_MAX + 1, 60))
    if times[-1] != T_MAX:
        times.append(T_MAX)
    rows = []
    for index, t in enumerate(times, 1):
        sample = lookup[t]
        rows.append([
            index, float(t), float(t), float(t), float(t + PTS_ZERO), sample[6], sample[7],
            round(sample[8] * 1000, 1), 1, sample[23], "synthetic_segment_01",
            "synthetic_demo_anchor", "first" if index == 1 else "regular", None if index == 1 else float(t - times[index - 2]),
        ])
    return table(columns, rows, source_semantics="synthetic demo anchors")


def build_intervals(trajectory: dict[str, Any]) -> dict[str, Any]:
    columns = [
        "interval_id", "segment_id", "left_record_index", "right_record_index", "start_tplus_s", "end_tplus_s",
        "mid_tplus_s", "dt_source_s", "dt_wall_s", "time_basis_difference_ms", "mid_latitude_deg", "mid_longitude_deg",
        "mid_altitude_km", "mid_ecef_x_m", "mid_ecef_y_m", "mid_ecef_z_m", "avg_ecef_vx_mps", "avg_ecef_vy_mps",
        "avg_ecef_vz_mps", "avg_ecef_speed_kmh", "avg_ground_speed_kmh", "avg_climb_rate_mps", "avg_heading_deg",
        "avg_east_mps", "avg_north_mps", "wall_avg_ecef_vx_mps", "wall_avg_ecef_vy_mps", "wall_avg_ecef_vz_mps",
        "wall_avg_ecef_speed_kmh", "wall_avg_ground_speed_kmh", "wall_avg_climb_rate_mps", "interval_horizontal_displacement_km",
        "segment_cumulative_horizontal_start_km", "segment_cumulative_horizontal_end_km", "future_conditioned", "result_level",
    ]
    lookup = {int(row[0]): row for row in trajectory["rows"]}
    rows: list[list[Any]] = []
    cumulative = 0.0
    for index, start in enumerate(range(0, T_MAX, 10), 1):
        end = min(T_MAX + 0.001, start + 10)
        mid = min(T_MAX, start + 5)
        sample = lookup[mid]
        displacement = sample[19] / 3.6 * (end - start) / 1000
        rows.append([
            f"synthetic_interval_{index:03d}", "synthetic_segment_01", index, index + 1, float(start), float(end), float(mid),
            float(end - start), float(end - start), 0.0, sample[6], sample[7], sample[8], sample[3], sample[4], sample[5],
            sample[9], sample[10], sample[11], sample[15], sample[19], sample[18], sample[20], sample[16], sample[17],
            sample[9], sample[10], sample[11], sample[15], sample[19], sample[18], round(displacement, 4), round(cumulative, 4),
            round(cumulative + displacement, 4), False, "SYNTHETIC_DEMO",
        ])
        cumulative += displacement
    return table(
        columns, rows, source_semantics="synthetic interval kinematics for public UI demonstration",
        source_validation_status="SYNTHETIC_DEMO", source_validation_checks=0,
        source_summary_status="SYNTHETIC_DEMO", hard_gaps_crossed=0, viewer_added_fields=[],
    )


def build_telemetry(trajectory: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    telemetry_columns = [
        "tplus_s", "file_pts_s", "source_frame_index", "source_level", "window_id", "sample_rate_hz", "broadcast_clock_s",
        "layout", "vehicle_identity", "trajectory_object", "speed_kmh", "altitude_km", "speed_raw", "altitude_raw",
        "speed_confidence", "altitude_confidence", "altitude_display_status", "usable_speed", "usable_altitude", "review_status", "qc_flags",
    ]
    object_columns = [
        "tplus_s", "file_pts_s", "source_frame_index", "layout", "qc_flags", "review_status",
        "stack_speed_value", "stack_speed_raw", "stack_speed_confidence", "stack_speed_status", "stack_speed_source",
        "stack_altitude_value", "stack_altitude_raw", "stack_altitude_confidence", "stack_altitude_status", "stack_altitude_source",
        "starship_speed_value", "starship_speed_raw", "starship_speed_confidence", "starship_speed_status", "starship_speed_source",
        "starship_altitude_value", "starship_altitude_raw", "starship_altitude_confidence", "starship_altitude_status", "starship_altitude_source",
        "super_heavy_speed_value", "super_heavy_speed_raw", "super_heavy_speed_confidence", "super_heavy_speed_status", "super_heavy_speed_source",
        "super_heavy_altitude_value", "super_heavy_altitude_raw", "super_heavy_altitude_confidence", "super_heavy_altitude_status", "super_heavy_altitude_source",
    ]
    telemetry_rows, object_rows = [], []
    for sample in trajectory["rows"]:
        t = int(sample[0])
        speed, altitude = sample[15], sample[8]
        identity = "integrated_stack" if t <= 175 else "starship"
        layout = "integrated_stack_right" if t <= 175 else "starship_left"
        telemetry_rows.append([
            float(t), float(t + PTS_ZERO), (t + PTS_ZERO) * FPS, "synthetic", "synthetic_1hz", 1.0, float(t), layout,
            identity, identity, speed, altitude, f"{speed:.0f}", f"{altitude:.1f}", 1.0, 1.0, "synthetic_demo",
            True, True, "synthetic_demo", "SYNTHETIC_NOT_OBSERVED",
        ])
        missing = [None, "", None, "not_displayed", ""]
        stack = [speed, f"{speed:.0f}", 1.0, "synthetic_demo", "generated"] if t <= 175 else missing
        stack_alt = [altitude, f"{altitude:.1f}", 1.0, "synthetic_demo", "generated"] if t <= 175 else missing
        ship = [speed, f"{speed:.0f}", 1.0, "synthetic_demo", "generated"] if t > 175 else missing
        ship_alt = [altitude, f"{altitude:.1f}", 1.0, "synthetic_demo", "generated"] if t > 175 else missing
        object_rows.append([
            float(t), float(t + PTS_ZERO), (t + PTS_ZERO) * FPS, layout, "SYNTHETIC_NOT_OBSERVED", "synthetic_demo",
            *stack, *stack_alt, *ship, *ship_alt, *missing, *missing,
        ])
    return table(telemetry_columns, telemetry_rows), table(object_columns, object_rows, source_semantics="synthetic public demo")


def build_mass_schedule() -> dict[str, Any]:
    columns = [
        "tplus_s", "booster_active_count_candidate", "ship_active_count_candidate", "booster_engine_seconds_cumulative",
        "ship_engine_seconds_cumulative", "booster_full_second_eligible", "ship_full_second_eligible",
    ]
    rows = []
    booster_seconds = ship_seconds = 0
    for t in range(T_MAX + 1):
        booster = 33 if t <= 175 else 10 if 385 <= t <= 422 else None
        ship = 6 if 142 <= t <= 485 else 1 if 2340 <= t <= 2355 else 3 if 3902 <= t <= 3922 else None
        rows.append([float(t), booster, ship, float(booster_seconds), float(ship_seconds), booster is not None, ship is not None])
        booster_seconds += booster or 0
        ship_seconds += ship or 0
    return table(columns, rows, semantics="synthetic engine-icon schedule for public demonstration", physical_engine_state_recovered=False, physical_mass_recovered=False)


def encode_u8(values: list[int]) -> str:
    return base64.b64encode(bytes(values)).decode("ascii")


def encode_u16(values: list[int]) -> str:
    payload = array("H", values)
    if payload.itemsize != 2:
        raise RuntimeError("Unexpected unsigned-short width")
    return base64.b64encode(payload.tobytes()).decode("ascii")


def build_ring() -> dict[str, Any]:
    left_mode = [1] * RING_LENGTH
    right_mode = [1] * RING_LENGTH
    left_confidence = [NULL_U8] * RING_LENGTH
    right_confidence = [NULL_U8] * RING_LENGTH
    left_bright = [NULL_U16] * RING_LENGTH
    right_bright = [NULL_U16] * RING_LENGTH
    booster_level = [NULL_U16] * RING_LENGTH
    ship_level = [NULL_U16] * RING_LENGTH
    booster_count = [NULL_U8] * RING_LENGTH
    ship_count = [NULL_U8] * RING_LENGTH

    for frame in range(RING_LENGTH):
        t = frame / FPS - PTS_ZERO
        if t < 0 or t > T_MAX:
            continue
        if t <= 175 or 385 <= t <= 422:
            left_mode[frame] = 2
            left_confidence[frame] = 250
            booster_count[frame] = 33 if t < 138 else 13 if t < 155 else 3 if t < 168 else 1 if t <= 175 else 10 if t < 395 else 5
            level = 1 - 0.72 * smoothstep(min(t, 175) / 175)
            if 385 <= t <= 422:
                level = 0.28 - 0.22 * smoothstep((t - 385) / 37)
            booster_level[frame] = round(max(0, min(1, level)) * (NULL_U16 - 1))
            left_bright[frame] = booster_level[frame]
        if 142 <= t <= 485 or 2340 <= t <= 2355 or 3902 <= t <= 3922:
            right_mode[frame] = 3
            right_confidence[frame] = 250
            ship_count[frame] = 6 if t <= 485 else 1 if t <= 2355 else 3 if t < 3910 else 1
            if t <= 485:
                level = 1 - 0.63 * smoothstep((t - 142) / 343)
            elif t <= 2355:
                level = 0.37 - 0.03 * smoothstep((t - 2340) / 15)
            else:
                level = 0.34 - 0.28 * smoothstep((t - 3902) / 20)
            ship_level[frame] = round(max(0, min(1, level)) * (NULL_U16 - 1))
            right_bright[frame] = ship_level[frame]

    return {
        "encoding": "base64 little-endian typed arrays; synthetic public demo",
        "length": RING_LENGTH,
        "fps": FPS,
        "tplus_zero_frame": PTS_ZERO * FPS,
        "null_u16": NULL_U16,
        "null_u8": NULL_U8,
        "mode_labels": MODE_LABELS,
        "arrays": {
            "left_mode_u8": encode_u8(left_mode), "right_mode_u8": encode_u8(right_mode),
            "left_confidence_u8": encode_u8(left_confidence), "right_confidence_u8": encode_u8(right_confidence),
            "left_bright_fraction_u16": encode_u16(left_bright), "right_bright_fraction_u16": encode_u16(right_bright),
            "booster_relative_level_u16": encode_u16(booster_level), "ship_relative_level_u16": encode_u16(ship_level),
            "booster_active_count_u8": encode_u8(booster_count), "ship_active_count_u8": encode_u8(ship_count),
        },
    }


def build_bundle() -> dict[str, Any]:
    trajectory = build_trajectory()
    telemetry, telemetry_objects = build_telemetry(trajectory)
    return {
        "schema_version": "flight13-timeline-viewer-data-v1.5-public-demo",
        "distribution": {
            "profile": "public_synthetic_demo",
            "contains_flight_observations": False,
            "notice": "All displayed mission data in this bundle are synthetic and exist only to exercise the public UI.",
        },
        "interpretation": {
            "raw_tracker_is_truth": False, "dense_trajectory_is_observation": False,
            "ring_level_is_propellant_percentage": False, "tracker_and_hud_independent": False,
            "interval_kinematics_is_instantaneous_navigation_state": False,
            "interval_cumulative_horizontal_path_is_geodesic_downrange": False,
            "hud_body_axes_are_registered_to_ecef_or_enu": False,
            "engine_icon_is_physical_thrust_state": False, "mass_scenario_is_physical_mass_recovery": False,
        },
        "coordinate_systems": {"ecef": {"name": "synthetic WGS84-compatible demo"}, "enu": {"name": "synthetic local East-North-Up demo"}, "hud_body": {"name": "display convention only"}},
        "time": {"viewer_tplus_min_s": 0.0, "viewer_tplus_max_s": float(T_MAX), "video_tplus_zero_pts_s": float(PTS_ZERO), "video_fps": FPS, "tracker_source_met_to_viewer_tplus_candidate_s": 0.0, "tracker_alignment_status": "synthetic demo", "video_time_calibration_uncertainty_s": None},
        "video": {"route": "/video/flight13.mp4", "runtime_asset": "media/Flight13_web_720p.mp4", "reference_source": None, "runtime_asset_note": "A user-supplied local video is optional and is not distributed with the public repository."},
        "source_paths": {}, "source_sha256": {},
        "trajectory": trajectory,
        "fixes": build_fixes(trajectory),
        "tracker_intervals": build_intervals(trajectory),
        "telemetry": telemetry,
        "telemetry_objects": telemetry_objects,
        "ring": build_ring(),
        "mass_schedule": build_mass_schedule(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the rights-clean synthetic public demo bundle.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "app")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(build_bundle(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    json_path = args.output_dir / "viewer-data.json"
    gzip_path = args.output_dir / "viewer-data.json.gz"
    json_path.write_bytes(raw)
    gzip_path.write_bytes(gzip.compress(raw, compresslevel=6, mtime=0))
    print(f"Wrote {json_path} ({len(raw):,} bytes, sha256={hashlib.sha256(raw).hexdigest()})")
    print(f"Wrote {gzip_path} ({gzip_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
