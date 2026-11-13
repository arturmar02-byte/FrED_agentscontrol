"""Verify offline bundle files against MANIFEST.json, without network access."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
    failures = []
    for name, expected in manifest["files_sha256"].items():
        relative = PurePosixPath(name)
        path = (root / relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(root):
            failures.append({"file": name, "reason": "Path outside the bundle."})
        elif not path.is_file():
            failures.append({"file": name, "reason": "File missing."})
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            failures.append({"file": name, "reason": "SHA-256 mismatch."})
    return {"ok": not failures, "verified_files": len(manifest["files_sha256"]), "failures": failures}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        result = verify(args.root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Verification failed: {exc}")
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
