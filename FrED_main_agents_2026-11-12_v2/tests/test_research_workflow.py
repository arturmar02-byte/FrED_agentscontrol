"""Hardware-free regression tests for research exports and evaluation."""
import base64
from collections import deque
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch

from main import main
from research.metrics import CHANNELS, analyze_csv, channel_metrics


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "run.csv"

    def write_csv(self, times=(0, 1, 3), valid=(1, 1, 1), legacy=False):
        columns = ["Time (s)"]
        for measured, target, _ in CHANNELS.values():
            columns.extend((measured, target))
        if not legacy:
            columns.append("Diameter valid")
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, delimiter=";")
            writer.writeheader()
            for t, is_valid in zip(times, valid):
                row = {"Time (s)": str(t).replace(".", ",")}
                for name, (measured, target, _) in CHANNELS.items():
                    row[measured], row[target] = ("0,33", "0,35") if name == "diameter" else ("8", "10")
                if not legacy:
                    row["Diameter valid"] = is_valid
                writer.writerow(row)

    def test_nonuniform_time_integrals_use_recording_origin(self):
        result = channel_metrics([5, 6, 8], [2, 2, 2])
        for key, expected in {"IAE": 6, "ISE": 12, "ITAE": 9, "ITSE": 18}.items():
            self.assertAlmostEqual(result[key], expected)
        self.assertEqual(result["time_weighted_RMSE"], 2)

    def test_missing_sample_is_not_bridged(self):
        result = channel_metrics([0, 1, 2, 3], [2, None, 2, 2])
        self.assertEqual(result["IAE"], 2)
        self.assertEqual(result["covered_duration_s"], 1)
        self.assertAlmostEqual(result["coverage_fraction"], 1 / 3)

    def test_settling_requires_final_valid_window_and_dwell(self):
        result = channel_metrics([0, 1, 2, 3, 4], [2, 0, None, 0, 0], 0.1, 1)
        self.assertEqual(result["settling_time_from_recording_start_s"], 3)
        result = channel_metrics([0, 1, 2], [2, 0, 0], 0.1, 2)
        self.assertIsNone(result["settling_time_from_recording_start_s"])

    def test_csv_decimal_comma_hash_and_unmeasured_objectives(self):
        self.write_csv()
        result = analyze_csv(self.path)
        self.assertAlmostEqual(result["channels"]["diameter"]["IAE"], 0.06)
        self.assertEqual(result["source_sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())
        for key in ("power_W", "energy_J", "throughput"):
            self.assertIsNone(result[key])

    def test_invalid_diameter_has_no_false_zero_error(self):
        self.write_csv(valid=(0, 0, 0))
        result = analyze_csv(self.path)["channels"]["diameter"]
        self.assertEqual(result["valid_samples"], 0)
        self.assertIsNone(result["IAE"])

    def test_rejects_duplicate_and_nonfinite_time(self):
        for times in ((0, 1, 1), (0, float("nan"), 2)):
            self.write_csv(times=times)
            with self.assertRaises(ValueError):
                analyze_csv(self.path)

    def test_legacy_diameter_validity_is_explicit(self):
        self.write_csv(legacy=True)
        self.assertTrue(any("Legacy CSV" in w for w in analyze_csv(self.path)["warnings"]))

    def test_settling_requires_explicit_criteria(self):
        self.write_csv()
        with self.assertRaises(ValueError):
            analyze_csv(self.path, {"diameter": 0.02})
        with self.assertRaises(ValueError):
            analyze_csv(self.path, {"diameter": float("nan")}, 1)

    def test_cli_protects_existing_report(self):
        self.write_csv()
        report = Path(self.temp.name) / "metrics.json"
        with patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(main(["analyze", str(self.path), "--output", str(report)]), 0)
            original = report.read_bytes()
            self.assertEqual(main(["analyze", str(self.path), "--output", str(report)]), 2)
        self.assertEqual(report.read_bytes(), original)


class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The real database imports YAML. Only the in-memory buffers are needed
        # here, so load the actual protocol and experiment against those buffers.
        cls.database = type("Database", (), {})
        for name in ("temperature_readings", "temperature_setpoint", "temperature_error",
                     "temperature_pid_output", "temperature_kp", "temperature_ki", "temperature_kd",
                     "fan_duty_cycle", "extruder_rpm", "spooler_setpoint", "spooler_rpm",
                     "spooler_kp", "spooler_ki", "spooler_kd"):
            setattr(cls.database, name, [])
        database_module = types.ModuleType("database")
        database_module.Database = cls.database
        root = Path(__file__).resolve().parents[1] / "fred-device-extcv-pi4v6"
        for attribute, filename in (("external", "external_diameter.py"), ("experiment", "experiment.py")):
            spec = importlib.util.spec_from_file_location("research_test_" + attribute, root / filename)
            module = importlib.util.module_from_spec(spec)
            with patch.dict("sys.modules", {"database": database_module}):
                spec.loader.exec_module(module)
            setattr(cls, attribute, module)

    def setUp(self):
        self.gui = types.SimpleNamespace(get_target_diameter=lambda: 0.35,
                                         get_sample_period=lambda: 0.02)
        with patch.object(self.external.ExternalDiameter, "_serve_loop", lambda self: None):
            self.source = self.external.ExternalDiameter(None, self.gui)
        self.source._thread.join(timeout=1)
        self.source.connected = True
        self.source.update = Mock()
        self.gui.diameter_source = self.source
        self.run = self.experiment.Experiment(self.gui)
        self.addCleanup(self.source.close)
        self.actuators = (Mock(), Mock(), Mock())

    def measurement(self, **overrides):
        message = {"v": 1, "d": 0.35, "u": "mm", "found": True}
        message.update(overrides)
        self.source._handle_line(json.dumps(message).encode())

    def test_freshness_is_not_renewed_by_heartbeat(self):
        self.measurement()
        self.assertTrue(self.source.measurement_snapshot()["valid"])
        self.source.last_measurement_time = time.time() - 10
        self.source._handle_line(b'{"hb": true}')
        self.assertFalse(self.source.measurement_snapshot()["valid"])

    def test_units_do_not_contaminate_filter_and_invalid_values_are_rejected(self):
        self.measurement(d=50, u="px")
        self.assertFalse(self.source.measurement_snapshot()["valid"])
        self.measurement(d=0.35, u="mm")
        self.assertEqual(self.source.measurement_snapshot()["diameter"], 0.35)
        for value in (float("nan"), float("inf"), 0, -1):
            self.measurement(d=value)
            self.assertFalse(self.source.measurement_snapshot()["valid"])

    def test_loss_of_detection_is_blank_in_export(self):
        self.measurement(found=False)
        self.run._append_row(1)
        row = dict(zip(self.run.COLUMNS, self.run._rows[-1]))
        self.assertEqual(row["Diameter (mm)"], "")
        self.assertEqual(row["Diameter raw (mm)"], "")
        self.assertEqual(row["Diameter valid"], 0)

    def test_completed_run_roundtrip_has_reproducible_metadata(self):
        self.measurement()
        params = {"name": "baseline", "data_taking_time": 1,
                  "research_context": {"calibration": {"units": "mm"}}}
        self.run.start(params)
        params["research_context"]["calibration"]["units"] = "px"
        for t in (0, 0.1, 0.2, 0.3, 1.3):
            self.run.update(t, *self.actuators)
        payload = self.run.data_payload()
        metadata = payload["metadata"]
        csv_bytes = base64.b64decode(payload["b64"])
        self.assertTrue(metadata["recording_complete"])
        self.assertEqual(metadata["recorded_rows"], 2)
        self.assertEqual(metadata["csv_sha256"], hashlib.sha256(csv_bytes).hexdigest())
        self.assertEqual(metadata["parameters"]["research_context"]["calibration"]["units"], "mm")
        self.assertIsNotNone(metadata["recording_started_at_utc"])
        self.assertIsNotNone(metadata["finished_at_utc"])
        self.assertEqual(len(list(csv.reader(io.StringIO(csv_bytes.decode()), delimiter=";"))[0]), len(self.run._rows[0]))

    def test_active_run_cannot_be_overwritten(self):
        self.run.start({"name": "original"})
        run_id = self.run.run_id
        with self.assertRaises(ValueError):
            self.run.start({"name": "replacement"})
        self.assertEqual(self.run.run_id, run_id)
        self.assertEqual(self.run.csv_name, "original")

    def test_abort_keeps_partial_recording_and_stops_actuators(self):
        self.measurement()
        self.run.start({"data_taking_time": 10})
        for t in (0, 0.1, 0.2, 0.3):
            self.run.update(t, *self.actuators)
        self.run.abort()
        self.run.update(0.4, *self.actuators)
        payload = self.run.data_payload()
        self.assertFalse(payload["metadata"]["recording_complete"])
        self.assertEqual(payload["metadata"]["phase_at_retrieval"], "aborted")
        self.actuators[0].stop_heater.assert_called()
        self.actuators[0].stop_stepper.assert_called()
        self.actuators[1].stop_motor.assert_called()
        self.actuators[2].update_duty_cycle.assert_called_with(0)


if __name__ == "__main__":
    unittest.main()
