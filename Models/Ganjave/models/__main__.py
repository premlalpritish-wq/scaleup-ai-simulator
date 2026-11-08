"""Command line entry point.

    cd Models/Ganjave && python -m models --help

Subcommands:

``parameters``  print the Table 2 parameter set as JSON
``reference``   print the paper's reported conditions and outcomes as JSON
``interface``   print the composition interface: ports, quantities, refusals
``simulate``    run a batch or fed-batch simulation and print the result

Exit codes: ``0`` success, ``1`` the run failed or produced an error
diagnostic, ``2`` the arguments were wrong.

Nothing here defaults an initial condition. ``--X``, ``--S2`` and ``--DO`` are
required for a batch run because the paper does not state them; the CLI refuses
rather than supplying one.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from schemas.parameters import table2_parameter_set

from . import composition, reference
from .fed_batch import FeedProgram
from .initial import build_initial_conditions
from .simulation import MODE_BATCH, MODE_FED_BATCH, simulate
from .solver import SolverConfig


def _emit(payload: Any) -> None:
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


def _add_initial_conditions(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--X", type=float, required=True,
        help="initial biomass concentration in g/L. Required: the paper reports "
             "an initial OD600 of 0.05 but no OD600-to-dry-cell-weight calibration.",
    )
    parser.add_argument(
        "--S2", type=float, required=True,
        help="initial complex-substrate concentration in g/L. Required: not "
             "stated in the paper.",
    )
    parser.add_argument(
        "--DO", type=float, required=True,
        help="initial dissolved oxygen in %% of saturation. Required: not "
             "stated in the paper.",
    )
    parser.add_argument(
        "--S1", type=float, default=None,
        help="initial glycerol in g/L (default: the reported 2.76 g/L)",
    )
    parser.add_argument(
        "--V", type=float, default=None,
        help="initial culture volume in L (default: the reported 0.1 L)",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m models",
        description=(
            "Executable cybernetic growth and fed-batch model of Ganjave et al. "
            "(2022), Biotechnology Reports 33:e00694, equations (1)-(16)."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("parameters", help="print the Table 2 parameter set")

    sub.add_parser("reference", help="print reported conditions and outcomes")

    sub.add_parser("interface", help="print the composition interface")

    run = sub.add_parser("simulate", help="run a simulation")
    run.add_argument(
        "--mode", choices=("batch", "fed_batch"), default=MODE_BATCH,
        help="operating mode; batch has no feed and no volume term",
    )
    run.add_argument(
        "--duration", type=float, required=True, help="integration time in hours"
    )
    run.add_argument(
        "--output-times", type=float, nargs="*", default=None,
        help="times in hours at which to record the trajectory exactly",
    )
    _add_initial_conditions(run)
    run.add_argument(
        "--glycerol-percent", type=float, default=None,
        help="feed glycerol in %% w/v (fed_batch). 1 %% w/v = 10 g/L.",
    )
    run.add_argument(
        "--yeast-percent", type=float, default=None,
        help="feed yeast extract in %% w/v (fed_batch). 1 %% w/v = 10 g/L.",
    )
    run.add_argument(
        "--flow-ml-h", type=float, default=None,
        help="volumetric feed rate in mL/h (fed_batch). 1 mL/h = 1e-3 L/h.",
    )
    run.add_argument(
        "--feed-start", type=float, default=0.0,
        help="time at which feeding starts, in hours (the paper starts at 6 h)",
    )
    run.add_argument("--rtol", type=float, default=SolverConfig().rtol)
    run.add_argument("--atol", type=float, default=SolverConfig().atol)
    run.add_argument(
        "--h-max", type=float, default=SolverConfig().h_max,
        help="largest integration step in hours (default 0.01, chosen from kLa)",
    )
    run.add_argument(
        "--summary", action="store_true",
        help="print a short summary instead of the whole trajectory",
    )
    return parser


def _summary(result) -> dict[str, Any]:
    final = result.final_state
    return {
        "ok": result.ok,
        "mode": result.mode,
        "duration_h": result.times_h[-1] if result.times_h else None,
        "points": len(result.states),
        "final_state": final.to_dict() if final else None,
        "solver_report": result.result.solver_report(),
        "diagnostics": [
            d.to_dict() for d in result.diagnostics
            if d.severity.value in ("warning", "error")
        ],
        "input_digest": result.provenance.input_digest,
    }


def _simulate(args: argparse.Namespace) -> int:
    mode = args.mode
    conditions = build_initial_conditions(
        X=args.X, S2=args.S2, DO=args.DO, mode=mode,
        S1=args.S1, V=args.V,
    )
    feed = None
    if mode == MODE_FED_BATCH:
        missing = [
            name for name, value in (
                ("--glycerol-percent", args.glycerol_percent),
                ("--yeast-percent", args.yeast_percent),
                ("--flow-ml-h", args.flow_ml_h),
            ) if value is None
        ]
        if missing:
            sys.stderr.write(
                f"fed_batch mode needs {', '.join(missing)}: eq. (13)-(16) read "
                f"S10, S20 and F.\n"
                f"The recipe the paper reports as its selected optimum is "
                f"--glycerol-percent 17.5 --yeast-percent 24.5 --flow-ml-h 0.72 "
                f"--feed-start 6.\n"
            )
            return 2
        feed = FeedProgram.from_recipe(
            args.glycerol_percent, args.yeast_percent, args.flow_ml_h,
            start_time_h=args.feed_start,
        )

    result = simulate(
        initial_conditions=conditions,
        duration_h=args.duration,
        mode=mode,
        feed=feed,
        solver=SolverConfig(rtol=args.rtol, atol=args.atol, h_max=args.h_max),
        output_times_h=args.output_times or None,
    )
    _emit(_summary(result) if args.summary else result.to_dict())
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "parameters":
            _emit(table2_parameter_set().to_dict())
            return 0
        if args.command == "reference":
            _emit(
                {
                    "manifest": reference.dataset_manifest(),
                    "operating_conditions": list(reference.operating_conditions()),
                    "feed_experiments": list(reference.feed_experiments()),
                    "observations": [o.to_dict() for o in reference.reported_observations()],
                    "unavailable_data": list(reference.unavailable_data()),
                    "selected_recipe": reference.selected_recipe(),
                }
            )
            return 0
        if args.command == "interface":
            _emit(composition.manifest())
            return 0
        if args.command == "simulate":
            return _simulate(args)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        return 2
    parser.error(f"unknown command {args.command!r}")  # pragma: no cover
    return 2


if __name__ == "__main__":
    raise SystemExit(main())