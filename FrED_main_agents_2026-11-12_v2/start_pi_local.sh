#!/bin/bash
# One desktop launcher for camera, experiments, device control and agents.
set -euo pipefail
FRED_ROOT="$(cd "$(dirname "$0")" && pwd)"
FRED_VENV="$FRED_ROOT/fred-device-extcv-pi4v6/fred-venv"
if [ "$#" -gt 0 ] && [[ "$1" != --* ]]; then
  FRED_VENV="$1"
  shift
fi
if [ ! -x "$FRED_VENV/bin/python" ]; then
  printf 'No Python environment found at %s\n' "$FRED_VENV"
  printf 'Run bash fred-device-extcv-pi4v6/setup_install.sh or supply an existing fred-venv path.\n'
  exit 1
fi
exec "$FRED_VENV/bin/python" "$FRED_ROOT/tools/run_pi_local.py" "$@"
