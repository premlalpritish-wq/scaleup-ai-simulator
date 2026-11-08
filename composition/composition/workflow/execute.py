"""Workflow orchestration.

The workflow owns stages 1-5 (problem, literature, extraction, encoding, model
construction) and then hands a normal composition graph to the existing
:func:`composition.runner.run_graph`.  It does not re-implement the engine,
compatibility rules, contracts or result schema.

Every stage writes an inspectable artifact.  A later stage never runs on an
earlier stage's failure: a missing quote, an unacquired target paper or a blocked
problem stops the run before a graph exists.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ..adapters import repository_root
from ..adapters.base import JsonWorker
from ..adapters.rna import MODEL_ID as RNA_MODEL_ID
from ..adapters.rna import MODEL_VERSION as RNA_MODEL_VERSION
from ..adapters.rna import RnaEvidenceAdapter
from ..runner import run_graph
from .encoding import EncodingError, encode
from .extract import ExtractionError, extract_document
from .literature import (
    LiteratureError,
    acquire_selected,
    discover,
    load_corpus,
)
from .model_builder import build_graph, build_model_spec
from .problem import ProblemInput, load_problem
from .schema import (
    SourceText,
    WorkflowDiagnostic,
    WorkflowRun,
)


def _write_json(path: Path, payload: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path.as_posix()


def _resolve(base_dir: Path, value: str | None, default: str) -> Path:
    path = Path(value or default)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _blocked(problem_input: ProblemInput, out_dir: Path, message: str) -> WorkflowRun:
    problem = problem_input.problem
    artifacts = {
        "problem_spec": _write_json(
            out_dir / "problem_spec.json", problem.to_dict()
        )
    }
    diagnostic = WorkflowDiagnostic(
        code="workflow.problem_blocked",
        severity="error",
        message=message,
        where=("problem", problem.problem_id),
        remediation=(
            "Name the organism and target molecule in the problem statement, or "
            "declare them in the problem JSON. The workflow will not search for a "
            "problem it has not understood."
        ),
    )
    run = WorkflowRun(
        problem=problem,
        sources=[],
        encoded=None,
        model=None,
        graph=None,
        execution=None,
        diagnostics=[diagnostic],
        artifacts=artifacts,
        status="blocked",
        exit_code=3,
    )
    artifacts["workflow_result"] = _write_json(
        out_dir / "workflow_result.json", _public_payload(run)
    )
    return run


def _public_payload(run: WorkflowRun) -> dict[str, Any]:
    payload = run.to_dict()
    payload["workflow_status"] = run.status
    if run.exit_code == 0:
        payload["status"] = (
            "success_with_warnings"
            if any(d.severity == "warning" for d in run.diagnostics)
            else "success"
        )
    elif run.exit_code == 1:
        payload["status"] = "invalid"
    elif run.exit_code == 3:
        payload["status"] = "invalid"
    else:
        payload["status"] = "failed"
    payload["error_count"] = sum(
        1 for d in run.diagnostics if d.severity == "error"
    )
    payload["warning_count"] = sum(
        1 for d in run.diagnostics if d.severity == "warning"
    )
    payload["results"] = (
        list((run.execution or {}).get("results", []) or [])
        if run.execution
        else []
    )
    return payload


def run_workflow(
    problem_path: Path,
    *,
    out_dir: Path | None = None,
    base: Path | None = None,
) -> tuple[dict[str, Any], int]:
    """Run the research-to-simulation workflow for one problem document."""
    problem_path = Path(problem_path).resolve()
    root = Path(base).resolve() if base is not None else repository_root()
    out = Path(out_dir).resolve() if out_dir is not None else (
        root / "composition" / "workflow_runs" / "latest"
    )

    problem_input = load_problem(problem_path)
    problem = problem_input.problem
    if problem.blocked:
        run = _blocked(
            problem_input,
            out,
            "The problem statement does not name an organism and a target molecule.",
        )
        return _public_payload(run), run.exit_code

    corpus_path = _resolve(
        problem_path.parent,
        str(problem_input.literature.get("corpus", "")),
        "sources.json",
    )
    passages_path = _resolve(
        problem_path.parent,
        str(problem_input.literature.get("passages", "")),
        "passages.json",
    )

    artifacts: dict[str, str] = {}
    diagnostics: list[WorkflowDiagnostic] = []
    artifacts["problem_spec"] = _write_json(
        out / "problem_spec.json", problem.to_dict()
    )

    try:
        corpus = load_corpus(corpus_path)
    except LiteratureError as exc:
        run = WorkflowRun(
            problem=problem,
            sources=[],
            encoded=None,
            model=None,
            graph=None,
            execution=None,
            diagnostics=[
                WorkflowDiagnostic(
                    code="workflow.literature_missing",
                    severity="error",
                    message=str(exc),
                    where=("literature", str(corpus_path)),
                    remediation=(
                        "Supply a sources.json with real acquired papers, or point "
                        "the problem document's literature.corpus at one."
                    ),
                )
            ],
            artifacts=artifacts,
            status="failed",
            exit_code=3,
        )
        artifacts["workflow_result"] = _write_json(
            out / "workflow_result.json", _public_payload(run)
        )
        return _public_payload(run), run.exit_code

    discovery = discover(problem, corpus)
    selected_ids = [item["source_id"] for item in discovery if item["selected"]]
    target_ids = [
        source.source_id for source in corpus if source.role == "target_organism"
    ]
    if not target_ids:
        diagnostics.append(
            WorkflowDiagnostic(
                code="workflow.no_target_source",
                severity="warning",
                message=(
                    "The corpus contains no source declared as target_organism. "
                    "Every encoded claim will be analogue or method-review evidence."
                ),
                where=("literature", str(corpus_path)),
                remediation=(
                    "Add the paper that studies the requested organism and declare "
                    "its role as target_organism."
                ),
            )
        )

    acquired, acquisition_report = acquire_selected(
        selected_ids, corpus, corpus_path.parent, out / "source_texts"
    )
    acquired_ids = {
        source.source_id
        for source in acquired
        if source.acquisition_status == "acquired"
    }
    failed_targets = [source_id for source_id in target_ids if source_id not in acquired_ids]
    if failed_targets:
        diagnostics.append(
            WorkflowDiagnostic(
                code="workflow.target_acquisition_failed",
                severity="error",
                message=(
                    f"The target-organism source(s) {failed_targets} could not be "
                    f"acquired. No model was built, because building one from "
                    f"analogues alone would misrepresent the evidence."
                ),
                where=("literature", ", ".join(failed_targets)),
                remediation="Restore the source file or supply a readable format.",
            )
        )

    literature_manifest = {
        "problem_id": problem.problem_id,
        "corpus": corpus_path.as_posix(),
        "discovery": discovery,
        "selected_source_ids": selected_ids,
        "target_source_ids": target_ids,
        "acquisition": acquisition_report,
        "sources": [source.to_dict() for source in acquired],
        "statement": (
            "Discovery ranks candidates; acquisition reads and hashes the selected "
            "files. A search result is not evidence until its text is acquired and "
            "its quotes are verified."
        ),
    }
    artifacts["literature_manifest"] = _write_json(
        out / "literature_manifest.json", literature_manifest
    )

    if failed_targets:
        run = WorkflowRun(
            problem=problem,
            sources=acquired,
            encoded=None,
            model=None,
            graph=None,
            execution=None,
            diagnostics=diagnostics,
            artifacts=artifacts,
            status="blocked",
            exit_code=3,
        )
        artifacts["workflow_result"] = _write_json(
            out / "workflow_result.json", _public_payload(run)
        )
        return _public_payload(run), run.exit_code

    documents: dict[str, SourceText] = {}
    by_id = {source.source_id: source for source in acquired}
    for source_id in acquired_ids:
        source = by_id[source_id]
        try:
            documents[source_id] = extract_document(
                corpus_path.parent / source.file, source_id
            )
        except ExtractionError as exc:
            diagnostics.append(
                WorkflowDiagnostic(
                    code="workflow.extraction_failed",
                    severity="error",
                    message=str(exc),
                    where=("literature", source_id),
                    remediation="Supply a readable JATS XML or text source.",
                )
            )

    if diagnostics and any(d.severity == "error" for d in diagnostics):
        run = WorkflowRun(
            problem=problem,
            sources=acquired,
            encoded=None,
            model=None,
            graph=None,
            execution=None,
            diagnostics=diagnostics,
            artifacts=artifacts,
            status="failed",
            exit_code=3,
        )
        artifacts["workflow_result"] = _write_json(
            out / "workflow_result.json", _public_payload(run)
        )
        return _public_payload(run), run.exit_code

    try:
        encoded = encode(
            problem,
            documents,
            passages_path,
            source_roles={source.source_id: source.role for source in acquired},
        )
    except (EncodingError, ExtractionError) as exc:
        diagnostics.append(
            WorkflowDiagnostic(
                code="workflow.encoding_failed",
                severity="error",
                message=str(exc),
                where=("encoding", passages_path.as_posix()),
                remediation=(
                    "Fix the passage document or the acquired source. A quote that "
                    "cannot be found is never softened to make it match."
                ),
            )
        )
        run = WorkflowRun(
            problem=problem,
            sources=acquired,
            encoded=None,
            model=None,
            graph=None,
            execution=None,
            diagnostics=diagnostics,
            artifacts=artifacts,
            status="failed",
            exit_code=3,
        )
        artifacts["workflow_result"] = _write_json(
            out / "workflow_result.json", _public_payload(run)
        )
        return _public_payload(run), run.exit_code

    artifacts["research_encoded"] = _write_json(
        out / "research_encoded.json", encoded.to_dict()
    )

    model = build_model_spec(problem, encoded, acquired)
    artifacts["model_spec"] = _write_json(
        out / "model_spec.json", model.to_dict()
    )

    graph = build_graph(model, problem)
    artifacts["composition_graph"] = _write_json(
        out / "composition_graph.json", graph
    )

    worker = JsonWorker(
        "composition._workers.rna_worker",
        root / "composition" / "workflow" / "model_package",
    )
    adapter = RnaEvidenceAdapter(worker)
    execution, code = run_graph(
        graph,
        base=root,
        adapters={RNA_MODEL_ID: lambda: adapter},
    )
    artifacts["simulation_result"] = _write_json(
        out / "simulation_result.json", execution
    )

    if code == 0:
        status = "completed"
    elif code == 1:
        status = "invalid"
        diagnostics.append(
            WorkflowDiagnostic(
                code="workflow.graph_invalid",
                severity="error",
                message=(
                    "The constructed graph did not validate. The run stopped before "
                    "execution; no result was inferred."
                ),
                where=("composition_graph", artifacts["composition_graph"]),
                remediation="Read the runner diagnostics in simulation_result.json.",
            )
        )
    else:
        status = "failed"
        diagnostics.append(
            WorkflowDiagnostic(
                code="workflow.execution_failed",
                severity="error",
                message=(
                    "The constructed graph validated but execution failed. The "
                    "runner diagnostics name the failing step."
                ),
                where=("simulation_result", artifacts["simulation_result"]),
                remediation="Read the runner diagnostics; no partial success is reported.",
            )
        )

    if encoded.verification.get("claim_count", 0) == 0:
        diagnostics.append(
            WorkflowDiagnostic(
                code="workflow.no_claims",
                severity="warning",
                message="No claims were encoded; the model has no evidence base.",
                where=("encoding", passages_path.as_posix()),
                remediation="Add verified passages for the acquired sources.",
            )
        )
    if model.readiness.get("unresolved_parameter_count", 0):
        diagnostics.append(
            WorkflowDiagnostic(
                code="workflow.unresolved_parameters",
                severity="info",
                message=(
                    f"{model.readiness['unresolved_parameter_count']} parameter(s) "
                    f"remain unknown because the acquired sources do not state them."
                ),
                where=("model_spec", model.model_id),
                remediation=(
                    "This is a finding, not a failure. Acquire a source that states "
                    "the parameter, or keep it unknown."
                ),
            )
        )

    run = WorkflowRun(
        problem=problem,
        sources=acquired,
        encoded=encoded,
        model=model,
        graph=graph,
        execution=execution,
        diagnostics=diagnostics,
        artifacts=artifacts,
        status=status,
        exit_code=code,
    )
    artifacts["workflow_result"] = _write_json(
        out / "workflow_result.json", _public_payload(run)
    )
    return _public_payload(run), run.exit_code
