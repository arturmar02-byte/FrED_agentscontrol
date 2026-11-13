#!/bin/bash
# Use the already working Pi virtual environment with the new source bundle.
set -euo pipefail
if [ "$#" -ne 1 ]; then
  printf 'Usage: bash tools/run_pi_offline.sh /absolute/path/to/existing/fred-venv\n'
  exit 1
fi
FRED_PYTHON="$1/bin/python"
if [ ! -x "$FRED_PYTHON" ] || [[ "$FRED_PYTHON" != /* ]]; then
  printf 'Provide an absolute path to a working fred-venv with bin/python.\n'
  exit 1
fi
FRED_BUNDLE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
"$FRED_PYTHON" "$FRED_BUNDLE_ROOT/tools/preflight.py" pi --root "$FRED_BUNDLE_ROOT"
cd "$FRED_BUNDLE_ROOT/fred-device-extcv-pi4v6"
exec "$FRED_PYTHON" main.py --external-camera
