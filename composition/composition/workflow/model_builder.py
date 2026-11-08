"""Model construction from verified claims.

The output is an **evidence-constrained protocol model**, not a kinetic model.
It has no yield equation, no degradation rate, and no fitted parameter.  What it
does have is a step-by-step account of what the literature establishes, what is
transferred by analogy, and what remains unknown.

This is a scientific choice, not a missing feature.  The pecan paper reports that
a TRIzol kit was used, but not the volumes, times, speeds, elution volume, yield
or RIN.  A model that produced those numbers would be inventing them.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from .schema import (
    STATE_REPORTED,
    STATE_UNKNOWN,
    EncodedResearch,
    ModelSpec,
    ProblemSpec,
    ProtocolStep,
    SourceRecord,
    StepParameter,
)

MODEL_ID = "pecan_rna_evidence_audit"
MODEL_VERSION = "0.1.0"
MODEL_KIND = "evidence_constrained_protocol_audit"


def _target_yield_claim(encoded: EncodedResearch) -> bool:
    for claim in encoded.claims:
        if claim.specificity != "target_organism" or claim.value is None:
            continue
        words = f"{claim.subject} {claim.obj} {claim.relation}".lower()
        if "yield" in words or "µg" in claim.unit or "ug" in claim.unit:
            return True
    return False


def build_model_spec(
    problem: ProblemSpec,
    encoded: EncodedResearch,
    sources: Sequence[SourceRecord],
) -> ModelSpec:
    direct_claims = [
        c for c in encoded.claims if c.specificity == "target_organism"
    ]
    analogue_claims = [
        c for c in encoded.claims if c.specificity == "analogous_species"
    ]
    method_claims = [
        c for c in encoded.claims if c.specificity == "method_review"
    ]
    direct_steps = [
        s for s in encoded.steps if s.evidence_status.startswith("direct_target")
    ]
    analogue_steps = [
        s for s in encoded.steps if s.evidence_status == "analogous_species_hypothesis"
    ]
    method_steps = [
        s for s in encoded.steps if s.evidence_status == "method_review_only"
    ]

    parameters: list[StepParameter] = []
    for step in encoded.steps:
        parameters.extend(step.parameters)
    reported = [p for p in parameters if p.state == STATE_REPORTED]
    unknown_parameters = [p for p in parameters if p.state == STATE_UNKNOWN]

    unknown_steps = [s.step_id for s in direct_steps if s.unknowns]
    target_yield = _target_yield_claim(encoded)
    analogue_protocol_available = any(
        len(step.parameters) >= 3 for step in analogue_steps
    )

    readiness = {
        "protocol_complete_for_target": bool(direct_steps) and not unknown_steps
        and not unknown_parameters,
        "quantitative_yield_available_for_target": target_yield,
        "analogue_protocol_available": analogue_protocol_available,
        "direct_target_claim_count": len(direct_claims),
        "analogue_claim_count": len(analogue_claims),
        "method_review_claim_count": len(method_claims),
        "direct_target_step_count": len(direct_steps),
        "analogue_step_count": len(analogue_steps),
        "method_review_step_count": len(method_steps),
        "reported_parameter_count": len(reported),
        "unresolved_parameter_count": len(unknown_parameters),
        "evidence_coverage_ratio": (
            len(direct_claims) / len(encoded.claims) if encoded.claims else 0.0
        ),
        "statement": (
            "This audits what the literature establishes. A complete protocol "
            "for the target organism, a quantitative yield, and an analogue "
            "protocol are three different findings; this block keeps them apart."
        ),
    }

    unknowns: list[str] = []
    for step in encoded.steps:
        for item in step.unknowns:
            entry = f"{step.step_id}: {item}"
            if entry not in unknowns:
                unknowns.append(entry)
    for parameter in unknown_parameters:
        entry = f"{parameter.parameter_id}: {parameter.name} is not stated"
        if entry not in unknowns:
            unknowns.append(entry)
    if not target_yield:
        unknowns.append(
            "no target-organism RNA yield, RIN or degradation measurement is "
            "reported by the acquired pecan source"
        )

    hypotheses: list[str] = []
    for step in analogue_steps:
        hypotheses.append(
            f"{step.step_id}: {step.label} is transferred from "
            f"{', '.join(step.source_ids)}; it has not been validated on the "
            f"target organism."
        )
    if not hypotheses:
        hypotheses.append(
            "No analogue protocol was selected; no cross-species transfer is made."
        )

    assumptions = [
        "A protocol reported for a different species is a hypothesis, not a "
        "measurement on the requested organism.",
        "A parameter absent from the acquired text stays unknown; it is never "
        "imputed, defaulted or placed at zero.",
        "The model audits evidence coverage and protocol readiness. It does not "
        "predict RNA yield, integrity or degradation.",
        "Only quotes that were found verbatim in an acquired source are allowed "
        "to support a step.",
    ]

    source_dicts = tuple(
        {
            "source_id": source.source_id,
            "title": source.title,
            "year": source.year,
            "doi": source.doi,
            "journal": source.journal,
            "role": source.role,
            "license": source.license,
            "url": source.url,
            "content_sha256": source.content_sha256,
            "extraction_method": source.extraction_method,
        }
        for source in sources
        if source.acquisition_status == "acquired"
    )

    return ModelSpec(
        model_id=MODEL_ID,
        model_version=MODEL_VERSION,
        title=(
            "Pecan embryo total-RNA extraction: evidence-constrained protocol audit"
        ),
        model_kind=MODEL_KIND,
        problem=problem.to_dict(),
        steps=encoded.steps,
        parameters=tuple(parameters),
        unknowns=tuple(unknowns),
        hypotheses=tuple(hypotheses),
        assumptions=tuple(assumptions),
        readiness=readiness,
        sources=source_dicts,
        claims=encoded.claims,
    )


def build_graph(model: ModelSpec, problem: ProblemSpec) -> dict[str, Any]:
    doises = [
        source["doi"] for source in model.sources if source.get("doi")
    ]
    return {
        "contract_version": "0.1.0",
        "graph_id": f"rna-workflow-{problem.problem_id.rsplit('-', 1)[-1]}",
        "title": model.title,
        "description": (
            "A single evidence-audit model constructed from verified literature "
            "claims. There are no cross-model connections: the model consumes no "
            "upstream value and publishes only counts and ratios about its own "
            "evidence base."
        ),
        "source_ref": "; ".join(doises),
        "notes": (
            "The model is an evidence audit, not a kinetic or yield model. Its "
            "outputs count verified claims, unresolved parameters and direct vs "
            "analogue evidence. It never reports a pecan RNA yield, RIN or "
            "degradation rate that the sources do not state."
        ),
        "composition_scope": {
            "target_model_id": model.model_id,
            "target_problem_id": problem.problem_id,
            "dynamic_connections_added": 0,
            "assessment": "generated by composition.workflow.model_builder",
            "statement": (
                "One generated model instance, no connections. The graph exists "
                "to place the constructed model inside the existing composition "
                "contract and execution boundary."
            ),
        },
        "instances": [
            {
                "instance_id": "pecan_rna_audit",
                "model_id": model.model_id,
                "model_version": model.model_version,
                "label": model.title,
                "role": "evidence audit (not a prediction)",
                "notes": (
                    "The model spec is carried in the instance parameters so the "
                    "run is reproducible from the graph document alone."
                ),
                "position": {"x": 80, "y": 80},
                "parameters": {
                    "model": {
                        "model_spec": model.to_dict(),
                    }
                },
            }
        ],
        "connections": [],
        "literal_inputs": {},
    }
