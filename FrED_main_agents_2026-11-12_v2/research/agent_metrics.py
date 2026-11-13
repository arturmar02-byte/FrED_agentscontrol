"""Bounded in-memory timings and asynchronous, session-scoped research logs."""
from collections import deque
from contextlib import ExitStack
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from queue import Empty, Full, Queue
import threading
import time
import uuid


def json_safe(value, depth=0):
    if depth > 8:
        return "[depth limit]"
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return value[:8192]
    if isinstance(value, dict):
        return {str(k): json_safe(v, depth + 1) for k, v in list(value.items())[:100]}
    if isinstance(value, (tuple, list)):
        return [json_safe(v, depth + 1) for v in value[:100]]
    return str(value)[:8192]


class TimingSeries:
    def __init__(self, window):
        self.recent = deque(maxlen=window)
        self.count = 0
        self.total = 0.0
        self.maximum = 0.0

    def add(self, value):
        self.recent.append(value)
        self.count += 1
        self.total += value
        self.maximum = max(self.maximum, value)

    def snapshot(self):
        values = sorted(self.recent)

        def percentile(fraction):
            position = (len(values) - 1) * fraction
            lower = int(position)
            upper = min(lower + 1, len(values) - 1)
            return values[lower] + (values[upper] - values[lower]) * (position - lower)

        return {"count": self.count, "mean_ms": self.total / self.count,
                "max_ms": self.maximum, "last_ms": self.recent[-1],
                "p50_ms": percentile(0.5), "p95_ms": percentile(0.95),
                "percentile_samples": len(values)}


class AgentMetrics:
    def __init__(self, output_dir=None, context=None, window=512, queue_size=4096):
        self.session_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:10]
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.started_ns = time.perf_counter_ns()
        self.context = context
        self.window = window
        self._lock = threading.RLock()
        self._series = {}
        self._counts = {}
        self._latest = deque(maxlen=100)
        self._queue = Queue(maxsize=queue_size)
        self._stop = threading.Event()
        self._writer = None
        self.dropped_events = 0
        self.io_error = None
        self.closed = False
        self.ended_ns = None
        self.last_llm_call = None
        self._last_resource_sample = (time.perf_counter(), time.process_time())
        self.resources = {"cpu_percent": None, "rss_mib": None, "scope": "control_agents_gui_process"}
        self.output_dir = None
        if output_dir is not None:
            try:
                self.output_dir = Path(output_dir) / self.session_id
                self.output_dir.mkdir(parents=True, exist_ok=False)
                self._writer = threading.Thread(target=self._write_loop, name="agent-metrics-writer", daemon=True)
                self._writer.start()
            except OSError as exc:
                self.io_error = str(exc)

    def record(self, kind, agent, status="ok", durations=None, **details):
        """Never wait on disk; retain counters even when the disk queue fills."""
        now = time.perf_counter_ns()
        try:
            context = self.context() if self.context is not None else {}
        except Exception as exc:
            context = {"context_error": str(exc)}
        event = {"schema_version": 1, "session_id": self.session_id,
                 "utc": datetime.now(timezone.utc).isoformat(), "monotonic_ns": now,
                 "elapsed_s": (now - self.started_ns) / 1e9,
                 "kind": kind, "agent": agent, "status": status,
                 **context, **details, "durations_ms": durations or {}}
        event = json_safe(event)
        with self._lock:
            if self.closed:
                return
            key = (agent, kind)
            counts = self._counts.setdefault(key, {"count": 0, "errors": 0, "rejected": 0})
            counts["count"] += 1
            counts["errors"] += status == "error"
            counts["rejected"] += status in ("rejected", "blocked")
            for name, value in (durations or {}).items():
                if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0:
                    self._series.setdefault((agent, kind, name), TimingSeries(self.window)).add(value)
            self._latest.append(event)
            if kind == "llm_call":
                self.last_llm_call = event
            if self._writer is not None:
                if self.io_error:
                    self.dropped_events += 1
                else:
                    try:
                        self._queue.put_nowait(event)
                    except Full:
                        self.dropped_events += 1

    def snapshot(self):
        with self._lock:
            elapsed = ((self.ended_ns or time.perf_counter_ns()) - self.started_ns) / 1e9
            groups = {}
            for (agent, kind), counts in self._counts.items():
                groups.setdefault(agent, {})[kind] = {
                    **counts, "rate_hz_session": counts["count"] / elapsed if elapsed else 0,
                    "timings": {name: series.snapshot()
                                for (a, k, name), series in self._series.items() if (a, k) == (agent, kind)}}
            return {"schema_version": 1, "session_id": self.session_id,
                    "started_at_utc": self.started_at, "elapsed_s": elapsed,
                    "percentile_window": self.window, "groups": groups,
                    "dropped_events": self.dropped_events, "writer_queue": self._queue.qsize(),
                    "io_error": self.io_error, "closed": self.closed,
                    "output_dir": str(self.output_dir) if self.output_dir else None,
                    "recent_events": list(self._latest), "last_llm_call": self.last_llm_call,
                    "resources": dict(self.resources)}

    def _sample_resources(self):
        now = (time.perf_counter(), time.process_time())
        elapsed = now[0] - self._last_resource_sample[0]
        cpu = 100 * (now[1] - self._last_resource_sample[1]) / elapsed if elapsed > 0 else None
        self._last_resource_sample = now
        try:
            rss = int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1024**2
        except (OSError, ValueError, AttributeError, IndexError):
            rss = None
        with self._lock:
            self.resources = {"cpu_percent": cpu, "rss_mib": rss, "scope": "control_agents_gui_process"}
        self.record("resources", "runtime", **self.resources)

    def _write_summary(self):
        snapshot = self.snapshot()
        # Raw prompts/results remain in events.jsonl; summary stays compact.
        snapshot.pop("recent_events")
        snapshot.pop("last_llm_call")
        path = self.output_dir / "summary.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        temporary.replace(path)
        with (self.output_dir / "timings.csv").open("w", newline="", encoding="utf-8") as handle:
            fields = ("session_id", "agent", "kind", "metric", "count", "mean_ms", "max_ms",
                      "last_ms", "p50_ms", "p95_ms", "percentile_samples")
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for agent, kinds in snapshot["groups"].items():
                for kind, values in kinds.items():
                    for name, timing in values["timings"].items():
                        writer.writerow({"session_id": self.session_id, "agent": agent,
                                         "kind": kind, "metric": name, **timing})

    def _write_loop(self):
        pending_event = None
        try:
            with ExitStack() as stack:
                handle = stack.enter_context((self.output_dir / "events.jsonl").open("x", encoding="utf-8"))
                flat = stack.enter_context((self.output_dir / "events.csv").open("x", encoding="utf-8", newline=""))
                fields = ("session_id", "utc", "elapsed_s", "run_id", "experiment_phase", "kind", "agent", "status",
                          "message_id", "correlation_id", "model", "provider", "simulated", "preview", "error",
                          "processing_ms", "queue_wait_ms", "trace_latency_ms", "inference_ms", "request_latency_ms",
                          "handoff_ms", "observation_to_stop_ms", "time_to_first_token_ms", "cost_usd", "usage_json",
                          "cpu_percent", "rss_mib", "scope")
                csv_writer = csv.DictWriter(flat, fieldnames=fields, extrasaction="ignore")
                csv_writer.writeheader()
                last_flush = time.monotonic()
                while not self._stop.is_set() or not self._queue.empty():
                    try:
                        event = self._queue.get(timeout=0.2)
                    except Empty:
                        event = None
                    if event is not None:
                        pending_event = event
                        try:
                            handle.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
                            row = {**event, **event["durations_ms"]}
                            row["usage_json"] = json.dumps(event["usage"], ensure_ascii=False) if event.get("usage") is not None else None
                            csv_writer.writerow(row)
                            pending_event = None
                        finally:
                            self._queue.task_done()
                    if time.monotonic() - last_flush >= 2:
                        self._sample_resources()
                        handle.flush()
                        flat.flush()
                        self._write_summary()
                        last_flush = time.monotonic()
                handle.flush()
                flat.flush()
            self._write_summary()
        except Exception as exc:
            with self._lock:
                self.io_error = str(exc)
                self.dropped_events += self._queue.qsize() + int(pending_event is not None)

    def close(self):
        with self._lock:
            self.closed = True
            self.ended_ns = self.ended_ns or time.perf_counter_ns()
        self._stop.set()
        if self._writer is not None:
            self._writer.join(timeout=5)
            if self._writer.is_alive():
                with self._lock:
                    self.io_error = "Metrics writer did not finish within 5 seconds."
