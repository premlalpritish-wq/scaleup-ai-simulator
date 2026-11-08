"""Deterministic problem ingestion.

The task asks for a research problem expressed in words or JSON.  This module
turns it into a :class:`ProblemSpec` using local rules only.  It does not call an
LLM, summarise with a model, or guess a missing field.

The important behaviour is what happens when a field is absent: it is recorded as
``unknown`` with the reason.  A problem whose organism or target molecule cannot
be read is marked ``blocked``; the workflow will stop before literature discovery
rather than search for a problem it has not understood.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .schema import (
    ProblemSpec,
    STATE_REPORTED,
    STATE_UNKNOWN,
    TrackedValue,
    unknown_value,
)

#: A deliberately small vocabulary for the first case.  Extending it is a code
#: change with a test, not a prompt to an unconstrained model.
ORGANISMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Carya illinoinensis", ("carya illinoinensis", "pecan")),
    ("Picea abies", ("picea abies", "norway spruce")),
    ("Cajanus cajan", ("cajanus cajan", "pigeonpea", "pigeon pea")),
)

TISSUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("embryo", ("embryo", "embryos")),
    ("seed", ("seed", "seeds")),
    ("leaf", ("leaf", "leaves")),
    ("needle", ("needle", "needles")),
    ("root", ("root", "roots")),
    ("phloem", ("phloem",)),
)

MOLECULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("total RNA", ("total rna", "total ribonucleic acid")),
    ("small RNA", ("small rna", "small-rna")),
    ("miRNA", ("mirna", "microrna")),
    ("mRNA", ("mrna", "messenger rna")),
)

DOWNSTREAM: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("small RNA sequencing", ("small rna sequencing", "small-rna sequencing")),
    ("miRNome", ("mirnome", "mirnome sequencing", "mirna sequencing")),
    ("degradome", ("degradome",)),
    ("transcriptome sequencing", ("transcriptome", "rna-seq", "rna seq")),
    ("qRT-PCR", ("qrt-pcr", "qrt pcr", "real-time pcr", "real time pcr")),
)

CONSTRAINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("recalcitrant tissue", ("recalcitrant", "difficult-to-extract", "difficult to extract")),
    ("polyphenol-rich", ("polyphenol", "phenolic")),
    ("polysaccharide-rich", ("polysaccharide", "polysaccharides")),
    ("secondary metabolites", ("secondary metabolite", "secondary metabolites")),
    ("high quality", ("high-quality", "high quality", "intact rna")),
)

DEFAULT_OUTPUTS = (
    "protocol_steps",
    "evidence_status",
    "unknowns",
    "readiness",
)


@dataclass(frozen=True)
class ProblemInput:
    problem: ProblemSpec
    literature: Mapping[str, Any]
    raw: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "problem": self.problem.to_dict(),
            "literature": dict(self.literature),
            "raw": dict(self.raw),
        }


def _normalise(text: str) -> str:
    return " ".join(str(text).lower().split())


def _find(
    text: str, vocabulary: tuple[tuple[str, tuple[str, ...]], ...]
) -> list[str]:
    found = []
    for canonical, terms in vocabulary:
        if any(term in text for term in terms):
            found.append(canonical)
    return found


def _tracked_find(
    text: str,
    vocabulary: tuple[tuple[str, tuple[str, ...]], ...],
    field_name: str,
) -> TrackedValue:
    found = _find(text, vocabulary)
    if not found:
        return unknown_value(f"the problem statement does not name a {field_name}")
    basis = "matched the problem statement's wording"
    if len(found) > 1:
        basis = "matched more than one term; the first in the controlled list was used"
    return TrackedValue(
        value=found[0],
        state=STATE_REPORTED,
        basis=basis,
        source_refs=("problem_statement",),
    )


def _problem_id(question: str, organism: TrackedValue, tissue: TrackedValue,
                molecule: TrackedValue) -> str:
    payload = {
        "question": " ".join(question.split()),
        "organism": organism.value,
        "tissue": tissue.value,
        "molecule": molecule.value,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return f"problem-{digest[:12]}"


def parse_problem(payload: Mapping[str, Any] | str) -> ProblemInput:
    """Parse a JSON problem document or a plain statement.

    A supplied field wins over the text-derived value, but is still checked
    against the controlled vocabulary.  A supplied value outside it is preserved
    verbatim and marked reported, so a later stage can show the exact string
    instead of silently replacing it.
    """
    if isinstance(payload, str):
        raw: dict[str, Any] = {"text": payload}
    elif isinstance(payload, Mapping):
        raw = dict(payload)
    else:
        raise TypeError("a problem must be a JSON object or a string")

    text = str(raw.get("text") or raw.get("question") or "").strip()
    if not text:
        raise ValueError("the problem statement is empty")

    normalised = _normalise(text)

    if raw.get("organism"):
        organism = TrackedValue(
            str(raw["organism"]), STATE_REPORTED,
            basis="declared in the problem document",
            source_refs=("problem_statement",),
        )
    else:
        organism = _tracked_find(normalised, ORGANISMS, "organism")

    if raw.get("tissue"):
        tissue = TrackedValue(
            str(raw["tissue"]), STATE_REPORTED,
            basis="declared in the problem document",
            source_refs=("problem_statement",),
        )
    else:
        tissue = _tracked_find(normalised, TISSUES, "tissue")

    if raw.get("molecule"):
        molecule = TrackedValue(
            str(raw["molecule"]), STATE_REPORTED,
            basis="declared in the problem document",
            source_refs=("problem_statement",),
        )
    else:
        molecule = _tracked_find(normalised, MOLECULES, "target molecule")

    downstream = tuple(raw.get("downstream") or _find(normalised, DOWNSTREAM))
    constraints = tuple(
        dict.fromkeys(
            list(raw.get("constraints") or ()) + _find(normalised, CONSTRAINTS)
        )
    )
    requested = tuple(raw.get("requested_outputs") or DEFAULT_OUTPUTS)

    unknowns: list[str] = []
    if organism.state == STATE_UNKNOWN:
        unknowns.append("organism")
    if tissue.state == STATE_UNKNOWN:
        unknowns.append("tissue")
    if molecule.state == STATE_UNKNOWN:
        unknowns.append("target molecule")
    if not downstream:
        unknowns.append("downstream application")
    blocked = organism.state == STATE_UNKNOWN or molecule.state == STATE_UNKNOWN

    problem = ProblemSpec(
        problem_id=_problem_id(text, organism, tissue, molecule),
        question=" ".join(text.split()),
        organism=organism,
        tissue=tissue,
        molecule=molecule,
        downstream=downstream,
        constraints=constraints,
        requested_outputs=requested,
        source_text=text,
        unknowns=tuple(unknowns),
        blocked=blocked,
    )
    literature = dict(raw.get("literature") or {})
    return ProblemInput(problem=problem, literature=literature, raw=raw)


def load_problem(path: Path) -> ProblemInput:
    """Load a problem document.  JSON is parsed; anything else is plain text."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"problem document not found: {path}")
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError(f"{path} must contain a JSON object")
        return parse_problem(payload)
    return parse_problem(path.read_text(encoding="utf-8"))
