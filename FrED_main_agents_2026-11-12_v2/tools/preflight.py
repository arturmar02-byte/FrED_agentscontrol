"""Check an offline FrED environment without starting the GUI or actuators."""
import argparse
import importlib
import json
import math
from pathlib import Path
import platform
import shutil
import sys


LAPTOP_IMPORTS = ("tkinter", "cv2", "numpy", "PIL.Image", "PIL.ImageTk", "openpyxl")
PI_IMPORTS = ("PyQt5.QtWidgets", "PyQt5.QtSvg", "matplotlib.backends.backend_qt5agg",
              "numpy", "yaml", "RPi.GPIO", "spidev", "board", "busio",
              "digitalio", "adafruit_mcp3xxx.mcp3008")
PI_LOCAL_IMPORTS = PI_IMPORTS + LAPTOP_IMPORTS + ("agent_runtime", "hardware.pi_runtime")


def check_environment(target, root):
    root = Path(root)
    result = {"target": target, "python": sys.executable,
              "python_version": platform.python_version(),
              "platform": platform.platform(), "checks": [],
              "scope": "Local dependency and configuration checks only; no GUI, camera, network or actuator startup."}

    def record(name, ok, detail):
        result["checks"].append({"name": name, "ok": bool(ok), "detail": str(detail)})

    record("python_version", sys.version_info >= (3, 9), "Python 3.9 or newer required by the current source.")
    imports = {"laptop": LAPTOP_IMPORTS, "pi": PI_IMPORTS, "pi-local": PI_LOCAL_IMPORTS}[target]
    for name in dict.fromkeys(imports):
        try:
            importlib.import_module(name)
            record(name, True, "Import available in this interpreter.")
        except Exception as exc:
            record(name, False, exc)
    if target == "laptop":
        calibration_path = root / "FrEDFiberMeasurewithStreamingv6" / "calibration.json"
        try:
            calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
            factor = calibration.get("units_per_pixel")
            valid = (isinstance(factor, (int, float)) and not isinstance(factor, bool)
                     and math.isfinite(factor) and factor > 0 and calibration.get("units") == "mm")
            record("camera_calibration_file", valid,
                   "Stored calibration in mm; physical scale and focus still need verification at the bench.")
        except (OSError, ValueError, TypeError) as exc:
            record("camera_calibration_file", False, exc)
    else:
        record("pi_platform", sys.platform.startswith("linux") and platform.machine().lower().startswith(("arm", "aarch64")),
               "Run this target on the Raspberry Pi, not on Windows.")
        if target == "pi":
            record("hotspot_tool", shutil.which("nmcli") is not None, "NetworkManager nmcli is required by setup_hotspot.sh.")
        else:
            cameras = sorted(str(path) for path in Path("/dev").glob("video*"))
            record("camera_devices", bool(cameras), cameras or "No V4L2 camera found. Connect the USB camera to the Pi.")
        calibration_path = root / "fred-device-extcv-pi4v6" / "calibration.yaml"
        try:
            yaml = importlib.import_module("yaml")
            calibration = yaml.safe_load(calibration_path.read_text(encoding="utf-8"))
            slope, intercept = calibration["motor_slope"], calibration["motor_intercept"]
            valid = (not isinstance(slope, bool) and not isinstance(intercept, bool)
                     and math.isfinite(float(slope)) and float(slope) > 0 and math.isfinite(float(intercept)))
            record("motor_calibration_file", valid, "Use the calibration from the working Pi installation.")
        except (OSError, ValueError, TypeError, KeyError, ImportError) as exc:
            record("motor_calibration_file", False, exc)
        spi_devices = sorted(str(path) for path in Path("/dev").glob("spidev*"))
        record("spi_devices", bool(spi_devices), spi_devices or "No SPI device found; check the Pi's SPI setting.")
    result["ok"] = all(check["ok"] for check in result["checks"])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("laptop", "pi", "pi-local"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    sys.path.insert(0, str(args.root.resolve()))
    result = check_environment(args.target, args.root)
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
