"""Research-explorer adapter over the existing research-to-simulation workflow.

This module is a *thin* boundary. It does not encode science, parse papers or
build models: it calls `composition.workflow.execute.run_workflow` (the canonical
entry point used by the CLI and the Godot scene) and projects the documents that
run writes into the shape the browser page renders.

Three rules decide the behaviour here:

* **the pecan case is the shipped run, not a mock** -- the overview, evidence and
  gap views read `composition/workflow_runs/pecan/`, and every quote is re-checked
  against the acquired source text at its recorded offsets before it is served;
* **a submitted problem is executed, never answered** -- the only way this module
  produces results is by running the real workflow on a temporary problem document
  and reading its artifacts; when the workflow refuses a problem, the refusal is
  reported with its own diagnostics and no results;
* **absolute paths stay server-side** -- responses name artifacts by URL, never by
  filesystem path.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "composition"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from composition.workflow.execute import run_workflow  # noqa: E402

#: The shipped, reproducible pecan run (see
#: `reports/RESEARCH_TO_SIMULATION_ARCHITECTURE.md`).
CASE_RUN_DIR = ROOT / "composition" / "workflow_runs" / "pecan"
FIXTURES_DIR = ROOT / "composition" / "composition" / "workflow" / "fixtures" / "pecan"

MAX_RUNS = int(os.environ.get("SCALEUP_RESEARCH_RETENTION", "5"))
MAX_FIELD_CHARS = 4000
MAX_RECORD_BYTES = 8 * 1024 * 1024
FEEDBACK_DIR = os.environ.get("SCALEUP_FEEDBACK_DIR", "")

ARTIFACT_NAMES = (
    "problem_spec",
    "literature_manifest",
    "research_encoded",
    "model_spec",
    "composition_graph",
    "simulation_result",
    "workflow_result",
)

#: What the workflow does, stated as capability rather than aspiration.
CAPABILITIES = (
    "Parse a problem statement into a problem specification, leaving absent "
    "fields explicitly unknown.",
    "Rank and acquire full text from a local corpus of five open-access papers, "
    "recording the SHA-256 of every acquired file.",
    "Verify that every encoded claim is a verbatim quote in the acquired text and "
    "that every number appears inside its own quote.",
    "Keep direct target-organism evidence, analogous-species evidence and "
    "method-review evidence structurally separate.",
    "Build an evidence-constrained protocol audit and execute it through the "
    "existing composition engine.",
)

LIMITATIONS = (
    "There is no live literature search or download. Discovery reads the bundled "
    "corpus only.",
    "Passages are curated in the repository; the workflow verifies them, it does "
    "not mine arbitrary full text.",
    "The model is an evidence audit. It does not predict RNA yield, RIN, purity or "
    "degradation, and none of those values appears in its outputs.",
    "Extraction method, additional protocol details and observations submitted in "
    "the form are recorded in your report as context; they are not encoded as "
    "evidence and do not change the model.",
    "The spruce and pigeonpea protocols are hypotheses transferred from other "
    "species. They have not been validated on pecan.",
    "Only the pecan case has a verified corpus. A problem about a different "
    "organism is refused by the workflow rather than answered with pecan data.",
)


class ResearchError(Exception):
    """A request that cannot be served, with a public status and code."""

    def __init__(self, status: int, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.status, self.code, self.details = status, code, details
        self.message = message


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _claim_class(specificity: str) -> str:
    return {
        "target_organism": "direct",
        "analogous_species": "analogue",
        "method_review": "method_review",
    }.get(specificity, "unknown")


def _verify_quotes(
    claims: list[Mapping[str, Any]], text_dir: Path
) -> dict[str, Any]:
    """Re-find every quote at its recorded offsets in the acquired text."""

    texts: dict[str, str] = {}
    if text_dir.is_dir():
        for path in sorted(text_dir.glob("*.txt")):
            texts[path.stem] = path.read_text(encoding="utf-8")
    checked = 0
    failures: list[dict[str, Any]] = []
    for claim in claims:
        source_id = str(claim.get("source_id", ""))
        text = texts.get(source_id)
        locator = claim.get("locator") or {}
        try:
            start, end = int(locator["start"]), int(locator["end"])
        except (KeyError, TypeError, ValueError):
            failures.append({"claim_id": claim.get("claim_id"), "reason": "no locator"})
            continue
        if text is None:
            failures.append(
                {"claim_id": claim.get("claim_id"), "reason": "no acquired text"}
            )
            continue
        checked += 1
        if text[start:end] != claim.get("quote"):
            failures.append(
                {
                    "claim_id": claim.get("claim_id"),
                    "reason": "quote does not match the acquired text at its offsets",
                }
            )
    return {
        "checked": checked,
        "failed": len(failures),
        "failures": failures[:10],
        "method": (
            "each quote is sliced out of the acquired text at the claim's own "
            "locator offsets and compared with the quote string"
        ),
    }


def _normalise_name(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def _human(name: str) -> str:
    """`storage_duration` reads as words in prose; the id is kept separately."""

    return re.sub(r"[_]+", " ", str(name)).strip()


def _analogue_references(model: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Parameter name -> reported values from steps that are hypotheses.

    The cross-reference is offered so a reader can see that an analogue protocol
    exists. It is never presented as a pecan value.
    """

    references: dict[str, list[dict[str, Any]]] = {}
    for step in model.get("steps") or ():
        analogue = str(step.get("evidence_status", "")).startswith("analogous") or bool(
            step.get("hypothesis")
        )
        if not analogue:
            continue
        for parameter in step.get("parameters") or ():
            if parameter.get("state") != "reported" or parameter.get("value") is None:
                continue
            key = _normalise_name(parameter.get("name", ""))
            references.setdefault(key, []).append(
                {
                    "step_id": step.get("step_id"),
                    "step_label": step.get("label"),
                    "parameter": parameter.get("name"),
                    "value": parameter.get("value"),
                    "unit": parameter.get("unit"),
                    "source_ids": list(step.get("source_ids") or ()),
                    "evidence_status": step.get("evidence_status"),
                    "claim_ids": list(step.get("claim_ids") or ()),
                }
            )
    return references


def _gap_view(model: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Unresolved parameters and open questions, with their own evidence.

    `why` states what is missing and why it blocks reproduction. It is derived
    from the step the gap belongs to; no value and no recommendation is invented.
    """

    references = _analogue_references(model)
    gaps: list[dict[str, Any]] = []
    for step in model.get("steps") or ():
        step_id = str(step.get("step_id", ""))
        label = str(step.get("label", ""))
        status = str(step.get("evidence_status", ""))
        direct = status.startswith("direct_target")
        for parameter in step.get("parameters") or ():
            if parameter.get("state") != "unknown":
                continue
            name = str(parameter.get("name", ""))
            human = _human(name)
            analogue = references.get(_normalise_name(name), [])
            why = (
                f"The source text that supports '{label}' does not state {human}. "
                + (
                    "Without it the target protocol cannot be reproduced from the "
                    "literature alone, so the workflow keeps it unknown."
                    if direct
                    else "This step is a hypothesis transferred from another "
                    "species, and this parameter is missing from it."
                )
            )
            gaps.append(
                {
                    "gap_id": f"{step_id}:{parameter.get('parameter_id') or name}",
                    "class": "unresolved_parameter",
                    "step_id": step_id,
                    "step_label": label,
                    "parameter": human,
                    "parameter_id": parameter.get("parameter_id"),
                    "unit": parameter.get("unit", ""),
                    "state": "unknown",
                    "evidence_status": status,
                    "evidence_class": "direct" if direct else "analogue",
                    "basis": parameter.get("basis", ""),
                    "source_ids": list(step.get("source_ids") or ()),
                    "claim_ids": list(step.get("claim_ids") or ()),
                    "why": why,
                    "hypothesis_references": analogue,
                }
            )
        for question in step.get("unknowns") or ():
            slug = re.sub(r"[^a-z0-9]+", "-", str(question).lower()).strip("-")[:60]
            gaps.append(
                {
                    "gap_id": f"{step_id}:question:{slug}",
                    "class": "open_question",
                    "step_id": step_id,
                    "step_label": label,
                    "parameter": str(question),
                    "unit": "",
                    "state": "unknown",
                    "evidence_status": status,
                    "evidence_class": "direct" if direct else "analogue",
                    "basis": "listed by the encoder as unresolved for this step",
                    "source_ids": list(step.get("source_ids") or ()),
                    "claim_ids": list(step.get("claim_ids") or ()),
                    "why": (
                        "The acquired sources leave this open. Nothing in the "
                        "corpus resolves it, so no answer is offered."
                    ),
                    "hypothesis_references": [],
                }
            )
    return gaps


def _output_view(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    execution = payload.get("execution") or {}
    for result in execution.get("results") or ():
        for output in result.get("outputs") or ():
            value = output.get("value") or {}
            ref = output.get("ref") or {}
            outputs.append(
                {
                    "port_id": ref.get("port_id"),
                    "instance_id": ref.get("instance_id"),
                    "value": value.get("value"),
                    "unit": value.get("unit"),
                    "provenance": value.get("provenance"),
                    "method": value.get("method"),
                    "source_ref": value.get("source_ref"),
                }
            )
    return outputs



def _source_view(sources: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_id": source.get("source_id"),
            "title": source.get("title"),
            "doi": source.get("doi"),
            "pmcid": source.get("pmcid"),
            "pmid": source.get("pmid"),
            "journal": source.get("journal"),
            "year": source.get("year"),
            "license": source.get("license"),
            "url": source.get("url"),
            "role": source.get("role"),
            "acquisition_status": source.get("acquisition_status"),
            "content_sha256": source.get("content_sha256"),
            "extraction_method": source.get("extraction_method"),
            "section_count": source.get("section_count"),
        }
        for source in sources
    ]


def _claim_view(
    claims: list[Mapping[str, Any]], sources: list[Mapping[str, Any]],
    steps: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {str(source.get("source_id")): source for source in sources}
    step_labels = {
        str(step.get("step_id")): str(step.get("label", "")) for step in steps
    }
    out: list[dict[str, Any]] = []
    for claim in claims:
        source = by_id.get(str(claim.get("source_id")), {})
        out.append(
            {
                "claim_id": claim.get("claim_id"),
                "claim_type": claim.get("claim_type"),
                "claim_text": " ".join(
                    part
                    for part in (
                        str(claim.get("subject", "")).strip(),
                        str(claim.get("relation", "")).strip(),
                        str(claim.get("object", "")).strip(),
                    )
                    if part
                ),
                "quote": claim.get("quote"),
                "section": claim.get("section"),
                "locator": claim.get("locator"),
                "organism": claim.get("organism"),
                "tissue": claim.get("tissue"),
                "specificity": claim.get("specificity"),
                "evidence_class": _claim_class(str(claim.get("specificity", ""))),
                "hypothesis": bool(claim.get("hypothesis")),
                "uncertainty": claim.get("uncertainty"),
                "value": claim.get("value"),
                "unit": claim.get("unit"),
                "supports_step": claim.get("supports_step"),
                "step_label": step_labels.get(str(claim.get("supports_step")), ""),
                "source": {
                    "source_id": source.get("source_id"),
                    "title": source.get("title"),
                    "doi": source.get("doi"),
                    "pmcid": source.get("pmcid"),
                    "journal": source.get("journal"),
                    "year": source.get("year"),
                    "license": source.get("license"),
                    "url": source.get("url"),
                    "role": source.get("role"),
                },
            }
        )
    return out


def _step_view(steps: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for step in steps:
        parameters = [
            {
                "parameter_id": p.get("parameter_id"),
                "name": p.get("name"),
                "value": p.get("value"),
                "unit": p.get("unit"),
                "state": p.get("state"),
                "basis": p.get("basis"),
                "source_refs": list(p.get("source_refs") or ()),
            }
            for p in step.get("parameters") or ()
        ]
        out.append(
            {
                "step_id": step.get("step_id"),
                "order": step.get("order"),
                "label": step.get("label"),
                "action": step.get("action"),
                "evidence_status": step.get("evidence_status"),
                "hypothesis": bool(step.get("hypothesis")),
                "claim_ids": list(step.get("claim_ids") or ()),
                "source_ids": list(step.get("source_ids") or ()),
                "parameters": parameters,
                "reported_parameters": [p for p in parameters if p["state"] == "reported"],
                "unknown_parameters": [p for p in parameters if p["state"] == "unknown"],
                "unknowns": list(step.get("unknowns") or ()),
                "notes": step.get("notes", ""),
            }
        )
    return out



def _projection(
    payload: Mapping[str, Any],
    *,
    origin: str,
    quote_check: Mapping[str, Any],
    submission: Mapping[str, Any] | None = None,
    artifacts: Mapping[str, str] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    encoded = payload.get("encoded") or {}
    model = payload.get("model") or {}
    sources = list(payload.get("sources") or ())
    steps = _step_view(list(model.get("steps") or encoded.get("steps") or ()))
    claims = _claim_view(
        list(encoded.get("claims") or ()), sources,
        list(model.get("steps") or encoded.get("steps") or ()),
    )
    classes = {"direct": 0, "analogue": 0, "method_review": 0}
    for claim in claims:
        classes[claim["evidence_class"]] = classes.get(claim["evidence_class"], 0) + 1
    readiness = dict(model.get("readiness") or {})
    execution = payload.get("execution") or {}
    return {
        "case_id": "pecan_rna_extraction",
        "origin": origin,
        "run_id": run_id,
        "problem": payload.get("problem") or model.get("problem") or {},
        "summary": {
            "claim_count": len(claims),
            "direct_claims": classes.get("direct", 0),
            "analogue_claims": classes.get("analogue", 0),
            "method_review_claims": classes.get("method_review", 0),
            "step_count": len(steps),
            "source_count": len(sources),
            "unresolved_parameter_count": readiness.get("unresolved_parameter_count"),
            "reported_parameter_count": readiness.get("reported_parameter_count"),
            "protocol_complete_for_target": readiness.get("protocol_complete_for_target"),
            "quantitative_yield_available_for_target": readiness.get(
                "quantitative_yield_available_for_target"
            ),
            "analogue_protocol_available": readiness.get("analogue_protocol_available"),
        },
        "sources": _source_view(sources),
        "claims": claims,
        "steps": steps,
        "gaps": _gap_view(model) if model else [],
        "readiness": readiness,
        "unknowns": list(model.get("unknowns") or ()),
        "hypotheses": list(model.get("hypotheses") or ()),
        "assumptions": list(model.get("assumptions") or ()),
        "verification": {
            **dict(encoded.get("verification") or {}),
            "quote_recheck": dict(quote_check),
        },
        "execution": {
            "workflow_status": payload.get("status"),
            "workflow_state": payload.get("workflow_status"),
            "exit_code": payload.get("exit_code"),
            "engine_status": execution.get("status"),
            "graph_id": execution.get("graph_id"),
            "instances": [
                {
                    "instance_id": result.get("instance_id"),
                    "model_id": result.get("model_id"),
                    "model_version": result.get("model_version"),
                    "status": result.get("status"),
                }
                for result in execution.get("results") or ()
            ],
            "outputs": _output_view(payload),
        },
        "diagnostics": list(payload.get("diagnostics") or ()),
        "capabilities": list(CAPABILITIES),
        "limitations": list(LIMITATIONS),
        "submission": dict(submission or {}),
        "artifacts": dict(artifacts or {}),
    }



_case_lock = threading.Lock()
_case_cache: dict[str, Any] | None = None
_case_work_dir: Path | None = None


def _case_source() -> tuple[dict[str, Any], str, Path]:
    """Return the shipped pecan run, or compute it once from the fixtures."""

    global _case_cache, _case_work_dir
    result_path = CASE_RUN_DIR / "workflow_result.json"
    if result_path.is_file():
        return _read_json(result_path), "composition/workflow_runs/pecan", CASE_RUN_DIR / "source_texts"
    with _case_lock:
        if _case_cache is not None and _case_work_dir is not None:
            return _case_cache, "computed from fixtures at startup", _case_work_dir / "source_texts"
        if not (FIXTURES_DIR / "problem.json").is_file():
            raise ResearchError(
                503,
                "case_unavailable",
                "Neither the shipped pecan run nor the pecan fixtures are present on this server.",
            )
        work = Path(tempfile.mkdtemp(prefix="scaleup-research-case-"))
        payload, code = run_workflow(
            FIXTURES_DIR / "problem.json", out_dir=work / "artifacts", base=ROOT
        )
        if code != 0 or not payload.get("encoded"):
            shutil.rmtree(work, ignore_errors=True)
            raise ResearchError(
                503,
                "case_unavailable",
                "The pecan fixtures are present but the workflow could not reproduce the case.",
                details={"diagnostics": payload.get("diagnostics", [])},
            )
        _case_cache, _case_work_dir = payload, work
        return payload, "computed from fixtures at startup", work / "source_texts"


def load_case() -> dict[str, Any]:
    """The pecan case as the browser page shows it.

    Every quote is re-verified against the acquired text before it is served. A
    mismatch stops the request: unverified claims are never displayed as evidence.
    """

    payload, origin, text_dir = _case_source()
    claims = list((payload.get("encoded") or {}).get("claims") or ())
    if not claims:
        raise ResearchError(
            503,
            "case_unavailable",
            "The pecan case document contains no encoded claims.",
        )
    quote_check = _verify_quotes(claims, text_dir)
    if quote_check["failed"]:
        raise ResearchError(
            503,
            "case_unverified",
            "The pecan case artifacts are internally inconsistent: a quote no "
            "longer matches the acquired text. No evidence is served until that "
            "is fixed.",
            details={"quote_recheck": quote_check},
        )
    return _projection(
        payload, origin=origin, quote_check=quote_check,
        artifacts={name: f"/api/research/case/artifacts/{name}" for name in ARTIFACT_NAMES},
    )



def _artifact_name(name: str) -> str:
    """Accept `model_spec` and `model_spec.json`; allow nothing else."""

    cleaned = str(name).strip()
    if cleaned.endswith(".json"):
        cleaned = cleaned[: -len(".json")]
    if cleaned not in ARTIFACT_NAMES:
        raise ResearchError(404, "artifact_not_found", "No such artifact.")
    return cleaned


def case_artifact_path(name: str) -> Path:
    """Allow-listed artifact file of the pecan case."""

    name = _artifact_name(name)
    _case_source()
    if CASE_RUN_DIR.is_dir() and (CASE_RUN_DIR / f"{name}.json").is_file():
        return CASE_RUN_DIR / f"{name}.json"
    if _case_work_dir is not None:
        candidate = _case_work_dir / "artifacts" / f"{name}.json"
        if candidate.is_file():
            return candidate
    raise ResearchError(404, "artifact_not_found", "That artifact was not written for this case.")


# --------------------------------------------------------------------- runs

_runs: dict[str, dict[str, Any]] = {}
_runs_lock = threading.Lock()


def _drop_run(run_id: str) -> None:
    record = _runs.pop(run_id, None)
    if record and record.get("work_dir"):
        shutil.rmtree(str(record["work_dir"]), ignore_errors=True)


def _store_run(record: Mapping[str, Any]) -> str:
    run_id = str(uuid.uuid4())
    stored = dict(record)
    with _runs_lock:
        _runs[run_id] = stored
        while len(_runs) > max(1, MAX_RUNS):
            oldest = next(iter(_runs))
            if oldest == run_id:
                break
            _drop_run(oldest)
    return run_id


def get_run(run_id: str) -> dict[str, Any]:
    with _runs_lock:
        record = _runs.get(run_id)
    if record is None:
        raise ResearchError(
            404,
            "analysis_not_found",
            "No analysis exists with that identifier. Analyses are kept in memory "
            "only for the most recent runs and disappear when the service restarts.",
        )
    return record


def run_artifact_path(run_id: str, name: str) -> Path:
    name = _artifact_name(name)
    record = get_run(run_id)
    candidate = Path(record["work_dir"]) / "artifacts" / f"{name}.json"
    if not candidate.is_file():
        raise ResearchError(404, "artifact_not_found", "That artifact was not written for this run.")
    return candidate



# ---------------------------------------------------------------- submission

_TEXT_FIELDS = {
    "problem": 4000,
    "organism": 200,
    "tissue": 200,
    "molecule": 200,
    "extraction_method": 400,
    "details": 4000,
    "observations": 4000,
    "downstream": 300,
    "constraints": 400,
}


def _text_field(body: Mapping[str, Any], key: str) -> str:
    value = body.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ResearchError(400, "invalid_field", f"Field '{key}' must be a string.")
    value = value.strip()
    if "\x00" in value:
        raise ResearchError(400, "invalid_field", f"Field '{key}' contains a NUL character.")
    limit = _TEXT_FIELDS[key]
    if len(value) > limit:
        raise ResearchError(
            413,
            "field_too_long",
            f"Field '{key}' is longer than the {limit}-character limit.",
        )
    return value


def _list_field(value: str) -> list[str]:
    parts = re.split(r"[;,\n]", value)
    return [part.strip() for part in parts if part.strip()][:20]


def _submission(body: Any) -> dict[str, Any]:
    if not isinstance(body, Mapping):
        raise ResearchError(400, "invalid_request", "The request body must be a JSON object.")
    unknown = sorted(set(body) - set(_TEXT_FIELDS) - {"case_id"})
    if unknown:
        raise ResearchError(
            400,
            "unknown_field",
            "The request contains fields this endpoint does not accept: "
            + ", ".join(unknown),
        )
    values = {key: _text_field(body, key) for key in _TEXT_FIELDS}
    if not values["problem"]:
        raise ResearchError(
            400,
            "problem_required",
            "Describe the current problem in the 'problem' field. An empty problem "
            "statement is not a request.",
        )
    return values


def _problem_document(values: Mapping[str, str]) -> dict[str, Any]:
    document: dict[str, Any] = {"text": values["problem"]}
    for key in ("organism", "tissue", "molecule"):
        if values[key]:
            document[key] = values[key]
    downstream = _list_field(values["downstream"])
    if downstream:
        document["downstream"] = downstream
    constraints = _list_field(values["constraints"])
    if constraints:
        document["constraints"] = constraints
    context = {
        key: values[key]
        for key in ("extraction_method", "details", "observations")
        if values[key]
    }
    if context:
        # Preserved in the run's problem document for audit. `parse_problem`
        # ignores unknown keys: the workflow does not turn this text into
        # evidence, and the response says so.
        document["researcher_context"] = context
    document["literature"] = {
        "corpus": str((FIXTURES_DIR / "sources.json").resolve()),
        "passages": str((FIXTURES_DIR / "passages.json").resolve()),
    }
    return document


def _applicability(payload: Mapping[str, Any]) -> dict[str, Any]:
    errors = [
        item
        for item in payload.get("diagnostics") or ()
        if str(item.get("severity")) == "error"
    ]
    codes = {str(item.get("code")) for item in errors}
    first = errors[0] if errors else {}
    if "workflow.problem_blocked" in codes:
        return {
            "applicable": False,
            "code": "problem_blocked",
            "reason": str(first.get("message", "")),
            "note": (
                "Name the organism and the target molecule, in the fields or in the "
                "problem statement. The workflow does not guess either."
            ),
        }
    if "workflow.encoding_failed" in codes:
        return {
            "applicable": False,
            "code": "evidence_not_applicable",
            "reason": str(first.get("message", "")),
            "note": (
                "The bundled corpus holds verified full text for the pecan case "
                "(Carya illinoinensis, embryo, total RNA). A problem outside that "
                "case has no verified evidence here, so the workflow refuses it "
                "instead of answering with pecan data."
            ),
        }
    if codes & {"workflow.literature_missing", "workflow.target_acquisition_failed"}:
        return {
            "applicable": False,
            "code": "corpus_unavailable",
            "reason": str(first.get("message", "")),
            "note": "The corpus this deployment ships could not be read.",
        }
    return {
        "applicable": True,
        "code": "executed" if payload.get("status") in {"success", "success_with_warnings"} else "execution_failed",
        "reason": "",
        "note": "",
    }



# ----------------------------------------------------------------- analysis

def analyse(body: Any) -> tuple[dict[str, Any], int]:
    """Run the real workflow on the submitted problem and project its result.

    Returns ``(payload, http_status)``. HTTP 200 means the workflow executed and
    its own exit code was 0; 422 means the workflow refused or failed, and the
    response says which -- no partial or substituted result is returned.
    """

    values = _submission(body)
    document = _problem_document(values)
    work = Path(tempfile.mkdtemp(prefix="scaleup-research-run-"))
    problem_path = work / "submitted-problem.json"
    problem_path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    artifacts_dir = work / "artifacts"
    try:
        payload, code = run_workflow(problem_path, out_dir=artifacts_dir, base=ROOT)
    except Exception as exc:  # noqa: BLE001 - the service reports, never guesses
        shutil.rmtree(work, ignore_errors=True)
        raise ResearchError(
            503,
            "workflow_unavailable",
            f"The workflow could not run: {type(exc).__name__}. No result was produced.",
        ) from exc

    claims = list((payload.get("encoded") or {}).get("claims") or ())
    quote_check = _verify_quotes(claims, artifacts_dir / "source_texts")
    applicability = _applicability(payload)
    executed = (
        code == 0
        and payload.get("status") in {"success", "success_with_warnings"}
        and bool(payload.get("execution"))
    )

    if quote_check["failed"] and executed:
        shutil.rmtree(work, ignore_errors=True)
        raise ResearchError(
            503,
            "analysis_unverified",
            "The run's own artifacts are inconsistent: a quote does not match the "
            "text it was extracted from. No result is returned.",
            details={"quote_recheck": quote_check},
        )

    submission_used = {
        "problem": values["problem"],
        "organism": values["organism"],
        "tissue": values["tissue"],
        "molecule": values["molecule"],
        "downstream": document.get("downstream", []),
        "constraints": document.get("constraints", []),
    }
    recorded_not_used = {
        key: values[key]
        for key in ("extraction_method", "details", "observations")
        if values[key]
    }

    if not executed:
        shutil.rmtree(work, ignore_errors=True)
        return (
            {
                "status": "refused" if not applicability["applicable"] else "failed",
                "execution_status": "not_applicable" if not applicability["applicable"] else "failed",
                "analysis_id": None,
                "applicability": applicability,
                "input": {"used": submission_used, "recorded_not_used": recorded_not_used},
                "problem": payload.get("problem") or {},
                "diagnostics": list(payload.get("diagnostics") or ()),
                "verification": dict((payload.get("encoded") or {}).get("verification") or {}),
                "result": None,
                "message": (
                    "The workflow refused this problem. No evidence, parameter or "
                    "output was produced."
                    if not applicability["applicable"]
                    else "The workflow ran but its model execution failed. No output "
                    "was produced."
                ),
            },
            422,
        )

    run_id = _store_run(
        {
            "work_dir": str(work),
            "payload": payload,
            "submission": submission_used,
            "recorded_not_used": recorded_not_used,
            "applicability": applicability,
            "quote_check": quote_check,
            "created_at": time.time(),
        }
    )
    projection = _projection(
        payload,
        origin=f"analysis {run_id}",
        quote_check=quote_check,
        submission={
            "used_by_engine": submission_used,
            "recorded_not_used_as_evidence": recorded_not_used,
        },
        artifacts={name: f"/api/research/runs/{run_id}/artifacts/{name}" for name in ARTIFACT_NAMES},
        run_id=run_id,
    )
    return (
        {
            "status": "completed",
            "execution_status": "completed",
            "analysis_id": run_id,
            "applicability": applicability,
            "input": {"used": submission_used, "recorded_not_used": recorded_not_used},
            "problem": projection["problem"],
            "diagnostics": projection["diagnostics"],
            "verification": projection["verification"],
            "result": projection,
            "message": (
                "The workflow executed the generated evidence-audit model through "
                "the composition engine. These are its outputs."
            ),
        },
        200,
    )


def get_analysis(run_id: str) -> dict[str, Any]:
    record = get_run(run_id)
    payload = record["payload"]
    projection = _projection(
        payload,
        origin=f"analysis {run_id}",
        quote_check=record["quote_check"],
        submission={
            "used_by_engine": record["submission"],
            "recorded_not_used_as_evidence": record["recorded_not_used"],
        },
        artifacts={name: f"/api/research/runs/{run_id}/artifacts/{name}" for name in ARTIFACT_NAMES},
        run_id=run_id,
    )
    return {
        "status": "completed",
        "execution_status": "completed",
        "analysis_id": run_id,
        "applicability": record["applicability"],
        "input": {
            "used": record["submission"],
            "recorded_not_used": record["recorded_not_used"],
        },
        "problem": projection["problem"],
        "diagnostics": projection["diagnostics"],
        "verification": projection["verification"],
        "result": projection,
        "message": "Stored analysis.",
    }



# ------------------------------------------------------------------- report

def _cell(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ").strip()


def _evidence_section(
    lines: list[str], projection: Mapping[str, Any], evidence_class: str,
    heading: str, note: str,
) -> None:
    add = lines.append
    claims = [
        claim
        for claim in projection.get("claims") or ()
        if claim["evidence_class"] == evidence_class
    ]
    add(f"## {heading}")
    add("")
    add(note)
    add("")
    if not claims:
        add("(none)")
        add("")
        return
    for claim in claims:
        source = claim.get("source") or {}
        add(f"### {_cell(claim.get('claim_id'))}")
        add("")
        add(f"- Claim: {_cell(claim.get('claim_text'))}")
        add(f"- Type: {_cell(claim.get('claim_type'))}"
            + (f"; value {_cell(claim.get('value'))} {_cell(claim.get('unit'))}"
               if claim.get("value") is not None else ""))
        add(f"- Source: {_cell(source.get('title'))}")
        add(f"- DOI: {_cell(source.get('doi'))}; PMCID: {_cell(source.get('pmcid'))}")
        add(f"- Section: {_cell(claim.get('section'))}")
        add(f"- Supports step: {_cell(claim.get('supports_step'))}")
        add(f"- Hypothesis: {'yes' if claim.get('hypothesis') else 'no'}"
            + (f"; uncertainty: {_cell(claim.get('uncertainty'))}"
               if claim.get("uncertainty") else ""))
        add(f"- Quote: {_cell(claim.get('quote'))}")
        add("")


def _gap_section(lines: list[str], projection: Mapping[str, Any]) -> None:
    add = lines.append
    gaps = list(projection.get("gaps") or ())
    add("## Research gaps")
    add("")
    add(f"{len(gaps)} unresolved item(s) were recorded. No value was imputed.")
    add("")
    for gap in gaps:
        add(f"### {_cell(gap.get('step_label'))} — {_cell(gap.get('parameter'))}")
        add("")
        add(f"- Class: {_cell(gap.get('class'))}; state: unknown")
        add(f"- Evidence status of the step: {_cell(gap.get('evidence_status'))}")
        add(f"- Why it cannot be closed from this corpus: {_cell(gap.get('why'))}")
        references = gap.get("hypothesis_references") or ()
        if references:
            add("- Analogue values exist as hypotheses only:")
            for reference in references:
                add(f"  - {_cell(reference.get('step_label'))}: "
                    f"{_cell(reference.get('value'))} {_cell(reference.get('unit'))} "
                    f"(from {_cell(', '.join(reference.get('source_ids') or []))})")
        else:
            add("- No analogue value is available either.")
        add("")



def _render_markdown(projection: Mapping[str, Any], meta: Mapping[str, Any]) -> str:
    problem = projection.get("problem") or {}
    summary = projection.get("summary") or {}
    verification = projection.get("verification") or {}
    recheck = verification.get("quote_recheck") or {}
    lines: list[str] = []
    add = lines.append

    add(f"# {meta.get('title', 'ScaleUp research explorer report')}")
    add("")
    add(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    add(f"Source: {projection.get('origin', '')}")
    add("")
    add("## Case")
    add("")
    add(f"- Organism: {_cell((problem.get('organism') or {}).get('value'))} "
        f"({(problem.get('organism') or {}).get('state')})")
    add(f"- Material: {_cell((problem.get('tissue') or {}).get('value'))} "
        f"({(problem.get('tissue') or {}).get('state')})")
    add(f"- Target molecule: {_cell((problem.get('molecule') or {}).get('value'))} "
        f"({(problem.get('molecule') or {}).get('state')})")
    add("")
    add("### Problem statement")
    add("")
    add(str(problem.get("question", "")).strip() or "(not recorded)")
    add("")

    submission = projection.get("submission") or {}
    used = submission.get("used_by_engine") or {}
    recorded = submission.get("recorded_not_used_as_evidence") or {}
    if used or recorded:
        add("## Researcher-submitted context")
        add("")
        if used:
            add("Used by the workflow (it became the problem specification):")
            add("")
            for key, value in used.items():
                if value:
                    add(f"- **{key}**: {_cell(value)}")
            add("")
        if recorded:
            add("Recorded in this report, but **not used as evidence** and not read "
                "by the model:")
            add("")
            for key, value in recorded.items():
                add(f"- **{key}**: {_cell(value)}")
            add("")

    add("## What this analysis is, and is not")
    add("")
    add("Capabilities demonstrated by this run:")
    add("")
    for item in projection.get("capabilities") or ():
        add(f"- {item}")
    add("")
    add("Limitations that apply to this report:")
    add("")
    for item in projection.get("limitations") or ():
        add(f"- {item}")
    add("")

    add("## Evidence summary")
    add("")
    add(f"- Direct target-organism claims: {summary.get('direct_claims')}")
    add(f"- Analogous-species claims (hypotheses): {summary.get('analogue_claims')}")
    add(f"- Method-review claims: {summary.get('method_review_claims')}")
    add(f"- Protocol steps: {summary.get('step_count')}")
    add(f"- Sources: {summary.get('source_count')}")
    add(f"- Quotes verified: {verification.get('quotes_verified')} of "
        f"{verification.get('quotes_checked')}")
    add(f"- Numbers verified inside their own quote: "
        f"{verification.get('numeric_values_verified')} of "
        f"{verification.get('numeric_values_checked')}")
    add(f"- Source-role ceiling: {verification.get('source_role_check')}")
    add(f"- Independent quote re-check for this report: {recheck.get('checked')} "
        f"checked, {recheck.get('failed')} failed")
    add("")

    _evidence_section(
        lines, projection, "direct", "Direct evidence (target organism)",
        "Quoted verbatim from the pecan paper. This is the only class that supports "
        "a direct claim about pecan.",
    )
    _evidence_section(
        lines, projection, "analogue",
        "Analogous evidence (hypotheses, not pecan measurements)",
        "Quoted verbatim from papers on other species. These are transfer "
        "hypotheses and have not been validated on pecan.",
    )
    _evidence_section(
        lines, projection, "method_review", "Method-review evidence",
        "Quoted verbatim from method papers and reviews. Neither a pecan "
        "measurement nor a species-specific protocol.",
    )


    add("## Protocol steps")
    add("")
    add("| Step | Evidence status | Reported parameters | Unknown parameters |")
    add("|---|---|---|---|")
    for step in projection.get("steps") or ():
        add(f"| {_cell(step.get('label'))} | {_cell(step.get('evidence_status'))} | "
            f"{len(step.get('reported_parameters') or ())} | "
            f"{len(step.get('unknown_parameters') or ())} |")
    add("")

    _gap_section(lines, projection)

    readiness = projection.get("readiness") or {}
    if readiness:
        add("## Model readiness")
        add("")
        add(f"- Protocol complete for target: {readiness.get('protocol_complete_for_target')}")
        add(f"- Quantitative yield available for target: "
            f"{readiness.get('quantitative_yield_available_for_target')}")
        add(f"- Analogue protocol available: {readiness.get('analogue_protocol_available')}")
        add(f"- Reported parameters: {readiness.get('reported_parameter_count')}")
        add(f"- Unresolved parameters: {readiness.get('unresolved_parameter_count')}")
        add("")
    if projection.get("assumptions"):
        add("## Assumptions")
        add("")
        for item in projection["assumptions"]:
            add(f"- {item}")
        add("")
    if projection.get("hypotheses"):
        add("## Hypotheses carried into the model")
        add("")
        for item in projection["hypotheses"]:
            add(f"- {item}")
        add("")

    outputs = ((projection.get("execution") or {}).get("outputs")) or []
    if outputs:
        add("## Computed outputs")
        add("")
        add("Produced by the executed evidence-audit model through the composition "
            "engine. These are counts and ratios about the evidence base; no RNA "
            "yield, RIN or degradation value is computed.")
        add("")
        add("| Port | Value | Unit | Method |")
        add("|---|---|---|---|")
        for output in outputs:
            add(f"| {_cell(output.get('port_id'))} | {_cell(output.get('value'))} | "
                f"{_cell(output.get('unit'))} | {_cell(output.get('method'))} |")
        add("")

    diagnostics = projection.get("diagnostics") or ()
    if diagnostics:
        add("## Diagnostics")
        add("")
        for item in diagnostics:
            add(f"- [{item.get('severity')}] {item.get('code')}: {_cell(item.get('message'))}")
        add("")

    add("## Artifacts")
    add("")
    for name, url in (projection.get("artifacts") or {}).items():
        add(f"- {name}: {url}")
    add("")
    add("## Privacy and retention")
    add("")
    add("- The problem you submit is sent to this deployment's Python service to run "
        "the workflow. It is not sent to any third party.")
    add("- Analyses and their artifacts are kept in the service's memory and "
        "temporary storage for a bounded number of most recent runs, and disappear "
        "when the service restarts.")
    add("- Feedback is stored on this server only when the operator configured a "
        "feedback directory; the endpoint reports which happened.")
    add("")
    add("## Reproduction")
    add("")
    add("```bash")
    add("cd composition")
    add("python -m composition.runner --run-workflow "
        "composition/workflow/fixtures/pecan/problem.json --repo-root ..")
    add("```")
    add("")
    return "\n".join(lines)


def case_markdown() -> str:
    return _render_markdown(
        load_case(), {"title": "ScaleUp research explorer — pecan RNA case"}
    )


def analysis_markdown(run_id: str) -> str:
    record = get_run(run_id)
    projection = _projection(
        record["payload"],
        origin=f"analysis {run_id}",
        quote_check=record["quote_check"],
        submission={
            "used_by_engine": record["submission"],
            "recorded_not_used_as_evidence": record["recorded_not_used"],
        },
        artifacts={
            name: f"/api/research/runs/{run_id}/artifacts/{name}"
            for name in ARTIFACT_NAMES
        },
        run_id=run_id,
    )
    return _render_markdown(
        projection, {"title": "ScaleUp research explorer — pecan RNA analysis"}
    )



# ----------------------------------------------------------------- feedback

_FEEDBACK_FIELDS = {"message": 4000, "role": 200, "case_id": 200, "analysis_id": 200}


def record_feedback(body: Any) -> dict[str, Any]:
    """Store a researcher's feedback on this server, and say whether it was stored.

    Nothing is sent anywhere else, and the response never pretends persistence
    that did not happen.
    """

    if not isinstance(body, Mapping):
        raise ResearchError(400, "invalid_request", "The request body must be a JSON object.")
    unknown = sorted(set(body) - set(_FEEDBACK_FIELDS))
    if unknown:
        raise ResearchError(
            400,
            "unknown_field",
            "The feedback endpoint does not accept: " + ", ".join(unknown),
        )
    values: dict[str, str] = {}
    for key, limit in _FEEDBACK_FIELDS.items():
        value = body.get(key, "")
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise ResearchError(400, "invalid_field", f"Field '{key}' must be a string.")
        value = value.strip()
        if "\x00" in value:
            raise ResearchError(400, "invalid_field", f"Field '{key}' contains a NUL character.")
        if len(value) > limit:
            raise ResearchError(
                413, "field_too_long", f"Field '{key}' is longer than {limit} characters."
            )
        values[key] = value
    if len(values["message"]) < 10:
        raise ResearchError(
            400,
            "feedback_required",
            "Write at least a sentence of feedback. An empty message is not stored.",
        )

    entry = {
        "received_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "message": values["message"],
        "role": values["role"],
        "case_id": values["case_id"] or "pecan_rna_extraction",
        "analysis_id": values["analysis_id"],
    }
    if not FEEDBACK_DIR:
        return {
            "received": True,
            "persisted": False,
            "storage": "none",
            "note": (
                "This deployment has no feedback store configured, so the message "
                "was not saved anywhere. Nothing was sent to a third party."
            ),
        }
    path = Path(FEEDBACK_DIR)
    try:
        path.mkdir(parents=True, exist_ok=True)
        with (path / "feedback.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        return {
            "received": True,
            "persisted": False,
            "storage": "unavailable",
            "note": (
                "The server could not write the feedback file. The message was not "
                "saved."
            ),
        }
    return {
        "received": True,
        "persisted": True,
        "storage": "server",
        "note": (
            "Stored in this deployment's feedback file. It is not sent to any third "
            "party."
        ),
    }

