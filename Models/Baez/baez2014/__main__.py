"""Print this package's manifest as JSON.

    cd Baez && python -m baez2014            # stdout
    cd Baez && python -m baez2014 --check manifest.json

Writes to stdout only, so nothing under the package is modified. `--check`
compares stdout against a file and exits non-zero on any difference, which is
how the committed `manifest.json` is kept from going stale.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .manifest import build_manifest


def _dump() -> str:
    return (
        json.dumps(build_manifest(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m baez2014",
        description="Emit the Baez et al. (2014) package manifest.",
    )
    parser.add_argument(
        "--check",
        metavar="PATH",
        help="exit 0 only if PATH holds exactly this manifest",
    )
    args = parser.parse_args(argv)

    text = _dump()
    if args.check is None:
        sys.stdout.write(text)
        return 0

    path = Path(args.check)
    if not path.is_file():
        sys.stderr.write(f"{path}: no such file\n")
        return 2
    if path.read_text(encoding="utf-8") != text:
        sys.stderr.write(
            f"{path}: differs from the manifest this package declares; "
            f"regenerate it with 'python -m baez2014 > {path.name}'\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())