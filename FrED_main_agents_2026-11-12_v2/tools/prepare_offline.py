"""Build a verified FrED source bundle and laptop wheel cache while online."""
import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import zipfile


SOURCE_DIRS = ("agents", "communication", "config", "hardware", "llm", "research",
               "tests", "tools", "docs", "fred-device-extcv-pi4v6", "FrEDFiberMeasurewithStreamingv6")
EXTENSIONS = {".py", ".md", ".txt", ".sh", ".bat", ".json", ".yaml"}
PACKAGES = ("opencv-python", "numpy", "Pillow", "openpyxl", "et_xmlfile")


def copy_source(root, destination, pi_local=False):
    files = [root / name for name in ("README.md", "main.py", "agent_runtime.py", "start_pi_local.sh")]
    for directory in SOURCE_DIRS:
        files.extend(path for path in (root / directory).rglob("*")
                     if path.is_file() and path.suffix.lower() in EXTENSIONS
                     and not any(part in {"__pycache__", "Data", "fred-venv", ".venv", "venv"}
                                 for part in path.relative_to(root / directory).parts))
    for path in sorted(set(files)):
        relative = path.relative_to(root)
        # Never present repository calibration as the working Pi's calibration.
        if relative.as_posix() == "fred-device-extcv-pi4v6/calibration.yaml":
            relative = relative.with_name("calibration.example.yaml")
        if pi_local and relative.as_posix() == "FrEDFiberMeasurewithStreamingv6/calibration.json":
            relative = relative.with_name("calibration.example.json")
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        data = path.read_bytes()
        if path.suffix == ".sh":
            data = data.replace(b"\r\n", b"\n")
        output.write_bytes(data)


def build_bundle(root, output):
    output.mkdir(parents=True, exist_ok=False)
    copy_source(root, output)
    versions = {name: metadata.version(name) for name in PACKAGES}
    lock = output / "requirements.laptop.lock.txt"
    lock.write_text("".join(f"{name}=={version}\n" for name, version in versions.items()), encoding="utf-8")
    wheelhouse = output / "wheelhouse-laptop"
    wheelhouse.mkdir()
    subprocess.run([sys.executable, "-m", "pip", "download", "--disable-pip-version-check",
                    "--only-binary=:all:", "--dest", str(wheelhouse), "-r", str(lock)], check=True)
    interpreter = sys.executable
    install = (
        '@echo off\r\nsetlocal\r\ncd /d "%~dp0"\r\n'
        f'"{interpreter}" -m venv laptop-venv\r\nif errorlevel 1 exit /b 1\r\n'
        '"laptop-venv\\Scripts\\python.exe" -m pip install --no-index --find-links "wheelhouse-laptop" -r "requirements.laptop.lock.txt"\r\n'
        'if errorlevel 1 exit /b 1\r\n'
        '"laptop-venv\\Scripts\\python.exe" tools\\preflight.py laptop\r\npause\r\n'
    )
    (output / "INSTALL_LAPTOP_OFFLINE.bat").write_bytes(install.encode("utf-8"))
    launch = (
        '@echo off\r\nsetlocal\r\ncd /d "%~dp0"\r\n'
        'if not exist "laptop-venv\\Scripts\\python.exe" (\r\n'
        '  echo Run INSTALL_LAPTOP_OFFLINE.bat first.\r\n  pause\r\n  exit /b 1\r\n)\r\n'
        '"laptop-venv\\Scripts\\python.exe" tools\\preflight.py laptop\r\n'
        'if errorlevel 1 (\r\n  pause\r\n  exit /b 1\r\n)\r\n'
        '"laptop-venv\\Scripts\\python.exe" FrEDFiberMeasurewithStreamingv6\\fiber_measure.py\r\n'
        'if errorlevel 1 pause\r\n'
    )
    (output / "RUN_LAPTOP.bat").write_bytes(launch.encode("utf-8"))
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "laptop_python": platform.python_version(), "laptop_platform": platform.platform(),
        "laptop_interpreter": interpreter, "laptop_packages": versions,
        "pi_dependencies_included": False,
        "pi_requirement": "Reuse a working fred-venv, or install Pi dependencies while the Pi has internet.",
        "files_sha256": {},
    }
    for path in sorted(output.rglob("*")):
        if path.is_file():
            manifest["files_sha256"][path.relative_to(output).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    (output / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    archive = output.with_suffix(".zip")
    # Exclusive creation prevents replacement of a previous experimental bundle.
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as handle:
        for path in sorted(output.rglob("*")):
            if path.is_file():
                handle.write(path, Path(output.name) / path.relative_to(output))
    return archive


def build_pi_bundle(root, output):
    """Source-only transfer package; install ARM dependencies on the Pi."""
    output.mkdir(parents=True, exist_ok=False)
    copy_source(root, output, pi_local=True)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "target": "pi-local", "pi_dependencies_included": False,
        "pi_requirement": "Run setup_install.sh with internet on the Pi, then the normal start_fred.sh (device main.py). No hotspot required.",
        "files_sha256": {},
    }
    for path in sorted(output.rglob("*")):
        if path.is_file():
            manifest["files_sha256"][path.relative_to(output).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    (output / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    archive = output.with_suffix(".zip")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as handle:
        for path in sorted(output.rglob("*")):
            if path.is_file():
                handle.write(path, Path(output.name) / path.relative_to(output))
    return archive


def main(argv=None):
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root / "artifacts" / ("FrED_offline_" + datetime.now().strftime("%Y%m%d_%H%M%S")))
    parser.add_argument("--pi-local", action="store_true", help="Source-only Pi package, without Windows wheels.")
    args = parser.parse_args(argv)
    if args.pi_local:
        archive = build_pi_bundle(root, args.output.resolve())
        print(f"Pi local bundle: {archive}")
        print("Install ARM dependencies on the Pi with internet before the first local run.")
        return 0
    if sys.platform != "win32":
        parser.error("Build this laptop bundle on its Windows host to download compatible wheels.")
    archive = build_bundle(root, args.output.resolve())
    print(f"Offline bundle: {archive}")
    print("Pi dependencies are not included: verify the Pi environment before activating the hotspot.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
