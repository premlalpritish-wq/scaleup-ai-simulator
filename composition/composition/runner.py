"""The composition runner: JSON in, JSON out, explicit exit status.

Godot invokes this and nothing else.  The contract with the editor is:

* the graph document goes in on ``--graph``;
* the result document comes out on ``--result``;
* the **exit status is the answer**, and it is never "probably fine".

Exit codes
----------

===  =========================================================================
0    the graph validated and executed; see ``status`` in the result for
     whether warnings were raised
1    the graph did not validate.  A result file is still written, with every
     diagnostic, so the editor has something to display
2    the graph validated and execution failed (a model failed, or a dependent
     instance was skipped).  A result file is written
3    the input was unusable: a missing file, malformed JSON, or a document that
     does not satisfy the contract.  A result file is written describing why
4    the runner itself could not run (internal error).  A result file is written
===  =========================================================================

A missing or malformed result file is therefore never treated as a successful
run: the editor checks the exit code first and the file second, and a
disagreement between them is reported as an error rather than resolved in the
editor's favour.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Mapping

from . import __version__
from .adapters import known_models
from .contracts import CONTRACT_VERSION, ContractError, RunStatus, load_graph
from .diagnostics import DiagnosticCode, ModelDiagnostic, Origin, Severity
from .engine import CompositionEngine
from .quantities import describe_registry

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_FAILED = 2
EXIT_BAD_INPUT = 3
EXIT_RUNNER_ERROR = 4


def _error_result(
    graph_id: str,
    diagnostics: list[ModelDiagnostic],
    *,
    status: RunStatus,
    notes: str,
) -> dict[str, Any]:
    return {
        "run_id": f"{graph_id}::error",
        "graph_id": graph_id,
        "contract_version": CONTRACT_VERSION,
        "status": status.value,
        "runner_version": __version__,
        "plan": {
            "plan_id": f"{graph_id}::error",
            "graph_id": graph_id,
            "contract_version": CONTRACT_VERSION,
            "order": [],
            "steps": [],
            "diagnostics": [],
            "digest": "",
        },
        "results": [],
        "diagnostics": [d.to_dict() for d in diagnostics],
        "provenance_index": {},
        "reproducibility": "",
        "model_versions": {},
        "error_count": sum(1 for d in diagnostics if d.is_error),
        "warning_count": sum(
            1 for d in diagnostics if d.severity is Severity.WARNING
        ),
        "notes": notes,
    }


def load_document(path: Path) -> tuple[Mapping[str, Any] | None, list[ModelDiagnostic]]:
    if not path.is_file():
        return None, [
            ModelDiagnostic(
                code=DiagnosticCode.RUNNER_BAD_INPUT,
                severity=Severity.ERROR,
                message=(
                    f"the graph document {path} does not exist. The run was not "
                    f"attempted and no result was inferred."
                ),
                where=("runner", str(path)),
                origin=Origin.RUNNER,
                remediation="Check the path, or load one of composition/examples/.",
            )
        ]
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except json.JSONDecodeError as exc:
        return None, [
            ModelDiagnostic(
                code=DiagnosticCode.RUNNER_BAD_INPUT,
                severity=Severity.ERROR,
                message=(
                    f"{path} is not valid JSON: {exc}. The runner refuses to guess "
                    f"what was meant; a malformed document is not an empty graph."
                ),
                where=("runner", str(path)),
                origin=Origin.RUNNER,
                remediation="Fix the JSON syntax.",
            )
        ]


def write_result(path: Path | None, payload: Mapping[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=False, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def run_graph(
    graph: Mapping[str, Any], *, plan_only: bool = False, base: Path | None = None
) -> tuple[dict[str, Any], int]:
    """Execute one graph document. Returns ``(result, exit_code)``."""
    try:
        parsed = load_graph(graph)
    except ContractError as exc:
        diagnostics = [
            ModelDiagnostic(
                code=DiagnosticCode.RUNNER_BAD_INPUT,
                severity=Severity.ERROR,
                message=str(exc),
                where=("runner", "graph"),
                origin=Origin.RUNNER,
                remediation=(
                    f"The runner implements contract {CONTRACT_VERSION}. Regenerate "
                    f"the document or upgrade the runner."
                ),
            )
        ]
        return (
            _error_result(
                graph.get("graph_id", "unnamed"),
                diagnostics,
                status=RunStatus.INVALID,
                notes="The document does not satisfy the contract. Nothing was run.",
            ),
            EXIT_BAD_INPUT,
        )

    engine = CompositionEngine(base_path=base)
    try:
        result = engine.execute(parsed, plan_only=plan_only)
    except Exception as exc:  # noqa: BLE001 - the runner must still report
        diagnostics = [
            ModelDiagnostic(
                code=DiagnosticCode.RUNNER_WORKER_CRASHED,
                severity=Severity.ERROR,
                message=(
                    f"the composition engine raised {type(exc).__name__}: {exc}. "
                    f"The run was abandoned; no partial success is reported."
                ),
                where=("runner", parsed.graph_id),
                origin=Origin.RUNNER,
                remediation="See the traceback in the runner output.",
                detail={"traceback": traceback.format_exc()[-4000:]},
            )
        ]
        return (
            _error_result(
                parsed.graph_id,
                diagnostics,
                status=RunStatus.FAILED,
                notes="The engine raised. Nothing was executed to completion.",
            ),
            EXIT_RUNNER_ERROR,
        )

    payload = result.to_dict()
    payload["runner_version"] = __version__

    if result.status is RunStatus.INVALID or result.status is RunStatus.REFUSED:
        return payload, EXIT_INVALID
    if result.status is RunStatus.FAILED:
        return payload, EXIT_FAILED
    return payload, EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m composition.runner",
        description="Run a ScaleUp AI composition graph.",
    )
    parser.add_argument("--graph", help="path to the graph JSON document")
    parser.add_argument("--result", help="path to write the result JSON document")
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="validate and order, but execute nothing",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="list the models this runner can reach and exit",
    )
    parser.add_argument(
        "--describe-contract",
        action="store_true",
        help="print the quantity/unit registry as JSON and exit",
    )
    parser.add_argument(
        "--repo-root", help="repository root, if it is not the default location"
    )
    args = parser.parse_args(argv)

    base = Path(args.repo_root).resolve() if args.repo_root else None

    if args.list_models:
        json.dump(
            {"contract_version": CONTRACT_VERSION,
             "runner_version": __version__,
             "models": known_models(base)},
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return EXIT_OK

    if args.describe_contract:
        json.dump(describe_registry(), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return EXIT_OK

    if not args.graph:
        diagnostics = [
            ModelDiagnostic(
                code=DiagnosticCode.RUNNER_BAD_INPUT,
                severity=Severity.ERROR,
                message="no --graph was supplied, so there is nothing to run.",
                where=("runner",),
                origin=Origin.RUNNER,
                remediation="Pass --graph <path>, or use --list-models.",
            )
        ]
        write_result(
            Path(args.result) if args.result else None,
            _error_result("unnamed", diagnostics, status=RunStatus.INVALID,
                          notes="No graph supplied."),
        )
        return EXIT_BAD_INPUT

    graph_path = Path(args.graph)
    document, diagnostics = load_document(graph_path)
    if document is None:
        result_path = Path(args.result) if args.result else None
        payload = _error_result(
            graph_path.stem,
            diagnostics,
            status=RunStatus.INVALID,
            notes="The graph document could not be read. Nothing was run.",
        )
        write_result(result_path, payload)
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return EXIT_BAD_INPUT

    payload, code = run_graph(document, plan_only=args.plan_only, base=base)
    result_path = Path(args.result) if args.result else None
    write_result(result_path, payload)

    if result_path is None:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        summary = {
            "run_id": payload.get("run_id"),
            "graph_id": payload.get("graph_id"),
            "status": payload.get("status"),
            "reproducibility": payload.get("reproducibility"),
            "errors": payload.get("error_count"),
            "warnings": payload.get("warning_count"),
            "result_file": str(result_path),
            "exit_code": code,
        }
        json.dump(summary, sys.stdout, indent=2)
        sys.stdout.write("\n")

    return code


if __name__ == "__main__":
    raise SystemExit(main())