"""Self-checks: does this package still match the paper it was built from?

`validate()` returns a deterministic report. It is called by this package's own
test suite and by the composition layer's paper->model fidelity check, so the
same evidence is checked in one place rather than two.

Every check is *structural evidence about the transcription*: that the cited
page carries the quoted value, that the printed equations are all attached to a
page that exists, that the Appendix's two correction branches behave as printed,
and that the model runs. None of them establishes scientific validity, and none
of them compares a curve to a figure -- the paper prints no digitised curve.
"""

from __future__ import annotations

from typing import Any

from . import context, manifest, model, parameters as params, source


def _check(checks: list[dict[str, Any]], cid: str, ok: bool, detail: str) -> None:
    checks.append({"id": cid, "ok": bool(ok), "detail": detail})


def _page_text_complete() -> tuple[bool, str]:
    pages = source.paper_pages()
    missing = [
        p for p in range(source.FIRST_PRINTED_PAGE, source.LAST_PRINTED_PAGE + 1)
        if not source.page_text(p).strip()
    ]
    return (not missing), f"pages without extracted text: {missing}"


def _page_numbering() -> tuple[bool, str]:
    bad = [
        p for p in range(source.FIRST_PRINTED_PAGE, source.LAST_PRINTED_PAGE + 1)
        if p != source.FIRST_PRINTED_PAGE and not source.page_states_its_own_number(p)
    ]
    return (not bad), f"pages not stating their own printed number: {bad}"


def _value_on_page(value: float, page: int) -> bool:
    """Strict-ish lookup: the printed integer/decimal string appears on `page`."""
    text = source.page_text(page)
    candidates = {f"{value:g}", f"{value:.4f}".rstrip("0").rstrip(".")}
    if float(value).is_integer():
        candidates.add(str(int(value)))
    return any(c and c in text for c in candidates)


def _table_i_on_page() -> tuple[bool, str]:
    bad: list[str] = []
    for param in params.TABLE_I:
        for strain, value in param.values.items():
            if value is None:
                continue
            if not _value_on_page(float(value), params.TABLE_I_PAGE):
                bad.append(f"{param.name}@{strain}={value}")
    return (not bad), f"Table I values not found on p.{params.TABLE_I_PAGE}: {bad}"


def _capacities_on_page() -> tuple[bool, str]:
    bad: list[str] = []
    for q in params.REPORTED_CAPACITIES:
        if not _value_on_page(float(q.value), params.ABSTRACT_PAGE):
            bad.append(q.quantity_id)
    return (not bad), f"reported capacities not found on p.{params.ABSTRACT_PAGE}: {bad}"


def _context_quotes_present() -> tuple[bool, str]:
    bad: list[str] = []
    for cond in context.EXPERIMENTAL_CONTEXT:
        page = cond.evidence.printed_page
        quote = cond.evidence.quote
        if quote and not source.page_contains(page, quote):
            bad.append(f"{cond.key} (p.{page}): {quote!r}")
    return (not bad), f"context quotes not found on their cited page: {bad}"


def _equations_have_pages() -> tuple[bool, str]:
    bad = [
        e["id"] for e in manifest.PRINTED_EQUATIONS
        if not source.FIRST_PRINTED_PAGE <= e["printed_page"] <= source.LAST_PRINTED_PAGE
        or not source.page_text(e["printed_page"]).strip()
    ]
    return (not bad), f"printed equations without a populated cited page: {bad}"


# --------------------------------------------------------------------------- #
# model behaviour
# --------------------------------------------------------------------------- #

#: The constants a check supplies. They are *not* defaults of the model: the
#: package refuses to run without them; the checks just need some value.
_CHECK_INPUTS = dict(cS=1.0, cO=1.0, kLa=60.0, DOT_star=100.0, H=14000.0)


def check_parameters(culture: str = "w3110_exponential") -> model.SimulationParameters:
    """A Table I culture with the checker's own run inputs, for the checks."""
    return model.SimulationParameters.from_culture(culture, **_CHECK_INPUTS)


def _initial_values() -> tuple[bool, str]:
    p = check_parameters()
    notes: list[str] = []
    ok = True
    if abs(p.mu_max - (p.qSmax - p.qm) * p.YXS_ox) > 1e-12:
        ok = False
        notes.append("mu_max does not match (qSmax - qm) YX/S,ox")
    if not (p.rS0 > 0 and p.rO0 > 0):
        ok = False
        notes.append("rS0/rO0 are not positive")
    s = model.subsidiary(p.initial_state(), p)
    if abs(s.qScap - p.qSmax) > 1e-9:
        ok = False
        notes.append("qScap at rS=rS0 is not qSmax")
    notes.append(f"mu_max={p.mu_max:.4f}, rS0={p.rS0:.4f}, rO0={p.rO0:.4f}")
    return ok, "; ".join(notes)


def _printed_worked_example() -> tuple[bool, str]:
    """Reproduce a worked state by hand from the printed chain (W3110, cS=cO=1).

    At the initial state the paper's oxygen-capacity branch must fire, because
    qOs (1.82383) exceeds qOcap (0.607), and mu must come out at 0.45360 1/h.
    """
    p = check_parameters()
    s = model.subsidiary(p.initial_state(), p)
    expected = {"qScap": 1.86, "qOcap": 0.607, "mu": 0.45360}
    got = {"qScap": s.qScap, "qOcap": s.qOcap, "mu": s.mu}
    ok = (
        all(abs(got[k] - v) < 5e-4 for k, v in expected.items())
        and s.oxygen_capacity_clamped
        and abs(s.qOs - p.qOmax) < 1e-9
    )
    return ok, f"worked example {got} (clamped={s.oxygen_capacity_clamped})"


def _maintenance_floor_branch() -> tuple[bool, str]:
    """Force the Appendix's second correction branch and observe it fire."""
    from dataclasses import replace

    p = replace(check_parameters(), qOmax=0.01)
    s = model.subsidiary(p.initial_state(), p)
    ok = s.maintenance_reduced_below_qm and abs(s.qSoxan) < 1e-12 and (
        abs(s.qmr - s.qSox) < 1e-12
    )
    return ok, f"qmr={s.qmr:.6f}, qSox={s.qSox:.6f}, qSoxan={s.qSoxan:.3e}"


def _simulation_runs() -> tuple[bool, str]:
    p = check_parameters()
    result = model.simulate(
        p, model.feed_constant(0.0532), t_end=1.0, dt=0.005, record_every=20
    )
    xs = [s.state.X for s in result.samples]
    finite = all(v == v and abs(v) != float("inf") for v in xs)
    grew = xs[-1] > xs[0]
    vols = [s.state.V for s in result.samples]
    volume_up = vols[-1] > vols[0]
    ok = finite and grew and volume_up
    return ok, (
        f"X {xs[0]:.4f} -> {xs[-1]:.4f}, V {vols[0]:.4f} -> {vols[-1]:.4f}, "
        f"finite={finite}"
    )


def _pulse_equation() -> tuple[bool, str]:
    p = check_parameters()
    # A pulse of 1 g/L into a 7 L culture is 7 g of glucose; no feed contribution.
    q = model.qScap_from_pulse(
        delta_S_g=7.0, integral_F_Si_g=0.0, V_L=p.V0, X_g_per_L=1.0,
        tP_h=0.0, tR_h=0.01,
    )
    ok = abs(q - 100.0) < 1e-9
    return ok, f"qScap_from_pulse(7 g, 0 g, 7 L, 1 g/L, 0, 0.01 h) = {q:.4f} 1/h"


def validate() -> dict[str, Any]:
    """Run every check and return the report the fidelity gate consumes."""
    checks: list[dict[str, Any]] = []
    _check(checks, "source.page_text_complete", *_page_text_complete())
    _check(checks, "source.page_numbering", *_page_numbering())
    _check(checks, "fidelity.table_i_values", *_table_i_on_page())
    _check(checks, "fidelity.abstract_capacities", *_capacities_on_page())
    _check(checks, "fidelity.context_quotes", *_context_quotes_present())
    _check(checks, "model.equations_declared", *_equations_have_pages())
    _check(checks, "model.initial_values", *_initial_values())
    _check(checks, "model.printed_worked_example", *_printed_worked_example())
    _check(checks, "model.maintenance_floor_branch", *_maintenance_floor_branch())
    _check(checks, "model.simulation_runs", *_simulation_runs())
    _check(checks, "model.pulse_equation", *_pulse_equation())

    failures = [f"{c['id']}: {c['detail']}" for c in checks if not c["ok"]]
    return {
        "package": manifest.ARTEFACT_ID,
        "module": "lin2000",
        "paper_folder": "Lin",
        "checks": checks,
        "failures": failures,
        "ok": not failures,
    }
