"""Timing, trace correlation and durable telemetry without Pi dependencies."""
import json
import csv
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from agent_runtime import AgentRuntime
from communication.schemas import Message, MessageType
from research.agent_metrics import AgentMetrics


def wait_until(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.005)
    if not predicate():
        raise AssertionError("Timed out waiting for agent work")


def hardware():
    fred = Mock(spec=("get_temperature", "get_diameter", "get_spooler_rpm", "get_diameter_status", "stop_all"))
    fred.get_temperature.return_value = 20
    fred.get_diameter.return_value = 0.35
    fred.get_spooler_rpm.return_value = 0
    fred.get_diameter_status.return_value = {"streaming": True, "age": 0.01}
    return fred


class RecorderTests(unittest.TestCase):
    def test_recent_percentiles_and_cumulative_mean_are_distinct(self):
        metrics = AgentMetrics(window=3)
        for value in (100, 1, 2, 3):
            metrics.record("message", "test", durations={"processing_ms": value})
        stats = metrics.snapshot()["groups"]["test"]["message"]["timings"]["processing_ms"]
        self.assertEqual(stats["count"], 4)
        self.assertEqual(stats["mean_ms"], 26.5)
        self.assertEqual(stats["max_ms"], 100)
        self.assertEqual(stats["p50_ms"], 2)
        self.assertAlmostEqual(stats["p95_ms"], 2.9)
        metrics.close()

    def test_jsonl_summary_csv_and_run_link_survive_close(self):
        with tempfile.TemporaryDirectory() as temporary:
            metrics = AgentMetrics(temporary, context=lambda: {"run_id": "run-123"})
            metrics.record("llm_call", "reasoning_agent", status="rejected",
                           durations={"inference_ms": 10.5}, response={"value": float("nan")})
            metrics.close()
            self.assertFalse(metrics._writer.is_alive())
            summary = json.loads((metrics.output_dir / "summary.json").read_text(encoding="utf-8"))
            events = [json.loads(line) for line in (metrics.output_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["run_id"], "run-123")
            self.assertEqual(events[0]["session_id"], metrics.session_id)
            self.assertIsNone(events[0]["response"]["value"])
            self.assertEqual(summary["groups"]["reasoning_agent"]["llm_call"]["rejected"], 1)
            self.assertTrue(summary["closed"])
            self.assertIsNone(summary["io_error"])
            self.assertIn("inference_ms", (metrics.output_dir / "timings.csv").read_text(encoding="utf-8"))
            with (metrics.output_dir / "events.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["run_id"], "run-123")
            self.assertEqual(float(rows[0]["inference_ms"]), 10.5)
            elapsed = metrics.snapshot()["elapsed_s"]
            time.sleep(0.01)
            self.assertEqual(metrics.snapshot()["elapsed_s"], elapsed)

    def test_full_disk_queue_drops_logging_without_blocking_processing(self):
        metrics = AgentMetrics(queue_size=1)
        # A stalled writer is represented without depending on a slow disk.
        metrics._writer = Mock()
        metrics.record("sample", "perception_agent")
        started = time.perf_counter()
        metrics.record("sample", "perception_agent")
        self.assertLess(time.perf_counter() - started, 0.1)
        self.assertEqual(metrics.snapshot()["dropped_events"], 1)
        self.assertEqual(metrics.snapshot()["groups"]["perception_agent"]["sample"]["count"], 2)

    def test_unwritable_output_exposes_failure_and_keeps_memory_metrics(self):
        with patch("research.agent_metrics.Path.mkdir", side_effect=PermissionError("read only")):
            metrics = AgentMetrics("not-writable")
        metrics.record("sample", "perception_agent", durations={"processing_ms": 1})
        self.assertIn("read only", metrics.snapshot()["io_error"])
        self.assertEqual(metrics.snapshot()["groups"]["perception_agent"]["sample"]["count"], 1)
        metrics.close()

    def test_process_resource_samples_are_exportable_without_display(self):
        metrics = AgentMetrics()
        metrics._last_resource_sample = (10, 2)
        with patch("research.agent_metrics.time.perf_counter", return_value=11), patch(
                "research.agent_metrics.time.process_time", return_value=2.2):
            metrics._sample_resources()
        snapshot = metrics.snapshot()
        self.assertAlmostEqual(snapshot["resources"]["cpu_percent"], 20)
        self.assertEqual(snapshot["recent_events"][-1]["kind"], "resources")
        self.assertEqual(snapshot["recent_events"][-1]["scope"], "control_agents_gui_process")
        metrics.close()


class RuntimeMetricsTests(unittest.TestCase):
    def test_queue_model_and_total_latency_are_separate_and_preview_never_dispatches(self):
        class SlowModel:
            model_name = "test-delay-model"
            provider = "unit-test"
            is_simulated = True

            def generate(self, prompt):
                time.sleep(0.02)
                return {"command": "set_fan_duty", "duty_cycle": 30,
                        "usage": {"input_tokens": 5, "output_tokens": 3}}

        fred = hardware()
        runtime = AgentRuntime(fred, enable_reasoning=True, model=SlowModel())
        request = Message(sender="test", receiver="reasoning_agent", message_type=MessageType.REQUEST,
                          payload={"prompt": "set fan to 30 percent", "preview": True})
        runtime.bus.publish(request)
        time.sleep(0.03)
        runtime.start()
        try:
            wait_until(lambda: runtime.snapshot()["groups"].get("reasoning_agent", {}).get("message", {}).get("count", 0) == 1)
            snapshot = runtime.snapshot()
            groups = snapshot["groups"]["reasoning_agent"]
            inference = groups["llm_call"]["timings"]["inference_ms"]["last_ms"]
            queue = groups["message"]["timings"]["queue_wait_ms"]["last_ms"]
            total = groups["llm_call"]["timings"]["request_latency_ms"]["last_ms"]
            self.assertGreaterEqual(inference, 15)
            self.assertGreaterEqual(queue, 25)
            self.assertGreaterEqual(total, inference + queue)
            self.assertEqual(runtime.controller_agent.inbox.qsize(), 0)
            self.assertEqual(snapshot["last_llm_call"]["message_id"], request.message_id)
            self.assertEqual(snapshot["last_llm_call"]["usage"]["input_tokens"], 5)
            self.assertIsNone(snapshot["last_llm_call"]["time_to_first_token_ms"])
            self.assertIsNone(snapshot["last_llm_call"]["cost_usd"])
            fred.stop_all.assert_not_called()
        finally:
            runtime.stop()

    def test_model_errors_and_rejections_are_visible_without_killing_worker(self):
        model = Mock()
        model.generate.side_effect = [RuntimeError("model unavailable"), {"command": "unknown"}]
        runtime = AgentRuntime(hardware(), enable_reasoning=True, model=model)
        runtime.start()
        try:
            with self.assertLogs("reasoning_agent", level="ERROR"):
                runtime.request_reasoning("first")
                wait_until(lambda: runtime.snapshot()["groups"].get("reasoning_agent", {}).get("message", {}).get("count", 0) == 1)
            runtime.request_reasoning("second")
            wait_until(lambda: runtime.snapshot()["groups"]["reasoning_agent"]["message"]["count"] == 2)
            stats = runtime.snapshot()["groups"]["reasoning_agent"]
            self.assertEqual(stats["llm_call"]["count"], 2)
            self.assertEqual(stats["llm_call"]["errors"], 1)
            self.assertEqual(stats["llm_call"]["rejected"], 1)
            self.assertTrue(runtime.reasoning_agent._thread.is_alive())
        finally:
            runtime.stop()

    def test_dashboard_requests_are_bounded_and_default_to_preview(self):
        runtime = AgentRuntime(hardware(), enable_reasoning=True)
        with self.assertRaises(ValueError):
            runtime.request_reasoning("before startup")
        runtime.reasoning_agent._running.set()
        for _ in range(8):
            runtime.request_reasoning("set fan to 10")
        with self.assertRaises(ValueError):
            runtime.request_reasoning("one too many")
        runtime.reasoning_agent._running.clear()
        while not runtime.reasoning_agent.inbox.empty():
            *_, message = runtime.reasoning_agent.inbox.get_nowait()
            self.assertTrue(message.payload["preview"])
        runtime.metrics.close()


if __name__ == "__main__":
    unittest.main()
