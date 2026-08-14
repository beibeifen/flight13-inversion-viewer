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
        cls.hud = (REPO_ROOT / "app" / "hud" / "index.html").read_text(encoding="utf-8")

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
        self.assertIn("圆弧比例 → 外给端点之间的条件质量", self.html)
        self.assertNotIn("q<sub>B</sub>(t) + q<sub>S</sub>(t)", self.html)
        self.assertNotIn("100 单位", self.html + self.js)
        self.assertNotIn("归一质量", self.html + self.js)
        self.assertNotIn("normalizedMass", self.js)

    def test_mass_input_constraints_are_coupled(self) -> None:
        self.assertIn("const boosterInitial = boosterWeight * initialTotal", self.js)
        self.assertIn("const shipInitial = (1 - boosterWeight) * initialTotal", self.js)
        self.assertIn("boosterDry: clamp(raw.boosterDry, 0, boosterInitial)", self.js)
        self.assertIn("shipDry: clamp(raw.shipDry, 0, shipInitial)", self.js)

    def test_obsolete_mass_dependent_thrust_display_is_removed(self) -> None:
        self.assertNotIn('id="boosterThrustValue"', self.html)
        self.assertNotIn('id="shipThrustValue"', self.html)
        self.assertNotIn("SIMPLE_AERO_MODEL", self.js)
        self.assertNotIn("function atmosphereDensityAt", self.js)
        self.assertNotIn("function trajectoryDynamicsAt", self.js)
        self.assertNotIn("function simplifiedThrustForMass", self.js)
        self.assertNotIn("function simplifiedThrustAt", self.js)
        self.assertNotIn("T̂(t) = ‖F̂<sub>T</sub>(t)‖", self.html)
        self.assertNotIn('class="panel formula-panel"', self.html)
        self.assertIn("不是动力学反演，不输出推力", self.html)

    def test_mass_chart_has_synchronized_time_range(self) -> None:
        self.assertRegex(self.html, r'<input id="massTimeRange" type="range" min="0" max="3923"')
        self.assertIn('const massRange = $("massTimeRange")', self.js)
        self.assertIn('bindTimeRange(range)', self.js)
        self.assertIn('bindTimeRange(massRange)', self.js)
        self.assertIn('state.draggingRange !== "massTimeRange"', self.js)

    def test_rated_thrust_inversion_is_an_independent_board(self) -> None:
        self.assertIn("用发动机推力反推飞行中的质量", self.html)
        self.assertIn('id="ratedEngineCountValue"', self.html)
        self.assertIn('id="ratedSpeedValue"', self.html)
        self.assertIn('id="ratedAltitudeValue"', self.html)
        self.assertIn('id="ratedMassCanvas"', self.html)
        self.assertIn('id="ratedMassTimeRange"', self.html)
        self.assertIn("下方反演不读取本板块任何质量", self.html)
        self.assertNotIn("这是什么？", self.html)
        self.assertNotIn("技术细节：", self.html)
        self.assertIn("function ratedMassInversionAt", self.js)
        self.assertIn("function ratedSensitivityAt", self.js)
        self.assertIn("function buildRatedMassSeries", self.js)
        self.assertIn("function standardAtmosphere1976At", self.js)
        self.assertIn("function ratedThrustAt", self.js)
        rated_start = self.js.index("function ratedMassInversionAt")
        rated_end = self.js.index("function buildRatedMassSeries", rated_start)
        rated_solver = self.js[rated_start:rated_end]
        self.assertNotIn("absoluteMassAt", rated_solver)
        self.assertNotIn("simplifiedThrustAt", rated_solver)
        self.assertNotIn("simplifiedThrustForMass", rated_solver)
        self.assertNotIn("state.massParameters", rated_solver)

    def test_rated_inversion_inputs_windows_and_uncertainty_are_explicit(self) -> None:
        defaults = {
            "ratedBoosterSeaLevelTf": "8240",
            "ratedRaptorSeaLevelTf": "250",
            "ratedRaptorVacuumTf": "275",
            "ratedThrustUncertainty": "3",
            "ratedRaptorDiameter": "1.3",
            "ratedRaptorVacuumDiameter": "2.3",
            "ratedVehicleDiameter": "9",
            "ratedCdUncertainty": "25",
        }
        for input_id, default in defaults.items():
            self.assertRegex(self.html, rf'<input id="{input_id}"[^>]*value="{default}"')
        self.assertIn('start: 2, end: 114, vehicle: "stack"', self.js)
        self.assertIn('start: 192, end: 334, vehicle: "ship"', self.js)
        self.assertIn('start: 388, end: 468, vehicle: "ship"', self.js)
        self.assertIn("trajectory.ecef_ax_mps2", self.js)
        self.assertNotIn("beforeVelocity", self.js)
        self.assertNotIn("primaryHalfWindowS", self.js)
        self.assertIn("alignmentOffsetsS: Object.freeze([-1.56, 0, 1.04])", self.js)
        self.assertIn("cdUncertaintyFraction", self.js)
        self.assertIn("thrustUncertaintyFraction", self.js)

    def test_rated_inversion_gates_unsupported_phases(self) -> None:
        for phrase in [
            "定位缺口 / 热分离 / 分离事件：必须留空",
            "分离后 Booster 无独立三维轨迹",
            "滑行、短时再点火、再入和着陆均不反演",
        ]:
            self.assertIn(phrase, self.js)
        self.assertNotIn("推力方向诊断", self.html)
        self.assertNotIn("不是发动机云台角", self.html)

    def test_rated_mass_time_range_is_synchronized(self) -> None:
        self.assertIn('const ratedMassRange = $("ratedMassTimeRange")', self.js)
        self.assertIn("bindTimeRange(ratedMassRange)", self.js)
        self.assertIn('state.draggingRange !== "ratedMassTimeRange"', self.js)
        self.assertIn("updateRatedInversion(t)", self.js)
        self.assertIn("seekTplus(Number(button.dataset.ratedSeek))", self.js)
        self.assertRegex(self.html, r'<input id="ratedMassTimeRange" type="range" min="0" max="500"')
        self.assertIn('#timeRange, #massTimeRange, #ratedMassTimeRange', self.css)
        self.assertIn('value="60"', self.html)
        self.assertIn('data-rated-seek="60"', self.html)
        self.assertIn('data-rated-seek="250"', self.html)
        self.assertIn('data-rated-seek="420"', self.html)

    def test_hud_velocity_card_uses_instantaneous_reconstructed_trajectory(self) -> None:
        self.assertIn("const trajectory = state.data ? trajectoryAt(t) : null", self.js)
        self.assertIn('semantics: "conditional_trajectory_instantaneous"', self.js)
        self.assertIn("east_mps: trajectory.east_velocity_mps", self.js)
        self.assertNotIn('semantics: "raw_interval_mean"', self.js)
        self.assertIn("瞬时速度（地固 ENU）", self.hud)
        self.assertIn("条件轨迹 · 瞬时速度", self.hud)
        self.assertIn("跨定位空档 · 瞬时重建", self.hud)
        self.assertNotIn("无有效 raw-fix 区间", self.hud)

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
