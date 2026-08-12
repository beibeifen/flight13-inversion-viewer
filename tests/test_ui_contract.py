from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class UiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (REPO_ROOT / "app" / "index.html").read_text(encoding="utf-8-sig")
        cls.js = (REPO_ROOT / "app" / "assets" / "app.js").read_text(encoding="utf-8")
        cls.css = (REPO_ROOT / "app" / "assets" / "app.css").read_text(encoding="utf-8")

    def test_main_document_uses_external_assets(self) -> None:
        self.assertIn('src="/assets/theme.js"', self.html)
        self.assertIn('href="/assets/app.css"', self.html)
        self.assertIn('src="/assets/app.js"', self.html)
        self.assertNotRegex(self.html, r"<style(?:\s|>)")
        inline_scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", self.html)
        self.assertEqual(inline_scripts, [])

    def test_absolute_mass_inputs_and_defaults(self) -> None:
        expectations = {
            "massInitialTotal": "4929",
            "massBoosterWeight": "73.2603",
            "massBoosterDry": "311",
            "massShipDry": "118",
        }
        for input_id, default in expectations.items():
            pattern = rf'<input\s+id="{input_id}"[^>]*\btype="number"[^>]*\bvalue="{default}"'
            self.assertRegex(self.html, pattern)
        self.assertIn("initialTotal: 3300 + 311 + 1200 + 118", self.js)
        self.assertIn("boosterWeight: (3300 + 311) / 4929", self.js)

    def test_mass_formula_is_stage_separable_and_tonne_scaled(self) -> None:
        self.assertIn("const propellant = initial - dry", self.js)
        self.assertIn("const value = dry + propellant * level", self.js)
        self.assertIn("M<sub>B</sub>(t) = D<sub>B</sub>", self.html)
        self.assertIn("M<sub>S</sub>(t) = D<sub>S</sub>", self.html)
        self.assertIn("M<sub>Σ</sub>(t)", self.html)
        self.assertNotIn("q<sub>B</sub>(t) + q<sub>S</sub>(t)", self.html)
        self.assertNotIn("100 单位", self.html + self.js)
        self.assertNotIn("归一质量", self.html + self.js)
        self.assertNotIn("normalizedMass", self.js)

    def test_mass_input_constraints_are_coupled(self) -> None:
        self.assertIn("const boosterInitial = boosterWeight * initialTotal", self.js)
        self.assertIn("const shipInitial = (1 - boosterWeight) * initialTotal", self.js)
        self.assertIn("boosterDry: clamp(raw.boosterDry, 0, boosterInitial)", self.js)
        self.assertIn("shipDry: clamp(raw.shipDry, 0, shipInitial)", self.js)

    def test_provenance_is_visible(self) -> None:
        footer = re.search(r'<footer class="lean-footer"([^>]*)>(.*?)</footer>', self.html, re.S)
        self.assertIsNotNone(footer)
        self.assertNotIn("hidden", footer.group(1))
        self.assertIn("合成演示数据", footer.group(2))
        self.assertIn("不含 Flight 13 第三方轨迹", footer.group(2))
        self.assertIn("CC BY 4.0", footer.group(2))

    def test_hud_and_data_routes_are_present(self) -> None:
        self.assertRegex(self.html, r'src="/hud/index\.html\?embed=1(?:&amp;|&)t=0"')
        self.assertIn('fetch("/viewer-data.json"', self.js)

    def test_repo_does_not_embed_local_user_paths(self) -> None:
        for path in (REPO_ROOT / "app").rglob("*"):
            if not path.is_file() or path.suffix in {".jpg", ".png", ".gz"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            self.assertNotIn("C:\\Users\\", text, str(path))

    def test_public_ui_does_not_reference_broadcast_frames(self) -> None:
        hud_html = (REPO_ROOT / "app" / "hud" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("reference-stack-", hud_html)
        self.assertNotIn("reference-ship-", hud_html)
        self.assertNotIn("hud-visual-cues.json", hud_html)
        self.assertEqual(list((REPO_ROOT / "app").rglob("*.jpg")), [])
        self.assertNotIn("R²", self.html)
        self.assertIn("q<sub>B</sub>(t)、q<sub>S</sub>(t) 为合成序列", self.html)


if __name__ == "__main__":
    unittest.main()
