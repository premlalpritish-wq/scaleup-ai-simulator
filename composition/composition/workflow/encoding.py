"""Scientific encoding with verbatim verification.

A claim is not a summary.  It stores the source's exact wording, the source id,
the section it came from, and character offsets into the acquired text.  Before a
claim enters the model, the encoder re-finds its quote in the acquired document.
A changed quote, a paraphrase, or a number that is not in the quote fails the
run.

The encoder also keeps three distances from the requested organism separate:

``target_organism``
    The paper studies the requested organism.  This is direct evidence.
``analogous_species``
    The paper studies a different organism with a comparable problem.  Its
    protocol can only enter as a hypothesis.
``method_review``
    A method paper or review, not a measurement on the requested organism.

That distinction is the whole scientific point of the pecan case: the pecan
paper names a TRIzol kit but not its parameters, while the exact modified-CTAB
protocol comes from Norway spruce and pigeonpea.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .extract import ExtractionError, find_quote
from .schema import (
    CLAIM_KINDS,
    SPECIFICITIES,
    SPECIFICITY_ANALOGUE,
    SPECIFICITY_METHOD,
    SPECIFICITY_TARGET,
    STATE_REPORTED,
    STATE_UNKNOWN,
    EncodedResearch,
    EvidenceClaim,
    ProblemSpec,
    ProtocolStep,
    SourceText,
    StepParameter,
)


class EncodingError(RuntimeError):
    """A claim could not be verified or the passage document is malformed."""


def _normalise(text: str) -> str:
    return " ".join(str(text).split())


#: How far evidence can travel.  A passage may be *weaker* than its source's
#: declared role (a target-organism paper can also review methods) but never
#: stronger: an analogue-species protocol paper cannot yield direct
#: target-organism evidence.
_ROLE_RANK = {
    "target_organism": 2,
    "analogous_protocol": 1,
    "method_review": 0,
    "background": 0,
}

_SPECIFICITY_RANK = {
    SPECIFICITY_TARGET: 2,
    SPECIFICITY_ANALOGUE: 1,
    SPECIFICITY_METHOD: 0,
}


def _specificity_error(
    claim_id: str,
    source_id: str,
    specificity: str,
    source_role: str | None,
    organism: str,
    problem_organism: str,
) -> str | None:
    """Return why a claim's specificity is not supported by its source."""

    # A claim may never claim more directness than the paper it comes from.
    if source_role is None:
        # Documents were supplied without roles (unit-level use).  The caller
        # has opted out of the role check; nothing else can be verified here.
        return None
    if source_role not in _ROLE_RANK:
        return (
            f"{claim_id}: source {source_id} declares unknown role "
            f"{source_role!r}; the workflow cannot tell direct evidence from "
            f"analogy"
        )
    if _SPECIFICITY_RANK[specificity] > _ROLE_RANK[source_role]:
        return (
            f"{claim_id}: source {source_id} has role {source_role!r} but the "
            f"passage claims specificity {specificity!r}. Analogue or review "
            f"evidence cannot be relabelled as direct target-organism evidence."
        )
    if specificity == SPECIFICITY_TARGET and organism and problem_organism:
        if _normalise(organism).lower() != _normalise(problem_organism).lower():
            return (
                f"{claim_id}: a target-organism claim names organism "
                f"{organism!r}, but the problem asks about "
                f"{problem_organism!r}"
            )
    return None


def _number_in_quote(value: float, value_text: str | None, quote: str) -> bool:
    if value_text:
        return _normalise(value_text) in _normalise(quote)
    candidates = {
        f"{value:g}",
        f"{value:.1f}",
        f"{value:.2f}",
        str(value),
        str(value).replace(".", ","),
    }
    normalised = _normalise(quote)
    return any(candidate and candidate in normalised for candidate in candidates)


def load_passages(path: Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise EncodingError(f"passage document not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EncodingError(f"{path} is not valid JSON: {exc}") from None
    if not isinstance(payload, Mapping):
        raise EncodingError(f"{path} must contain a JSON object")
    passages = payload.get("passages")
    if not isinstance(passages, list) or not passages:
        raise EncodingError(f"{path} must contain a non-empty 'passages' array")
    return dict(payload)


def _claims_and_steps(
    problem: ProblemSpec,
    documents: Mapping[str, SourceText],
    payload: Mapping[str, Any],
    source_roles: Mapping[str, str] | None = None,
) -> tuple[list[EvidenceClaim], list[ProtocolStep], list[dict[str, Any]],
           dict[str, Any]]:
    passages = payload["passages"]
    claims: list[EvidenceClaim] = []
    failures: list[str] = []
    numeric_checked = 0
    quotes_checked = 0

    step_meta: dict[str, dict[str, Any]] = {}
    step_claims: dict[str, list[EvidenceClaim]] = {}
    step_parameters: dict[str, list[StepParameter]] = {}
    step_unknowns: dict[str, list[str]] = {}

    for index, passage in enumerate(passages, start=1):
        if not isinstance(passage, Mapping):
            failures.append(f"passage {index}: not an object")
            continue
        claim_id = str(passage.get("claim_id", "")).strip()
        source_id = str(passage.get("source_id", "")).strip()
        quote = str(passage.get("quote", ""))
        if not claim_id or not source_id:
            failures.append(f"passage {index}: claim_id and source_id are required")
            continue
        if source_id not in documents:
            failures.append(
                f"{claim_id}: source {source_id} was not acquired; a claim cannot "
                f"rest on a paper the run did not read"
            )
            continue
        document = documents[source_id]
        quotes_checked += 1
        try:
            start, end, section = find_quote(document, quote)
        except ExtractionError as exc:
            failures.append(f"{claim_id}: {exc}")
            continue

        claim_type = str(passage.get("claim_type", "protocol_step"))
        specificity = str(passage.get("specificity", SPECIFICITY_METHOD))
        if claim_type not in CLAIM_KINDS:
            failures.append(f"{claim_id}: unknown claim_type {claim_type!r}")
            continue
        if specificity not in SPECIFICITIES:
            failures.append(f"{claim_id}: unknown specificity {specificity!r}")
            continue

        problem_organism = ""
        if problem.organism.state == STATE_REPORTED:
            problem_organism = str(problem.organism.value or "")
        role_error = _specificity_error(
            claim_id,
            source_id,
            specificity,
            None if source_roles is None else source_roles.get(source_id),
            str(passage.get("organism", "")),
            problem_organism,
        )
        if role_error:
            failures.append(role_error)
            continue

        value = passage.get("value")
        unit = str(passage.get("unit", ""))
        if value is not None:
            numeric_checked += 1
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                failures.append(f"{claim_id}: value {value!r} is not numeric")
                continue
            if not unit:
                failures.append(f"{claim_id}: numeric claim has no unit")
                continue
            if not _number_in_quote(numeric, passage.get("value_text"), quote):
                failures.append(
                    f"{claim_id}: value {numeric:g} {unit} does not appear in its "
                    f"own quote; refusing to encode an untraceable number"
                )
                continue
            value = numeric
        else:
            value = None

        claim = EvidenceClaim(
            claim_id=claim_id,
            source_id=source_id,
            quote=quote,
            section=section.path if section is not None else "",
            locator={"start": start, "end": end},
            claim_type=claim_type,
            subject=str(passage.get("subject", "")),
            relation=str(passage.get("relation", "")),
            obj=str(passage.get("object", "")),
            organism=str(passage.get("organism", "")),
            tissue=str(passage.get("tissue", "")),
            specificity=specificity,
            # A claim about another species is a transfer hypothesis by
            # construction: the corpus cannot present it as a finding on the
            # requested organism. A target-organism claim can never be one
            # (`EvidenceClaim` enforces that).
            hypothesis=(
                bool(passage.get("hypothesis", False))
                or specificity == SPECIFICITY_ANALOGUE
            ),
            uncertainty=str(passage.get("uncertainty", "")),
            supports_step=str(passage.get("step_id", "")),
            value=value,
            unit=unit,
        )
        claims.append(claim)

        step_id = str(passage.get("step_id", "")).strip() or "unassigned"
        step_meta.setdefault(
            step_id,
            {
                "order": int(passage.get("step_order", len(step_meta) + 1)),
                "label": str(passage.get("step_label", step_id)),
                "action": str(passage.get("step_action", "")),
                "notes": str(passage.get("step_notes", "")),
            },
        )
        step_claims.setdefault(step_id, []).append(claim)

        for raw_parameter in passage.get("parameters") or ():
            if not isinstance(raw_parameter, Mapping):
                failures.append(f"{claim_id}: a parameter is not an object")
                continue
            name = str(raw_parameter.get("name", "")).strip()
            if not name:
                failures.append(f"{claim_id}: a parameter has no name")
                continue
            raw_value = raw_parameter.get("value")
            param_unit = str(raw_parameter.get("unit", ""))
            if raw_value is not None:
                numeric_checked += 1
                try:
                    numeric = float(raw_value)
                except (TypeError, ValueError):
                    failures.append(f"{claim_id}: parameter {name} is not numeric")
                    continue
                if not param_unit:
                    failures.append(f"{claim_id}: parameter {name} has no unit")
                    continue
                if not _number_in_quote(
                    numeric, raw_parameter.get("value_text"), quote
                ):
                    failures.append(
                        f"{claim_id}: parameter {name}={numeric:g} {param_unit} "
                        f"does not appear in its own quote"
                    )
                    continue
                state = STATE_REPORTED
                value: float | None = numeric
            else:
                state = STATE_UNKNOWN
                value = None
            step_parameters.setdefault(step_id, []).append(
                StepParameter(
                    parameter_id=f"{claim_id}.{name.replace(' ', '_')}",
                    name=name,
                    value=value,
                    unit=param_unit,
                    state=state,
                    basis=str(raw_parameter.get("basis", "")) or claim_id,
                    source_refs=(claim.claim_id,),
                )
            )
        for unknown in passage.get("unknowns") or ():
            text = str(unknown).strip()
            if text and text not in step_unknowns.setdefault(step_id, []):
                step_unknowns[step_id].append(text)

    if failures:
        raise EncodingError("; ".join(failures))

    steps: list[ProtocolStep] = []
    for step_id, meta in sorted(step_meta.items(), key=lambda item: item[1]["order"]):
        members = step_claims.get(step_id, [])
        specificities = {claim.specificity for claim in members}
        if SPECIFICITY_TARGET in specificities and len(specificities) > 1:
            status = "direct_target_plus_analogue"
        elif SPECIFICITY_TARGET in specificities:
            status = "direct_target_evidence"
        elif SPECIFICITY_ANALOGUE in specificities:
            status = "analogous_species_hypothesis"
        else:
            status = "method_review_only"
        step = ProtocolStep(
            step_id=step_id,
            order=int(meta["order"]),
            label=meta["label"],
            action=meta["action"],
            evidence_status=status,
            claim_ids=tuple(c.claim_id for c in members),
            source_ids=tuple(sorted({c.source_id for c in members})),
            parameters=tuple(step_parameters.get(step_id, ())),
            unknowns=tuple(step_unknowns.get(step_id, ())),
            notes=meta["notes"],
            hypothesis=SPECIFICITY_TARGET not in specificities,
        )
        steps.append(step)

    by_id = {claim.claim_id: claim for claim in claims}
    tensions: list[dict[str, Any]] = []
    for raw in payload.get("tensions") or ():
        if not isinstance(raw, Mapping):
            failures.append("a tension is not an object")
            continue
        left = str(raw.get("left_claim_id", ""))
        right = str(raw.get("right_claim_id", ""))
        if left not in by_id or right not in by_id:
            failures.append(
                f"tension {raw.get('tension_id', '(unnamed)')} names a claim that "
                f"was not encoded"
            )
            continue
        tensions.append(
            {
                "tension_id": str(raw.get("tension_id", f"tension-{len(tensions)+1}")),
                "topic": str(raw.get("topic", "")),
                "left_claim_id": left,
                "right_claim_id": right,
                "statement": str(raw.get("statement", "")),
                "resolution": str(raw.get("resolution", "")),
                "is_contradiction": False,
            }
        )
    if failures:
        raise EncodingError("; ".join(failures))

    verification = {
        "quotes_checked": quotes_checked,
        "quotes_verified": quotes_checked,
        "numeric_values_checked": numeric_checked,
        "numeric_values_verified": numeric_checked,
        "claim_count": len(claims),
        "source_count": len({c.source_id for c in claims}),
        "method": (
            "exact substring match after whitespace normalisation; every number "
            "must also appear in its own quote"
        ),
        "failures": [],
    }
    return claims, steps, tensions, verification


def encode(
    problem: ProblemSpec,
    documents: Mapping[str, SourceText],
    passages_path: Path,
    source_roles: Mapping[str, str] | None = None,
) -> EncodedResearch:
    """Encode verified passages into claims and steps.

    ``source_roles`` maps a source id to the role the corpus declares for it
    (``target_organism``, ``analogous_protocol``, ``method_review``,
    ``background``).  When it is supplied, a passage may not claim a specificity
    stronger than its source.  ``run_workflow`` always supplies it; unit callers
    that pass documents only still get quote and number verification.
    """

    payload = load_passages(passages_path)
    claims, steps, tensions, verification = _claims_and_steps(
        problem, documents, payload, source_roles
    )
    verification = dict(verification)
    verification["source_role_check"] = (
        "not requested" if source_roles is None else "enforced"
    )
    return EncodedResearch(
        problem_id=problem.problem_id,
        claims=tuple(claims),
        steps=tuple(steps),
        tensions=tuple(tensions),
        source_ids=tuple(sorted({c.source_id for c in claims})),
        verification=verification,
    )


def claims_for_step(encoded: EncodedResearch, step_id: str) -> Sequence[EvidenceClaim]:
    return tuple(c for c in encoded.claims if c.supports_step == step_id)
