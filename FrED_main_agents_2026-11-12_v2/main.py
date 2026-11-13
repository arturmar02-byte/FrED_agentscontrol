"""Laptop tools for preparing and evaluating FrED baseline experiments."""
import argparse
import json
from pathlib import Path
import socket
import sys

from research.metrics import analyze_csv


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check-connection", help="Probe SSH and the FrED TCP server; no actuator commands are sent.")
    check.add_argument("--host", default="192.168.4.1")
    check.add_argument("--port", type=int, default=5005)
    check.add_argument("--timeout", type=float, default=3.0)
    analyze = commands.add_parser("analyze", help="Calculate baseline metrics from the retrieved wide CSV.")
    analyze.add_argument("csv", type=Path)
    analyze.add_argument("--output", type=Path)
    analyze.add_argument("--temperature-tolerance", type=float, help="Absolute settling tolerance in C.")
    analyze.add_argument("--diameter-tolerance", type=float, help="Absolute settling tolerance in mm.")
    analyze.add_argument("--spooler-tolerance", type=float, help="Absolute settling tolerance in RPM.")
    analyze.add_argument("--minimum-dwell", type=float, help="Required final time inside the settling band, in seconds.")
    args = parser.parse_args(argv)
    try:
        if args.command == "check-connection":
            if not 0 < args.timeout <= 30 or not 1 <= args.port <= 65535:
                raise ValueError("Use timeout in (0, 30] and a valid TCP port.")
            result = {"host": args.host, "ports": {}}
            for name, port in (("ssh", 22), ("fred", args.port)):
                try:
                    with socket.create_connection((args.host, port), timeout=args.timeout):
                        result["ports"][name] = {"port": port, "reachable": True}
                except OSError as exc:
                    result["ports"][name] = {"port": port, "reachable": False, "error": str(exc)}
            result["note"] = "TCP reachability only; this does not verify sensors, calibration or readiness to actuate. Run before connecting the CV app."
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result["ports"]["fred"]["reachable"] else 1
        tolerances = {
            name: getattr(args, name + "_tolerance")
            for name in ("temperature", "diameter", "spooler")
            if getattr(args, name + "_tolerance") is not None
        }
        result = analyze_csv(args.csv, tolerances, args.minimum_dwell)
        content = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        if args.output:
            # Protect experimental evidence from accidental replacement.
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(content)
        print(content, end="")
        return 0
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
