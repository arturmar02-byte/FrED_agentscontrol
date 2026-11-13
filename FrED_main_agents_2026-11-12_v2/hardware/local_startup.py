"""Process helpers used by FrED's regular main.py (no Qt or GPIO imports)."""
from pathlib import Path
import subprocess
import sys
import tempfile


def acquire_device_lock():
    import fcntl
    handle = (Path(tempfile.gettempdir()) / "fred-pi-hardware.lock").open("a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise RuntimeError("FrED is already running. Close the existing device program first.") from None
    return handle


def launch_camera(root, options, port):
    command = [sys.executable, "-u", str(root / "FrEDFiberMeasurewithStreamingv6/fiber_measure.py"),
               "--local", "--port", str(port), "--camera", str(options.camera),
               "--fps", str(options.fps), "--data-dir", str(options.data_dir)]
    for name in ("width", "height", "calibration"):
        value = getattr(options, name)
        if value is not None:
            command.extend(("--" + name, str(value)))
    return subprocess.Popen(command, cwd=root, start_new_session=True)


def stop_camera(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
