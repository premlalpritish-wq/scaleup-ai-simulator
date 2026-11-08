"""Run the Ganjave reproduction fixture and compare against the paper's figures.

    python tools/run_scientific_validation.py

Loads ``data/validation_fig5.json``, runs every case through the model's own CLI
with the fixture's parameter set and solver, reads the digitized reference data
from ``data/figure_reference_data.json``, computes the fixture's criteria, and
writes ``data/validation_results.json``.

The comparison is against the paper's own plotted model prediction, which is the
right target: matching the *measured* points would require refitting the
parameters against them, and this fixture explicitly does not do that. The
measured points are reported alongside, labelled as measurements, so the
difference between "the model reproduces the model" and "the model reproduces
the experiment" stays visible.

Nothing here adjusts a parameter, an initial condition, or a solver setting to
make a case pass.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

TIMES = [round(t, 3) for t in np.arange(0.0, 24.0 + 1e-9, 0.25)]


def run_model(case: dict, duration_h: float = 24.0) -> dict:
    """One run of the model's own CLI with the case's initial conditions."""
    cmd = [
        sys.executable, "-m", "models", "simulate",
        "--mode", "fed_batch", "--duration", str(duration_h),
        "--X", str(case["X0_g_per_L"]),
        "--S2", str(case["S2_0_g_per_L"]),
        "--DO", str(case["DO0_percent"]),
        "--S1", "2.76", "--V", "0.1",
        "--glycerol-percent", "17.5", "--yeast-percent", "24.5",
        "--flow-ml-h", "0.72", "--feed-start", "6",
    ]
    completed = subprocess.run(
        cmd, cwd=HERE, capture_output=True, text=True, timeout=1200,
    )
    if completed.returncode != 0:
        raise SystemExit(f"model run failed for {case['case_id']}: {completed.stderr}")
    return json.loads(completed.stdout)


def at_time(states: list[dict], t: float, key: str) -> float | None:
    """Interpolate one quantity of the dense trajectory at time `t`."""
    ts = np.array([s["t_h"] for s in states], dtype=float)
    vs = np.array([s[key] for s in states], dtype=float)
    if t < ts[0] - 1e-12 or t > ts[-1] + 1e-12:
        return None
    return float(np.interp(t, ts, vs))


def rel_rmse(ours: list[float], ref: list[float]) -> float:
    """Root-mean-square error as a percentage of the reference mean."""
    a = np.asarray(ours, dtype=float)
    b = np.asarray(ref, dtype=float)
    if a.size == 0:
        return float("nan")
    scale = float(np.mean(np.abs(b)))
    if scale <= 0:
        scale = 1.0
    return float(np.sqrt(np.mean((a - b) ** 2)) / scale * 100.0)


def evaluate(case: dict, reference: dict) -> dict:
    """Run one case and score it against the fixture's criteria."""
    run = run_model(case)
    states = run["states"]

    fig5 = reference["figures"]["6"]["panels"]
    fig3 = reference["figures"]["5"]["panels"]

    # --- against the paper's own plotted model prediction (Fig. 5) -----------
    model_biomass = [s for s in fig5["c"]["series"]["Model_predicted"]["samples"]
                     if s.get("value") is not None]
    model_do = [s for s in fig5["a"]["series"]["Model_predicted"]["samples"]
                if s.get("value") is not None]
    model_gly = [s for s in fig5["d"]["series"]["Model_predicted"]["samples"]
                 if s.get("value") is not None]

    points = []
    for sample in model_biomass:
        t = sample["t_h"]
        ours = at_time(states, t, "biomass_concentration_g_per_L")
        if ours is None:
            continue
        points.append({"t_h": round(t, 3), "reference": sample["value"],
                       "ours": round(ours, 5)})

    biomass_ours = [p["ours"] for p in points]
    biomass_ref = [p["reference"] for p in points]

    do_ours = [at_time(states, t, "dissolved_oxygen_percent") for t in TIMES]
    do_ref = [next((s["value"] for s in model_do
                    if abs(s["t_h"] - t) <= 0.15), None) for t in TIMES]
    do_pairs = [(a, b) for a, b in zip(do_ours, do_ref)
                if a is not None and b is not None]

    gly_ours = [at_time(states, t, "glycerol_concentration_g_per_L") for t in TIMES]
    gly_ref = [next((s["value"] for s in model_gly
                     if abs(s["t_h"] - t) <= 0.15), None) for t in TIMES]
    gly_pairs = [(a, b) for a, b in zip(gly_ours, gly_ref)
                 if a is not None and b is not None]

    # --- the paper's measured points, kept separate and labelled -------------
    measured = [
        {"t_h": m["t_h"], "value_g_per_L": m["value"],
         "uncertainty_g_per_L": round(m["reading_uncertainty"]
                                      + m["calibration_uncertainty"], 4)}
        for m in fig3["b"]["series"]["PDGF"]["marks"]
    ]
    measured_compared = []
    for m in measured:
        ours = at_time(states, m["t_h"], "biomass_concentration_g_per_L")
        if ours is None:
            continue
        measured_compared.append({
            "t_h": round(m["t_h"], 3),
            "measured_g_per_L": m["value_g_per_L"],
            "ours_g_per_L": round(ours, 5),
            "difference_g_per_L": round(ours - m["value_g_per_L"], 5),
            "combined_uncertainty_g_per_L": m["uncertainty_g_per_L"],
        })

    # --- criteria ------------------------------------------------------------
    final = at_time(states, 24.0, "biomass_concentration_g_per_L")
    do_after_feed = [v for t, v in zip(TIMES, do_ours)
                     if t >= 6.0 and v is not None]
    min_do = min(do_after_feed) if do_after_feed else None

    range_lo, range_hi = 19.9, 21.5

    return {
        "case_id": case["case_id"],
        "initial_conditions": {
            "X0_g_per_L": case["X0_g_per_L"],
            "S2_0_g_per_L": case["S2_0_g_per_L"],
            "DO0_percent": case["DO0_percent"],
        },
        "final_biomass_g_per_L": final,
        "min_DO_percent_after_feed": min_do,
        "biomass_vs_model_prediction": {
            "relative_rmse_percent": round(rel_rmse(biomass_our := biomass_ours,
                                                    biomass_ref), 3),
            "points_compared": len(points),
            "first": points[0] if points else None,
            "last": points[-1] if points else None,
        },
        "dissolved_oxygen_vs_model_prediction": {
            "relative_rmse_percent": round(
                rel_rmse([a for a, _b in do_pairs], [b for _a, b in do_pairs]), 3),
            "points_compared": len(do_pairs),
        },
        "glycerol_vs_model_prediction": {
            "relative_rmse_percent": round(
                rel_rmse([a for a, _b in gly_pairs], [b for _a, b in gly_pairs]), 3),
            "points_compared": len(gly_pairs),
        },
        "biomass_vs_measured_points": {
            "note": "the paper's MEASUREMENTS from the held-out validation "
                    "experiment, reported separately and never used as a target",
            "points": measured_compared,
        },
        "criteria": {
            "A_limiting_regime": {
                "pass": min_do is not None and min_do < 10.0,
                "observed_min_DO_percent": min_do,
                "threshold": "< 10 %",
            },
            "B_reported_endpoint": {
                "pass": final is not None and range_lo <= final <= range_hi,
                "observed_final_biomass_g_per_L": final,
                "threshold": f"within [{range_lo}, {range_hi}] g/L",
            },
            "C_model_curve_shape": {
                "pass": rel_rmse(biomass_our, biomass_ref) <= 25.0,
                "observed_relative_rmse_percent": round(
                    rel_rmse(biomass_our, biomass_ref), 3),
                "threshold": "<= 25 %",
            },
        },
        "input_digest": run["provenance"]["input_digest"],
    }


def tn02_what_if(fixture, reference) -> list[dict]:
    """Sensitivity to the unresolved TN-02 reading, as a labelled what-if.

    Table 2 prints the initial enzyme ratio for combination 2 as ``e20/em1``.
    The denominator must be ``e_m2``, which is how the model reads it
    (``e_ratio2_0 = 0.874``), but the printed string cannot be reconciled with
    the notation and the item is open.  Rather than pick a second reading, this
    sweeps the value and reports what the choice costs, so the open item has a
    measured consequence rather than an argument.

    Every run here overrides the parameter, which the model marks ``assumed``
    and records in the result's provenance.  None of these runs is the model;
    none of them is used in any criterion.
    """
    from models.fed_batch import FeedProgram
    from models.initial import build_initial_conditions
    from models.simulation import simulate
    from schemas.parameters import table2_parameter_set

    config = fixture["configuration"]
    primary = next(c for c in fixture["cases"] if c["case_id"] == "primary")
    base = table2_parameter_set()
    feed = FeedProgram(
        S10_g_per_L=config["feed"]["S10_g_per_L"],
        S20_g_per_L=config["feed"]["S20_g_per_L"],
        flow_L_per_h=config["feed"]["flow_mL_per_h"] * 1.0e-3,
        start_time_h=config["feed"]["feed_start_h"],
    )

    curve = [s for s in reference["figures"]["6"]["panels"]["c"]["series"]
             ["Model_predicted"]["samples"]
             if s.get("value") is not None and s["t_h"] <= 24.0]
    ts = np.array([s["t_h"] for s in curve])
    ref_vals = np.array([s["value"] for s in curve])

    out = []
    for e2_0 in (0.1, 0.3, 0.5, 0.874, 1.0):
        params = base.with_overrides(
            {"e_ratio2_0": e2_0},
            reason="what-if sensitivity to the unresolved TN-02 reading "
                   "(Table 2 prints 'e20/em1')",
        )
        conditions = build_initial_conditions(
            X=primary["X0_g_per_L"], S2=primary["S2_0_g_per_L"],
            DO=primary["DO0_percent"], mode="fed_batch",
            S1=config["initial_conditions"]["S1_0"]["value"],
            V=config["initial_conditions"]["V0"]["value"],
            parameters=params,
        )
        result = simulate(
            initial_conditions=conditions,
            duration_h=config["duration_h"],
            mode="fed_batch",
            feed=feed,
            parameters=params,
        )
        states = result.states
        t_all = np.array([s.t for s in states])
        ours = np.array([
            np.interp(t, t_all, [s.X for s in states]) for t in ts
        ])
        out.append({
            "e_ratio2_0": e2_0,
            "is_the_models_reading": e2_0 == 0.874,
            "final_biomass_g_per_L": round(float(states[-1].X), 4),
            "relative_rmse_vs_paper_model_percent": round(rel_rmse(ours, ref_vals), 3),
            "note": "what-if run only; the parameter is marked assumed in its "
                    "provenance and this case is not the model",
        })
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path,
                        default=HERE / "data" / "validation_fig5.json")
    parser.add_argument("--reference", type=Path,
                        default=HERE / "data" / "figure_reference_data.json")
    parser.add_argument("--out", type=Path,
                        default=HERE / "data" / "validation_results.json")
    parser.add_argument("--cases", nargs="*", default=None,
                        help="restrict to these case ids")
    args = parser.parse_args()

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    reference = json.loads(args.reference.read_text(encoding="utf-8"))

    cases = fixture["cases"]
    if args.cases:
        cases = [c for c in cases if c["case_id"] in args.cases]

    results = [evaluate(case, reference) for case in cases]

    # Criterion D: two runs of the primary case must agree.
    primary = next((c for c in cases if c["case_id"] == "primary"), None)
    determinism = None
    if primary is not None:
        a = run_model(primary)
        b = run_model(primary)
        worst = 0.0
        for sa, sb in zip(a["states"], b["states"]):
            for key in ("biomass_concentration_g_per_L",
                        "dissolved_oxygen_percent",
                        "glycerol_concentration_g_per_L"):
                va, vb = sa[key], sb[key]
                denom = max(abs(va), abs(vb), 1e-12)
                worst = max(worst, abs(va - vb) / denom)
        determinism = {
            "pass": worst <= 1e-9,
            "observed_worst_relative_difference": worst,
            "threshold": "<= 1e-9",
            "digests_equal": a["provenance"]["input_digest"]
                              == b["provenance"]["input_digest"],
        }

    tn02 = tn02_what_if(fixture, reference)
    document = {
        "fixture_id": fixture["fixture_id"],
        "fixture_version": fixture["version"],
        "model": fixture["model"],
        "criteria_definitions": fixture["criteria"],
        "cases": results,
        "D_determinism": determinism,
        "tn02_what_if": tn02,
        "status": fixture["status"],
    }
    with args.out.open("w", encoding="utf-8") as fh:
        json.dump(document, fh, indent=2)

    # ---- console summary ---------------------------------------------------
    print("=" * 92)
    print(f"Reproduction fixture {fixture['fixture_id']} v{fixture['version']}")
    print("=" * 92)
    print(f"{'case':>24} {'X(24)':>8} {'minDO':>7} {'RMSEvs':>8} "
          f"{'A':>4} {'B':>4} {'C':>4}")
    print(f"{'':>24} {'g/L':>8} {'%':>7} {'paper':>8} {'':>4} {'':>4} {'':>4}")
    for r in results:
        c = r["criteria"]
        print(
            f"{r['case_id']:>24} "
            f"{'--' if r['final_biomass_g_per_L'] is None else f'{r['final_biomass_g_per_L']:8.3f}'} "
            f"{'--' if r['min_DO_percent_after_feed'] is None else f'{r['min_DO_percent_after_feed']:7.2f}'} "
            f"{r['biomass_vs_model_prediction']['relative_rmse_percent']:8.2f} "
            f"{'PASS' if c['A_limiting_regime']['pass'] else 'FAIL':>4} "
            f"{'PASS' if c['B_reported_endpoint']['pass'] else 'FAIL':>4} "
            f"{'PASS' if c['C_model_curve_shape']['pass'] else 'FAIL':>4}"
        )
    if determinism is not None:
        print()
        print(
            f"D determinism: {'PASS' if determinism['pass'] else 'FAIL'} "
            f"(worst relative difference "
            f"{determinism['observed_worst_relative_difference']:.3e}, "
            f"digests equal: {determinism['digests_equal']})"
        )
    print()
    print("A = oxygen-limited after feeding   B = final biomass in the paper's "
          "reported range")
    print("C = biomass trajectory vs the paper's own plotted model prediction")
    print()
    for r in results:
        m = r["biomass_vs_measured_points"]
        pts = m["points"]
        if not pts:
            continue
        worst = max(p["difference_g_per_L"] for p in pts)
        unc = min(p["combined_uncertainty_g_per_L"] for p in pts)
        print(
            f"  {r['case_id']:>24}: vs {len(pts)} measured points from the "
            f"held-out experiment, worst difference {worst:+.3f} g/L "
            f"(reading uncertainty >= {unc:.3f} g/L) -- measurements, not a target"
        )
    print()
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
