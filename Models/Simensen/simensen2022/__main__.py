"""CLI for the Simensen et al. (2022) package.

    cd Simensen && python -m simensen2022                       # manifest JSON
    cd Simensen && python -m simensen2022 --write manifest.json
    cd Simensen && python -m simensen2022 --check manifest.json
    cd Simensen && python -m simensen2022 --validate
    cd Simensen && python -m simensen2022 --composition this_work
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import model
from .manifest import build_manifest
from .validate import validate


def _dump() -> str:
    return json.dumps(build_manifest(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m simensen2022",
        description="Emit the manifest, validate the transcription, or print a composition.",
    )
    parser.add_argument("--check", metavar="PATH",
                        help="exit 0 only if PATH holds exactly this manifest")
    parser.add_argument("--write", metavar="PATH",
                        help="write this manifest to PATH as UTF-8 (no BOM)")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--composition", metavar="COLUMN",
                        choices=sorted(model.COLUMNS),
                        help="print the top-level composition of a column")
    args = parser.parse_args(argv)

    if args.validate:
        report = validate()
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        return 0 if report["ok"] else 1
    if args.composition:
        summary = {
            "column": args.composition,
            "unit": "g/g (g gCDW-1)",
            "composition": model.composition(args.composition),
            "printed_sum": model.printed_sum(args.composition),
            "computed_sum": model.computed_macromolecule_sum(args.composition),
        }
        sys.stdout.write(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
        return 0

    text = _dump()
    if args.write is not None:
        Path(args.write).write_text(text, encoding="utf-8", newline="\n")
        return 0
    if args.check is None:
        sys.stdout.write(text)
        return 0

    path = Path(args.check)
    if not path.is_file():
        sys.stderr.write(f"{path}: no such file\n")
        return 2
    if path.read_text(encoding="utf-8") != text:
        sys.stderr.write(
            f"{path}: differs from the manifest this package declares; regenerate "
            f"it with 'python -m simensen2022 --write {path.name}'\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
