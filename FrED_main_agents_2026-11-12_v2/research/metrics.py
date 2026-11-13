"""Evaluate FrED's wide experiment CSV using its recorded timestamps.

Only adjacent valid samples contribute to integrals: missing observations are
never interpolated. All integral indices use trapezoidal quadrature.
"""
import csv
import hashlib
import io
import math
from pathlib import Path


CHANNELS = {
    "temperature": ("Temperature (C)", "Temp setpoint (C)", "C"),
    "diameter": ("Diameter (mm)", "Diameter setpoint (mm)", "mm"),
    "spooler": ("Spooler RPM", "Spooler setpoint (RPM)", "RPM"),
}


def number(value):
    try:
        result = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def channel_metrics(times, errors, tolerance=None, minimum_dwell=None):
    """Return error indices, with coverage explicitly reported."""
    indices = {name: 0.0 for name in ("IAE", "ISE", "ITAE", "ITSE")}
    coverage = 0.0
    for i in range(1, len(times)):
        if errors[i - 1] is None or errors[i] is None:
            continue
        dt = times[i] - times[i - 1]
        coverage += dt
        a, b = errors[i - 1], errors[i]
        ta, tb = times[i - 1] - times[0], times[i] - times[0]
        indices["IAE"] += dt * (abs(a) + abs(b)) / 2
        indices["ISE"] += dt * (a * a + b * b) / 2
        indices["ITAE"] += dt * (ta * abs(a) + tb * abs(b)) / 2
        indices["ITSE"] += dt * (ta * a * a + tb * b * b) / 2
    if coverage == 0:
        indices = dict.fromkeys(indices)
    result = {
        **indices,
        "valid_samples": sum(error is not None for error in errors),
        "covered_duration_s": coverage,
        "coverage_fraction": coverage / (times[-1] - times[0]),
        "time_weighted_MAE": indices["IAE"] / coverage if coverage else None,
        "time_weighted_RMSE": math.sqrt(indices["ISE"] / coverage) if coverage else None,
        "settling_time_from_recording_start_s": None,
    }
    if tolerance is not None:
        if not math.isfinite(tolerance) or tolerance <= 0:
            raise ValueError("Settling tolerance must be finite and positive.")
        if minimum_dwell is None or not math.isfinite(minimum_dwell) or minimum_dwell <= 0:
            raise ValueError("Specify a positive minimum dwell for settling analysis.")
        last_outside = max(
            (i for i, e in enumerate(errors) if e is None or abs(e) > tolerance),
            default=-1,
        )
        first_inside = last_outside + 1
        if first_inside < len(times) and times[-1] - times[first_inside] >= minimum_dwell:
            result["settling_time_from_recording_start_s"] = times[first_inside] - times[0]
        result["settling_tolerance"] = tolerance
        result["minimum_dwell_s"] = minimum_dwell
    return result


def analyze_csv(path, tolerances=None, minimum_dwell=None):
    path = Path(path)
    raw = path.read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), delimiter=";")
    required = {"Time (s)"}
    for measured, target, _ in CHANNELS.values():
        required.update((measured, target))
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise ValueError("Expected a wide FrED experiment CSV; missing: " + ", ".join(sorted(missing)))
    rows = list(reader)
    if len(rows) < 2:
        raise ValueError("At least two recorded samples are required.")
    times = [number(row.get("Time (s)")) for row in rows]
    if any(t is None or t < 0 for t in times):
        raise ValueError("Every timestamp must be finite and nonnegative.")
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("Timestamps must be strictly increasing; samples are not sorted or deduplicated.")
    tolerances = tolerances or {}
    for tolerance in tolerances.values():
        if not math.isfinite(tolerance) or tolerance <= 0:
            raise ValueError("Settling tolerances must be finite and positive.")
    if tolerances and (minimum_dwell is None or not math.isfinite(minimum_dwell) or minimum_dwell <= 0):
        raise ValueError("Specify a positive minimum dwell for settling analysis.")
    channels = {}
    for name, (measured, target, unit) in CHANNELS.items():
        errors = []
        targets = []
        for row in rows:
            value, reference = number(row.get(measured)), number(row.get(target))
            if name == "diameter":
                if "Diameter valid" in row and number(row["Diameter valid"]) != 1:
                    value = None
                if value is not None and value <= 0:
                    value = None
            errors.append(reference - value if value is not None and reference is not None else None)
            if reference is not None:
                targets.append(reference)
        tolerance = tolerances.get(name)
        constant_target = bool(targets) and min(targets) == max(targets)
        metrics = channel_metrics(times, errors, tolerance if constant_target else None, minimum_dwell)
        channels[name] = {
            "unit": unit,
            **metrics,
            "constant_setpoint": constant_target,
        }
        if tolerance is not None and not constant_target:
            channels[name]["settling_unavailable_reason"] = "Split changing setpoints into separate step-response windows."
    warnings = [
        "Indices and settling cover the recording window only; heating and settle phases are excluded.",
        "CSV row rate is not the independent sensor acquisition or PID update rate.",
        "Trapezoidal integration uses adjacent valid samples only; check coverage before comparisons.",
    ]
    if "Diameter valid" not in (reader.fieldnames or []):
        warnings.append("Legacy CSV: diameter freshness, detection and units cannot be verified.")
    return {
        "schema_version": 1,
        "source": str(path.resolve()),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "samples": len(rows),
        "recording_start_s": times[0],
        "recorded_duration_s": times[-1] - times[0],
        "row_rate_hz": (len(rows) - 1) / (times[-1] - times[0]),
        "largest_row_interval_s": max(b - a for a, b in zip(times, times[1:])),
        "channels": channels,
        "power_W": None,
        "energy_J": None,
        "throughput": None,
        "missing_objective_measurements": [
            "Calibrated electrical power measurements with timestamps.",
            "An agreed throughput definition and its corresponding physical measurements; commanded RPM is not throughput.",
        ],
        "warnings": warnings,
    }
