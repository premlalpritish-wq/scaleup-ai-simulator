"""CLI for the Nanchen, Schicker & Sauer (2006) package.

    cd nanchen && python -m nanchen2006                      # manifest JSON
    cd nanchen && python -m nanchen2006 --write manifest.json
    cd nanchen && python -m nanchen2006 --check manifest.json
    cd nanchen && python -m nanchen2006 --validate
    cd nanchen && python -m nanchen2006 --run --mu 0.4
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
        prog="python -m nanchen2006",
        description="Emit the manifest, validate the transcription, or evaluate the model.",
    )
    parser.add_argument("--check", metavar="PATH",
                        help="exit 0 only if PATH holds exactly this manifest")
    parser.add_argument("--write", metavar="PATH",
                        help="write this manifest to PATH as UTF-8 (no BOM)")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--run", action="store_true",
                        help="evaluate Pirt's relation at --mu")
    parser.add_argument("--mu", type=float, default=0.4,
                        help="specific growth rate in 1/h (default 0.4)")
    args = parser.parse_args(argv)

    if args.validate:
        report = validate()
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        return 0 if report["ok"] else 1
    if args.run:
        p = model.THIS_STUDY
        summary = {
            "strain": p.strain,
            "mu_per_h": args.mu,
            "qglc_mmol_per_gdw_h": model.q_glc(args.mu, p.Yglc_max, p.mglc),
            "biomass_yield_gdw_per_mol": model.biomass_yield(
                args.mu, p.Yglc_max, p.mglc
            ),
            "mglc_mmol_per_gdw_h": p.mglc,
            "Yglc_max_gdw_per_mol": p.Yglc_max,
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
            f"it with 'python -m nanchen2006 --write {path.name}'\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
