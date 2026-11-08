"""CLI for the Lin et al. (2001) package.

    cd Lin && python -m lin2000                      # manifest JSON on stdout
    cd Lin && python -m lin2000 --check manifest.json
    cd Lin && python -m lin2000 --validate            # run the fidelity checks
    cd Lin && python -m lin2000 --run                 # integrate, print a summary

`--run` needs a feed protocol and the five unvalued constants. It reads them
from `--feed`/`--input` only; there are no defaults, so a run never quietly uses
a number the paper does not print.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import model
from .manifest import build_manifest
from .validate import check_parameters, validate


def _dump() -> str:
    return json.dumps(build_manifest(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _run(args: argparse.Namespace) -> int:
    try:
        p = model.SimulationParameters.from_culture(
            args.culture, cS=args.cS, cO=args.cO, kLa=args.kLa,
            DOT_star=args.DOT_star, H=args.H, variant=args.variant,
        )
    except model.ModelError as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    feed = (
        model.feed_constant(args.feed_rate)
        if args.feed == "constant"
        else model.feed_exponential(args.feed_rate, args.feed_constant_per_h)
    )
    result = model.simulate(
        p, feed, t_end=args.t_end, dt=args.dt, record_every=args.record_every
    )
    final = result.final()
    summary = {
        "culture": p.culture,
        "t_end": final.t,
        "final_state": final.state.to_dict(),
        "final_subsidiary": final.subsidiary.to_dict(),
        "samples": len(result.samples),
    }
    sys.stdout.write(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m lin2000",
        description="Emit the manifest, validate the transcription, or run the model.",
    )
    parser.add_argument("--check", metavar="PATH",
                        help="exit 0 only if PATH holds exactly this manifest")
    parser.add_argument("--write", metavar="PATH",
                        help="write this manifest to PATH as UTF-8 (no BOM)")
    parser.add_argument("--validate", action="store_true",
                        help="run the fidelity checks and print their report")
    parser.add_argument("--run", action="store_true", help="integrate the model once")
    parser.add_argument("--culture", default="w3110_exponential",
                        choices=sorted(model.params.CULTURES))
    parser.add_argument("--variant", default="growth_dependent",
                        choices=["growth_dependent", "constant_capacity"])
    parser.add_argument("--feed", default="constant", choices=["constant", "exponential"])
    parser.add_argument("--feed-rate", type=float, default=0.0532)
    parser.add_argument("--feed-constant-per-h", type=float, default=0.27)
    parser.add_argument("--t-end", type=float, default=1.0)
    parser.add_argument("--dt", type=float, default=0.005)
    parser.add_argument("--record-every", type=int, default=20)
    parser.add_argument("--cS", type=float, default=None)
    parser.add_argument("--cO", type=float, default=None)
    parser.add_argument("--kLa", type=float, default=None)
    parser.add_argument("--DOT-star", type=float, default=None)
    parser.add_argument("--H", type=float, default=None)
    args = parser.parse_args(argv)

    if args.validate:
        report = validate()
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        return 0 if report["ok"] else 1
    if args.run:
        return _run(args)

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
            f"it with 'python -m lin2000 > {path.name}'\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
