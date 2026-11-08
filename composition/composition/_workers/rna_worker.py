"""Subprocess evaluator for the generated RNA evidence-audit model.

Run with ``python -m composition._workers.rna_worker --model-root <path>`` and a
JSON request on stdin.  One JSON response on stdout.

The worker contains no RNA science.  It counts what the verified model spec
contains and computes two ratios.  It has no yield equation and no degradation
term, because inventing one would defeat the purpose of the audit.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from typing import Any, Mapping

MODEL_ID = "pecan_rna_evidence_audit"
MODEL_VERSION = "0.1.0"

PORTS: tuple[tuple[str, str], ...] = (
    ("step_count", "Number of protocol steps in the constructed model"),
    ("claim_count", "Verified literature claims supporting the model"),
    ("direct_target_claim_count", "Claims about the requested organism"),
    ("analogue_claim_count", "Claims transferred from analogous species"),
    ("method_review_claim_count", "Method-review claims"),
    ("reported_parameter_count", "Parameters the sources state"),
    ("unresolved_parameter_count", "Parameters the sources do not state"),
    ("evidence_coverage_ratio", "Direct target claims divided by all claims"),
    ("protocol_complete_for_target", "1 when every target step has all parameters"),
    ("quantitative_yield_available_for_target", "1 when a target yield is reported"),
    ("analogue_protocol_available", "1 when an analogue protocol with parameters exists"),
)


def manifest() -> dict[str, Any]:
    return {
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "title": "Pecan RNA extraction evidence audit",
        "adapter": "rna",
        "contract_version": "0.1.0",
        "summary": (
            "Counts verified claims, direct vs analogue evidence, and unresolved "
            "parameters. It is not a yield or degradation model."
        ),
        "ports": [
            {
                "port_id": port_id,
                "direction": "output",
                "dimension": "dimensionless",
                "unit": "1",
                "label": label,
                "provenance": "derived",
                "role": "evidence_audit",
                "description": label,
            }
            for port_id, label in PORTS
        ],
        "parameters": {},
        "capabilities": ["evidence_coverage_audit", "research_workflow"],
        "unsupported_capabilities": {
            "quantitative_yield_prediction": (
                "No pecan-specific yield, RIN or degradation measurement is in "
                "the acquired sources; the model does not invent one."
            ),
            "cross_species_transfer_validation": (
                "An analogue protocol is reported as a hypothesis, never as a "
                "pecan-validated result."
            ),
        },
        "assumptions": [
            {"assumption": "Only quote-verified claims enter the model spec."},
            {
                "assumption": (
                    "An absent parameter is unknown, never zero and never "
                    "defaulted."
                )
            },
        ],
        "missing_information": [
            {
                "item": "pecan RNA extraction parameters",
                "reason": (
                    "TRIzol volumes, incubation times, centrifugation speeds, "
                    "elution volume, yield and RIN for pecan embryos are not "
                    "printed in the acquired target-organism source."
                ),
            }
        ],
    }


def _readiness(model_spec: Mapping[str, Any]) -> Mapping[str, Any]:
    readiness = model_spec.get("readiness")
    if not isinstance(readiness, Mapping):
        raise ValueError("the model spec has no readiness block")
    return readiness


def _source_ref(model_spec: Mapping[str, Any]) -> str:
    refs = []
    for source in model_spec.get("sources") or ():
        if not isinstance(source, Mapping):
            continue
        label = str(source.get("doi") or source.get("source_id") or "")
        if label:
            refs.append(label)
    return "; ".join(refs)


def run(model_spec: Mapping[str, Any]) -> dict[str, Any]:
    readiness = _readiness(model_spec)
    claims = model_spec.get("claims") or ()
    steps = model_spec.get("steps") or ()
    source_ref = _source_ref(model_spec)

    def boolean(name: str) -> float:
        return 1.0 if readiness.get(name) else 0.0

    values = {
        "step_count": float(len(steps)),
        "claim_count": float(len(claims)),
        "direct_target_claim_count": float(
            readiness.get("direct_target_claim_count", 0)
        ),
        "analogue_claim_count": float(readiness.get("analogue_claim_count", 0)),
        "method_review_claim_count": float(
            readiness.get("method_review_claim_count", 0)
        ),
        "reported_parameter_count": float(
            readiness.get("reported_parameter_count", 0)
        ),
        "unresolved_parameter_count": float(
            readiness.get("unresolved_parameter_count", 0)
        ),
        "evidence_coverage_ratio": float(
            readiness.get("evidence_coverage_ratio", 0.0)
        ),
        "protocol_complete_for_target": boolean("protocol_complete_for_target"),
        "quantitative_yield_available_for_target": boolean(
            "quantitative_yield_available_for_target"
        ),
        "analogue_protocol_available": boolean("analogue_protocol_available"),
    }

    outputs = []
    for port_id, _label in PORTS:
        outputs.append(
            {
                "port_id": port_id,
                "state": "number" if values[port_id] != 0 else "zero",
                "value": values[port_id],
                "unit": "1",
                "dimension": "dimensionless",
                "provenance": "derived",
                "source_ref": source_ref,
                "method": (
                    "derived by counting verified claims, steps and unresolved "
                    "parameters in the generated model spec"
                ),
                "extra": {
                    "readiness_statement": readiness.get("statement", ""),
                },
            }
        )

    diagnostics = []
    unresolved = int(values["unresolved_parameter_count"])
    if unresolved:
        diagnostics.append(
            {
                "severity": "info",
                "message": (
                    f"{unresolved} parameter(s) are not stated by the acquired "
                    f"sources and remain unknown. They were not defaulted."
                ),
            }
        )
    if values["quantitative_yield_available_for_target"] == 0:
        diagnostics.append(
            {
                "severity": "info",
                "message": (
                    "No target-organism RNA yield, RIN or degradation measurement "
                    "is reported, so the model returns no prediction for them."
                ),
            }
        )
    if values["analogue_protocol_available"] == 1:
        diagnostics.append(
            {
                "severity": "info",
                "message": (
                    "An analogue protocol with reported parameters is available "
                    "as a hypothesis. It has not been validated on the target "
                    "organism."
                ),
            }
        )

    return {
        "outputs": outputs,
        "summary": {
            "step_count": len(steps),
            "claim_count": len(claims),
            "unresolved_parameter_count": unresolved,
            "direct_target_claim_count": int(values["direct_target_claim_count"]),
            "analogue_claim_count": int(values["analogue_claim_count"]),
            "model_kind": model_spec.get("model_kind", ""),
        },
        "diagnostics": diagnostics,
        "unresolved": [
            {"target": unknown, "reason": "not stated by the acquired sources"}
            for unknown in model_spec.get("unknowns") or ()
        ],
    }


def _write(payload: Mapping[str, Any]) -> None:
    """Emit one ASCII-escaped JSON line.

    The evidence text is real paper text and contains characters such as the
    micro sign in ``uL`` units.  ``JsonWorker`` sends requests with
    ``json.dumps``' default ASCII escaping and decodes stdout with the host
    locale, so the response must use the same convention.  Writing raw
    non-ASCII would raise ``UnicodeEncodeError`` on a cp1252 console and lose
    the whole result.
    """

    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="composition._workers.rna_worker")
    parser.add_argument("--model-root", default="")
    args = parser.parse_args(argv)
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, Mapping):
            raise ValueError("the request must be a JSON object")
        op = request.get("op")
        if op == "manifest":
            payload = {"ok": True, "manifest": manifest()}
        elif op == "run":
            model_spec = request.get("model_spec")
            if not isinstance(model_spec, Mapping):
                raise ValueError("run requires a model_spec object")
            payload = {"ok": True, **run(model_spec)}
        else:
            raise ValueError(f"unknown operation {op!r}")
    except Exception as exc:  # noqa: BLE001 - one JSON error response
        payload = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc()[-4000:],
        }
        _write(payload)
        return 1
    _write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
