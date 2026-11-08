"""Self-checks: does this package still match the paper's table?

`validate()` returns a deterministic report and is called by this package's own
test suite and by the composition layer's paper->model fidelity gate, so the same
evidence is checked once. Every check is structural evidence about the
transcription; none establishes scientific validity.
"""

from __future__ import annotations

from typing import Any

from . import context, manifest, model, source


def _check(checks: list[dict[str, Any]], cid: str, ok: bool, detail: str) -> None:
    checks.append({"id": cid, "ok": bool(ok), "detail": detail})


def _page_text_complete() -> tuple[bool, str]:
    missing = [
        p for p in range(source.FIRST_PRINTED_PAGE, source.LAST_PRINTED_PAGE + 1)
        if not source.page_text(p).strip()
    ]
    return (not missing), f"pages without extracted text: {missing}"


def _page_numbering() -> tuple[bool, str]:
    bad = [
        p for p in range(source.FIRST_PRINTED_PAGE, source.LAST_PRINTED_PAGE + 1)
        if not source.page_states_its_own_number(p)
    ]
    return (not bad), f"pages not stating their own footer: {bad}"


def _distinctive_values() -> list[tuple[str, float]]:
    """The cells whose printed form is distinctive enough to look up strictly.

    Short decimals (0.1, 0.01) occur elsewhere on the page, so checking them
    would be noise rather than evidence. A value is checked when its printed
    form has at least three significant digits.
    """
    out: list[tuple[str, float]] = []
    for r in model.TABLE_1:
        for column in model.COLUMNS:
            cell = r.cell(column)
            if cell.value is None:
                continue
            printed = f"{cell.value:g}"
            digits = sum(ch.isdigit() for ch in printed)
            if digits >= 3:
                out.append((f"{r.name}@{column}", cell.value))
    return out


def _table_values_on_page() -> tuple[bool, str]:
    text = source.page_text(model.TABLE_I_PAGE)
    missing = [
        label for label, value in _distinctive_values() if f"{value:g}" not in text
    ]
    return (not missing), (
        f"Table 1 values with >=3 printed digits not found on "
        f"p.{model.TABLE_I_PAGE}: {missing}"
    )


def _markers_are_preserved() -> tuple[bool, str]:
    """A non-numeric cell must keep its printed marker, not become 0.0."""
    bad: list[str] = []
    for r in model.TABLE_1:
        for column in model.COLUMNS:
            cell = r.cell(column)
            if cell.value is None and not cell.note:
                bad.append(f"{r.name}@{column}")
    return (not bad), f"non-numeric cells with no printed marker: {bad}"


def _sums_match_the_printed_sums() -> tuple[bool, str]:
    notes: list[str] = []
    ok = True
    for column in model.COLUMNS:
        computed = model.computed_macromolecule_sum(column)
        printed = model.printed_sum(column)
        notes.append(f"{column}: computed={computed:.4f} printed={printed:.3f}")
        if abs(computed - printed) > 0.005:
            ok = False
    return ok, "; ".join(notes)


def _amino_acids_are_within_the_protein_pool() -> tuple[bool, str]:
    """Only ``This work`` is checked, where one sample produced both numbers.

    Neidhardt's and Beck et al.'s ``Protein`` values and their amino-acid lists
    come from different publications, so the two need not be consistent with each
    other (Neidhardt's amino-acid fractions in fact sum to slightly more than his
    rounded ``Protein`` value). Asserting an invariant across columns would be an
    assertion about those other papers, not about this transcription.
    """
    aa = model.amino_acid_sum("this_work")
    protein = model.row("Protein").value("this_work")
    others = {
        c: (model.amino_acid_sum(c), model.row("Protein").cell(c).value)
        for c in model.COLUMNS if c != "this_work"
    }
    ok = aa <= protein + 1e-9
    return ok, (
        f"this_work: amino acids={aa:.4f} <= protein={protein:g}; "
        f"not asserted for the comparison columns: {others}"
    )


def _statements_on_page() -> tuple[bool, str]:
    bad = [
        s.statement_id for s in model.REPORTED_STATEMENTS
        if not source.page_contains(s.evidence.printed_page, f"{s.value:g}")
    ]
    return (not bad), f"reported statements not found on their cited page: {bad}"


def _context_quotes_present() -> tuple[bool, str]:
    bad = [
        c.key for c in context.EXPERIMENTAL_CONTEXT
        if c.evidence.quote
        and not source.page_contains(c.evidence.printed_page, c.evidence.quote)
    ]
    return (not bad), f"context quotes not found on their cited page: {bad}"


def validate() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    _check(checks, "source.page_text_complete", *_page_text_complete())
    _check(checks, "source.page_numbering", *_page_numbering())
    _check(checks, "fidelity.table_values", *_table_values_on_page())
    _check(checks, "fidelity.markers_preserved", *_markers_are_preserved())
    _check(checks, "fidelity.reported_statements", *_statements_on_page())
    _check(checks, "fidelity.context_quotes", *_context_quotes_present())
    _check(checks, "dataset.macromolecule_sums", *_sums_match_the_printed_sums())
    _check(checks, "dataset.amino_acids_within_protein",
           *_amino_acids_are_within_the_protein_pool())

    failures = [f"{c['id']}: {c['detail']}" for c in checks if not c["ok"]]
    return {
        "package": manifest.ARTEFACT_ID,
        "module": "simensen2022",
        "paper_folder": "Simensen",
        "checks": checks,
        "failures": failures,
        "ok": not failures,
    }
