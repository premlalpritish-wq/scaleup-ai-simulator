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

Introspection flags
-------------------

``--list-models``, ``--describe-model <id>[@<version>]`` and
``--describe-contract`` answer the editor's questions about what *exists*
before it asks anything to be executed.  All three write JSON to stdout and exit
0 when the question has an answer.  ``--describe-model`` exits 3 when the
reference does not resolve to exactly one registered model, and its payload
lists the references that would; it never substitutes a model.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Mapping

from . import __version__
from .adapters import (
    REFERENCE_SEPARATOR,
    REGISTRATIONS,
    AdapterRegistration,
    adapter_for,
    known_models,
)
from .contracts import (
    CONTRACT_VERSION,
    ContractError,
    ModelManifest,
    PortDirection,
    RunStatus,
    load_graph,
)
from .diagnostics import DiagnosticCode, ModelDiagnostic, Origin, Severity
from . import compatibility
from . import cross_model
from . import cross_paper
from . import gaps as scientific_gaps
from . import prompt as prompt_interpreter
from . import report
from .engine import CompositionEngine
from .quantities import describe_registry

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_FAILED = 2
EXIT_BAD_INPUT = 3
EXIT_RUNNER_ERROR = 4


# --------------------------------------------------------------------------- #
# model reference resolution
#
# The editor asks "what is this model_id?" by name. A name that matches nothing,
# or that matches more than one registered version, must not be answered with a
# guess: it is answered with the list of references that *would* resolve.
# --------------------------------------------------------------------------- #


def _reference_error(
    message: str, remediation: str, where: tuple[str, ...]
) -> ModelDiagnostic:
    return ModelDiagnostic(
        code=DiagnosticCode.RUNNER_BAD_INPUT,
        severity=Severity.ERROR,
        message=message,
        where=where,
        origin=Origin.RUNNER,
        remediation=remediation,
    )


def registered_references() -> list[str]:
    """Every ``model_id@model_version`` this runner can reach, sorted."""
    return sorted(
        f"{reg.model_id}{REFERENCE_SEPARATOR}{reg.model_version}"
        for reg in REGISTRATIONS
    )


def resolve_model_reference(
    reference: str,
) -> tuple[AdapterRegistration | None, list[ModelDiagnostic]]:
    """Resolve ``<model_id>[@<version>]`` to exactly one registered model.

    Refuses rather than picking a candidate when the reference is empty, unknown,
    version-mismatched, or ambiguous because the same id is registered at more
    than one version.
    """
    raw = (reference or "").strip()
    where = ("runner", "--describe-model", raw)

    if not raw:
        return None, [
            _reference_error(
                "no model reference was given, so nothing was resolved.",
                f"Pass one of: {', '.join(registered_references())}.",
                where,
            )
        ]

    model_id, _, version = raw.partition(REFERENCE_SEPARATOR)
    model_id = model_id.strip()
    version = version.strip()

    if not model_id:
        return None, [
            _reference_error(
                f"{raw!r} has no model id before the "
                f"{REFERENCE_SEPARATOR!r} separator.",
                f"Use <model_id>{REFERENCE_SEPARATOR}<model_version>, one of: "
                f"{', '.join(registered_references())}.",
                where,
            )
        ]

    by_id = [reg for reg in REGISTRATIONS if reg.model_id == model_id]
    if not by_id:
        return None, [
            _reference_error(
                f"no model is registered under the id {model_id!r}. Nothing was "
                f"substituted: the composition layer does not guess which model "
                f"was meant.",
                f"Registered references: {', '.join(registered_references())}.",
                where,
            )
        ]

    versions = sorted({reg.model_version for reg in by_id})
    if len(by_id) > 1 and not version:
        return None, [
            _reference_error(
                f"{model_id!r} is registered at more than one version "
                f"({', '.join(versions)}), so a bare model id does not resolve to "
                f"one model.",
                f"Ask for one of: "
                f"{', '.join(f'{model_id}{REFERENCE_SEPARATOR}{v}' for v in versions)}.",
                where,
            )
        ]

    if version:
        matching = [reg for reg in by_id if reg.model_version == version]
        if not matching:
            return None, [
                _reference_error(
                    f"{model_id}{REFERENCE_SEPARATOR}{version} is not registered; "
                    f"the registered version is "
                    f"{', '.join(versions)}.",
                    f"Ask for {model_id}{REFERENCE_SEPARATOR}{versions[0]}, or "
                    f"install the version this runner declares.",
                    where,
                )
            ]
        if len(matching) > 1:
            return None, [
                _reference_error(
                    f"{model_id}{REFERENCE_SEPARATOR}{version} is registered more "
                    f"than once. The registry keeps one and will not choose.",
                    "This is a repository fault; report it rather than relying on "
                    "whichever registration happened to be read first.",
                    where,
                )
            ]
        return matching[0], []

    return by_id[0], []


def _manifest_note(manifest: ModelManifest | None, registration: AdapterRegistration
                   ) -> str:
    """Why there is a manifest, or why there is not. Never a substitute for one."""
    if manifest is not None:
        return (
            "The manifest is the model's own declaration for this contract: every "
            "port below is one the model publishes. It says nothing about whether "
            "the model is correct or scientifically compatible with another."
        )
    return (
        f"{registration.model_id} requires an instance declaration before it will "
        f"publish a manifest, so its port set is instance-parameterised rather than "
        f"empty. This is the difference between a model that declares no ports and "
        f"a model whose ports are not fixed. Ask again through a graph instance, "
        f"which supplies the instance parameters."
    )


def describe_model(
    reference: str, base: Path | None = None
) -> tuple[dict[str, Any], int]:
    """Describe one registered model: its exact identity and its manifest.

    Returns ``(payload, exit_code)``.  A model that legitimately declines to
    publish a manifest without instance parameters is **not** a failure: the
    payload says so, in ``port_dependence`` and in ``notes``, and the exit code
    is 0.  A reference that does not resolve to exactly one registered model is a
    failure, and names the references that would.
    """
    registration, diagnostics = resolve_model_reference(reference)
    if registration is None:
        payload = {
            "contract_version": CONTRACT_VERSION,
            "runner_version": __version__,
            "requested": (reference or "").strip(),
            "resolved": False,
            "model_id": None,
            "model_version": None,
            "reference": None,
            "package": None,
            "package_available": False,
            "port_dependence": None,
            "port_counts": {"input": 0, "output": 0},
            "manifest": None,
            "diagnostics": [d.to_dict() for d in diagnostics],
            "registered_references": registered_references(),
            "notes": (
                "The reference did not resolve to exactly one registered model. "
                "No model was substituted."
            ),
        }
        return payload, EXIT_BAD_INPUT

    adapter, load_diagnostics = adapter_for(registration.model_id, base)
    if adapter is None:
        diagnostics = diagnostics + list(load_diagnostics)
        payload = {
            "contract_version": CONTRACT_VERSION,
            "runner_version": __version__,
            "requested": (reference or "").strip(),
            "resolved": False,
            "model_id": registration.model_id,
            "model_version": registration.model_version,
            "reference": (
                f"{registration.model_id}{REFERENCE_SEPARATOR}"
                f"{registration.model_version}"
            ),
            "package": None,
            "package_available": False,
            "port_dependence": None,
            "port_counts": {"input": 0, "output": 0},
            "manifest": None,
            "diagnostics": [d.to_dict() for d in diagnostics],
            "registered_references": registered_references(),
            "notes": (
                "The model is registered but its package could not be reached. No "
                "manifest was invented for it."
            ),
        }
        return payload, EXIT_BAD_INPUT

    manifest: ModelManifest | None = None
    try:
        manifest, manifest_diagnostics = adapter.manifest({})
    except Exception as exc:  # noqa: BLE001 - reported, never raised at the CLI
        manifest, manifest_diagnostics = None, [
            ModelDiagnostic(
                code=DiagnosticCode.MANIFEST_INVALID,
                severity=Severity.ERROR,
                message=(
                    f"{registration.model_id} raised {type(exc).__name__} when asked "
                    f"for its manifest: {exc}. No port set was inferred from the "
                    f"failure."
                ),
                where=("manifest", registration.model_id),
                origin=Origin.MANIFEST,
                remediation=(
                    "Read the traceback in the runner output. This is a model or "
                    "adapter failure, not a missing declaration."
                ),
                model_id=registration.model_id,
                model_version=registration.model_version,
                detail={"traceback": traceback.format_exc()[-4000:]},
            )
        ]
    diagnostics = diagnostics + list(manifest_diagnostics)

    if manifest is not None:
        ports = list(manifest.ports)
        counts = {
            "input": sum(1 for p in ports if p.direction is PortDirection.INPUT),
            "output": sum(1 for p in ports if p.direction is PortDirection.OUTPUT),
        }
        dependence = "fixed"
        # The manifest contract check is reported, but it does not make the
        # description unusable: the editor shows the mismatch as a diagnostic.
        diagnostics.extend(manifest.validate_against_contract())
    else:
        counts = {"input": 0, "output": 0}
        dependence = "instance"

    payload = {
        "contract_version": CONTRACT_VERSION,
        "runner_version": __version__,
        "requested": (reference or "").strip(),
        "resolved": True,
        "model_id": registration.model_id,
        "model_version": registration.model_version,
        "reference": (
            f"{registration.model_id}{REFERENCE_SEPARATOR}{registration.model_version}"
        ),
        "package": str(adapter.worker.model_root),
        "package_available": bool(adapter.worker.available),
        "adapter": registration.worker_module,
        "port_dependence": dependence,
        "port_counts": counts,
        "manifest": manifest.to_dict() if manifest is not None else None,
        "diagnostics": [d.to_dict() for d in diagnostics],
        "registered_references": registered_references(),
        "notes": _manifest_note(manifest, registration),
    }
    return payload, EXIT_OK


def _error_result(
    graph_id: str,
    diagnostics: list[ModelDiagnostic],
    *,
    status: RunStatus,
    notes: str,
    composition_report: Mapping[str, Any] | None = None,
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
        # Every document this runner writes carries a report, including one that
        # never reached the engine. An absent report would read as "nothing to
        # assess", which is indistinguishable from a clean run.
        "composition_report": composition_report,
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
        # The input may be a JSON array, a string, or anything else that is not
        # a graph object at all, so the graph id is read defensively. Assuming
        # a mapping here would turn a clean "bad input" refusal into an
        # AttributeError -- an error about the runner on a document the runner
        # was never able to read.
        graph_id = (
            str(graph.get("graph_id", "unnamed"))
            if isinstance(graph, Mapping)
            else "unnamed"
        )
        return (
            _error_result(
                graph_id,
                diagnostics,
                status=RunStatus.INVALID,
                notes="The document does not satisfy the contract. Nothing was run.",
                composition_report=report.empty_report(
                    graph_id,
                    "The document could not be read as a composition graph, so no "
                    "connection was assessed. Nothing here says anything about "
                    "the models it names.",
                    diagnostics,
                ),
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
                composition_report=report.empty_report(
                    parsed.graph_id,
                    "The engine raised while assessing this graph, so no "
                    "connection has a verdict. The crash is not evidence about "
                    "the connections themselves.",
                    diagnostics,
                ),
            ),
            EXIT_RUNNER_ERROR,
        )

    payload = result.to_dict()
    payload["runner_version"] = __version__
    # Which paper encodes each instance, and what that model is relative to the
    # insulin process. The engine owns whether two instances are connected; this
    # block owns attribution, and it never claims a connection the graph lacks.
    payload["composition"] = compatibility.compose_block(payload.get("results"))

    if result.status is RunStatus.INVALID or result.status is RunStatus.REFUSED:
        return payload, EXIT_INVALID
    if result.status is RunStatus.FAILED:
        return payload, EXIT_FAILED
    return payload, EXIT_OK


def compare_composition(base: Path | None = None) -> dict[str, Any]:
    """Run the baseline replay and the multi-model composition, and compare them.

    Two in-process runs of two shipped graphs, then a values-only comparison of the
    insulin instance. Nothing is connected between the models, and the comparison
    exists to show that adding the second instance changed no baseline value.
    """
    root = base or Path(__file__).resolve().parents[2]
    plan = {
        "baseline": ("replay/zielinski_replay.json", "zielinski_replay"),
        "composed": ("replay/zielinski_multimodel.json", "zielinski_baseline"),
    }
    payloads: dict[str, dict[str, Any]] = {}
    codes: dict[str, int] = {}
    for name, (relative, _instance) in plan.items():
        path = root / "composition" / relative
        graph = json.loads(path.read_text(encoding="utf-8"))
        payload, code = run_graph(graph, base=base)
        payloads[name] = payload
        codes[name] = code

    comparison = compatibility.compare_runs(
        payloads["baseline"],
        payloads["composed"],
        baseline_instance=plan["baseline"][1],
        composed_instance=plan["composed"][1],
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "baseline": {
            "graph": plan["baseline"][0],
            "graph_id": payloads["baseline"].get("graph_id", ""),
            "status": payloads["baseline"].get("status", ""),
            "exit_code": codes["baseline"],
            "instance": plan["baseline"][1],
        },
        "composed": {
            "graph": plan["composed"][0],
            "graph_id": payloads["composed"].get("graph_id", ""),
            "status": payloads["composed"].get("status", ""),
            "exit_code": codes["composed"],
            "instance": plan["composed"][1],
        },
        "comparison": comparison,
        "composition": payloads["composed"].get("composition", {}),
        "note": (
            "The baseline is executed on its own graph; the composed run executes "
            "the same insulin configuration beside an independently runnable "
            "second model. The comparison is values-only, because attribution "
            "fields name the instance and must differ. A successful exit here is "
            "evidence that the pipeline and the separation work -- it is not "
            "evidence that either model's numbers are right."
        ),
    }


def _prompt_failure(interpretation: dict[str, Any]) -> dict[str, Any]:
    payload = dict(interpretation)
    clarification = interpretation.get("clarification", ()) or ()
    payload["status"] = "invalid"
    payload["error_count"] = max(1, len(clarification))
    payload["warning_count"] = len(interpretation.get("warnings", ()) or ())
    payload["results"] = []
    payload["prompt_interpretation"] = interpretation
    payload["notes"] = (
        "The prompt was not executed. The clarification and missing-information "
        "entries state what is needed; no default, process or scientific value "
        "was substituted."
    )
    payload["diagnostics"] = [
        {
            "code": item.get("code", "prompt.clarification"),
            "severity": "error",
            "message": item.get("message", ""),
            "where": ["prompt"],
            "origin": "runner",
        }
        for item in clarification
    ] + list(interpretation.get("diagnostics", ()) or ())
    return payload


def run_prompt(
    text: str, base: Path | None = None
) -> tuple[dict[str, Any], int]:
    """Interpret, validate, and execute one natural-language prompt.

    The configured graph is the original replay graph plus declared literal
    inputs. The original graph is also run, so the returned ``prompt_effect``
    can state whether any published value changed.
    """
    interpretation = prompt_interpreter.interpret(text, base=base)
    if not interpretation.get("ok") or not interpretation.get("validation", {}).get("ok", False):
        return _prompt_failure(interpretation), EXIT_BAD_INPUT

    manifest, diagnostics = prompt_interpreter.load_manifest(base)
    if manifest is None:
        interpretation["ok"] = False
        interpretation["status"] = "rejected"
        interpretation["clarification"] = [{
            "code": "model_unavailable",
            "message": "The Zielinski model package or manifest could not be read.",
        }]
        return _prompt_failure(interpretation), EXIT_RUNNER_ERROR

    graph = prompt_interpreter.build_graph(interpretation, base)
    validation = prompt_interpreter.validate_graph(graph, manifest)
    interpretation["validation"] = validation
    if not validation.get("ok"):
        interpretation["ok"] = False
        interpretation["status"] = "needs_clarification"
        interpretation["clarification"] = list(validation.get("errors", ()))
        return _prompt_failure(interpretation), EXIT_BAD_INPUT

    root = base or prompt_interpreter.ROOT
    baseline_graph = json.loads(
        (root / "composition/replay/zielinski_replay.json").read_text(encoding="utf-8")
    )
    baseline, baseline_code = run_graph(baseline_graph, base=base)
    configured, configured_code = run_graph(graph, base=base)
    configured["prompt_interpretation"] = interpretation
    configured["prompt_effect"] = prompt_interpreter.compare_effect(
        baseline, configured, interpretation
    )
    configured["prompt_effect"]["baseline_exit_code"] = baseline_code
    configured["prompt_effect"]["configured_exit_code"] = configured_code
    return configured, configured_code


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
        "--describe-model",
        metavar="<model_id>[@<version>]",
        help=(
            "print one registered model's exact identity and manifest as JSON and "
            "exit. An unknown or ambiguous reference fails with the references "
            "that would resolve; no model is substituted."
        ),
    )
    parser.add_argument(
        "--describe-contract",
        action="store_true",
        help="print the quantity/unit registry as JSON and exit",
    )
    parser.add_argument(
        "--describe-connections",
        action="store_true",
        help=(
            "print the declared cross-model connection position as JSON and "
            "exit: every ordered pair of registered models, whether a "
            "connection is permitted, the evidence, and what is unresolved"
        ),
    )
    parser.add_argument(
        "--describe-compatibility",
        action="store_true",
        help=(
            "print the standing of every model in the project against the "
            "Zielinski insulin simulation as JSON and exit: its classification, "
            "what was inspected, why it cannot contribute, and which dynamic "
            "connections the engine actually permits"
        ),
    )
    parser.add_argument(
        "--compare-composition",
        action="store_true",
        help=(
            "execute the baseline replay and the multi-model composition graph, "
            "compare the insulin instance's values across the two runs, and "
            "exit: reports whether adding the independent instance changed any "
            "baseline value"
        ),
    )
    parser.add_argument(
        "--describe-cross-paper-context",
        metavar="<model_id>[@<version>]",
        help=(
            "print the cross-paper scientific context for one registered "
            "model as JSON and exit: the other registered models, what they "
            "share with it, what the compatibility engine says about "
            "composing them, and the papers examined against its declared "
            "gaps"
        ),
    )
    parser.add_argument(
        "--describe-papers",
        action="store_true",
        help=(
            "print the ingested-paper corpus index as JSON and exit: every "
            "paper folder under Models/, the model that encodes it if one "
            "exists, whether that model is registered, and the recorded reason "
            "for the ones no model encodes. This is not a compatibility "
            "position -- an entry here is never an executable component"
        ),
    )
    parser.add_argument(
        "--describe-gaps",
        action="store_true",
        help=(
            "print the scientific gap discovery for the Zielinski insulin "
            "simulation as JSON and exit: the gaps declared by the model, the "
            "existing literature that partly informs or merely touches each "
            "one, the research recommendations, and the project's prior "
            "literature investigation. No model is executed or modified"
        ),
    )
    parser.add_argument(
        "--interpret-prompt",
        metavar="TEXT",
        help=(
            "interpret a natural-language request against the Zielinski manifest "
            "and print the structured interpretation, configuration and validation "
            "as JSON. Nothing is executed"
        ),
    )
    parser.add_argument(
        "--run-prompt",
        metavar="TEXT",
        help=(
            "interpret and validate a natural-language request, run the original "
            "Zielinski replay and the configured replay, and write the configured "
            "result with its prompt interpretation and an unchanged-baseline "
            "comparison"
        ),
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

    if args.describe_model is not None:
        payload, code = describe_model(args.describe_model, base)
        if args.result:
            write_result(Path(args.result), payload)
        json.dump(payload, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
        return code

    if args.describe_contract:
        json.dump(describe_registry(), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return EXIT_OK

    if args.describe_connections:
        payload = cross_model.describe()
        text = json.dumps(payload, indent=2) + "\n"
        if args.result:
            write_result(Path(args.result), payload)
        sys.stdout.write(text)
        return EXIT_OK

    if args.describe_compatibility:
        payload = compatibility.describe()
        payload["problems"] = compatibility.problem_messages(compatibility.problems())
        text = json.dumps(payload, indent=2, default=str) + "\n"
        if args.result:
            write_result(Path(args.result), payload)
        sys.stdout.write(text)
        return EXIT_OK

    if args.compare_composition:
        payload = compare_composition(base)
        text = json.dumps(payload, indent=2, default=str) + "\n"
        if args.result:
            write_result(Path(args.result), payload)
        sys.stdout.write(text)
        both_ok = (
            payload["baseline"]["exit_code"] == EXIT_OK
            and payload["composed"]["exit_code"] == EXIT_OK
        )
        return EXIT_OK if both_ok else EXIT_FAILED

    if args.describe_cross_paper_context is not None:
        payload, code = cross_paper.context_for(
            args.describe_cross_paper_context, base=base,
        )
        text = json.dumps(payload, indent=2, default=str) + "\n"
        if args.result:
            write_result(Path(args.result), payload)
        if code == EXIT_OK or not args.result:
            sys.stdout.write(text)
        return code

    if args.describe_papers:
        # Imported lazily: the evidence package is only needed for this question,
        # and it carries a Zielinski-specific catalogue the runner otherwise
        # never reads.
        from .evidence import papers as paper_index

        payload = paper_index.audit()
        text = json.dumps(payload, indent=2, default=str) + "\n"
        if args.result:
            write_result(Path(args.result), payload)
        sys.stdout.write(text)
        return EXIT_OK

    if args.describe_gaps:
        payload = scientific_gaps.describe()
        payload["problems"] = scientific_gaps.problems(payload)
        text = json.dumps(payload, indent=2, default=str) + "\n"
        if args.result:
            write_result(Path(args.result), payload)
        sys.stdout.write(text)
        return EXIT_OK

    if args.interpret_prompt is not None:
        payload = prompt_interpreter.interpret(args.interpret_prompt, base=base)
        text = json.dumps(payload, indent=2, default=str) + "\n"
        if args.result:
            write_result(Path(args.result), payload)
        sys.stdout.write(text)
        return EXIT_OK

    if args.run_prompt is not None:
        payload, code = run_prompt(args.run_prompt, base=base)
        text = json.dumps(payload, indent=2, default=str) + "\n"
        if args.result:
            write_result(Path(args.result), payload)
        sys.stdout.write(text)
        return code

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