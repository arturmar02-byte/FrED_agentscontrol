"""Compatibility alias: the regular FrED main now owns local startup."""
from pathlib import Path
import os
import sys


def main(argv=None):
    root = Path(__file__).resolve().parents[1]
    arguments = list(sys.argv[1:] if argv is None else argv)
    os.execv(sys.executable, [sys.executable, str(root / "fred-device-extcv-pi4v6/main.py"),
                             *arguments])


if __name__ == "__main__":
    raise SystemExit(main())
