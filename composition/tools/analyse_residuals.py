"""Residual analysis for the held-out trajectory, with a dependency-free SVG plot.

    python composition/tools/analyse_residuals.py

Reads the frozen evaluation results, and for every compared observation reports the
signed residual, the absolute and squared error, the digitisation uncertainty, the
point's share of the sum of squared errors, and what the RMSE would be without it.
Then writes ``data/ganjave2022/investigation/residuals.json`` and a trajectory plot.

## What this does and does not claim

A residual is a number. It says the prediction and the reading disagree by that much,
and nothing about *why*. The structural segmentation below reports where the sign
changes and where the error grows; attributing either to a mechanism is the
investigation report's job and requires evidence this file does not contain.

The one thing computed here that is more than bookkeeping is the leave-one-out RMSE,
because it is what makes "this point dominates" a measured claim rather than an
impression.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data" / "ganjave2022" / "results" / "evaluation_results.json"
RUNS = ROOT / "data" / "ganjave2022" / "results" / "runs"
OUT_DIR = ROOT / "data" / "ganjave2022" / "investigation"
OUT_JSON = OUT_DIR / "residuals.json"
OUT_SVG = OUT_DIR / "heldout_trajectory.svg"

#: A residual is called *material* when it exceeds twice the observation's own
#: digitisation uncertainty. Below that, the disagreement is inside the resolution of
#: the reference data and cannot be distinguished from reading noise.
MATERIAL_SIGMA = 2.0

#: Process landmarks in the fed-batch run, from the paper and the model's own
#: trajectory. Used only to segment the residuals for reporting; no number is changed.
PHASES = [
    ("batch_growth", 0.0, 6.0, "before feeding; batch phase"),
    ("fed_batch_start", 6.0, 12.0, "feed starts at 6 h; DO falls"),
    ("late_fed_batch", 12.0, 27.0, "after 12 h; substrate-limited growth"),
]


def phase_of(t: float) -> str:
    for name, low, high, _ in PHASES:
        if low <= t < high:
            return name
    return PHASES[-1][0]


def rows_for(results: dict, scenario_id: str, quantity: str
             ) -> tuple[str, list[dict[str, Any]]]:
    for scenario in results["scenarios"]:
        if scenario["scenario_id"] != scenario_id:
            continue
        for name, comparison in scenario["observation_sets"].items():
            if comparison["quantity"] == quantity:
                return name, comparison
    raise SystemExit(f"no {quantity} set in scenario {scenario_id}")


def enrich(rows: list[dict[str, Any]], rmse: float) -> list[dict[str, Any]]:
    """Add the per-point error accounting.

    ``share_of_sse`` is the point's fraction of the total squared error -- the honest
    way to say which observation dominates. ``rmse_if_excluded`` is separate and
    different: removing a point changes the mean as well as the sum, so the two can
    disagree, and only the second says what the comparison would look like without it.
    """
    scored = [r for r in rows if r.get("compared") and "residual" in r]
    total_sse = sum(r["residual"] ** 2 for r in scored) or 1.0

    out: list[dict[str, Any]] = []
    for row in rows:
        enriched = dict(row)
        if not row.get("compared") or "residual" not in row:
            enriched["phase"] = phase_of(row["t_h"])
            enriched.update({
                "squared_error": None,
                "share_of_sse": None,
                "rmse_if_excluded": None,
                "material": False,
            })
            out.append(enriched)
            continue

        residual = row["residual"]
        others = [r["residual"] for r in scored if r is not row]
        remaining_rmse = (
            math.sqrt(sum(v ** 2 for v in others) / len(others)) if others else None
        )
        limit = MATERIAL_SIGMA * row["combined_uncertainty"]
        enriched.update({
            "phase": phase_of(row["t_h"]),
            "abs_error": round(abs(residual), 6),
            "squared_error": round(residual ** 2, 6),
            "share_of_sse": round(residual ** 2 / total_sse, 6),
            "rmse_if_excluded": round(remaining_rmse, 6) if remaining_rmse else None,
            "material_2sigma": bool(abs(residual) > limit),
            "material": bool(abs(residual) > limit),
            "signed_in_uncertainty_units": round(
                residual / row["combined_uncertainty"], 4),
        })
        out.append(enriched)
    return out


def characterise(rows: list[dict[str, Any]], rmse: float, bias: float) -> dict[str, Any]:
    """The descriptive facts about the residual pattern. No mechanism is inferred."""
    scored = [r for r in rows if r.get("compared") and "residual" in r]
    material = [r for r in scored if r["material"]]
    positive = [r for r in scored if r["residual"] > 0]
    negative = [r for r in scored if r["residual"] < 0]

    # Where does the disagreement first exceed what the reference data can resolve?
    first_material = None
    for row in sorted(scored, key=lambda r: r["t_h"]):
        if row["material"]:
            first_material = {
                "t_h": row["t_h"],
                "residual_g_per_L": row["residual"],
                "uncertainty_g_per_L": row["combined_uncertainty"],
            }
            break

    by_phase: dict[str, dict[str, Any]] = {}
    for name, low, high, description in PHASES:
        members = [r for r in scored if low <= r["t_h"] < high]
        if not members:
            continue
        by_phase[name] = {
            "window_h": [low, high],
            "description": description,
            "n": len(members),
            "mean_residual_g_per_L": round(
                sum(r["residual"] for r in members) / len(members), 6),
            "rmse_g_per_L": round(
                math.sqrt(sum(r["residual"] ** 2 for r in members) / len(members)), 6),
            "n_material": sum(1 for r in members if r["material"]),
        }

    ranked = sorted(scored, key=lambda r: r["share_of_sse"], reverse=True)
    return {
        "n_compared": len(scored),
        "rmse_g_per_L": rmse,
        "bias_g_per_L": bias,
        "sign": {
            "positive": len(positive),
            "negative": len(negative),
            "verdict": (
                "predictions run high" if len(positive) > len(negative)
                else "predictions run low" if len(negative) > len(positive)
                else "balanced"
            ),
        },
        "first_material_divergence": first_material,
        "by_phase": by_phase,
        "largest_contributors": [
            {
                "observation_id": r["observation_id"],
                "t_h": r["t_h"],
                "residual_g_per_L": r["residual"],
                "share_of_sse": r["share_of_sse"],
                "rmse_if_excluded": r["rmse_if_excluded"],
            }
            for r in ranked[:4]
        ],
        "rmse_excluding_single_largest_contributor": (
            ranked[0]["rmse_if_excluded"] if ranked else None
        ),
        "growth_pattern": _growth_pattern(by_phase),
        "endpoint_consistency": None,  # filled by the caller, which knows the endpoint
    }


def _growth_pattern(by_phase: dict[str, dict[str, Any]]) -> str:
    """Describes only whether the mean error grows with time. Names no mechanism."""
    order = [n for n, _, _, _ in PHASES if n in by_phase]
    means = [by_phase[n]["mean_residual_g_per_L"] for n in order]
    rmses = [by_phase[n]["rmse_g_per_L"] for n in order]
    growing = all(b > a for a, b in zip(rmses, rmses[1:]))
    shrinking = all(b < a for a, b in zip(rmses, rmses[1:]))
    if growing:
        shape = "error grows monotonically with time"
    elif shrinking:
        shape = "error shrinks with time"
    else:
        shape = "error is not monotonic in time"
    return (
        f"{shape}. Mean signed residual by phase (g/L): "
        + ", ".join(f"{n}={by_phase[n]['mean_residual_g_per_L']:+.3f}" for n in order)
        + ". RMSE by phase (g/L): "
        + ", ".join(f"{n}={by_phase[n]['rmse_g_per_L']:.3f}" for n in order)
    )


# --------------------------------------------------------------------------- #
# a small dependency-free SVG plotter
# --------------------------------------------------------------------------- #


class Svg:
    """Just enough SVG to draw axes, a curve, points and error bars."""

    def __init__(self, width: int = 900, height: int = 560) -> None:
        self.width, self.height = width, height
        self.parts: list[str] = []

    def add(self, markup: str) -> None:
        self.parts.append(markup)

    def render(self) -> str:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" '
            f'height="{self.height}" viewBox="0 0 {self.width} {self.height}" '
            f'font-family="Helvetica,Arial,sans-serif">'
            + "".join(self.parts) + "</svg>"
        )


def plot_trajectory(svg: Svg, predicted: list[tuple[float, float]],
                    observations: list[dict[str, Any]],
                    title: str, subtitle: str, x_label: str, y_label: str,
                    x_max: float, y_max: float, material_sigma: float) -> None:
    left, right, top, bottom = 78, 24, 58, 74
    plot_w = svg.width - left - right
    plot_h = svg.height - top - bottom

    def sx(t: float) -> float:
        return left + plot_w * (t / x_max if x_max else 0)

    def sy(v: float) -> float:
        return top + plot_h * (1.0 - (v / y_max if y_max else 0))

    svg.add(f'<rect width="{svg.width}" height="{svg.height}" fill="#ffffff"/>')
    svg.add(f'<text x="{left}" y="26" font-size="16" font-weight="bold" '
            f'fill="#111">{title}</text>')
    svg.add(f'<text x="{left}" y="44" font-size="11" fill="#666">{subtitle}</text>')

    # Grid and axes.
    for i in range(6):
        value = y_max * i / 5
        y = sy(value)
        svg.add(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" '
                f'stroke="#e8e8e8"/>')
        svg.add(f'<text x="{left - 8}" y="{y + 4:.1f}" font-size="10" fill="#555" '
                f'text-anchor="end">{value:.0f}</text>')
    for i in range(9):
        value = x_max * i / 8
        x = sx(value)
        svg.add(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}" '
                f'stroke="#f2f2f2"/>')
        svg.add(f'<text x="{x:.1f}" y="{top + plot_h + 18}" font-size="10" fill="#555" '
                f'text-anchor="middle">{value:.0f}</text>')

    svg.add(f'<rect x="{left}" y="{top}" width="{plot_w}" height="{plot_h}" '
            f'fill="none" stroke="#888"/>')
    svg.add(f'<text x="{left + plot_w / 2:.0f}" y="{svg.height - 14}" font-size="11" '
            f'fill="#333" text-anchor="middle">{x_label}</text>')
    svg.add(f'<text x="18" y="{top + plot_h / 2:.0f}" font-size="11" fill="#333" '
            f'text-anchor="middle" transform="rotate(-90 18 {top + plot_h / 2:.0f})">'
            f'{y_label}</text>')

    # Feed start, a documented landmark.
    feed_x = sx(6.0)
    svg.add(f'<line x1="{feed_x:.1f}" y1="{top}" x2="{feed_x:.1f}" '
            f'y2="{top + plot_h}" stroke="#c88" stroke-width="1" '
            f'stroke-dasharray="4,3"/>')
    svg.add(f'<text x="{feed_x + 4:.1f}" y="{top + 12}" font-size="9" fill="#a66">'
            f'feed starts 6 h</text>')

    # Model prediction.
    if predicted:
        path = " ".join(
            f"{'M' if i == 0 else 'L'}{sx(t):.2f},{sy(v):.2f}"
            for i, (t, v) in enumerate(predicted)
            if v is not None
        )
        svg.add(f'<path d="{path}" fill="none" stroke="#3060c0" stroke-width="2"/>')

    # Observations with their digitisation uncertainty.
    for row in observations:
        if not row.get("compared"):
            continue
        x, y = sx(row["t_h"]), sy(row["observed"])
        sigma = row["combined_uncertainty"]
        colour = "#d04020" if row.get("material") else "#2a8a4a"
        svg.add(f'<line x1="{x:.1f}" y1="{sy(row["observed"] - sigma):.1f}" '
                f'x2="{x:.1f}" y2="{sy(row["observed"] + sigma):.1f}" '
                f'stroke="{colour}" stroke-width="1.2" opacity="0.65"/>')
        for cap in (row["observed"] - sigma, row["observed"] + sigma):
            svg.add(f'<line x1="{x - 4:.1f}" y1="{sy(cap):.1f}" x2="{x + 4:.1f}" '
                    f'y2="{sy(cap):.1f}" stroke="{colour}" stroke-width="1.2" '
                    f'opacity="0.65"/>')
        svg.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{colour}" '
                f'stroke="#ffffff" stroke-width="1"/>')

    # Legend.
    legend_x, legend_y = left + 12, top + plot_h - 14
    entries = [
        ("#3060c0", "model prediction"),
        ("#2a8a4a", "observation within 2 sigma"),
        ("#d04020", f"observation beyond {material_sigma:g} sigma"),
        ("#999999", "digitisation uncertainty (+/- 1 sigma)"),
    ]
    for index, (colour, label) in enumerate(entries):
        y = legend_y - index * 15
        svg.add(f'<rect x="{legend_x}" y="{y - 8}" width="11" height="9" '
                f'fill="{colour}"/>')
        svg.add(f'<text x="{legend_x + 17}" y="{y}" font-size="10" fill="#333">'
                f'{label}</text>')


# --------------------------------------------------------------------------- #


def main() -> int:
    results = json.loads(RESULTS.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "analysis_id": "ganjave2022.heldout_residual_analysis",
        "version": "1.0.0",
        "source_results": "data/ganjave2022/results/evaluation_results.json",
        "material_threshold": (
            f"|residual| > {MATERIAL_SIGMA:g} x the observation's own digitisation "
            f"uncertainty. Below this the disagreement is inside the resolution of "
            f"the reference data."
        ),
        "phases": [
            {"name": n, "window_h": [lo, hi], "description": d}
            for n, lo, hi, d in PHASES
        ],
        "claim_limit": (
            "These are measurements of disagreement. No mechanism is inferred here; "
            "attribution requires evidence this file does not contain."
        ),
        "scenarios": {},
    }

    plots: list[tuple[str, list[tuple[float, float]], list[dict], dict]] = []

    for scenario in results["scenarios"]:
        name, comparison = rows_for(
            results, scenario["scenario_id"], "biomass_concentration")
        metrics = comparison["metrics"]
        rows = enrich(comparison["rows"], metrics["rmse_g_per_L"])
        character = characterise(rows, metrics["rmse_g_per_L"], metrics["bias_g_per_L"])

        endpoint = scenario.get("endpoint")
        if endpoint:
            character["endpoint_consistency"] = {
                "observed_at_h": endpoint["observed_at_h"],
                "observed_g_per_L": endpoint["observed_g_per_L"],
                "predicted_g_per_L": endpoint["predicted_g_per_L"],
                "error_g_per_L": endpoint["error_g_per_L"],
                "agrees_in_sign_with_mean_bias": (
                    (endpoint["error_g_per_L"] > 0) == (metrics["bias_g_per_L"] > 0)
                ),
                "note": (
                    "A single endpoint cannot confirm or refute a trajectory-wide "
                    "pattern; it is recorded so the two can be compared."
                ),
            }

        payload["scenarios"][scenario["scenario_id"]] = {
            "observation_set": name,
            "evaluation_role": scenario["evaluation_role"],
            "blinded": scenario["blinded"],
            "metrics": metrics,
            "metrics_excluding_declared_anomaly":
                comparison.get("metrics_excluding_declared_anomaly"),
            "characterisation": character,
            "observations": rows,
        }
        plots.append((scenario["scenario_id"], [], rows, character))

    # Prediction curve from the stored run, decimated for a readable polyline.
    import numpy as np

    run_payload = json.loads(
        (RUNS / "heldout_fig3.result.json").read_text(encoding="utf-8"))
    times, values = None, None
    for result in run_payload["results"]:
        for output in result["outputs"]:
            if output["ref"]["port_id"] == "biomass_concentration":
                trajectory = output["value"]["extra"]["trajectory"]
                times = np.asarray(trajectory["time_axis"]["values"], dtype=float)
                values = np.asarray(trajectory["values"], dtype=float)
    if times is not None:
        keep = [i for i, t in enumerate(times) if t <= 27.0][::6]
        if keep and keep[-1] != len(times) - 1:
            keep.append(int(np.searchsorted(times, 27.0)))
        curve = [(float(times[i]), float(values[i])) for i in keep]
        plots[0] = ("heldout_fig3", curve, plots[0][2], plots[0][3])
        payload["prediction_curve_sampled"] = {
            "scenario": "heldout_fig3",
            "port": "biomass_concentration",
            "unit": "g/L",
            "n_sampled_points": len(curve),
            "note": (
                "Decimated for plotting only. Every metric in this file is computed "
                "on the solver's full dense output."
            ),
        }

    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")

    for scenario_id, curve, rows, _character in plots:
        scored = [r for r in rows if r.get("compared") and "residual" in r]
        svg = Svg()
        plot_trajectory(
            svg, curve, scored,
            title=f"Ganjave et al. (2022) held-out validation experiment (Fig. 3b)",
            subtitle=(
                f"scenario {scenario_id} - paper-reported experimental biomass against "
                f"the frozen prediction (parameters as printed, not refitted)"),
            x_label="time (h)", y_label="biomass (g/L DCW)",
            x_max=27.0, y_max=22.0, material_sigma=MATERIAL_SIGMA,
        )
        path = OUT_DIR / f"heldout_trajectory_{scenario_id}.svg"
        path.write_text(svg.render(), encoding="utf-8")

    print(f"wrote {OUT_JSON.relative_to(ROOT)}")
    for scenario_id, entry in payload["scenarios"].items():
        character = entry["characterisation"]
        print(f"  {scenario_id}: RMSE {character['rmse_g_per_L']:.3f}, bias "
              f"{character['bias_g_per_L']:+.3f}, {character['sign']['verdict']}")
        print(f"    first material divergence: {character['first_material_divergence']}")
        print(f"    {character['growth_pattern']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
