"""Execute the frozen configuration and compare with the independent observations.

    python composition/tools/evaluate_heldout_biomass.py

Builds one graph document per scenario in ``data/ganjave2022/frozen_configuration.json``,
runs each through ``python -m composition.runner`` -- the normal ScaleUp AI execution
pipeline -- reads the predictions back, compares them against the digitized
experimental observations in ``data/ganjave2022/observations.json``, evaluates the
pre-registered criteria from ``data/ganjave2022/evaluation_protocol.json``, runs the
sensitivity cases, and writes
``data/ganjave2022/results/evaluation_results.json``.

## What this does not do

It does not adjust a parameter, an initial condition, a feed value or a solver setting.
It does not choose a scenario, a criterion or a threshold. It does not refit anything.
If a criterion fails, the failure is written down with its observed value and its
threshold and the run continues to the next one. The decision rule is read from the
protocol, not implemented here, so changing the code cannot change the verdict.

## Why the runner and not the model's own CLI

The evaluation has to go through the path the application uses, so that what is being
validated is what a user would actually get: the same adapters, the same diagnostics,
the same composition report and the same provenance. A private CLI path could pass
while the shipped pipeline failed.

## Why the observations are read only from the dataset

The dataset separates observations from the authors' model curve at the file level.
This tool reads ``observation_sets`` for targets and ``model_predictions`` for the
like-for-like benchmark, and never crosses the two. The authors' curve is a benchmark,
never a target: matching it shows the equations were transcribed faithfully, which is a
different and weaker claim than reproducing the experiment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
COMPOSITION = ROOT / "composition"
DATA = ROOT / "data" / "ganjave2022"
RESULTS = DATA / "results"

CONFIG = DATA / "frozen_configuration.json"
DATASET = DATA / "observations.json"
PROTOCOL = DATA / "evaluation_protocol.json"

GANJAVE_MODEL_ID = "ganjave"
GANJAVE_MODEL_VERSION = "0.1.0"

#: The ports Ganjave requires and the paper does not supply. Every one of these
#: carries a source reference in the literal; the adapter will not invent a default,
#: and neither does this tool.
REQUIRED_LITERALS = {
    "initial_biomass_concentration": (
        "mass_concentration", "g/L",
        "Ganjave et al. 2022, sec. 2.2, printed p. 2: initial culture OD600 of 0.05. "
        "The paper prints no OD600-to-dry-cell-weight calibration, so this g/L value is "
        "an assumption, not a paper value."
    ),
    "initial_complex_substrate_concentration": (
        "mass_concentration", "g/L",
        "Derived from the stated medium: SOB is tryptone 20 g/L plus yeast extract 5 g/L "
        "(printed p. 2, sec. 2.2), both complex nitrogen-rich substrates. Derived from a "
        "stated recipe, not a stated model input."
    ),
    "initial_dissolved_oxygen": (
        "dimensionless", "%",
        "Not stated in the paper. An air-saturated shake flask is declared as 100 %. "
        "Sensitivity case do0_80 tests whether it matters."
    ),
    "feed_glycerol_concentration": (
        "mass_concentration", "g/L",
        "Reported feed recipe at the paper's own 1 % w/v = 10 g/L convention."
    ),
    "feed_complex_substrate_concentration": (
        "mass_concentration", "g/L",
        "Reported feed recipe at the paper's own 1 % w/v = 10 g/L convention."
    ),
    "feed_flow_rate": (
        "volume_flow", "mL/h",
        "Reported feed rate at the paper's own 1 mL/h = 1e-3 L/h convention. Volumetric, "
        "not a mass flow: a mass rate would need a feed density the paper does not state."
    ),
    "feed_start_time": (
        "time", "h",
        "Printed p. 3, sec. 3.1: feeding begins at 6 h, the DO landmark."
    ),
}


# --------------------------------------------------------------------------- #
# graph construction
# --------------------------------------------------------------------------- #


def literal(port_id: str, value: float, unit: str) -> dict[str, Any]:
    quantity, declared_unit, source_ref = REQUIRED_LITERALS[port_id]
    assert declared_unit == unit, (
        f"{port_id}: the frozen config says {unit} but the contract declares "
        f"{declared_unit}. A silent unit change would be an invented conversion."
    )
    return {
        "state": "number",
        "quantity": quantity,
        "value": value,
        "unit": unit,
        "source_ref": source_ref,
        "method": "declared graph input; see the assumption register for its classification",
        "reason": "Required by the model with no default. The adapter will not invent one.",
    }


def build_graph(scenario: dict[str, Any], initial: dict[str, float] | None = None,
                case_id: str = "primary") -> dict[str, Any]:
    """One graph document, built only from the frozen configuration.

    ``initial`` overrides the three conditions the paper does not state. It is used
    only by the sensitivity cases and is recorded in the result, so a sensitivity run
    can never be mistaken for the primary one.
    """
    values = {
        "X0": scenario["initial_conditions"]["X0"]["value"],
        "S2_0": scenario["initial_conditions"]["S2_0"]["value"],
        "DO0": scenario["initial_conditions"]["DO0"]["value"],
        "S1_0": scenario["initial_conditions"]["S1_0"]["value"],
        "V0": scenario["initial_conditions"]["V0"]["value"],
    }
    if initial:
        values.update(initial)

    feed = scenario["feed"]
    instance_id = f"ganjave_{case_id}"
    return {
        "contract_version": "0.1.0",
        "graph_id": f"ganjave2022-heldout-{scenario['scenario_id']}-{case_id}",
        "title": (
            f"Ganjave et al. (2022) fed-batch, paper Fig. {scenario['paper_figure']} "
            f"configuration; single model, no connections"
        ),
        "description": (
            "Frozen evaluation configuration from "
            "data/ganjave2022/frozen_configuration.json. Parameters are Table 2 as "
            "printed and are not refitted. One instance and no connections: this "
            "evaluates a model, not a composition."
        ),
        "source_ref": (
            "Ganjave et al. 2022, Biotechnology Reports 33:e00694, "
            "doi:10.1016/j.btre.2021.e00694"
        ),
        "notes": (
            "Expect success_with_warnings: capability.unsupported findings are "
            "statements about the model, not failures of the run."
        ),
        "instances": [{
            "instance_id": instance_id,
            "model_id": GANJAVE_MODEL_ID,
            "model_version": GANJAVE_MODEL_VERSION,
            "label": f"Frozen evaluation: paper Fig. {scenario['paper_figure']}",
            "role": "single model under evaluation",
            "position": {"x": 240, "y": 160},
            "parameters": {
                "simulation": {
                    "mode": scenario["mode"],
                    "duration_h": scenario["duration_h"],
                    "output_times_h": [0.0, 6.0, 12.0, 18.0, 24.0, scenario["duration_h"]],
                    "solver": dict(
                        json.loads(CONFIG.read_text(encoding="utf-8"))["model"]["solver"]
                    ),
                }
            },
        }],
        "connections": [],
        "literal_inputs": {
            f"{instance_id}/initial_biomass_concentration":
                literal("initial_biomass_concentration", values["X0"], "g/L"),
            f"{instance_id}/initial_complex_substrate_concentration":
                literal("initial_complex_substrate_concentration", values["S2_0"], "g/L"),
            f"{instance_id}/initial_dissolved_oxygen":
                literal("initial_dissolved_oxygen", values["DO0"], "%"),
            f"{instance_id}/initial_glycerol_concentration":
                {
                    "state": "number", "quantity": "mass_concentration",
                    "value": values["S1_0"], "unit": "g/L",
                    "source_ref": (
                        "Ganjave et al. 2022, sec. 2.2, printed p. 2: 'The initial "
                        "production medium was supplemented with 2.76 g/L glycerol'. "
                        "Reported directly."
                    ),
                    "method": "reported initial concentration",
                    "reason": "The only initial concentration the paper states.",
                },
            f"{instance_id}/initial_culture_volume":
                {
                    "state": "number", "quantity": "volume",
                    "value": values["V0"], "unit": "L",
                    "source_ref": (
                        "Ganjave et al. 2022, sec. 2.3, printed p. 2: 'These flasks were "
                        "filled with 100 mL medium'. Reported directly."
                    ),
                    "method": "reported working volume",
                    "reason": "Reported directly.",
                },
            f"{instance_id}/feed_glycerol_concentration":
                literal("feed_glycerol_concentration", feed["S10_g_per_L"]["value"], "g/L"),
            f"{instance_id}/feed_complex_substrate_concentration":
                literal("feed_complex_substrate_concentration", feed["S20_g_per_L"]["value"], "g/L"),
            f"{instance_id}/feed_flow_rate":
                literal("feed_flow_rate", feed["flow_mL_per_h"]["value"], "mL/h"),
            f"{instance_id}/feed_start_time":
                literal("feed_start_time", feed["feed_start_h"]["value"], "h"),
        },
        "defaults": {},
    }


def run_graph(document: dict[str, Any], workdir: Path, tag: str) -> dict[str, Any]:
    """Run one graph through the normal pipeline and return the result document."""
    workdir.mkdir(parents=True, exist_ok=True)
    graph_path = workdir / f"{tag}.graph.json"
    result_path = workdir / f"{tag}.result.json"
    graph_path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    completed = subprocess.run(
        [sys.executable, "-m", "composition.runner",
         "--graph", str(graph_path), "--result", str(result_path)],
        cwd=COMPOSITION, capture_output=True, text=True, timeout=3600,
        env={"PYTHONPATH": str(COMPOSITION), "PATH": ""},
    )
    if not result_path.exists():
        raise SystemExit(
            f"{tag}: the runner wrote no result document.\n"
            f"exit {completed.returncode}\n{completed.stdout[-3000:]}\n"
            f"{completed.stderr[-3000:]}"
        )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload["_exit_code"] = completed.returncode
    return payload


# --------------------------------------------------------------------------- #
# extracting the prediction
# --------------------------------------------------------------------------- #


def trajectory_of(payload: dict[str, Any], port_id: str) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """The solver's dense output for one port, plus its unit."""
    for result in payload.get("results", []):
        for output in result.get("outputs", []):
            if output["ref"]["port_id"] != port_id:
                continue
            trajectory = output["value"]["extra"]["trajectory"]
            return (
                np.asarray(trajectory["time_axis"]["values"], dtype=float),
                np.asarray(trajectory["values"], dtype=float),
                {"quantity": trajectory["quantity"], "unit": trajectory["unit"],
                 "instance_id": result["instance_id"]},
            )
    raise SystemExit(f"the run published no trajectory for port {port_id!r}")


def at(times: np.ndarray, values: np.ndarray, t: float) -> float:
    """Linear interpolation of the *prediction* onto an observed time.

    The prediction is interpolated; the observation never is.
    """
    return float(np.interp(t, times, values))


def authors_curve(dataset: dict[str, Any], paper_figure: int, panel: str,
                  quantity_axis: str) -> tuple[np.ndarray, np.ndarray] | None:
    """The authors' own plotted model curve for one panel, read from the digitisation.

    Samples whose value is not finite are dropped. The trace is read from a raster
    column profile and runs off the end of the readable span into empty columns; a
    sample there carries ``NaN``. Interpolating across one would poison a whole
    metric, so those times are simply where the curve is not readable -- which is
    what they are.
    """
    source = json.loads(
        (ROOT / "Models" / "Ganjave" / "data" / "figure_reference_data.json")
        .read_text(encoding="utf-8")
    )
    key = {3: "5", 5: "6"}[paper_figure]
    series = source["figures"][key]["panels"][panel]["series"]["Model_predicted"]
    samples = series.get("samples", [])
    if not samples:
        return None
    times = np.asarray([s["t_h"] for s in samples], dtype=float)
    values = np.asarray([s["value"] for s in samples], dtype=float)
    finite = np.isfinite(times) & np.isfinite(values)
    times, values = times[finite], values[finite]
    if times.size < 2:
        return None
    order = np.argsort(times)
    return times[order], values[order]


# --------------------------------------------------------------------------- #
# comparison
# --------------------------------------------------------------------------- #


def compare(observations: list[dict[str, Any]], times: np.ndarray,
            values: np.ndarray, authors: tuple[np.ndarray, np.ndarray] | None,
            duration_h: float) -> dict[str, Any]:
    """Every compared point, with its residual, plus the aggregate metrics."""
    rows: list[dict[str, Any]] = []
    for observation in observations:
        t = observation["t_h"]
        in_window = 0.0 <= t <= duration_h
        row = {
            "observation_id": observation["observation_id"],
            "t_h": t,
            "observed": observation["value"],
            "combined_uncertainty": observation["combined_uncertainty"],
            "culture": observation["culture"],
            "compared": in_window,
            "exclusion_reason": "" if in_window else (
                "outside the simulated interval [0, %g] h" % duration_h),
        }
        if in_window:
            predicted = at(times, values, t)
            residual = predicted - observation["value"]
            row["predicted"] = round(predicted, 6)
            row["residual"] = round(residual, 6)
            row["abs_residual"] = round(abs(residual), 6)
            row["within_1_sigma"] = abs(residual) <= observation["combined_uncertainty"]
            row["within_2_sigma"] = abs(residual) <= 2.0 * observation["combined_uncertainty"]
            if authors is not None:
                a_t, a_v = authors
                authors_value = (
                    at(a_t, a_v, t)
                    if a_t[0] <= t <= a_t[-1] else None
                )
                if authors_value is not None and np.isfinite(authors_value):
                    row["authors_model"] = round(authors_value, 6)
                    row["authors_residual"] = round(
                        authors_value - observation["value"], 6)
                    row["authors_abs_residual"] = round(
                        abs(authors_value - observation["value"]), 6)
                else:
                    # Not readable here. Recorded rather than skipped silently, so a
                    # benchmark that covers fewer points than a metric says so.
                    row["authors_model"] = None
                    row["authors_residual"] = None
                    row["authors_abs_residual"] = None
                    row["authors_unreadable"] = True
        rows.append(row)

    compared = [r for r in rows if r["compared"]]
    scored = [r for r in compared if "residual" in r]
    return {"rows": rows, "metrics": metrics(scored)}


def metrics(scored: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate error statistics over the compared points.

    Returned as ``None`` rather than 0 when a metric is undefined, so an empty
    comparison can never read as a perfect one.
    """
    if not scored:
        return {"n": 0}
    residual = np.asarray([r["residual"] for r in scored], dtype=float)
    observed = np.asarray([r["observed"] for r in scored], dtype=float)
    rmse = float(np.sqrt(np.mean(residual ** 2)))
    mae = float(np.mean(np.abs(residual)))
    scale = float(np.mean(np.abs(observed)))
    out: dict[str, Any] = {
        "n": len(scored),
        "rmse_g_per_L": round(rmse, 6),
        "mae_g_per_L": round(mae, 6),
        "bias_g_per_L": round(float(np.mean(residual)), 6),
        "observed_mean_g_per_L": round(scale, 6),
        "normalised_rmse_percent": round(rmse / scale * 100.0, 4) if scale > 0 else None,
        "max_abs_residual_g_per_L": round(float(np.max(np.abs(residual))), 6),
        "within_1_sigma": sum(1 for r in scored if r["within_1_sigma"]),
        "within_2_sigma": sum(1 for r in scored if r["within_2_sigma"]),
    }
    out["fraction_within_2_sigma"] = round(out["within_2_sigma"] / len(scored), 6)

    authors = [r for r in scored if r.get("authors_abs_residual") is not None]
    if authors:
        a = np.asarray([r["authors_abs_residual"] for r in authors], dtype=float)
        authors_rmse = float(np.sqrt(np.mean(a ** 2)))
        out["n_vs_authors"] = len(authors)
        out["authors_unreadable"] = len(scored) - len(authors)
        out["authors_rmse_g_per_L"] = (
            round(authors_rmse, 6) if np.isfinite(authors_rmse) else None)
        out["authors_bias_g_per_L"] = round(
            float(np.mean([r["authors_residual"] for r in authors])), 6)
        out["authors_within_2_sigma"] = sum(
            1 for r in authors
            if r["authors_abs_residual"] <= 2.0 * r["combined_uncertainty"])
        # Only comparable over the points where both curves are readable.
        ours_over_same = np.asarray(
            [r["abs_residual"] for r in authors], dtype=float)
        ours_rmse_same = float(np.sqrt(np.mean(ours_over_same ** 2)))
        out["rmse_g_per_L_where_authors_readable"] = round(ours_rmse_same, 6)
        out["ratio_rmse_ours_over_authors"] = (
            round(ours_rmse_same / authors_rmse, 6)
            if authors_rmse > 0 and np.isfinite(authors_rmse) else None)
    return out


def endpoint_error(scored: list[dict[str, Any]], target_h: float = 24.0,
                   window_h: float = 1.0) -> dict[str, Any] | None:
    """Endpoint error from the observation nearest 24 h within a stated window."""
    candidates = [
        r for r in scored
        if r.get("compared") and abs(r["t_h"] - target_h) <= window_h
    ]
    if not candidates:
        return None
    best = min(candidates, key=lambda r: abs(r["t_h"] - target_h))
    return {
        "target_h": target_h,
        "observed_at_h": best["t_h"],
        "observed_g_per_L": best["observed"],
        "predicted_g_per_L": best["predicted"],
        "error_g_per_L": round(best["abs_residual"], 6),
        "within_uncertainty": best["within_2_sigma"],
    }


# --------------------------------------------------------------------------- #
# criteria
# --------------------------------------------------------------------------- #


def limit_of(threshold: Any) -> float:
    """The numeric bound inside a protocol threshold such as ``"<= 1.5"``.

    Parsed rather than duplicated, so the number that decides the verdict is the
    number written in the protocol. Editing the code cannot move a threshold.
    """
    if isinstance(threshold, (int, float)):
        return float(threshold)
    text = str(threshold).strip()
    for operator in ("<=", ">=", "<", ">", "=="):
        if text.startswith(operator):
            return float(text[len(operator):].strip())
    return float(text)


def range_of(threshold: Any) -> tuple[float, float]:
    """The bounds inside a protocol range such as ``"[19.9, 21.5]"``."""
    if isinstance(threshold, (list, tuple)) and len(threshold) == 2:
        return float(threshold[0]), float(threshold[1])
    text = str(threshold).strip().strip("[]()")
    low, _, high = text.partition(",")
    return float(low), float(high)


def evaluate_criteria(protocol: dict[str, Any], scenario_id: str,
                      per_set: dict[str, dict[str, Any]], run: dict[str, Any]
                      ) -> dict[str, Any]:
    """Apply the protocol's thresholds. The rules live in the protocol, not here."""
    verdicts: dict[str, Any] = {}
    biomass_sets = [
        s for s in per_set.values() if s["quantity"] == "biomass_concentration"
    ]
    biomass_metrics = biomass_sets[0]["metrics"] if biomass_sets else {"n": 0}
    final_biomass = run.get("final_biomass_g_per_L")
    min_do = run.get("min_DO_percent_after_feed")

    for criterion in protocol["criteria"]:
        if scenario_id not in criterion["applies_to"]:
            continue
        cid = criterion["id"]
        passed: bool | None = None
        observed: Any = None
        threshold = criterion["threshold"]
        note = ""

        if cid == "E_heldout_trajectory":
            limit = limit_of(threshold["rmse_g_per_L"])
            observed = biomass_metrics.get("rmse_g_per_L")
            passed = observed is not None and observed <= limit
        elif cid == "F_no_worse_than_authors_model":
            limit = limit_of(threshold["ratio"])
            observed = biomass_metrics.get("ratio_rmse_ours_over_authors")
            if observed is None:
                # An unevaluable criterion is inconclusive, never a failure.
                # Scoring "we could not tell" as "it failed" would be a claim
                # nobody made, and it is the same conflation the composition
                # report exists to prevent.
                passed, note = None, (
                    "the authors' model curve could not be evaluated against enough "
                    "of the observations to form a benchmark")
            else:
                passed = observed <= limit
        elif cid == "G_oxygen_limiting_regime":
            observed = min_do
            passed = min_do is not None and min_do < 10.0
        elif cid == "H_agreement_with_reported_uncertainty":
            threshold_fraction = 0.6
            observed = biomass_metrics.get("fraction_within_2_sigma")
            passed = observed is not None and observed >= threshold_fraction
        elif cid == "I_reported_endpoint_range":
            low, high = range_of(threshold["range_g_per_L"])
            observed = final_biomass
            passed = final_biomass is not None and low <= final_biomass <= high
        elif cid == "J_determinism":
            observed = run.get("determinism_relative_difference")
            passed = observed is not None and observed <= limit_of(threshold["relative_difference"])

        verdicts[cid] = {
            "statement": criterion["statement"],
            "primary": criterion["primary"],
            "threshold": threshold,
            "observed": observed,
            "pass": passed,
            "verdict": "pass" if passed else ("inconclusive" if passed is None else "fail"),
            "note": note,
        }

    return verdicts


def decide(verdicts: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    """PASS / FAIL / INCONCLUSIVE, straight from the protocol's decision rule."""
    primary = [v for v in verdicts.values() if v["primary"]]
    if any(v["verdict"] == "inconclusive" for v in primary):
        outcome = "inconclusive"
    elif any(v["verdict"] == "fail" for v in primary):
        outcome = "fail"
    elif primary and all(v["verdict"] == "pass" for v in primary):
        outcome = "pass"
    else:
        outcome = "inconclusive"

    failures = [
        {"criterion": cid, "observed": v["observed"], "threshold": v["threshold"]}
        for cid, v in verdicts.items() if v["verdict"] == "fail"
    ]
    return {
        "outcome": outcome,
        "primary_criteria": sorted(v["statement"][:40] for v in primary),
        "failures": failures,
        "scope_of_a_pass": (
            "A pass would establish only that this implementation reproduces these "
            "observations under these conditions. It is not a validation of any "
            "composed process, and not a claim of general predictive accuracy."
        ),
        "what_this_never_establishes": [
            "validation of a composed process: no composition was evaluated",
            "general predictive accuracy beyond paper Fig. 3's and Fig. 5's conditions",
            "any statement about a second culture, a scale-up, or another strain",
        ],
    }


# --------------------------------------------------------------------------- #
# scenarios
# --------------------------------------------------------------------------- #


def evaluate_scenario(scenario: dict[str, Any], dataset: dict[str, Any],
                      protocol: dict[str, Any], workdir: Path) -> dict[str, Any]:
    document = build_graph(scenario)
    payload = run_graph(document, workdir, scenario["scenario_id"])
    composition_report = payload.get("composition_report") or {}

    if not payload.get("results"):
        raise SystemExit(
            f"{scenario['scenario_id']} produced no result:\n"
            f"{json.dumps(payload.get('diagnostics', []), indent=2)[:3000]}"
        )

    times, values, units = trajectory_of(payload, "biomass_concentration")
    if units["unit"] != "g/L":
        raise SystemExit(f"biomass came back in {units['unit']!r}, expected g/L")

    glycerol_times, glycerol_values, _ = trajectory_of(payload, "glycerol_concentration")

    per_set: dict[str, dict[str, Any]] = {}
    for observation_set in dataset["observation_sets"]:
        if observation_set["observation_set_id"] not in scenario["observation_sets"]:
            continue
        panel = observation_set["panel"]
        is_biomass = observation_set["quantity"] == "biomass_concentration"
        authors = authors_curve(
            dataset, observation_set["paper_figure"], panel,
            observation_set["quantity"]) if is_biomass else None
        comparison = compare(
            observation_set["points"],
            times if is_biomass else glycerol_times,
            values if is_biomass else glycerol_values,
            authors,
            scenario["duration_h"],
        )
        comparison["quantity"] = observation_set["quantity"]
        comparison["unit"] = observation_set["unit"]
        comparison["paper_figure"] = observation_set["paper_figure"]
        per_set[observation_set["observation_set_id"]] = comparison

    # Excluding the pre-declared non-monotone mark, as the protocol requires.
    biomass_sets = [s for s in per_set.values()
                    if s["quantity"] == "biomass_concentration"]
    for comparison in biomass_sets:
        scored = comparison["rows"]
        excluding = [r for r in scored if r["observation_id"] != "fig3b:PDGF:8"]
        comparison["metrics_excluding_declared_anomaly"] = metrics(
            [r for r in excluding if "residual" in r]
        )

    final_biomass = at(times, values, min(24.0, scenario["duration_h"]))
    do_times, do_values, _ = trajectory_of(payload, "dissolved_oxygen")
    window = (do_times >= 6.0) & (do_times <= 24.0)
    min_do = float(np.min(do_values[window])) if window.any() else None

    repeat = run_graph(build_graph(scenario), workdir, f"{scenario['scenario_id']}-repeat")
    repeat_times, repeat_values, _ = trajectory_of(repeat, "biomass_concentration")
    denominator = float(np.max(np.abs(values))) or 1.0
    determinism = float(np.max(np.abs(values - repeat_values))) / denominator

    run_summary = {
        "status": payload.get("status"),
        "exit_code": payload.get("_exit_code"),
        "final_biomass_g_per_L": round(final_biomass, 6),
        "min_DO_percent_after_feed": round(min_do, 6) if min_do is not None else None,
        "determinism_relative_difference": determinism,
        "model_versions": payload.get("model_versions", {}),
        "reproducibility_digest": payload.get("reproducibility", ""),
        "error_count": payload.get("error_count", 0),
        "warning_count": payload.get("warning_count", 0),
        "composition_report": {
            "schema": composition_report.get("schema"),
            "execution": composition_report.get("execution"),
            "connections": composition_report.get("connections"),
            "combined_graph": (composition_report.get("science") or {}).get("combined_graph"),
        },
        "diagnostics": [
            {"code": d.get("code"), "severity": d.get("severity"),
             "message": str(d.get("message", ""))[:400]}
            for d in payload.get("diagnostics", [])
        ],
        "provenance": {
            result["instance_id"]: [
                {"where": r.get("where"), "kind": r.get("kind"),
                 "method": str(r.get("method", ""))[:160]}
                for r in output.get("provenance_chain", [])
            ]
            for result in payload.get("results", [])
            for output in result.get("outputs", [])
            if output["ref"]["port_id"] == "biomass_concentration"
        },
    }

    verdicts = evaluate_criteria(protocol, scenario["scenario_id"], per_set, run_summary)
    decision = decide(verdicts, protocol)

    return {
        "scenario_id": scenario["scenario_id"],
        "evaluation_role": scenario["role"],
        "blinded": scenario["blinded"],
        "blinding_note": scenario["blinding_note"],
        "paper_figure": scenario["paper_figure"],
        "independence": scenario["independence"],
        "duration_h": scenario["duration_h"],
        "run": run_summary,
        "observation_sets": per_set,
        "endpoint": endpoint_error(
            biomass_sets[0]["rows"] if biomass_sets else []),
        "criteria": verdicts,
        "decision": decision,
    }


def run_sensitivity(scenario: dict[str, Any], dataset: dict[str, Any],
                    workdir: Path) -> list[dict[str, Any]]:
    """Vary the conditions the paper does not state. Reported separately, never merged."""
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []
    biomass_set_id = None
    for observation_set in dataset["observation_sets"]:
        if (observation_set["observation_set_id"] in scenario["observation_sets"]
                and observation_set["quantity"] == "biomass_concentration"):
            biomass_set_id = observation_set["observation_set_id"]
    points = next(
        s["points"] for s in dataset["observation_sets"]
        if s["observation_set_id"] == biomass_set_id)

    for case in protocol["sensitivity"]["cases"]:
        change = case["change"]
        field, _, raw = change.partition("=")
        overrides = {field.strip(): float(raw.split()[0])}
        payload = run_graph(
            build_graph(scenario, overrides, case_id=case["case_id"]),
            workdir, f"sensitivity-{case['case_id']}")
        times, values, _ = trajectory_of(payload, "biomass_concentration")
        comparison = compare(points, times, values, None, scenario["duration_h"])
        out.append({
            "case_id": case["case_id"],
            "change": change,
            "why": case["why"],
            "overrides": overrides,
            "final_biomass_g_per_L": round(
                at(times, values, min(24.0, scenario["duration_h"])), 6),
            "metrics": comparison["metrics"],
        })
    return out


# --------------------------------------------------------------------------- #


def json_safe(value: Any) -> Any:
    """Strict JSON, with no NaN or Infinity.

    ``json.dumps`` writes bare ``NaN`` by default, which is not valid JSON and is
    rejected by most parsers -- including Godot's. A machine-readable artefact that
    only some parsers accept is not machine-readable, and a non-finite number in a
    metric almost always means "undefined", which is better written as ``null``.
    """
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if np.isfinite(number) else None
    return value


def digest_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default=None,
                        help="evaluate one scenario; default is all of them")
    parser.add_argument("--no-sensitivity", action="store_true")
    arguments = parser.parse_args()

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))

    workdir = RESULTS / "runs"
    RESULTS.mkdir(parents=True, exist_ok=True)

    scenarios = [
        s for s in config["scenarios"]
        if arguments.scenario in (None, s["scenario_id"])
    ]
    evaluated = [evaluate_scenario(s, dataset, protocol, workdir) for s in scenarios]

    sensitivity: dict[str, Any] = {}
    if not arguments.no_sensitivity:
        for scenario in scenarios:
            if scenario["scenario_id"] != "heldout_fig3":
                continue
            sensitivity[scenario["scenario_id"]] = run_sensitivity(
                scenario, dataset, workdir)

    payload = {
        "result_id": "ganjave2022.heldout_evaluation",
        "protocol_version": protocol["version"],
        "protocol_id": protocol["protocol_id"],
        "scope": config["scope"],
        "input_digests": {
            "frozen_configuration.json": digest_of(CONFIG),
            "observations.json": digest_of(DATASET),
            "evaluation_protocol.json": digest_of(PROTOCOL),
            "figure_reference_data.json": digest_of(
                ROOT / "Models" / "Ganjave" / "data" / "figure_reference_data.json"),
            "reference_parameters.json": digest_of(
                ROOT / "Models" / "Ganjave" / "data" / "reference_parameters.json"),
        },
        "scenarios": evaluated,
        "sensitivity": sensitivity,
        "composition_finding": {
            "statement": (
                "No cross-model composition was evaluated. Every cross-model boundary "
                "in composition/composition/cross_model.py is refused and both permitted "
                "boundaries are same-model, so no composition is scientifically "
                "available to validate. See reports/COMPOSED_PROCESS_VALIDATION_PLAN.md."
            ),
            "cross_model_boundaries_permitted": [
                "morris2011.material_balance -> morris2011.material_balance",
                "ganjave -> ganjave",
            ],
        },
    }

    out = RESULTS / "evaluation_results.json"
    out.write_text(
        json.dumps(json_safe(payload), indent=2, ensure_ascii=False, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )

    for scenario in evaluated:
        decision = scenario["decision"]
        print(f"{scenario['scenario_id']} ({scenario['evaluation_role']}, "
              f"blinded={scenario['blinded']}): {decision['outcome'].upper()}")
        for cid, verdict in scenario["criteria"].items():
            mark = {"pass": "PASS", "fail": "FAIL"}.get(verdict["verdict"], "????")
            observed = verdict["observed"]
            if isinstance(observed, float):
                observed = round(observed, 4)
            print(f"    {mark}  {cid:<36} observed={observed}")
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
