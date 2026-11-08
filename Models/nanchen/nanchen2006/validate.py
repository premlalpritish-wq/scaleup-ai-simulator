"""Self-checks: does this package still match the paper it was built from?

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
    return (not bad), f"pages not stating their own printed number: {bad}"


def _this_study_row_on_page() -> tuple[bool, str]:
    text = source.page_text(model.TABLE_I_PAGE)
    want = [f"{model.THIS_STUDY.mglc:g}", f"{model.THIS_STUDY.Yglc_max:g}",
            f"{model.THIS_STUDY.mglc_ci:g}", f"{model.THIS_STUDY.Yglc_max_ci:g}"]
    missing = [w for w in want if w not in text]
    return (not missing), f"Table 1 values not found on p.{model.TABLE_I_PAGE}: {missing}"


def _readings_on_page() -> tuple[bool, str]:
    bad = [
        r.reading_id for r in model.REPORTED_READINGS
        if not source.page_contains(r.evidence.printed_page, f"{r.value:g}")
    ]
    return (not bad), f"reported readings not found on their cited page: {bad}"


def _context_quotes_present() -> tuple[bool, str]:
    bad = [
        c.key for c in context.EXPERIMENTAL_CONTEXT
        if c.evidence.quote
        and not source.page_contains(c.evidence.printed_page, c.evidence.quote)
    ]
    return (not bad), f"context quotes not found on their cited page: {bad}"


def _equations_have_pages() -> tuple[bool, str]:
    bad = [
        e["id"] for e in manifest.PRINTED_EQUATIONS
        if not source.FIRST_PRINTED_PAGE <= e["printed_page"] <= source.LAST_PRINTED_PAGE
        or not source.page_text(e["printed_page"]).strip()
    ]
    return (not bad), f"printed equations without a populated cited page: {bad}"


def _relation_behaves_as_printed() -> tuple[bool, str]:
    p = model.THIS_STUDY
    at_zero = model.q_glc(0.0, p.Yglc_max, p.mglc)
    at_point_four = model.q_glc(0.4, p.Yglc_max, p.mglc)
    slope = (at_point_four - at_zero) / 0.4
    expected_slope = model.MOL_PER_MMOL / p.Yglc_max
    round_trip = model.mu_from_q_glc(at_point_four, p.Yglc_max, p.mglc)
    ok = (
        abs(at_zero - p.mglc) < 1e-12
        and abs(slope - expected_slope) < 1e-9
        and abs(round_trip - 0.4) < 1e-12
    )
    return ok, (
        f"qglc(0)={at_zero:g}, qglc(0.4)={at_point_four:g}, "
        f"slope={slope:g} (=1000/Y={expected_slope:g}), mu round-trip={round_trip:g}"
    )


def _yield_falls_with_maintenance() -> tuple[bool, str]:
    p = model.THIS_STUDY
    y_low = model.biomass_yield(0.05, p.Yglc_max, p.mglc)
    y_high = model.biomass_yield(0.5, p.Yglc_max, p.mglc)
    ok = y_low < y_high < p.Yglc_max
    return ok, f"Y(0.05)={y_low:.2f} < Y(0.5)={y_high:.2f} < Ymax={p.Yglc_max:g} gdw/mol"


def validate() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    _check(checks, "source.page_text_complete", *_page_text_complete())
    _check(checks, "source.page_numbering", *_page_numbering())
    _check(checks, "fidelity.table1_this_study_row", *_this_study_row_on_page())
    _check(checks, "fidelity.reported_readings", *_readings_on_page())
    _check(checks, "fidelity.context_quotes", *_context_quotes_present())
    _check(checks, "model.equations_declared", *_equations_have_pages())
    _check(checks, "model.pirt_relation", *_relation_behaves_as_printed())
    _check(checks, "model.yield_falls_with_maintenance", *_yield_falls_with_maintenance())

    failures = [f"{c['id']}: {c['detail']}" for c in checks if not c["ok"]]
    return {
        "package": manifest.ARTEFACT_ID,
        "module": "nanchen2006",
        "paper_folder": "nanchen",
        "checks": checks,
        "failures": failures,
        "ok": not failures,
    }
