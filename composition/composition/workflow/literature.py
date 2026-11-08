"""Literature discovery and acquisition.

This is a local corpus provider, not a live Europe PMC client.  A corpus is a
directory containing ``sources.json`` and the source files it names.  The shipped
pecan corpus is real open-access full text; a caller may point the workflow at
another corpus produced by any external search tool.

Keeping discovery and acquisition separate matters:

* **discovery** decides which candidate papers are relevant to the problem and
  records *why* each was selected;
* **acquisition** reads exactly the selected file, hashes its bytes, extracts its
  text and records whether extraction succeeded.

A search result is not evidence.  Only an acquired, quote-verified source enters
scientific encoding.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from .extract import ExtractionError, extract_document
from .schema import ProblemSpec, SourceRecord


class LiteratureError(RuntimeError):
    """The corpus cannot be read or a selected source cannot be acquired."""


ROLE_WEIGHTS = {
    "target_organism": 100,
    "analogous_protocol": 20,
    "method_review": 10,
    "background": 1,
}


def _normalise(text: str) -> str:
    return " ".join(str(text).lower().split())


def _terms(source: SourceRecord) -> str:
    return _normalise(
        " ".join(
            [
                source.title,
                source.abstract,
                source.journal,
                " ".join(source.relevance_terms),
            ]
        )
    )


def load_corpus(path: Path) -> list[SourceRecord]:
    path = Path(path)
    if not path.is_file():
        raise LiteratureError(f"literature corpus not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LiteratureError(f"{path} is not valid JSON: {exc}") from None
    entries = payload.get("sources") if isinstance(payload, Mapping) else payload
    if not isinstance(entries, list):
        raise LiteratureError(f"{path} must contain a 'sources' array")
    out: list[SourceRecord] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise LiteratureError(f"{path}: every source must be an object")
        source_id = str(entry.get("source_id", "")).strip()
        if not source_id:
            raise LiteratureError(f"{path}: a source has no source_id")
        if source_id in seen:
            raise LiteratureError(f"{path}: duplicate source_id {source_id!r}")
        seen.add(source_id)
        if not entry.get("file"):
            raise LiteratureError(f"{source_id}: no source file is declared")
        out.append(
            SourceRecord(
                source_id=source_id,
                title=str(entry.get("title", "")),
                authors=tuple(entry.get("authors") or ()),
                year=str(entry.get("year", "")),
                doi=str(entry.get("doi", "")),
                journal=str(entry.get("journal", "")),
                license=str(entry.get("license", "")),
                url=str(entry.get("url", "")),
                file=str(entry["file"]),
                role=str(entry.get("role", "background")),
                relevance_terms=tuple(entry.get("relevance_terms") or ()),
                retrieved_via=str(entry.get("retrieved_via", "local corpus")),
                abstract=str(entry.get("abstract", "")),
                pmcid=str(entry.get("pmcid", "")),
                pmid=str(entry.get("pmid", "")),
            )
        )
    if not out:
        raise LiteratureError(f"{path}: the corpus contains no sources")
    return out


def discover(problem: ProblemSpec, sources: Iterable[SourceRecord]) -> list[dict[str, Any]]:
    """Rank candidates and record the reason for each selection.

    The ranking is a transparent term overlap, not a relevance model.  A
    ``target_organism`` source is always retained: it is the paper that names the
    requested organism, and dropping it would make the run look better while
    removing the only direct evidence.
    """
    organism = _normalise(problem.organism.value or "")
    tissue = _normalise(problem.tissue.value or "")
    molecule = _normalise(problem.molecule.value or "")
    constraints = [_normalise(c) for c in problem.constraints]
    downstream = [_normalise(d) for d in problem.downstream]

    out: list[dict[str, Any]] = []
    for source in sources:
        haystack = _terms(source)
        reasons: list[str] = []
        score = ROLE_WEIGHTS.get(source.role, 0)
        if source.role in ROLE_WEIGHTS:
            reasons.append(f"declared role: {source.role}")
        if organism and organism in haystack:
            score += 8
            reasons.append(f"names the target organism ({problem.organism.value})")
        if tissue and tissue in haystack:
            score += 3
            reasons.append(f"mentions the target tissue ({problem.tissue.value})")
        if molecule and molecule in haystack:
            score += 4
            reasons.append(f"mentions the target molecule ({problem.molecule.value})")
        for constraint in constraints:
            if constraint and constraint in haystack:
                score += 1
                reasons.append(f"addresses {constraint}")
        for term in downstream:
            if term and term in haystack:
                score += 1
                reasons.append(f"mentions {term}")
        selected = source.role == "target_organism" or score >= 4
        out.append(
            {
                "source_id": source.source_id,
                "title": source.title,
                "year": source.year,
                "doi": source.doi,
                "role": source.role,
                "score": score,
                "selected": selected,
                "reasons": list(dict.fromkeys(reasons)),
            }
        )
    out.sort(key=lambda item: (-item["score"], -int(item["year"] or 0),
                               item["source_id"]))
    return out


def acquire(
    source: SourceRecord,
    corpus_dir: Path,
    text_dir: Path,
) -> SourceRecord:
    """Read one source, hash it, extract its text and write the artifact."""
    corpus_dir = Path(corpus_dir)
    text_dir = Path(text_dir)
    path = (corpus_dir / source.file).resolve()
    if not path.is_file():
        return replace(
            source,
            acquisition_status="failed",
            diagnostics=(f"source file not found: {path}",),
        )
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    try:
        document = extract_document(path, source.source_id)
    except ExtractionError as exc:
        return replace(
            source,
            content_sha256=digest,
            acquisition_status="failed",
            diagnostics=(str(exc),),
        )
    text_dir.mkdir(parents=True, exist_ok=True)
    text_path = text_dir / f"{source.source_id}.txt"
    text_path.write_text(document.text + "\n", encoding="utf-8", newline="\n")
    return replace(
        source,
        content_sha256=digest,
        text_path=text_path.as_posix(),
        section_count=len(document.sections),
        extraction_method=document.extraction_method,
        acquisition_status="acquired",
        diagnostics=document.diagnostics,
    )


def acquire_selected(
    selected_ids: Iterable[str],
    sources: Iterable[SourceRecord],
    corpus_dir: Path,
    text_dir: Path,
) -> tuple[list[SourceRecord], list[dict[str, Any]]]:
    wanted = set(selected_ids)
    acquired: list[SourceRecord] = []
    report: list[dict[str, Any]] = []
    for source in sources:
        if source.source_id not in wanted:
            continue
        result = acquire(source, corpus_dir, text_dir)
        acquired.append(result)
        report.append(
            {
                "source_id": result.source_id,
                "status": result.acquisition_status,
                "content_sha256": result.content_sha256,
                "text_path": result.text_path,
                "section_count": result.section_count,
                "extraction_method": result.extraction_method,
                "diagnostics": list(result.diagnostics),
            }
        )
    missing = wanted - {s.source_id for s in acquired}
    for source_id in sorted(missing):
        report.append(
            {
                "source_id": source_id,
                "status": "not_found",
                "diagnostics": ["selected source is not in the corpus"],
            }
        )
    return acquired, report
