(() => {
      "use strict";
      const $ = (id) => document.getElementById(id);
      const video = $("sourceVideo");
      const range = $("timeRange");
      const massRange = $("massTimeRange");
      const timeInput = $("timeInput");
      const globe = $("globeCanvas");
      const timeline = $("timelineCanvas");
      const hudFrame = $("hudFrame");
      const absoluteMassCanvas = $("absoluteMassCanvas");
      const ratedMassRange = $("ratedMassTimeRange");
      const ratedMassCanvas = $("ratedMassCanvas");
      const gctx = globe.getContext("2d");
      const tctx = timeline.getContext("2d");
      const mctx = absoluteMassCanvas.getContext("2d");
      const rmctx = ratedMassCanvas.getContext("2d");
      const DEFAULT_MASS_PARAMETERS = Object.freeze({
        initialTotal: 3300 + 311 + 1200 + 118,
        boosterWeight: (3300 + 311) / 4929,
        boosterDry: 311,
        shipDry: 118,
      });
      const DEFAULT_RATED_PARAMETERS = Object.freeze({
        boosterSeaLevelTf: 8240,
        raptorSeaLevelTf: 250,
        raptorVacuumTf: 275,
        thrustUncertaintyFraction: 0.03,
        raptorDiameterM: 1.3,
        raptorVacuumDiameterM: 2.3,
        vehicleDiameterM: 9,
        cdUncertaintyFraction: 0.25,
        cdSubsonic: 0.30,
        cdTransonic: 0.60,
        cdSupersonic: 0.35,
        cdHypersonic: 0.30,
      });
      const RATED_MODEL = Object.freeze({
        earthRotationRadS: 7.292115e-5,
        gravitationalParameterM3S2: 3.986004418e14,
        standardGravityMps2: 9.80665,
        airGasConstantJkgK: 287.05287,
        heatCapacityRatio: 1.4,
        geopotentialEarthRadiusM: 6356766,
        alignmentOffsetsS: Object.freeze([-1.56, 0, 1.04]),
        primaryAlignmentOffsetS: 0,
        minimumNonGravityAccelerationMps2: 0.05,
        chartEndT: 500,
        atmosphereLayers: Object.freeze([
          Object.freeze([0, 288.15, 101325, -0.0065]),
          Object.freeze([11000, 216.65, 22632.06, 0]),
          Object.freeze([20000, 216.65, 5474.889, 0.001]),
          Object.freeze([32000, 228.65, 868.0187, 0.0028]),
          Object.freeze([47000, 270.65, 110.9063, 0]),
          Object.freeze([51000, 270.65, 66.93887, -0.0028]),
          Object.freeze([71000, 214.65, 3.956420, -0.002]),
          Object.freeze([84852, 186.946, 0.3734, 0]),
        ]),
      });
      const RATED_WINDOWS = Object.freeze([
        Object.freeze({ start: 2, end: 114, vehicle: "stack", expectedCount: 33, label: "组合体 · 33 发稳定窗口" }),
        Object.freeze({ start: 192, end: 334, vehicle: "ship", expectedCount: 6, label: "Ship · 分离后 6 发稳定窗口 I" }),
        Object.freeze({ start: 388, end: 468, vehicle: "ship", expectedCount: 6, label: "Ship · 分离后 6 发稳定窗口 II" }),
      ]);
      const state = {
        data: null,
        trajectory: [], fixes: [], fixByRecord: new Map(), trackerIntervals: [], telemetry: [], objectTelemetry: [], objectTelemetryBySecond: new Map(), massSchedule: [], ring: null, absoluteMassSeries: [], ratedMassSeries: [],
        massParameters: { ...DEFAULT_MASS_PARAMETERS },
        ratedParameters: { ...DEFAULT_RATED_PARAMETERS },
        t: 0, draggingRange: false, videoFrameCallback: null,
        yaw: 85 * Math.PI / 180, pitch: 0, zoom: 0.88,
        rotating: false, pointerX: 0, pointerY: 0,
        globeHits: [], lastUiAt: 0, lastHudAt: 0, hudReady: false,
      };
      const T_MIN = 0;
      const T_MAX = 3923;
      const FRAME_DT = 1 / 30;
      const HUD_SYNC_INTERVAL_MS = 100;
      const STACK_SEPARATION_T = 174.6;
      const BOOSTER_TRACK_END_T = 422.367;
      const MASS_BURN_PHASES = Object.freeze([
        Object.freeze({ stage: "booster", start: 0, end: 174.6, allowedCounts: Object.freeze([33, 13, 3, 2, 1]), excludeStart: 138.233, excludeEnd: 148.633, label: "一级上升 33→13→3→2→1" }),
        Object.freeze({ stage: "ship", start: 142.333, end: 484.6, allowedCounts: Object.freeze([6]), label: "二级上升 6" }),
        Object.freeze({ stage: "booster", start: 385.467, end: 422.367, allowedCounts: Object.freeze([10, 8, 5]), label: "一级降落 10→8→5" }),
        Object.freeze({ stage: "ship", start: 2340.367, end: 2355.367, allowedCounts: Object.freeze([1]), label: "二级单发 1" }),
        Object.freeze({ stage: "ship", start: 3902.367, end: 3922.367, allowedCounts: Object.freeze([1, 2, 3]), label: "二级降落 3→2→1" }),
      ]);

      function syncHud(t, force = false) {
        if (!state.hudReady || !hudFrame.contentWindow) return;
        const now = performance.now();
        if (!force && now - state.lastHudAt < HUD_SYNC_INTERVAL_MS) return;
        state.lastHudAt = now;
        const clamped = clamp(t);
        const trajectory = state.data ? trajectoryAt(t) : null;
        const provenance = trajectory ? trajectoryProvenanceAt(t) : null;
        const velocity = trajectory ? {
          valid: true,
          semantics: "conditional_trajectory_instantaneous",
          provenance: provenance?.kind || "reconstructed",
          enu: {
            east_mps: trajectory.east_velocity_mps,
            north_mps: trajectory.north_velocity_mps,
            up_mps: trajectory.vertical_velocity_mps,
          },
          ecef: {
            x_mps: trajectory.ecef_vx_mps,
            y_mps: trajectory.ecef_vy_mps,
            z_mps: trajectory.ecef_vz_mps,
          },
        } : { valid: false, semantics: "no_conditional_trajectory" };
        hudFrame.contentWindow.postMessage({ type: "flight13-time", tplus: clamped, velocity }, location.origin);
      }

      window.addEventListener("message", (event) => {
        if (event.origin !== location.origin || event.source !== hudFrame.contentWindow) return;
        if (event.data?.type === "flight13-hud-ready") {
          state.hudReady = true;
          syncHud(state.t, true);
        } else if (event.data?.type === "flight13-hud-size" && finite(Number(event.data.height))) {
          const requested = Math.max(270, Math.min(420, Math.ceil(Number(event.data.height)) + 4));
          hudFrame.style.height = `${requested}px`;
        }
      });

      function rowsToObjects(table) {
        return table.rows.map((row) => Object.fromEntries(table.columns.map((key, index) => [key, row[index]])));
      }

      function decodeBase64(text, Type) {
        const binary = atob(text);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
        return new Type(bytes.buffer);
      }

      function decodeRing(ring) {
        const a = ring.arrays;
        return {
          length: ring.length, fps: ring.fps, labels: ring.mode_labels,
          null16: ring.null_u16, null8: ring.null_u8,
          leftMode: decodeBase64(a.left_mode_u8, Uint8Array),
          rightMode: decodeBase64(a.right_mode_u8, Uint8Array),
          leftConfidence: decodeBase64(a.left_confidence_u8, Uint8Array),
          rightConfidence: decodeBase64(a.right_confidence_u8, Uint8Array),
          leftBright: decodeBase64(a.left_bright_fraction_u16, Uint16Array),
          rightBright: decodeBase64(a.right_bright_fraction_u16, Uint16Array),
          boosterLevel: decodeBase64(a.booster_relative_level_u16, Uint16Array),
          shipLevel: decodeBase64(a.ship_relative_level_u16, Uint16Array),
          boosterCount: decodeBase64(a.booster_active_count_u8, Uint8Array),
          shipCount: decodeBase64(a.ship_active_count_u8, Uint8Array),
        };
      }

      function clamp(value, min = T_MIN, max = T_MAX) { return Math.max(min, Math.min(max, value)); }
      function finite(value) { return typeof value === "number" && Number.isFinite(value); }
      function fmt(value, digits = 1, missing = "—") { return finite(value) ? value.toFixed(digits) : missing; }
      function timeText(seconds) {
        const value = Math.max(0, seconds);
        const minutes = Math.floor(value / 60);
        const rest = value - minutes * 60;
        return `${String(minutes).padStart(2, "0")}:${rest.toFixed(3).padStart(6, "0")}`;
      }
      function lowerBound(rows, t, key = "tplus_s") {
        let lo = 0, hi = rows.length;
        while (lo < hi) {
          const mid = (lo + hi) >> 1;
          if (rows[mid][key] < t) lo = mid + 1; else hi = mid;
        }
        return lo;
      }
      function nearest(rows, t, key = "tplus_s") {
        if (!rows.length) return null;
        const i = lowerBound(rows, t, key);
        const a = rows[Math.max(0, i - 1)];
        const b = rows[Math.min(rows.length - 1, i)];
        return Math.abs(a[key] - t) <= Math.abs(b[key] - t) ? a : b;
      }
      function neighbors(rows, t, key) {
        const i = lowerBound(rows, t, key);
        return { previous: i > 0 ? rows[i - 1] : null, next: i < rows.length ? rows[i] : null };
      }

      function ringValue(raw, nullValue) { return raw === nullValue ? null : raw / (nullValue - 1); }
      function ringAt(t) {
        const ring = state.ring;
        const pts = t + state.data.time.video_tplus_zero_pts_s;
        const frame = Math.max(0, Math.min(ring.length - 1, Math.round(pts * ring.fps)));
        return {
          frame,
          leftMode: ring.labels[ring.leftMode[frame]], rightMode: ring.labels[ring.rightMode[frame]],
          leftConfidence: ring.leftConfidence[frame] === ring.null8 ? null : ring.leftConfidence[frame] / (ring.null8 - 1),
          rightConfidence: ring.rightConfidence[frame] === ring.null8 ? null : ring.rightConfidence[frame] / (ring.null8 - 1),
          leftBright: ringValue(ring.leftBright[frame], ring.null16), rightBright: ringValue(ring.rightBright[frame], ring.null16),
          boosterLevel: ringValue(ring.boosterLevel[frame], ring.null16), shipLevel: ringValue(ring.shipLevel[frame], ring.null16),
          boosterCount: ring.boosterCount[frame] === ring.null8 ? null : ring.boosterCount[frame],
          shipCount: ring.shipCount[frame] === ring.null8 ? null : ring.shipCount[frame],
        };
      }

      const modeNames = {
        outside_flight_scope_unassigned: "飞行范围外",
        mode_transition_or_not_visible: "转场/不可见",
        booster_engine_array: "助推器发动机阵列",
        ship_engine_array: "星舰发动机阵列",
        speed_numeric: "速度数字",
        altitude_numeric: "高度数字",
        attitude_globe: "姿态地球仪",
      };
      function modeName(value) { return modeNames[value] || value || "未知"; }

      function telemetryAt(t) {
        const sample = nearest(state.telemetry, t);
        if (!sample) return null;
        const tolerance = 0.51 / Math.max(sample.sample_rate_hz || 1, 1);
        const delta = sample.tplus_s - t;
        return Math.abs(delta) <= tolerance + 0.002 ? { sample, delta } : null;
      }

      function objectTelemetryAt(t) {
        const sample = nearest(state.objectTelemetry, t);
        if (!sample || Math.abs(sample.tplus_s - t) > 0.51) return null;
        return sample;
      }

      function trackerIntervalAt(t) {
        const rows = state.trackerIntervals;
        const queryT = Math.round(t * 1000) / 1000;
        let lo = 0, hi = rows.length;
        while (lo < hi) {
          const mid = (lo + hi) >> 1;
          if (rows[mid].start_tplus_s <= queryT) lo = mid + 1; else hi = mid;
        }
        const interval = rows[lo - 1];
        return interval && queryT >= interval.start_tplus_s && queryT < interval.end_tplus_s ? interval : null;
      }

      function setIntervalMetric(id, value, note = "", className = "") {
        const node = $(id);
        node.replaceChildren();
        node.className = className;
        node.title = note;
        node.append(document.createTextNode(value));
      }

      function compassName(degrees) {
        if (!finite(degrees)) return "—";
        return ["北", "东北", "东", "东南", "南", "西南", "西", "西北"][Math.round(degrees / 45) % 8];
      }

      function vehicleName(value) {
        return {
          integrated_stack: "组合体",
          integrated_stack_right: "组合体",
          starship: "飞船",
          starship_ship: "飞船",
          super_heavy: "助推器",
          super_heavy_booster: "助推器",
        }[value] || value || "—";
      }

      function trajectoryProvenanceAt(t) {
        const publicDemo = state.data?.distribution?.profile === "public_synthetic_demo";
        const closest = nearest(state.fixes, t, "aligned_tplus_s");
        const exact = closest && Math.abs(closest.aligned_tplus_s - t) <= 0.55 ? closest : null;
        const pair = neighbors(state.fixes, t + 1e-6, "aligned_tplus_s");
        const crossesGap = Boolean(
          pair.previous && pair.next
          && pair.previous.segment_id !== pair.next.segment_id
          && t > pair.previous.aligned_tplus_s && t < pair.next.aligned_tplus_s
        );
        if (exact) return { kind: "anchor", label: publicDemo ? `邻近合成锚点 ${exact.record_index}` : `邻近原始定位点 ${exact.record_index}`, pair, exact };
        if (crossesGap) {
          const duration = pair.next.aligned_tplus_s - pair.previous.aligned_tplus_s;
          return { kind: "gap", label: publicDemo ? `跨 ${duration.toFixed(0)} 秒合成段间隔` : `跨 ${duration.toFixed(0)} 秒断点重建`, pair, exact: null };
        }
        return { kind: "reconstructed", label: publicDemo ? "合成锚点之间的演示插值" : "定位点之间的轨迹重建", pair, exact: null };
      }

      function updateTrajectoryState(t) {
        const trajectory = trajectoryAt(t);
        if (!trajectory) {
          ["intervalSpeedValue", "intervalGroundValue", "intervalClimbValue", "intervalHeadingValue", "intervalEcefValue", "intervalEnuValue", "intervalDistanceValue", "fixStatusValue", "intervalBasisValue"].forEach((id) => setIntervalMetric(id, "—", "", "missing"));
          setText("intervalSummary", `T+${t.toFixed(3)} 超出轨迹支持范围`, "missing");
          setText("intervalTimeBasis", "稠密轨迹仅覆盖 T+2–3911");
          setText("intervalStatus", "首尾无模型支持的时段保持为空，不用外推值伪装成轨迹点", "missing");
          return;
        }
        const provenance = trajectoryProvenanceAt(t);
        const rowType = trajectory.render_interpolated ? "1 Hz 行间插值" : "1 Hz 轨迹点";
        setText("intervalSummary", `T+${t.toFixed(3)} · ${rowType} · ${provenance.label}`, provenance.kind === "anchor" ? "observed" : "derived");
        setText("intervalTimeBasis", `连续条件轨迹 · ${trajectory.phase_label} · ${trajectory.derivative_quality_code}`);
        setIntervalMetric("intervalSpeedValue", `${trajectory.ecef_speed_kmh.toFixed(1)} km/h`, "WGS-84 ECEF 地固瞬时速度模；不是空速");
        setIntervalMetric("intervalGroundValue", `${trajectory.ground_speed_kmh.toFixed(1)} km/h`, "当前轨迹点 ENU 水平速度模");
        setIntervalMetric("intervalClimbValue", `${trajectory.vertical_velocity_mps >= 0 ? "上升 +" : "下降 "}${trajectory.vertical_velocity_mps.toFixed(1)} m/s`, "当前轨迹点 ENU Up");
        if (trajectory.ground_speed_kmh < 18) {
          setIntervalMetric("intervalHeadingValue", `方向不稳 / γ ${trajectory.flight_path_angle_deg.toFixed(1)}°`, "地速 < 5 m/s", "missing");
        } else {
          setIntervalMetric("intervalHeadingValue", `${trajectory.heading_deg.toFixed(1)}° ${compassName(trajectory.heading_deg)} / γ ${trajectory.flight_path_angle_deg.toFixed(1)}°`, "航向 0° 北；γ 为当前轨迹点航迹倾角");
        }
        const signed = (value) => `${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
        setIntervalMetric("intervalEcefValue", `${signed(trajectory.ecef_vx_mps)} / ${signed(trajectory.ecef_vy_mps)} / ${signed(trajectory.ecef_vz_mps)} m/s`, "+X / +Y / +Z · WGS-84 ECEF 地固瞬时分量");
        setIntervalMetric("intervalEnuValue", `${signed(trajectory.east_velocity_mps)} / ${signed(trajectory.north_velocity_mps)} / ${signed(trajectory.vertical_velocity_mps)} m/s`, "当前点局部东 / 北 / 上");
        setIntervalMetric("intervalDistanceValue", `${trajectory.latitude_deg.toFixed(5)}° / ${trajectory.longitude_deg.toFixed(5)}°`, "当前条件轨迹点纬度 / 经度");
        setIntervalMetric("fixStatusValue", `${trajectory.ellipsoid_altitude_km.toFixed(3)} / ${trajectory.distance_from_pad_km.toFixed(1)} km`, `椭球高度 / 离发射台大圆距离；${provenance.label}`);
        setIntervalMetric("intervalBasisValue", "WGS-84 ECEF / 当前点 ENU", "稠密轨迹为条件重建，不是逐秒实测定位");
        const gapDetail = provenance.kind === "gap"
          ? `；原始定位 ${provenance.pair.previous.record_index} → ${provenance.pair.next.record_index} 之间没有观测`
          : "";
        const publicDemo = state.data?.distribution?.profile === "public_synthetic_demo";
        setText("intervalStatus", publicDemo
          ? "公开包使用纯合成锚点与演示插值；所有数值均非 Flight 13 观测"
          : `稠密轨迹覆盖 T+2–3911；原始定位点作为锚点叠加，重建点不冒充观测${gapDetail}`,
        publicDemo ? "derived" : provenance.kind === "anchor" ? "observed" : "derived");
      }

      function tableStatusLabel(status, source) {
        if (source === "targeted_visual_transcription_no_numeric_ocr_confidence") return "复核补录";
        if (status === "observed_existing") return "OCR";
        if (status === "observed_targeted_reaudit") return "复核补录";
        if (status === "not_eligible_mode_transition") return "布局切换";
        if (status === "not_eligible_field_not_displayed_for_vehicle") return "HUD 未显示";
        return status ? status.replaceAll("_", " ") : "HUD 未显示";
      }

      function setTableValue(id, value, unit, confidence, status, source) {
        const cell = $(id);
        cell.replaceChildren();
        cell.className = finite(value) ? "observed" : "missing";
        cell.append(document.createTextNode(finite(value) ? `${value.toFixed(unit === "km/h" ? 0 : 1)} ${unit}` : "未显示"));
      }

      function setObjectStatus(id, values, layout) {
        const observed = values.some(finite);
        const layoutNames = {
          integrated_stack_right: "组合体画面",
          dual_super_heavy_left_starship_right: "双对象画面",
          telemetry_layout_transition: "布局切换",
          starship_left: "飞船画面",
        };
        setText(id, observed ? "有画面值" : "未显示", observed ? "observed" : "missing");
      }

      function updateObjectTable(t) {
        const sample = objectTelemetryAt(t);
        if (!sample) {
          ["stackSpeedCell", "stackAltitudeCell", "starshipSpeedCell", "starshipAltitudeCell", "superHeavySpeedCell", "superHeavyAltitudeCell"].forEach((id) => setTableValue(id, null, "", null, "no_nearby_l1_sample", ""));
          ["stackStatusCell", "starshipStatusCell", "superHeavyStatusCell"].forEach((id) => setText(id, "此刻附近无 1 Hz 转录", "missing"));
          return;
        }
        setTableValue("stackSpeedCell", sample.stack_speed_value, "km/h", sample.stack_speed_confidence, sample.stack_speed_status, sample.stack_speed_source);
        setTableValue("stackAltitudeCell", sample.stack_altitude_value, "km", sample.stack_altitude_confidence, sample.stack_altitude_status, sample.stack_altitude_source);
        setTableValue("starshipSpeedCell", sample.starship_speed_value, "km/h", sample.starship_speed_confidence, sample.starship_speed_status, sample.starship_speed_source);
        setTableValue("starshipAltitudeCell", sample.starship_altitude_value, "km", sample.starship_altitude_confidence, sample.starship_altitude_status, sample.starship_altitude_source);
        setTableValue("superHeavySpeedCell", sample.super_heavy_speed_value, "km/h", sample.super_heavy_speed_confidence, sample.super_heavy_speed_status, sample.super_heavy_speed_source);
        setTableValue("superHeavyAltitudeCell", sample.super_heavy_altitude_value, "km", sample.super_heavy_altitude_confidence, sample.super_heavy_altitude_status, sample.super_heavy_altitude_source);
        if (sample.layout === "telemetry_layout_transition") {
          ["stackStatusCell", "starshipStatusCell", "superHeavyStatusCell"].forEach((id) => setText(id, "布局切换", "missing"));
          return;
        }
        setObjectStatus("stackStatusCell", [sample.stack_speed_value, sample.stack_altitude_value], sample.layout);
        setObjectStatus("starshipStatusCell", [sample.starship_speed_value, sample.starship_altitude_value], sample.layout);
        setObjectStatus("superHeavyStatusCell", [sample.super_heavy_speed_value, sample.super_heavy_altitude_value], sample.layout);
      }

      function trajectoryAt(t) {
        const rows = state.trajectory;
        if (!rows.length || t < rows[0].tplus_s || t > rows[rows.length - 1].tplus_s) return null;
        const i = lowerBound(rows, t);
        if (i === 0) return { ...rows[0], render_interpolated: false };
        if (i >= rows.length) return { ...rows[rows.length - 1], render_interpolated: false };
        const a = rows[i - 1], b = rows[i];
        if (Math.abs(t - a.tplus_s) < 1e-9) return { ...a, render_interpolated: false };
        if (Math.abs(t - b.tplus_s) < 1e-9) return { ...b, render_interpolated: false };
        const f = (t - a.tplus_s) / (b.tplus_s - a.tplus_s);
        const out = { tplus_s: t, render_interpolated: true };
        const numeric = ["file_pts_s", "tracker_source_met_s", "ecef_x_m", "ecef_y_m", "ecef_z_m", "latitude_deg", "longitude_deg", "ellipsoid_altitude_km", "ecef_vx_mps", "ecef_vy_mps", "ecef_vz_mps", "ecef_ax_mps2", "ecef_ay_mps2", "ecef_az_mps2", "ecef_speed_kmh", "east_velocity_mps", "north_velocity_mps", "vertical_velocity_mps", "ground_speed_kmh", "heading_deg", "flight_path_angle_deg", "distance_from_pad_km"];
        numeric.forEach((key) => { out[key] = finite(a[key]) && finite(b[key]) ? a[key] + (b[key] - a[key]) * f : null; });
        const categorical = f < 0.5 ? a : b;
        out.phase_label = categorical.phase_label;
        out.derivative_quality_code = categorical.derivative_quality_code;
        return out;
      }

      function propellantGraphicAt(stage, t) {
        const ring = ringAt(t);
        if (stage === "booster") {
          return ring.leftMode === "booster_engine_array" && finite(ring.boosterLevel)
            ? { level: ring.boosterLevel, count: ring.boosterCount }
            : null;
        }
        return ring.rightMode === "ship_engine_array" && finite(ring.shipLevel)
          ? { level: ring.shipLevel, count: ring.shipCount }
          : null;
      }

      function massParametersFromInputs() {
        const values = [
          $("massInitialTotal").value,
          $("massBoosterWeight").value,
          $("massBoosterDry").value,
          $("massShipDry").value,
        ];
        if (values.some((value) => value.trim() === "")) return null;
        const raw = {
          initialTotal: Number(values[0]),
          boosterWeight: Number(values[1]) / 100,
          boosterDry: Number(values[2]),
          shipDry: Number(values[3]),
        };
        if (!Object.values(raw).every(finite)) return null;
        const initialTotal = clamp(raw.initialTotal, 0.01, 100000);
        const boosterWeight = clamp(raw.boosterWeight, 0.0001, 0.9999);
        const boosterInitial = boosterWeight * initialTotal;
        const shipInitial = (1 - boosterWeight) * initialTotal;
        return {
          initialTotal,
          boosterWeight,
          boosterDry: clamp(raw.boosterDry, 0, boosterInitial),
          shipDry: clamp(raw.shipDry, 0, shipInitial),
        };
      }

      function writeMassParameterInputs(parameters) {
        $("massInitialTotal").value = String(Number(parameters.initialTotal.toFixed(3)));
        $("massBoosterWeight").value = (100 * parameters.boosterWeight).toFixed(4);
        $("massBoosterDry").value = String(Number(parameters.boosterDry.toFixed(3)));
        $("massShipDry").value = String(Number(parameters.shipDry.toFixed(3)));
      }

      function massInputsMatch(parameters) {
        const displayed = [
          Number($("massInitialTotal").value),
          Number($("massBoosterWeight").value),
          Number($("massBoosterDry").value),
          Number($("massShipDry").value),
        ];
        const effective = [
          parameters.initialTotal,
          100 * parameters.boosterWeight,
          parameters.boosterDry,
          parameters.shipDry,
        ];
        return displayed.every((value, index) => finite(value) && Math.abs(value - effective[index]) <= 1e-6);
      }

      function updateMassComposition() {
        const { initialTotal, boosterWeight, boosterDry, shipDry } = state.massParameters;
        const boosterInitial = boosterWeight * initialTotal;
        const shipInitial = (1 - boosterWeight) * initialTotal;
        const values = {
          boosterPropellant: boosterInitial - boosterDry,
          boosterDry,
          shipPropellant: shipInitial - shipDry,
          shipDry,
        };
        for (const [name, value] of Object.entries(values)) {
          $(`mass${name[0].toUpperCase()}${name.slice(1)}Segment`).style.width = `${100 * value / initialTotal}%`;
          $(`mass${name[0].toUpperCase()}${name.slice(1)}Value`).textContent = `${value.toFixed(1)} t`;
        }
        $("massBoosterDry").max = String(boosterInitial);
        $("massShipDry").max = String(shipInitial);
        $("massTotalValue").textContent = `起飞 ${initialTotal.toFixed(1)} t`;
        $("massCompositionSummary").textContent = `Super Heavy ${boosterInitial.toFixed(1)} t / Ship ${shipInitial.toFixed(1)} t / 起飞合计 ${initialTotal.toFixed(1)} t`;
      }

      function applyMassParametersFromInputs(normalizeInputs = false) {
        const parameters = massParametersFromInputs();
        if (!parameters) {
          if (normalizeInputs) writeMassParameterInputs(state.massParameters);
          return;
        }
        state.massParameters = parameters;
        if (normalizeInputs || !massInputsMatch(parameters)) writeMassParameterInputs(parameters);
        updateMassComposition();
        if (!state.data || !state.ring) return;
        buildAbsoluteMassSeries();
        updatePropellantGauge(state.t);
      }

      function absoluteMassFromLevel(stage, level) {
        const { initialTotal, boosterWeight, boosterDry, shipDry } = state.massParameters;
        level = Math.max(0, Math.min(1, level));
        const initial = initialTotal * (stage === "booster" ? boosterWeight : 1 - boosterWeight);
        const dry = stage === "booster" ? boosterDry : shipDry;
        const propellant = initial - dry;
        const value = dry + propellant * level;
        return { level, value };
      }

      function massBurnPhaseAt(stage, t) {
        return MASS_BURN_PHASES.find((phase) => phase.stage === stage && t >= phase.start && t <= phase.end) || null;
      }

      function vectorAdd(...vectors) {
        return vectors[0].map((_value, index) => vectors.reduce((sum, vector) => sum + vector[index], 0));
      }

      function vectorScale(vector, scalar) { return vector.map((value) => value * scalar); }

      function vectorCross(a, b) {
        return [
          a[1] * b[2] - a[2] * b[1],
          a[2] * b[0] - a[0] * b[2],
          a[0] * b[1] - a[1] * b[0],
        ];
      }

      function vectorMagnitude(vector) { return Math.hypot(...vector); }

      function vectorDot(a, b) { return a.reduce((sum, value, index) => sum + value * b[index], 0); }

      function ratedWindowAt(t) {
        return RATED_WINDOWS.find((window) => t >= window.start && t <= window.end) || null;
      }

      function ratedParametersFromInputs() {
        const raw = {
          boosterSeaLevelTf: Number($("ratedBoosterSeaLevelTf").value),
          raptorSeaLevelTf: Number($("ratedRaptorSeaLevelTf").value),
          raptorVacuumTf: Number($("ratedRaptorVacuumTf").value),
          thrustUncertaintyFraction: Number($("ratedThrustUncertainty").value) / 100,
          raptorDiameterM: Number($("ratedRaptorDiameter").value),
          raptorVacuumDiameterM: Number($("ratedRaptorVacuumDiameter").value),
          vehicleDiameterM: Number($("ratedVehicleDiameter").value),
          cdUncertaintyFraction: Number($("ratedCdUncertainty").value) / 100,
          cdSubsonic: Number($("ratedCdSubsonic").value),
          cdTransonic: Number($("ratedCdTransonic").value),
          cdSupersonic: Number($("ratedCdSupersonic").value),
          cdHypersonic: Number($("ratedCdHypersonic").value),
        };
        if (!Object.values(raw).every(finite)) return null;
        return {
          boosterSeaLevelTf: Math.max(1, raw.boosterSeaLevelTf),
          raptorSeaLevelTf: Math.max(1, raw.raptorSeaLevelTf),
          raptorVacuumTf: Math.max(1, raw.raptorVacuumTf),
          thrustUncertaintyFraction: clamp(raw.thrustUncertaintyFraction, 0, 0.5),
          raptorDiameterM: Math.max(0.1, raw.raptorDiameterM),
          raptorVacuumDiameterM: Math.max(0.1, raw.raptorVacuumDiameterM),
          vehicleDiameterM: Math.max(0.1, raw.vehicleDiameterM),
          cdUncertaintyFraction: clamp(raw.cdUncertaintyFraction, 0, 1),
          cdSubsonic: clamp(raw.cdSubsonic, 0, 3),
          cdTransonic: clamp(raw.cdTransonic, 0, 3),
          cdSupersonic: clamp(raw.cdSupersonic, 0, 3),
          cdHypersonic: clamp(raw.cdHypersonic, 0, 3),
        };
      }

      function writeRatedParameterInputs(parameters) {
        $("ratedBoosterSeaLevelTf").value = String(parameters.boosterSeaLevelTf);
        $("ratedRaptorSeaLevelTf").value = String(parameters.raptorSeaLevelTf);
        $("ratedRaptorVacuumTf").value = String(parameters.raptorVacuumTf);
        $("ratedThrustUncertainty").value = String(100 * parameters.thrustUncertaintyFraction);
        $("ratedRaptorDiameter").value = String(parameters.raptorDiameterM);
        $("ratedRaptorVacuumDiameter").value = String(parameters.raptorVacuumDiameterM);
        $("ratedVehicleDiameter").value = String(parameters.vehicleDiameterM);
        $("ratedCdUncertainty").value = String(100 * parameters.cdUncertaintyFraction);
        $("ratedCdSubsonic").value = parameters.cdSubsonic.toFixed(2);
        $("ratedCdTransonic").value = parameters.cdTransonic.toFixed(2);
        $("ratedCdSupersonic").value = parameters.cdSupersonic.toFixed(2);
        $("ratedCdHypersonic").value = parameters.cdHypersonic.toFixed(2);
      }

      function applyRatedParametersFromInputs(normalizeInputs = false) {
        const parameters = ratedParametersFromInputs();
        if (!parameters) {
          if (normalizeInputs) writeRatedParameterInputs(state.ratedParameters);
          return;
        }
        state.ratedParameters = parameters;
        if (normalizeInputs) writeRatedParameterInputs(parameters);
        if (!state.data || !state.ring) return;
        buildRatedMassSeries();
        updateRatedInversion(state.t);
      }

      function standardAtmosphere1976At(geometricAltitudeM) {
        const g0 = RATED_MODEL.standardGravityMps2;
        const gasR = RATED_MODEL.airGasConstantJkgK;
        const re = RATED_MODEL.geopotentialEarthRadiusM;
        const geometric = Math.max(0, geometricAltitudeM);
        const geopotential = re * geometric / (re + geometric);
        const layers = RATED_MODEL.atmosphereLayers;
        let layer = layers[layers.length - 1];
        for (let index = 0; index < layers.length - 1; index += 1) {
          if (geopotential < layers[index + 1][0]) { layer = layers[index]; break; }
        }
        const [baseH, baseT, baseP, lapse] = layer;
        const deltaH = geopotential - baseH;
        let temperature;
        let pressure;
        if (Math.abs(lapse) < 1e-12) {
          temperature = baseT;
          pressure = baseP * Math.exp(-g0 * deltaH / (gasR * baseT));
        } else {
          temperature = baseT + lapse * deltaH;
          pressure = baseP * (baseT / temperature) ** (g0 / (gasR * lapse));
        }
        const density = pressure / (gasR * temperature);
        const speedOfSound = Math.sqrt(RATED_MODEL.heatCapacityRatio * gasR * temperature);
        return { geometricAltitudeM: geometric, geopotentialAltitudeM: geopotential, temperatureK: temperature, pressurePa: pressure, densityKgM3: density, speedOfSoundMps: speedOfSound, extrapolated: geopotential > 84852 };
      }

      function ratedCdAt(mach, parameters) {
        const nodes = [
          [0, parameters.cdSubsonic],
          [0.8, parameters.cdSubsonic],
          [1.05, parameters.cdTransonic],
          [1.5, parameters.cdSupersonic],
          [5, parameters.cdHypersonic],
        ];
        const value = Math.max(0, mach);
        for (let index = 1; index < nodes.length; index += 1) {
          if (value > nodes[index][0]) continue;
          const [m0, cd0] = nodes[index - 1], [m1, cd1] = nodes[index];
          return cd0 + (cd1 - cd0) * (value - m0) / (m1 - m0);
        }
        return parameters.cdHypersonic;
      }

      function ratedEngineGateAt(t, window) {
        const ring = ringAt(t);
        if (window.vehicle === "stack") {
          const valid = ring.leftMode === "booster_engine_array" && ring.boosterCount === window.expectedCount;
          return valid ? { valid: true, count: ring.boosterCount, composition: "33 台普通 Raptor（整级官网推力口径）" } : { valid: false, reason: "助推器发动机阵列模式或 33 发数量不可信" };
        }
        const valid = ring.rightMode === "ship_engine_array" && ring.shipCount === window.expectedCount;
        return valid ? { valid: true, count: ring.shipCount, composition: "3 台普通 Raptor + 3 台 Raptor Vacuum" } : { valid: false, reason: "Ship 发动机阵列模式或 6 发数量不可信" };
      }

      function ratedThrustAt(window, atmosphere, parameters, scale = 1) {
        const p0 = RATED_MODEL.atmosphereLayers[0][2];
        const tfN = RATED_MODEL.standardGravityMps2 * 1000;
        const raptorArea = Math.PI * parameters.raptorDiameterM ** 2 / 4;
        const vacuumArea = Math.PI * parameters.raptorVacuumDiameterM ** 2 / 4;
        if (window.vehicle === "stack") {
          const seaLevelN = parameters.boosterSeaLevelTf * tfN;
          return scale * (seaLevelN + 33 * (p0 - atmosphere.pressurePa) * raptorArea);
        }
        const raptorN = parameters.raptorSeaLevelTf * tfN + (p0 - atmosphere.pressurePa) * raptorArea;
        const vacuumN = parameters.raptorVacuumTf * tfN - atmosphere.pressurePa * vacuumArea;
        return scale * 3 * (raptorN + vacuumN);
      }

      function ratedTrajectoryDynamicsAt(t, alignmentOffsetS, window) {
        const centerT = t + alignmentOffsetS;
        if (t < window.start || t > window.end) return null;
        const trajectory = trajectoryAt(centerT);
        if (!trajectory) return null;
        const position = [trajectory.ecef_x_m, trajectory.ecef_y_m, trajectory.ecef_z_m];
        const velocity = [trajectory.ecef_vx_mps, trajectory.ecef_vy_mps, trajectory.ecef_vz_mps];
        const accelerationEcef = [trajectory.ecef_ax_mps2, trajectory.ecef_ay_mps2, trajectory.ecef_az_mps2];
        if (![...position, ...velocity, ...accelerationEcef].every(finite)) return null;
        const omega = [0, 0, RATED_MODEL.earthRotationRadS];
        const accelerationInertial = vectorAdd(accelerationEcef, vectorScale(vectorCross(omega, velocity), 2), vectorCross(omega, vectorCross(omega, position)));
        const radius = vectorMagnitude(position);
        const gravity = vectorScale(position, -RATED_MODEL.gravitationalParameterM3S2 / radius ** 3);
        const nonGravityAcceleration = vectorAdd(accelerationInertial, vectorScale(gravity, -1));
        return { trajectory, position, velocity, accelerationEcef, accelerationInertial, gravity, nonGravityAcceleration };
      }

      function ratedMassInversionAt(t, options = {}) {
        const parameters = options.parameters || state.ratedParameters;
        const window = ratedWindowAt(t);
        if (!window) return { valid: false, reason: "严格可计算窗口之外" };
        const gate = ratedEngineGateAt(t, window);
        if (!gate.valid) return { valid: false, reason: gate.reason, window };
        const alignmentOffsetS = options.alignmentOffsetS ?? RATED_MODEL.primaryAlignmentOffsetS;
        const dynamics = ratedTrajectoryDynamicsAt(t, alignmentOffsetS, window);
        if (!dynamics) return { valid: false, reason: "轨迹或二阶导数不可用", window };
        const airSpeed = vectorMagnitude(dynamics.velocity);
        if (!(airSpeed > 0)) return { valid: false, reason: "空速近似为零", window };
        const atmosphere = standardAtmosphere1976At(dynamics.trajectory.ellipsoid_altitude_km * 1000);
        const mach = airSpeed / atmosphere.speedOfSoundMps;
        const cd = ratedCdAt(mach, parameters) * (options.cdScale ?? 1);
        const referenceAreaM2 = Math.PI * parameters.vehicleDiameterM ** 2 / 4;
        const dragN = 0.5 * atmosphere.densityKgM3 * cd * referenceAreaM2 * airSpeed ** 2;
        const thrustN = ratedThrustAt(window, atmosphere, parameters, options.thrustScale ?? 1);
        const velocityDirection = vectorScale(dynamics.velocity, 1 / airSpeed);
        const acceleration = dynamics.nonGravityAcceleration;
        const accelerationMagnitude = vectorMagnitude(acceleration);
        if (accelerationMagnitude < RATED_MODEL.minimumNonGravityAccelerationMps2) return { valid: false, reason: "扣除重力后的加速度接近零", window };
        if (!(thrustN > dragN)) return { valid: false, reason: "阻力不低于额定推力", window };
        const aa = vectorDot(acceleration, acceleration);
        const bb = 2 * dragN * vectorDot(acceleration, velocityDirection);
        const cc = dragN ** 2 - thrustN ** 2;
        const discriminant = bb ** 2 - 4 * aa * cc;
        if (!(discriminant >= 0) || !finite(discriminant)) return { valid: false, reason: "质量方程无实根", window };
        const massKg = (-bb + Math.sqrt(discriminant)) / (2 * aa);
        if (!(massKg > 0) || !finite(massKg)) return { valid: false, reason: "质量方程无正根", window };
        const thrustVector = vectorAdd(vectorScale(acceleration, massKg), vectorScale(velocityDirection, dragN));
        const reconstructedThrustN = vectorMagnitude(thrustVector);
        if (!(reconstructedThrustN > 0)) return { valid: false, reason: "推力方向不可恢复", window };
        const thrustDirection = vectorScale(thrustVector, 1 / reconstructedThrustN);
        const directionAngleDeg = Math.acos(clamp(vectorDot(thrustDirection, velocityDirection), -1, 1)) * 180 / Math.PI;
        return {
          valid: true, t, window, gate, alignmentOffsetS, dynamics, atmosphere,
          massTonnes: massKg / 1000, thrustMN: thrustN / 1e6, reconstructedThrustMN: reconstructedThrustN / 1e6,
          dragMN: dragN / 1e6, airSpeedMps: airSpeed, mach, cd, referenceAreaM2,
          nonGravityAccelerationMps2: accelerationMagnitude, directionAngleDeg, thrustDirection,
        };
      }

      function ratedSensitivityAt(t) {
        const primary = ratedMassInversionAt(t);
        if (!primary.valid) return primary;
        const p = state.ratedParameters;
        const cdScales = [1 - p.cdUncertaintyFraction, 1, 1 + p.cdUncertaintyFraction];
        const thrustScales = [1 - p.thrustUncertaintyFraction, 1, 1 + p.thrustUncertaintyFraction];
        const candidates = [];
        for (const alignmentOffsetS of RATED_MODEL.alignmentOffsetsS) {
          for (const cdScale of cdScales) {
            for (const thrustScale of thrustScales) {
              const result = ratedMassInversionAt(t, { alignmentOffsetS, cdScale, thrustScale });
              if (result.valid) candidates.push(result);
            }
          }
        }
        if (!candidates.length) return { valid: false, reason: "敏感性候选全部不可用", window: primary.window };
        const masses = candidates.map((item) => item.massTonnes);
        const angles = candidates.map((item) => item.directionAngleDeg);
        return {
          ...primary,
          massLowTonnes: Math.min(...masses), massHighTonnes: Math.max(...masses),
          angleLowDeg: Math.min(...angles), angleHighDeg: Math.max(...angles),
          candidateCount: candidates.length,
        };
      }

      function buildRatedMassSeries() {
        const rows = [];
        for (const window of RATED_WINDOWS) {
          for (let t = window.start; t <= window.end; t += 1) {
            const result = ratedSensitivityAt(t);
            if (result.valid) rows.push(result);
          }
        }
        state.ratedMassSeries = rows;
        updateRatedSummaryCards();
      }

      function updateRatedSummaryCards() {
        const snapshots = [[60, "ratedSnapshot60Mass", "ratedSnapshot60Range"], [250, "ratedSnapshot250Mass", "ratedSnapshot250Range"], [420, "ratedSnapshot420Mass", "ratedSnapshot420Range"]];
        snapshots.forEach(([t, massId, rangeId]) => {
          const result = ratedSensitivityAt(t);
          setText(massId, result.valid ? `${result.massTonnes.toFixed(0)} t` : "—", result.valid ? "estimated" : "missing");
          setText(rangeId, result.valid ? `${result.massLowTonnes.toFixed(0)}–${result.massHighTonnes.toFixed(0)} t` : "—");
        });
        const consumptionPairs = [
          [20, 114, "ratedBoosterConsumed", "ratedBoosterConsumedRange"],
          [192, 468, "ratedShipConsumed", "ratedShipConsumedRange"],
        ];
        consumptionPairs.forEach(([startT, endT, valueId, rangeId]) => {
          const start = ratedSensitivityAt(startT), end = ratedSensitivityAt(endT);
          if (!start.valid || !end.valid) {
            setText(valueId, "—", "missing"); setText(rangeId, "—"); return;
          }
          const consumed = start.massTonnes - end.massTonnes;
          const low = start.massLowTonnes - end.massHighTonnes;
          const high = start.massHighTonnes - end.massLowTonnes;
          setText(valueId, `${consumed.toFixed(0)} t`, "estimated");
          setText(rangeId, `${Math.max(0, low).toFixed(0)}–${Math.max(0, high).toFixed(0)} t`);
        });
      }

      function buildAbsoluteMassSeries() {
        const levels = { booster: 1, ship: 1 };
        const rows = [];
        for (let t = 0; t <= T_MAX; t += 1) {
          const ring = ringAt(t);
          for (const stage of ["booster", "ship"]) {
            const phase = massBurnPhaseAt(stage, t);
            const modeMatches = stage === "booster"
              ? ring.leftMode === "booster_engine_array"
              : ring.rightMode === "ship_engine_array";
            const count = stage === "booster" ? ring.boosterCount : ring.shipCount;
            let candidate = stage === "booster" ? ring.boosterLevel : ring.shipLevel;
            let sampleAccepted = phase && phase.allowedCounts.includes(count);
            const transitionExcluded = phase && finite(phase.excludeStart)
              && t >= phase.excludeStart && t < phase.excludeEnd;
            if (transitionExcluded) {
              const beforeT = Math.floor(phase.excludeStart), afterT = Math.ceil(phase.excludeEnd);
              const beforeRing = ringAt(beforeT), afterRing = ringAt(afterT);
              const beforeLevel = stage === "booster" ? beforeRing.boosterLevel : beforeRing.shipLevel;
              const afterLevel = stage === "booster" ? afterRing.boosterLevel : afterRing.shipLevel;
              const fraction = (t - beforeT) / (afterT - beforeT);
              candidate = beforeLevel + (afterLevel - beforeLevel) * fraction;
              sampleAccepted = finite(beforeLevel) && finite(afterLevel);
            }
            if (phase && modeMatches && sampleAccepted && finite(candidate)) {
              levels[stage] = Math.min(levels[stage], Math.max(0, Math.min(1, candidate)));
            }
          }
          rows.push({
            t,
            booster: absoluteMassFromLevel("booster", levels.booster),
            ship: absoluteMassFromLevel("ship", levels.ship),
          });
        }
        state.absoluteMassSeries = rows;
      }

      function absoluteMassAt(stage, t) {
        if (!state.absoluteMassSeries.length || t < 0 || t > T_MAX) return null;
        if (stage === "booster" && t > BOOSTER_TRACK_END_T) return null;
        const row = state.absoluteMassSeries[Math.max(0, Math.min(T_MAX, Math.round(t)))];
        return row ? row[stage] : null;
      }

      function formatMassValue(mass, missingText = "暂无质量支持") {
        if (!mass) return missingText;
        return `${mass.value.toFixed(1)} t`;
      }

      function drawAbsoluteMass() {
        if (!state.data || !state.ring) return;
        const { initialTotal } = state.massParameters;
        const { width, height } = fitCanvas(absoluteMassCanvas, mctx);
        mctx.clearRect(0, 0, width, height);
        const left = 62, right = 10, top = 12, bottom = 34;
        const plotW = Math.max(1, width - left - right), plotH = Math.max(1, height - top - bottom);
        const x = (t) => left + Math.max(0, Math.min(T_MAX, t)) / T_MAX * plotW;
        const y = (mass) => top + (1 - mass / initialTotal) * plotH;
        const massTicks = [0, .25, .5, .75, 1].map((fraction) => initialTotal * fraction);
        mctx.strokeStyle = css("--border"); mctx.lineWidth = 1;
        massTicks.forEach((mass) => {
          mctx.beginPath(); mctx.moveTo(left, y(mass)); mctx.lineTo(left + plotW, y(mass)); mctx.stroke();
        });
        const drawSeries = (stage, color) => {
          const samples = state.absoluteMassSeries
            .filter((row) => stage !== "booster" || row.t <= BOOSTER_TRACK_END_T)
            .map((row) => ({ t: row.t, ...row[stage] }));
          if (!samples.length) return;
          mctx.strokeStyle = color; mctx.lineWidth = 1.8; mctx.beginPath();
          samples.forEach((sample, index) => {
            const px = x(sample.t), py = y(sample.value);
            if (!index) mctx.moveTo(px, py); else mctx.lineTo(px, py);
          });
          mctx.stroke();
        };
        drawSeries("booster", "#1f83b5");
        drawSeries("ship", "#8d63bf");
        mctx.strokeStyle = css("--text"); mctx.lineWidth = 1.2; mctx.beginPath();
        let combinedActive = false;
        for (let t = 0; t <= STACK_SEPARATION_T; t += 1) {
          const booster = absoluteMassAt("booster", t), ship = absoluteMassAt("ship", t);
          if (!booster || !ship) { combinedActive = false; continue; }
          const px = x(t), py = y(booster.value + ship.value);
          if (!combinedActive) { mctx.moveTo(px, py); combinedActive = true; } else mctx.lineTo(px, py);
        }
        mctx.stroke();
        MASS_BURN_PHASES.forEach((phase) => {
          const y0 = phase.stage === "booster" ? height - 20 : height - 11;
          const x0 = x(phase.start), x1 = x(phase.end);
          mctx.fillStyle = phase.stage === "booster" ? "#1f83b5" : "#8d63bf";
          mctx.fillRect(x0, y0, Math.max(2, x1 - x0), 5);
        });
        if (state.t <= T_MAX) {
          mctx.strokeStyle = css("--accent"); mctx.lineWidth = 1.2; mctx.beginPath(); mctx.moveTo(x(state.t), top); mctx.lineTo(x(state.t), top + plotH); mctx.stroke();
        }
        mctx.font = '13px "Segoe UI", sans-serif'; mctx.fillStyle = css("--muted");
        massTicks.forEach((mass) => {
          const label = `${Math.round(mass)} t`;
          mctx.fillText(label, Math.max(2, left - mctx.measureText(label).width - 6), y(mass) + 4);
        });
        [0, 1000, 2000, 3000, T_MAX].forEach((t) => {
          const label = t === T_MAX ? `T+${T_MAX}` : String(t);
          const labelX = Math.max(left, Math.min(width - mctx.measureText(label).width - 2, x(t) - mctx.measureText(label).width / 2));
          mctx.fillText(label, labelX, height - 23);
        });
        mctx.fillStyle = "#1f83b5"; mctx.fillText("Super Heavy", left + 8, top + 13);
        mctx.fillStyle = "#8d63bf"; mctx.fillText("Ship", left + 104, top + 13);
        mctx.fillStyle = css("--text"); mctx.fillText("组合体（仅分离前）", left + 145, top + 13);
      }

      function updatePropellantGauge(t) {
        if (!state.data || !state.ring) return;
        const ring = ringAt(t);
        const booster = propellantGraphicAt("booster", t);
        const ship = propellantGraphicAt("ship", t);
        setText("propellantMode", `${modeName(ring.leftMode)} / ${modeName(ring.rightMode)}`, "observed");
        const engineParts = [];
        if (booster && finite(booster.count)) engineParts.push(`助推器 ${booster.count} 个`);
        if (ship && finite(ship.count)) engineParts.push(`飞船 ${ship.count} 个`);
        setText("propellantEngines", engineParts.length ? engineParts.join(" / ") : "当前未显示发动机阵列", engineParts.length ? "observed" : "missing");
        setText("propellantBoosterLevel", booster ? `${(100 * booster.level).toFixed(1)} / 100` : "当前不适用", booster ? "derived" : "missing");
        setText("propellantShipLevel", ship ? `${(100 * ship.level).toFixed(1)} / 100` : "当前不适用", ship ? "derived" : "missing");
        const boosterMass = absoluteMassAt("booster", t), shipMass = absoluteMassAt("ship", t);
        setText("absoluteBoosterMass", formatMassValue(boosterMass, "一级任务段结束"), boosterMass ? "derived" : "missing");
        setText("absoluteShipMass", formatMassValue(shipMass), shipMass ? "derived" : "missing");
        const combinedMass = t <= STACK_SEPARATION_T && boosterMass && shipMass
          ? { value: boosterMass.value + shipMass.value }
          : null;
        setText("absoluteCombinedMass", combinedMass ? formatMassValue(combinedMass) : "已分离，不再相加", combinedMass ? "derived" : "missing");
        drawAbsoluteMass();
      }

      function ratedUnavailableReason(t) {
        if (t < 2) return "拟合轨迹从 T+2 开始";
        if (t <= 191) return "定位缺口 / 热分离 / 分离事件：必须留空";
        if (t <= 387) return "原始 StarDash 定位硬缺口：求导不得跨越";
        if (t <= 468) return "发动机图标或轨迹门控未通过";
        if (t <= 500) return "Ship 主发动机关机边缘：不在稳定推力窗口";
        if (t <= STACK_SEPARATION_T) return "热分离窗口：不拆分两级质量";
        if (t <= BOOSTER_TRACK_END_T) return "分离后 Booster 无独立三维轨迹";
        return "滑行、短时再点火、再入和着陆均不反演";
      }

      function updateRatedInversion(t) {
        const result = ratedSensitivityAt(t);
        if (!result.valid) {
          setText("ratedWindowStatus", `T+${t.toFixed(1)} / —`, "missing");
          ["ratedEngineCountValue", "ratedThrustValue", "ratedSpeedValue", "ratedAltitudeValue", "ratedDynamicsValue", "ratedAeroValue", "ratedMassValue", "ratedMassInterval", "ratedDirectionValue", "ratedQualityValue"].forEach((id) => setText(id, "—", "missing"));
          drawRatedCharts();
          return;
        }
        const vehicleLabel = result.window.vehicle === "stack" ? "组合体" : "Ship";
        setText("ratedWindowStatus", `T+${t.toFixed(1)} / ${vehicleLabel}`, "estimated");
        setText("ratedEngineCountValue", String(result.gate.count), "estimated");
        setText("ratedThrustValue", `${result.thrustMN.toFixed(2)} MN`, "estimated");
        setText("ratedSpeedValue", `${(result.airSpeedMps / 1000).toFixed(3)} km/s`, "estimated");
        setText("ratedAltitudeValue", `${result.dynamics.trajectory.ellipsoid_altitude_km.toFixed(3)} km`, "estimated");
        setText("ratedDynamicsValue", `${result.nonGravityAccelerationMps2.toFixed(3)} m/s²`, "estimated");
        setText("ratedAeroValue", `${result.mach.toFixed(2)} / ${result.cd.toFixed(3)} / ${result.dragMN.toFixed(3)} MN`, "estimated");
        setText("ratedMassValue", `${result.massTonnes.toFixed(1)} t`, "estimated");
        setText("ratedMassInterval", `${result.massLowTonnes.toFixed(1)}–${result.massHighTonnes.toFixed(1)} t`, "estimated");
        setText("ratedDirectionValue", `${result.directionAngleDeg.toFixed(2)}° / ${result.angleLowDeg.toFixed(2)}–${result.angleHighDeg.toFixed(2)}°`, "estimated");
        setText("ratedQualityValue", String(result.candidateCount), "estimated");
        drawRatedCharts();
      }

      function ratedChartWindows() {
        return RATED_WINDOWS.map((window) => ({ window, rows: state.ratedMassSeries.filter((row) => row.window === window) }));
      }

      function drawRatedMassChart() {
        const { width, height } = fitCanvas(ratedMassCanvas, rmctx);
        rmctx.clearRect(0, 0, width, height);
        const left = 62, right = 12, top = 12, bottom = 30;
        const plotW = Math.max(1, width - left - right), plotH = Math.max(1, height - top - bottom);
        const maxMass = Math.max(1, ...state.ratedMassSeries.map((row) => row.massHighTonnes));
        const yMax = Math.ceil(maxMass / 500) * 500;
        const x = (t) => left + t / RATED_MODEL.chartEndT * plotW;
        const y = (mass) => top + (1 - mass / yMax) * plotH;
        rmctx.strokeStyle = css("--border"); rmctx.lineWidth = 1;
        for (let index = 0; index <= 4; index += 1) {
          const mass = yMax * index / 4;
          rmctx.beginPath(); rmctx.moveTo(left, y(mass)); rmctx.lineTo(left + plotW, y(mass)); rmctx.stroke();
        }
        for (const { rows } of ratedChartWindows()) {
          if (!rows.length) continue;
          rmctx.fillStyle = "rgba(204, 145, 48, 0.22)";
          rmctx.beginPath();
          rows.forEach((row, index) => { const px = x(row.t), py = y(row.massHighTonnes); if (!index) rmctx.moveTo(px, py); else rmctx.lineTo(px, py); });
          [...rows].reverse().forEach((row) => rmctx.lineTo(x(row.t), y(row.massLowTonnes)));
          rmctx.closePath(); rmctx.fill();
          rmctx.strokeStyle = css("--estimated"); rmctx.lineWidth = 1.8; rmctx.beginPath();
          rows.forEach((row, index) => { const px = x(row.t), py = y(row.massTonnes); if (!index) rmctx.moveTo(px, py); else rmctx.lineTo(px, py); });
          rmctx.stroke();
        }
        if (state.t >= 0 && state.t <= RATED_MODEL.chartEndT) {
          rmctx.strokeStyle = css("--accent"); rmctx.lineWidth = 1.2; rmctx.beginPath(); rmctx.moveTo(x(state.t), top); rmctx.lineTo(x(state.t), top + plotH); rmctx.stroke();
        }
        rmctx.font = '12px "Segoe UI", sans-serif'; rmctx.fillStyle = css("--muted");
        for (let index = 0; index <= 4; index += 1) {
          const mass = yMax * index / 4, label = `${Math.round(mass)} t`;
          rmctx.fillText(label, Math.max(2, left - rmctx.measureText(label).width - 6), y(mass) + 4);
        }
        [0, 100, 200, 300, 400, 500].forEach((t) => { const label = `T+${t}`; rmctx.fillText(label, Math.max(left, Math.min(width - rmctx.measureText(label).width, x(t) - rmctx.measureText(label).width / 2)), height - 9); });
      }

      function drawRatedCharts() { drawRatedMassChart(); }

      function setText(id, text, className) {
        const node = $(id);
        node.textContent = text;
        if (className) node.className = className;
      }

      function updatePanels(t, announce = false) {
        const pts = t + state.data.time.video_tplus_zero_pts_s;
        const frame = Math.round(pts * state.data.time.video_fps);
        const inScope = t >= T_MIN && t <= T_MAX;
        setText("videoTplus", timeText(t));
        setText("videoPts", `${pts.toFixed(3)} s`);
        setText("videoFrame", String(frame));
        setText("scopeStatus", inScope ? "飞行范围" : "飞行范围外", inScope ? "" : "missing");
        setText("timeValue", `T+ ${timeText(t)}`);
        setText("ptsFrameValue", `${pts.toFixed(3)} s / ${frame}`);

        const hud = telemetryAt(t);
        if (hud) {
          const s = hud.sample;
          setText("objectValue", vehicleName(s.trajectory_object || s.vehicle_identity));
          setText("objectMeta", `${s.source_level} · ${s.layout} · Δt ${hud.delta >= 0 ? "+" : ""}${hud.delta.toFixed(3)} s`);
          setText("clockValue", finite(s.broadcast_clock_s) ? `T+${s.broadcast_clock_s.toFixed(1)} s` : "未显示");
          setText("speedValue", s.usable_speed && finite(s.speed_kmh) ? `${s.speed_kmh.toFixed(0)} km/h` : "未显示/不可用", s.usable_speed && finite(s.speed_kmh) ? "metric-value observed" : "metric-value missing");
          setText("speedMeta", `raw ${s.speed_raw || "—"} · confidence ${fmt(s.speed_confidence, 3)}`);
          setText("altitudeValue", s.usable_altitude && finite(s.altitude_km) ? `${s.altitude_km.toFixed(1)} km` : "未显示/不可用", s.usable_altitude && finite(s.altitude_km) ? "metric-value observed" : "metric-value missing");
          setText("altitudeMeta", `raw ${s.altitude_raw || "—"} · confidence ${fmt(s.altitude_confidence, 3)} · ${s.altitude_display_status || "—"}`);
          setText("hudSampleValue", `${s.source_level} / ${fmt(s.sample_rate_hz, 0)} Hz`);
          setText("hudQcValue", s.qc_flags || s.review_status || "无标志", s.qc_flags ? "metric-value estimated" : "metric-value");
        } else {
          ["objectValue", "clockValue", "speedValue", "altitudeValue", "hudSampleValue", "hudQcValue"].forEach((id) => setText(id, "此帧附近无转录", "metric-value missing"));
          setText("objectMeta", "不对相邻 OCR 样本插值"); setText("speedMeta", "—"); setText("altitudeMeta", "—");
        }

        const ring = ringAt(t);
        setText("ringModeValue", `${modeName(ring.leftMode)} / ${modeName(ring.rightMode)}`);
        setText("boosterRingValue", finite(ring.boosterLevel) ? `${(100 * ring.boosterLevel).toFixed(1)} / 100` : "不适用", finite(ring.boosterLevel) ? "metric-value observed" : "metric-value missing");
        setText("boosterRingMeta", finite(ring.boosterLevel) ? `发动机阵列模式的相对推进剂图形；不是整车油箱质量百分比 · 外环亮度 ${fmt(ring.leftBright, 3)} · mode conf ${fmt(ring.leftConfidence, 3)}` : `当前模式：${modeName(ring.leftMode)}`);
        setText("shipRingValue", finite(ring.shipLevel) ? `${(100 * ring.shipLevel).toFixed(1)} / 100` : "不适用", finite(ring.shipLevel) ? "metric-value observed" : "metric-value missing");
        setText("shipRingMeta", finite(ring.shipLevel) ? `发动机阵列模式的相对推进剂图形；不是整车油箱质量百分比 · 外环亮度 ${fmt(ring.rightBright, 3)} · mode conf ${fmt(ring.rightConfidence, 3)}` : `当前模式：${modeName(ring.rightMode)}`);
        setText("engineCountValue", `助推器 ${ring.boosterCount ?? "—"} / 飞船 ${ring.shipCount ?? "—"}`);

        const fixPair = neighbors(state.fixes, t, "aligned_tplus_s");
        if (fixPair.previous) {
          const p = fixPair.previous, dt = t - p.aligned_tplus_s;
          setText("prevFixValue", `record ${p.record_index} · ${dt.toFixed(1)} s 前`);
          setText("prevFixMeta", `${p.latitude_deg.toFixed(4)}°, ${p.longitude_deg.toFixed(4)}° · ${fmt(p.source_altitude_m / 1000, 2)} km · source MET ${p.source_met_s.toFixed(1)}`);
        } else { setText("prevFixValue", "无", "metric-value missing"); setText("prevFixMeta", "—"); }
        if (fixPair.next) {
          const n = fixPair.next, dt = n.aligned_tplus_s - t;
          setText("nextFixValue", `record ${n.record_index} · ${dt.toFixed(1)} s 后`);
          setText("nextFixMeta", `${n.latitude_deg.toFixed(4)}°, ${n.longitude_deg.toFixed(4)}° · ${fmt(n.source_altitude_m / 1000, 2)} km · source MET ${n.source_met_s.toFixed(1)}`);
        } else { setText("nextFixValue", "无", "metric-value missing"); setText("nextFixMeta", "—"); }

        const estimate = trajectoryAt(t);
        const enabled = $("showEstimate").checked;
        if (!enabled) {
          setText("estimateStatus", "已关闭");
          ["estimateLatLon", "estimateAltitude", "estimateSpeed", "estimateEcefVector", "estimateVelocity", "estimateGround", "estimatePath", "estimateQuality"].forEach((id) => setText(id, "—"));
        } else if (!estimate) {
          setText("estimateStatus", "NO_TRAJECTORY", "missing");
          ["estimateLatLon", "estimateAltitude", "estimateSpeed", "estimateEcefVector", "estimateVelocity", "estimateGround", "estimatePath", "estimateQuality"].forEach((id) => setText(id, "—"));
        } else {
          setText("estimateStatus", estimate.render_interpolated ? "1 Hz 模型行间渲染插值" : "1 Hz 模型行", "estimated");
          setText("estimateLatLon", `${estimate.latitude_deg.toFixed(5)}°, ${estimate.longitude_deg.toFixed(5)}°`);
          setText("estimateAltitude", `${estimate.ellipsoid_altitude_km.toFixed(3)} km`);
          setText("estimateSpeed", `${estimate.ecef_speed_kmh.toFixed(1)} km/h`);
          setText("estimateEcefVector", `${estimate.ecef_vx_mps.toFixed(1)} / ${estimate.ecef_vy_mps.toFixed(1)} / ${estimate.ecef_vz_mps.toFixed(1)} m/s`);
          setText("estimateVelocity", `${estimate.east_velocity_mps.toFixed(1)} / ${estimate.north_velocity_mps.toFixed(1)} / ${estimate.vertical_velocity_mps.toFixed(1)} m/s`);
          setText("estimateGround", `${estimate.ground_speed_kmh.toFixed(1)} km/h / ${estimate.heading_deg.toFixed(1)}°`);
          setText("estimatePath", `${estimate.flight_path_angle_deg.toFixed(2)}° / ${estimate.distance_from_pad_km.toFixed(1)} km`);
          setText("estimateQuality", `${estimate.phase_label} / ${estimate.derivative_quality_code}`);
        }
        if (announce) {
          const trajectory = trajectoryAt(t);
          const provenance = trajectory ? trajectoryProvenanceAt(t) : null;
          $("ariaStatus").textContent = `已定位 T+ ${timeText(t)}。${provenance ? provenance.label : "当前无轨迹支持"}。`;
        }
        updateObjectTable(t);
        updateTrajectoryState(t);
        updatePropellantGauge(t);
      }

      function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
      function fitCanvas(canvas, ctx) {
        const rect = canvas.getBoundingClientRect();
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const width = Math.max(1, Math.round(rect.width * dpr));
        const height = Math.max(1, Math.round(rect.height * dpr));
        if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        return { width: rect.width, height: rect.height, dpr };
      }

      function projectPoint(latDeg, lonDeg, altitudeKm, width, height) {
        const lat = latDeg * Math.PI / 180, lon = lonDeg * Math.PI / 180;
        const r = (1 + Math.max(-20, altitudeKm || 0) / 6378.137) * state.zoom;
        const x = r * Math.cos(lat) * Math.cos(lon), y = r * Math.cos(lat) * Math.sin(lon), z = r * Math.sin(lat);
        const cy = Math.cos(state.yaw), sy = Math.sin(state.yaw);
        const x1 = cy * x - sy * y, y1 = sy * x + cy * y;
        const cp = Math.cos(state.pitch), sp = Math.sin(state.pitch);
        const depth = cp * y1 - sp * z, z2 = sp * y1 + cp * z;
        const radius = Math.min(width, height) * 0.43;
        return { x: width / 2 + x1 * radius, y: height / 2 - z2 * radius, depth, front: depth < 0 };
      }

      function rotateEcefVector(x, y, z) {
        const cy = Math.cos(state.yaw), sy = Math.sin(state.yaw);
        const x1 = cy * x - sy * y, y1 = sy * x + cy * y;
        const cp = Math.cos(state.pitch), sp = Math.sin(state.pitch);
        return {
          screenX: x1,
          screenY: -(sp * y1 + cp * z),
          depth: cp * y1 - sp * z,
        };
      }

      function drawArrow2d(startX, startY, dx, dy, color, label, dashed = false, labelNormalOffset = 0) {
        const length = Math.hypot(dx, dy);
        if (length < 1) return;
        const ux = dx / length, uy = dy / length;
        const endX = startX + dx, endY = startY + dy;
        gctx.save();
        gctx.strokeStyle = color;
        gctx.fillStyle = color;
        gctx.lineWidth = 2;
        if (dashed) gctx.setLineDash([5, 4]);
        gctx.beginPath(); gctx.moveTo(startX, startY); gctx.lineTo(endX, endY); gctx.stroke();
        gctx.setLineDash([]);
        gctx.beginPath();
        gctx.moveTo(endX, endY);
        gctx.lineTo(endX - ux * 9 - uy * 4.5, endY - uy * 9 + ux * 4.5);
        gctx.lineTo(endX - ux * 9 + uy * 4.5, endY - uy * 9 - ux * 4.5);
        gctx.closePath(); gctx.fill();
        gctx.font = '600 11px "Segoe UI", sans-serif';
        gctx.textBaseline = "middle";
        gctx.fillText(label, endX + ux * 7 - uy * labelNormalOffset, endY + uy * 7 + ux * labelNormalOffset);
        gctx.restore();
      }

      function drawVelocityVector(anchor, vx, vy, vz, color, label, dashed = false, labelNormalOffset = 0) {
        if (!anchor?.front || ![vx, vy, vz].every(finite)) return false;
        const rotated = rotateEcefVector(vx, vy, vz);
        const magnitude = Math.hypot(vx, vy, vz);
        const projected = Math.hypot(rotated.screenX, rotated.screenY);
        if (magnitude < 1e-9) return false;
        gctx.save();
        if (projected / magnitude < 0.08) {
          gctx.strokeStyle = color; gctx.fillStyle = color; gctx.lineWidth = 2;
          gctx.beginPath(); gctx.arc(anchor.x, anchor.y, 7, 0, Math.PI * 2); gctx.stroke();
          if (rotated.depth < 0) {
            gctx.beginPath(); gctx.arc(anchor.x, anchor.y, 2.2, 0, Math.PI * 2); gctx.fill();
          } else {
            gctx.beginPath(); gctx.moveTo(anchor.x - 3.5, anchor.y - 3.5); gctx.lineTo(anchor.x + 3.5, anchor.y + 3.5); gctx.moveTo(anchor.x + 3.5, anchor.y - 3.5); gctx.lineTo(anchor.x - 3.5, anchor.y + 3.5); gctx.stroke();
          }
          gctx.font = '600 11px "Segoe UI", sans-serif';
          gctx.fillText(`${label} · 近视线`, anchor.x + 11, anchor.y - 8);
          gctx.restore();
          return true;
        }
        gctx.restore();
        const visualLength = 46;
        drawArrow2d(
          anchor.x,
          anchor.y,
          rotated.screenX / projected * visualLength,
          rotated.screenY / projected * visualLength,
          color,
          label,
          dashed,
          labelNormalOffset,
        );
        return true;
      }

      function drawEcefTriad(width, height) {
        if (!$("showEcefAxes").checked) return;
        const origin = { x: 54, y: Math.min(66, height * 0.25) };
        const axes = [
          ["Xₑ", 1, 0, 0, "#ff7070"],
          ["Yₑ", 0, 1, 0, "#66d58a"],
          ["Zₑ", 0, 0, 1, "#68a9ff"],
        ];
        gctx.save();
        gctx.fillStyle = "rgba(3,12,19,.72)";
        gctx.beginPath(); gctx.roundRect(origin.x - 42, origin.y - 42, 94, 91, 8); gctx.fill();
        axes.forEach(([label, x, y, z, color]) => {
          const vector = rotateEcefVector(x, y, z);
          const projected = Math.hypot(vector.screenX, vector.screenY);
          if (projected < 0.08) {
            gctx.strokeStyle = color; gctx.fillStyle = color; gctx.lineWidth = 1.6;
            gctx.beginPath(); gctx.arc(origin.x, origin.y, 5, 0, Math.PI * 2); gctx.stroke();
            if (vector.depth < 0) { gctx.beginPath(); gctx.arc(origin.x, origin.y, 1.7, 0, Math.PI * 2); gctx.fill(); }
            gctx.font = '600 10px "Segoe UI", sans-serif'; gctx.fillText(label, origin.x + 7, origin.y - 7);
          } else {
            drawArrow2d(origin.x, origin.y, vector.screenX * 31, vector.screenY * 31, color, label, false);
          }
        });
        gctx.fillStyle = "#eef7fb"; gctx.beginPath(); gctx.arc(origin.x, origin.y, 2.2, 0, Math.PI * 2); gctx.fill();
        gctx.font = '10px "Segoe UI", sans-serif'; gctx.fillStyle = "rgba(235,246,252,.82)"; gctx.fillText("ECEF", origin.x - 17, origin.y + 42);
        gctx.restore();
      }

      function drawGeoLine(points, width, height, color, lineWidth = 1) {
        gctx.strokeStyle = color; gctx.lineWidth = lineWidth; gctx.beginPath();
        let active = false;
        points.forEach((point) => {
          const p = projectPoint(point[0], point[1], point[2] || 0, width, height);
          if (!p.front) { active = false; return; }
          if (!active) { gctx.moveTo(p.x, p.y); active = true; } else gctx.lineTo(p.x, p.y);
        });
        gctx.stroke();
      }

      function drawGlobe() {
        if (!state.data) return;
        const { width, height } = fitCanvas(globe, gctx);
        gctx.clearRect(0, 0, width, height);
        const radius = Math.min(width, height) * 0.43 * state.zoom;
        const cx = width / 2, cy = height / 2;
        const sphere = gctx.createRadialGradient(cx - radius * 0.28, cy - radius * 0.3, radius * 0.1, cx, cy, radius);
        sphere.addColorStop(0, "#194d69"); sphere.addColorStop(0.72, "#0b2a3e"); sphere.addColorStop(1, "#06131e");
        gctx.fillStyle = sphere; gctx.beginPath(); gctx.arc(cx, cy, radius, 0, Math.PI * 2); gctx.fill();
        gctx.strokeStyle = "rgba(142,201,229,0.38)"; gctx.lineWidth = 1; gctx.stroke();
        for (let lat = -60; lat <= 60; lat += 30) {
          const points = []; for (let lon = -180; lon <= 180; lon += 3) points.push([lat, lon, 0]);
          drawGeoLine(points, width, height, "rgba(139,191,217,0.18)", 0.7);
        }
        for (let lon = -180; lon < 180; lon += 30) {
          const points = []; for (let lat = -90; lat <= 90; lat += 3) points.push([lat, lon, 0]);
          drawGeoLine(points, width, height, "rgba(139,191,217,0.18)", 0.7);
        }

        if ($("showEstimate").checked) {
          const estimated = [];
          for (let index = 0; index < state.trajectory.length; index += 4) {
            const row = state.trajectory[index];
            estimated.push([row.latitude_deg, row.longitude_deg, row.ellipsoid_altitude_km]);
          }
          const last = state.trajectory[state.trajectory.length - 1];
          if (last) estimated.push([last.latitude_deg, last.longitude_deg, last.ellipsoid_altitude_km]);
          gctx.setLineDash([5, 5]); drawGeoLine(estimated, width, height, "rgba(255,190,78,0.78)", 1.6); gctx.setLineDash([]);
        }

        state.globeHits = [];
        state.fixes.forEach((fix) => {
          if (fix.aligned_tplus_s > T_MAX + 1) return;
          const p = projectPoint(fix.latitude_deg, fix.longitude_deg, fix.source_altitude_m / 1000, width, height);
          gctx.fillStyle = p.front ? "rgba(88,214,241,0.92)" : "rgba(88,214,241,0.15)";
          gctx.beginPath(); gctx.arc(p.x, p.y, p.front ? 2.3 : 1.4, 0, Math.PI * 2); gctx.fill();
          if (p.front) state.globeHits.push({ x: p.x, y: p.y, fix });
        });

        const pair = neighbors(state.fixes, state.t, "aligned_tplus_s");
        [[pair.previous, "#57d9ff", 5], [pair.next, "#f7d35d", 5]].forEach(([fix, color, size]) => {
          if (!fix || fix.aligned_tplus_s > T_MAX + 1) return;
          const p = projectPoint(fix.latitude_deg, fix.longitude_deg, fix.source_altitude_m / 1000, width, height);
          if (!p.front) return;
          gctx.strokeStyle = color; gctx.lineWidth = 2; gctx.beginPath(); gctx.arc(p.x, p.y, size, 0, Math.PI * 2); gctx.stroke();
        });

        const exact = nearest(state.fixes, state.t, "aligned_tplus_s");
        if (exact && Math.abs(exact.aligned_tplus_s - state.t) <= 0.55) {
          const p = projectPoint(exact.latitude_deg, exact.longitude_deg, exact.source_altitude_m / 1000, width, height);
          if (p.front) { gctx.fillStyle = "#ffffff"; gctx.beginPath(); gctx.arc(p.x, p.y, 5, 0, Math.PI * 2); gctx.fill(); }
        }
        if ($("showEstimate").checked) {
          const estimate = trajectoryAt(state.t);
          if (estimate) {
            const p = projectPoint(estimate.latitude_deg, estimate.longitude_deg, estimate.ellipsoid_altitude_km, width, height);
            if (p.front) { gctx.fillStyle = "#ffbd4a"; gctx.beginPath(); gctx.moveTo(p.x, p.y - 7); gctx.lineTo(p.x + 6, p.y + 5); gctx.lineTo(p.x - 6, p.y + 5); gctx.closePath(); gctx.fill(); }
          }
        }

        if ($("showVelocity").checked) {
          const interval = trackerIntervalAt(state.t);
          if (interval) {
            const anchor = projectPoint(interval.mid_latitude_deg, interval.mid_longitude_deg, interval.mid_altitude_km, width, height);
            drawVelocityVector(
              anchor,
              interval.avg_ecef_vx_mps,
              interval.avg_ecef_vy_mps,
              interval.avg_ecef_vz_mps,
              "#58d6f4",
              `V̄区间 ${interval.avg_ecef_speed_kmh.toFixed(0)} km/h`,
              true,
              -11,
            );
          }
          if ($("showEstimate").checked) {
            const estimate = trajectoryAt(state.t);
            if (estimate) {
              const anchor = projectPoint(estimate.latitude_deg, estimate.longitude_deg, estimate.ellipsoid_altitude_km, width, height);
              drawVelocityVector(
                anchor,
                estimate.ecef_vx_mps,
                estimate.ecef_vy_mps,
                estimate.ecef_vz_mps,
                "#ffbd4a",
                `V模型 ${estimate.ecef_speed_kmh.toFixed(0)} km/h`,
                false,
                11,
              );
            }
          }
        }

        drawEcefTriad(width, height);

        const closest = nearest(state.fixes, state.t, "aligned_tplus_s");
        const before = pair.previous ? `${(state.t - pair.previous.aligned_tplus_s).toFixed(1)} s` : "无";
        const after = pair.next ? `${(pair.next.aligned_tplus_s - state.t).toFixed(1)} s` : "无";
        const currentTrajectory = trajectoryAt(state.t);
        const projection = currentTrajectory ? projectPoint(currentTrajectory.latitude_deg, currentTrajectory.longitude_deg, currentTrajectory.ellipsoid_altitude_km, width, height) : null;
        const hiddenHint = projection && !projection.front ? " · 当前点在地球背面，可点击“对准当前”" : "";
        if (currentTrajectory) {
          const provenance = trajectoryProvenanceAt(state.t);
          $("mapStatus").textContent = `${provenance.label} · 原始观测前 ${before} / 后 ${after}${hiddenHint}`;
        } else {
          $("mapStatus").textContent = `当前无轨迹支持 · 原始观测前 ${before} / 后 ${after}`;
        }
      }

      function prepareTimeline() {
        const layouts = [];
        state.objectTelemetry.forEach((sample) => {
          const start = clamp(sample.tplus_s - 0.5);
          const end = clamp(sample.tplus_s + 0.5);
          const last = layouts[layouts.length - 1];
          if (last && last.layout === sample.layout && start <= last.end + 0.015) {
            last.end = Math.max(last.end, end);
          } else {
            layouts.push({ layout: sample.layout, start, end });
          }
        });
        state.timelineData = { layouts };
      }

      function drawTimeline() {
        if (!state.data) return;
        const { width, height } = fitCanvas(timeline, tctx);
        tctx.clearRect(0, 0, width, height);
        const labelWidth = width < 520 ? 48 : 64, right = 8, plotWidth = width - labelWidth - right;
        const x = (t) => labelWidth + clamp(t) / T_MAX * plotWidth;
        tctx.font = "11px Segoe UI, sans-serif"; tctx.textBaseline = "middle";
        const y = 10, barHeight = 20;
        const layoutStyle = {
          integrated_stack_right: { color: "#3b82b5", label: "组合体" },
          dual_super_heavy_left_starship_right: { color: "#cf8d26", label: "飞船 + 助推器" },
          telemetry_layout_transition: { color: "#8a95a3", label: "切换" },
          starship_left: { color: "#2f8a62", label: "飞船" },
        };
        tctx.fillStyle = css("--muted"); tctx.fillText("HUD", 2, y + barHeight / 2);
        tctx.fillStyle = css("--surface-2"); tctx.fillRect(labelWidth, y, plotWidth, barHeight);
        state.timelineData.layouts.forEach(({ layout, start, end }) => {
          const style = layoutStyle[layout] || { color: "#8a95a3", label: layout || "未知" };
          const left = x(start), segmentWidth = Math.max(1, x(end) - left);
          tctx.fillStyle = style.color; tctx.fillRect(left, y, segmentWidth, barHeight);
          if (segmentWidth > 64) {
            tctx.save(); tctx.beginPath(); tctx.rect(left, y, segmentWidth, barHeight); tctx.clip();
            tctx.fillStyle = "#ffffff"; tctx.textAlign = "center"; tctx.fillText(style.label, left + segmentWidth / 2, y + barHeight / 2);
            tctx.restore(); tctx.textAlign = "start";
          }
        });
        tctx.strokeStyle = css("--accent"); tctx.lineWidth = 2; tctx.beginPath(); tctx.moveTo(x(state.t), 0); tctx.lineTo(x(state.t), height); tctx.stroke();
      }

      function syncAll(t, force = false, announce = false) {
        state.t = t;
        const clamped = clamp(t);
        if (state.draggingRange !== "timeRange") range.value = String(clamped);
        if (state.draggingRange !== "massTimeRange") massRange.value = String(clamped);
        if (state.draggingRange !== "ratedMassTimeRange") ratedMassRange.value = String(Math.min(clamped, RATED_MODEL.chartEndT));
        timeInput.value = clamped.toFixed(3);
        const now = performance.now();
        if (force || now - state.lastUiAt > 70) {
          state.lastUiAt = now; updatePanels(t, announce); updateRatedInversion(t); drawGlobe(); drawTimeline();
        }
        syncHud(clamped, force);
      }

      function seekTplus(t, announce = true) {
        const target = clamp(Number(t));
        syncAll(target, true, announce);
        if (Number.isFinite(video.duration)) video.currentTime = target + state.data.time.video_tplus_zero_pts_s;
      }

      function updateFromVideo(mediaTime, force = false) {
        if (state.draggingRange || !state.data) return;
        syncAll(mediaTime - state.data.time.video_tplus_zero_pts_s, force, false);
      }

      function scheduleVideoFrames() {
        if (!video.requestVideoFrameCallback || video.paused || state.videoFrameCallback !== null) return;
        state.videoFrameCallback = video.requestVideoFrameCallback((_now, metadata) => {
          state.videoFrameCallback = null;
          if (video.paused) return;
          updateFromVideo(metadata.mediaTime);
          scheduleVideoFrames();
        });
      }

      function cancelVideoFrames() {
        if (state.videoFrameCallback !== null && video.cancelVideoFrameCallback) {
          video.cancelVideoFrameCallback(state.videoFrameCallback);
        }
        state.videoFrameCallback = null;
      }

      function centerOn(latDeg, lonDeg) {
        state.yaw = -Math.PI / 2 - lonDeg * Math.PI / 180;
        state.pitch = latDeg * Math.PI / 180;
        drawGlobe();
      }

      function bindInteractions() {
        $("togglePlay").addEventListener("click", async () => { if (video.paused) await video.play(); else video.pause(); });
        video.addEventListener("play", () => { $("togglePlay").textContent = "暂停"; scheduleVideoFrames(); });
        video.addEventListener("pause", () => { cancelVideoFrames(); $("togglePlay").textContent = "播放"; updateFromVideo(video.currentTime, true); });
        video.addEventListener("ended", cancelVideoFrames);
        video.addEventListener("emptied", cancelVideoFrames);
        video.addEventListener("timeupdate", () => { if (!video.requestVideoFrameCallback || video.paused) updateFromVideo(video.currentTime); });
        video.addEventListener("seeked", () => updateFromVideo(video.currentTime, true));
        video.addEventListener("loadedmetadata", () => { video.currentTime = clamp(state.t) + state.data.time.video_tplus_zero_pts_s; });
        $("minusFrame").addEventListener("click", () => { video.pause(); seekTplus(state.t - FRAME_DT); });
        $("plusFrame").addEventListener("click", () => { video.pause(); seekTplus(state.t + FRAME_DT); });
        $("minusSecond").addEventListener("click", () => { video.pause(); seekTplus(state.t - 1); });
        $("plusSecond").addEventListener("click", () => { video.pause(); seekTplus(state.t + 1); });
        $("rateSelect").addEventListener("change", (event) => { video.playbackRate = Number(event.target.value); });
        for (const id of ["massInitialTotal", "massBoosterWeight", "massBoosterDry", "massShipDry"]) {
          $(id).addEventListener("input", () => applyMassParametersFromInputs(false));
          $(id).addEventListener("change", () => applyMassParametersFromInputs(true));
          $(id).addEventListener("blur", () => applyMassParametersFromInputs(true));
        }
        $("resetMassParameters").addEventListener("click", () => {
          writeMassParameterInputs(DEFAULT_MASS_PARAMETERS);
          applyMassParametersFromInputs(true);
        });
        for (const id of ["ratedBoosterSeaLevelTf", "ratedRaptorSeaLevelTf", "ratedRaptorVacuumTf", "ratedThrustUncertainty", "ratedRaptorDiameter", "ratedRaptorVacuumDiameter", "ratedVehicleDiameter", "ratedCdUncertainty", "ratedCdSubsonic", "ratedCdTransonic", "ratedCdSupersonic", "ratedCdHypersonic"]) {
          $(id).addEventListener("input", () => applyRatedParametersFromInputs(false));
          $(id).addEventListener("change", () => applyRatedParametersFromInputs(true));
          $(id).addEventListener("blur", () => applyRatedParametersFromInputs(true));
        }
        $("resetRatedParameters").addEventListener("click", () => {
          writeRatedParameterInputs(DEFAULT_RATED_PARAMETERS);
          applyRatedParametersFromInputs(true);
        });
        timeInput.addEventListener("change", () => { video.pause(); seekTplus(timeInput.value); });
        timeInput.addEventListener("keydown", (event) => {
          if (event.key !== "Enter") return;
          event.preventDefault(); video.pause(); seekTplus(timeInput.value);
        });
        function bindTimeRange(input) {
          input.addEventListener("pointerdown", () => { state.draggingRange = input.id; });
          input.addEventListener("input", () => {
            const target = Number(input.value); syncAll(target, true, false);
            requestAnimationFrame(() => { video.currentTime = target + state.data.time.video_tplus_zero_pts_s; });
          });
          const finish = () => {
            if (state.draggingRange !== input.id) return;
            state.draggingRange = false;
            seekTplus(input.value, true);
          };
          input.addEventListener("change", finish);
          input.addEventListener("pointerup", finish);
          input.addEventListener("pointercancel", finish);
        }
        bindTimeRange(range);
        bindTimeRange(massRange);
        bindTimeRange(ratedMassRange);
        document.querySelectorAll("[data-rated-seek]").forEach((button) => {
          button.addEventListener("click", () => {
            video.pause();
            seekTplus(Number(button.dataset.ratedSeek));
          });
        });
        $("prevFix").addEventListener("click", () => { const pair = neighbors(state.fixes, state.t - 0.001, "aligned_tplus_s"); if (pair.previous) seekTplus(pair.previous.aligned_tplus_s); });
        $("nextFix").addEventListener("click", () => { const pair = neighbors(state.fixes, state.t + 0.001, "aligned_tplus_s"); if (pair.next && pair.next.aligned_tplus_s <= T_MAX) seekTplus(pair.next.aligned_tplus_s); });
        $("showEstimate").addEventListener("change", () => { updatePanels(state.t); drawGlobe(); if ($("showEstimate").checked) $("estimateDetails").open = true; });
        $("showVelocity").addEventListener("change", drawGlobe);
        $("showEcefAxes").addEventListener("change", drawGlobe);
        hudFrame.addEventListener("load", () => syncHud(state.t));
        $("centerCurrent").addEventListener("click", () => {
          const target = $("showEstimate").checked ? trajectoryAt(state.t) : nearest(state.fixes, state.t, "aligned_tplus_s");
          if (target) centerOn(target.latitude_deg, target.longitude_deg);
        });

        timeline.addEventListener("click", (event) => {
          const rect = timeline.getBoundingClientRect(), labelWidth = rect.width < 520 ? 48 : 64;
          const fraction = clamp((event.clientX - rect.left - labelWidth) / Math.max(1, rect.width - labelWidth - 8), 0, 1);
          video.pause(); seekTplus(fraction * T_MAX);
        });
        globe.addEventListener("pointerdown", (event) => {
          state.rotating = true; state.pointerX = event.clientX; state.pointerY = event.clientY; globe.classList.add("dragging"); globe.setPointerCapture(event.pointerId);
        });
        globe.addEventListener("pointermove", (event) => {
          if (!state.rotating) return;
          state.yaw += (event.clientX - state.pointerX) * 0.008;
          state.pitch = Math.max(-1.45, Math.min(1.45, state.pitch + (event.clientY - state.pointerY) * 0.008));
          state.pointerX = event.clientX; state.pointerY = event.clientY; drawGlobe();
        });
        globe.addEventListener("pointerup", (event) => {
          const moved = Math.hypot(event.clientX - state.pointerX, event.clientY - state.pointerY);
          state.rotating = false; globe.classList.remove("dragging"); globe.releasePointerCapture(event.pointerId);
          if (moved < 3) {
            const rect = globe.getBoundingClientRect(); const x = event.clientX - rect.left, y = event.clientY - rect.top;
            const hit = state.globeHits.reduce((best, item) => {
              const d = Math.hypot(item.x - x, item.y - y); return d < best.distance ? { item, distance: d } : best;
            }, { item: null, distance: 10 });
            if (hit.item) seekTplus(hit.item.fix.aligned_tplus_s);
          }
        });
        globe.addEventListener("wheel", (event) => { event.preventDefault(); state.zoom = Math.max(0.65, Math.min(1.22, state.zoom * (event.deltaY > 0 ? 0.94 : 1.06))); drawGlobe(); }, { passive: false });
        new ResizeObserver(() => { drawGlobe(); drawTimeline(); drawAbsoluteMass(); drawRatedCharts(); }).observe(document.querySelector(".app"));
      }

      async function init() {
        try {
          const response = await fetch("/viewer-data.json", { cache: "no-store" });
          if (!response.ok) throw new Error(`数据请求失败：HTTP ${response.status}`);
          state.data = await response.json();
          state.trajectory = rowsToObjects(state.data.trajectory);
          state.fixes = rowsToObjects(state.data.fixes);
          state.fixByRecord = new Map(state.fixes.map((fix) => [fix.record_index, fix]));
          state.trackerIntervals = rowsToObjects(state.data.tracker_intervals);
          state.telemetry = rowsToObjects(state.data.telemetry);
          state.objectTelemetry = rowsToObjects(state.data.telemetry_objects);
          state.objectTelemetryBySecond = new Map(state.objectTelemetry.map((sample) => [Math.round(sample.tplus_s), sample]));
          state.massSchedule = rowsToObjects(state.data.mass_schedule);
          state.ring = decodeRing(state.data.ring);
          writeMassParameterInputs(state.massParameters);
          writeRatedParameterInputs(state.ratedParameters);
          updateMassComposition();
          buildAbsoluteMassSeries();
          buildRatedMassSeries();
          prepareTimeline(); bindInteractions();
          video.src = state.data.video.route;
          $("loadStatus").textContent = "就绪";
          const requested = Number(new URLSearchParams(location.search).get("t"));
          const initialT = Number.isFinite(requested) ? clamp(requested) : 0;
          syncAll(initialT, true, true);
          ratedMassRange.value = String(Math.min(state.t, RATED_MODEL.chartEndT));
          updateRatedInversion(state.t);
        } catch (error) {
          $("loadStatus").textContent = error.message;
          $("loadStatus").className = "loading missing";
          console.error(error);
        }
      }
      init();
    })();
