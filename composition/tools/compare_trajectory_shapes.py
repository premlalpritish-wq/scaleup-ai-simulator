"""Diagnostic: how does this implementation differ from the paper's own plotted curve?

    python composition/tools/compare_trajectory_shapes.py

The held-out residual analysis establishes that this implementation disagrees with the
paper's measurements. It cannot, on its own, say whether that disagreement is a defect
here or a property of the published model. Comparing the two *curves* on the same time
axis can: a transcription defect in the dynamics produces a difference that grows and
changes sign as the trajectory evolves, whereas a difference that stays roughly
constant is the signature of a scale term -- a yield, or an initial condition -- rather
than of the equations being wrong.

This is a diagnostic, not a correction. It fits nothing and changes nothing; it reports
the shape of a difference so the failure report can be attributed correctly.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "composition" / "tools"))

import compare_with_authors_curve as authors  # noqa: E402

RESULTS = ROOT / "data" / "ganjave2022" / "results" / "evaluation_results.json"
REFERENCE = ROOT / "Models" / "Ganjave" / "data" / "figure_reference_data.json"
RUNS = ROOT / "data" / "ganjave2022" / "results" / "runs"
OUT = ROOT / "data" / "ganjave2022" / "investigation" / "trajectory_shape_comparison.json"


def load_curve(run_name: str, port: str):
    payload = json.loads((RUNS / run_name).read_text(encoding="utf-8"))
    for result in payload["results"]:
        for output in result["outputs"]:
            if output["ref"]["port_id"] == port:
                trajectory = output["value"]["extra"]["trajectory"]
                return (np.asarray(trajectory["time_axis"]["values"], dtype=float),
                        np.asarray(trajectory["values"], dtype=float),
                        trajectory["unit"])
    raise SystemExit(f"{run_name}: no trajectory for {port}")


def curve_difference(run_name: str, dataset_key: str, panel: str,
                     reference: dict) -> dict:
    """Our trajectory minus the paper's, over the span where theirs is readable."""
    curve, y_max, _ = authors.curve_for_key(reference, dataset_key, panel)
    usable = sorted(
        [p for p in curve if p["value"] is not None and not p["off_scale"]],
        key=lambda p: p["t_h"],
    )
    a_t = np.asarray([p["t_h"] for p in usable], dtype=float)
    a_v = np.asarray([p["value"] for p in usable], dtype=float)

    times, values, unit = load_curve(run_name, "biomass_concentration")
    grid = np.linspace(a_t[0], a_t[-1], 400)
    ours = np.interp(grid, times, values)
    theirs = np.interp(grid, a_t, a_v)
    difference = ours - theirs

    def stats(mask: np.ndarray) -> dict:
        d = difference[mask]
        if d.size == 0:
            return {}
        return {
            "n": int(d.size),
            "mean_g_per_L": round(float(d.mean()), 4),
            "sd_g_per_L": round(float(d.std(ddof=1)) if d.size > 1 else 0.0, 4),
            "min_g_per_L": round(float(d.min()), 4),
            "max_g_per_L": round(float(d.max()), 4),
        }

    early = grid <= 12.0
    late = grid > 12.0
    slope, intercept = np.polyfit(grid, difference, 1)
    predicted = slope * grid + intercept
    ss_res = float(np.sum((difference - predicted) ** 2))
    ss_tot = float(np.sum((difference - difference.mean()) ** 2))

    return {
        "run": run_name,
        "dataset_key": dataset_key,
        "panel": panel,
        "unit": unit,
        "comparison_window_h": [float(grid[0]), float(grid[-1])],
        "n_points": int(grid.size),
        "authors_axis_maximum_g_per_L": y_max,
        "difference_ours_minus_authors": {
            "overall": stats(np.ones(grid.size, dtype=bool)),
            "before_12h": stats(early),
            "after_12h": stats(late),
        },
        "linear_trend": {
            "slope_g_per_L_per_h": round(float(slope), 6),
            "intercept_g_per_L": round(float(intercept), 4),
            "r_squared": round(1.0 - ss_res / ss_tot, 6) if ss_tot > 0 else None,
        },
    }


def main() -> int:
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))

    scenarios = {
        "heldout_fig3": curve_difference(
            "heldout_fig3.result.json", "5", "b", reference),
        "optimum_fig5": curve_difference(
            "optimum_fig5.result.json", "6", "c", reference),
    }

    report = {
        "diagnostic_id": "ganjave2022.trajectory_shape_comparison",
        "version": "1.0.0",
        "question": (
            "Is the difference between this implementation and the paper's own "
            "plotted model curve a change in the dynamics, or a constant scale "
            "difference?"
        ),
        "scenarios": scenarios,
        "reading": {
            "flat_difference": (
                "A near-zero slope means the difference does not grow with time. That "
                "is the signature of a scale term rather than of the equations being "
                "transcribed differently: a wrong numerator, denominator, "
                "parenthesisation or rate law changes how the trajectory evolves, "
                "not where it sits."
            ),
            "different_offsets_across_scenarios": (
                "If the offset has the same sign and size in both feed recipes it is a "
                "single scale term. If it changes with the recipe it is something the "
                "feed changes -- a substrate-specific yield, most likely -- and that "
                "is a different candidate explanation."
            ),
        },
        "interpretation_limit": (
            "This locates the difference; it does not name its cause. A constant "
            "offset is consistent with a yield coefficient, an initial condition, or a "
            "systematic offset in how the authors' curve was digitised, and this "
            "diagnostic cannot separate those three."
        ),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    for name, block in scenarios.items():
        overall = block["difference_ours_minus_authors"]["overall"]
        late = block["difference_ours_minus_authors"]["after_12h"]
        trend = block["linear_trend"]
        print(f"{name} (paper figure key {block['dataset_key']}, panel {block['panel']}):")
        print(f"  span   : {block['comparison_window_h'][0]:.2f} - "
              f"{block['comparison_window_h'][1]:.2f} h")
        print(f"  overall: mean {overall['mean_g_per_L']:+.4f} g/L, "
              f"sd {overall['sd_g_per_L']:.4f}")
        print(f"  >12 h  : mean {late['mean_g_per_L']:+.4f} g/L, sd {late['sd_g_per_L']:.4f}")
        print(f"  trend  : {trend['slope_g_per_L_per_h']:+.5f} g/L per h, "
              f"R^2 = {trend['r_squared']:.4f}")
        print()
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
