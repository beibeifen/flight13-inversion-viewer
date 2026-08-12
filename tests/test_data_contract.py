from __future__ import annotations

import gzip
import json
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = REPO_ROOT / "app" / "viewer-data.json"


class FrozenDataContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = DATA_PATH.read_bytes()
        cls.data = json.loads(cls.raw)

    def test_bundle_schema_and_interpretation_boundaries(self) -> None:
        self.assertEqual(
            self.data["schema_version"],
            "flight13-timeline-viewer-data-v1.4-public-demo",
        )
        self.assertEqual(self.data["distribution"]["profile"], "public_synthetic_demo")
        self.assertFalse(self.data["distribution"]["contains_flight_observations"])
        self.assertTrue(self.data["interpretation"])
        self.assertTrue(all(value is False for value in self.data["interpretation"].values()))
        self.assertNotIn("mass_scenario_defaults", self.data)

    def test_source_provenance_is_relative_and_hash_traced(self) -> None:
        paths = self.data["source_paths"]
        hashes = self.data["source_sha256"]
        self.assertEqual(set(paths), set(hashes))
        for key, path in paths.items():
            self.assertFalse(Path(path).is_absolute(), key)
            self.assertNotIn("\\", path)
            self.assertNotRegex(path, r"^[A-Za-z]:")
            self.assertRegex(hashes[key], r"^[0-9a-f]{64}$")

    def test_frozen_table_shapes(self) -> None:
        column_counts = {
            "trajectory": 22,
            "fixes": 14,
            "tracker_intervals": 36,
            "telemetry": 21,
            "telemetry_objects": 36,
            "mass_schedule": 7,
        }
        for name, column_count in column_counts.items():
            table = self.data[name]
            self.assertEqual(len(table["columns"]), column_count, name)
            self.assertGreater(len(table["rows"]), 0, name)
            self.assertTrue(
                all(len(row) == column_count for row in table["rows"]), name
            )

    def test_tracker_interval_semantics_are_explicit(self) -> None:
        intervals = self.data["tracker_intervals"]
        self.assertEqual(intervals["hard_gaps_crossed"], 0)
        self.assertIn("synthetic", intervals["source_semantics"])
        self.assertEqual(intervals["source_validation_status"], "SYNTHETIC_DEMO")

    def test_ring_payload_shape(self) -> None:
        ring = self.data["ring"]
        self.assertEqual(ring["length"], 117901)
        self.assertEqual(ring["fps"], 30)
        self.assertEqual(
            set(ring["arrays"]),
            {
                "left_mode_u8",
                "right_mode_u8",
                "left_confidence_u8",
                "right_confidence_u8",
                "left_bright_fraction_u16",
                "right_bright_fraction_u16",
                "booster_relative_level_u16",
                "ship_relative_level_u16",
                "booster_active_count_u8",
                "ship_active_count_u8",
            },
        )

    def test_video_reference_does_not_claim_runtime_identity(self) -> None:
        video = self.data["video"]
        self.assertEqual(video["route"], "/video/flight13.mp4")
        self.assertEqual(video["runtime_asset"], "media/Flight13_web_720p.mp4")
        self.assertIsNone(video["reference_source"])
        self.assertIn("not distributed", video["runtime_asset_note"])

    def test_public_bundle_has_no_private_observation_provenance(self) -> None:
        serialized = self.raw.decode("utf-8")
        self.assertNotIn("StarDash", serialized)
        self.assertNotIn("public_tracker_trajectory", serialized)
        self.assertNotIn("data_raw/flight13", serialized)
        self.assertEqual(self.data["source_paths"], {})
        self.assertEqual(self.data["source_sha256"], {})

    def test_precompressed_bundle_is_exact(self) -> None:
        compressed = DATA_PATH.with_suffix(".json.gz").read_bytes()
        self.assertEqual(gzip.decompress(compressed), self.raw)


if __name__ == "__main__":
    unittest.main()
