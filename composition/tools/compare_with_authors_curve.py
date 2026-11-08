"""Compare the frozen prediction, and the paper's own plotted curve, with the data.

    python composition/tools/compare_with_authors_curve.py

The residual analysis shows *that* the frozen implementation disagrees with the held-out
measurements. It cannot say whether the paper's own model agrees with us -- and that
distinction decides which of several explanations survives.

If the paper's own plotted curve shows the same excursions, the disagreement is a
property of the published model under these conditions, not a defect in this
implementation. If it does not, the disagreement is ours.

Two things this measures that a residual table cannot:

* **Off-scale detection.** The paper's curve is clipped by the plot frame in places. A
  clipped curve is not a wrong reading; it is a curve whose value exceeds the axis. A
  comparison that silently treated "above the top of the axis" as a number would be
  inventing one.
* **Whether the model's own claim holds.** The paper's Fig. 3 caption asserts "goodness
  of fit" against data held out of parameter estimation. This reports what the figure
  actually shows, which is a separate question from whether this implementation is
  faithful to it.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "data" / "ganjave2022" / "results" / "evaluation_results.json"
REFERENCE = ROOT / "Models" / "Ganjave" / "data" / "figure_reference_data.json"
OUT = ROOT / "data" / "ganjave2022" / "investigation" / "comparison_with_authors_curve.json"

DATASET_KEY = "5"          # figure_reference_data.json key for paper Fig. 3
BIOMASS_PANEL = "b"
GLYCEROL_PANEL = "c"


def curve_for(reference: dict, panel: str, series: str = "Model_predicted",
              dataset_key: str | None = None):
    """The paper's plotted series, split into the readable span and any clipping.

    Three kinds of sample exist and must not be conflated:

    * a real value inside the axis -- usable;
    * a value at or above the axis maximum -- the curve has left the plot through the
      top spine, so no number can be read off it;
    * a null value -- the digitiser found no trace in that column at all, which is
      not the same as the curve being off-scale.

    Conflating the last two is what makes a comparison quietly wrong, so they are kept
    apart here.
    """
    panel_data = reference["figures"][dataset_key or DATASET_KEY]["panels"][panel]
    calibration = panel_data["calibration"]
    series_data = panel_data["series"].get(series, {})
    y_max = panel_data["axes"]["ylim"][1]
    points = []
    for sample in series_data.get("samples", []):
        value = sample.get("value")
        if value is None or not isinstance(value, (int, float)):
            points.append({
                "t_h": sample["t_h"], "value": None,
                "off_scale": False, "no_trace": True,
            })
            continue
        points.append({
            "t_h": float(sample["t_h"]),
            "value": float(value),
            "off_scale": bool(value >= y_max - 1e-9),
            "no_trace": False,
        })
    return points, y_max, calibration


def curve_for_key(reference: dict, dataset_key: str, panel: str,
                  series: str = "Model_predicted"):
    """``curve_for`` with an explicit figure key, for the second scenario."""
    return curve_for(reference, panel, series=series, dataset_key=dataset_key)


def interpolate(points: list[dict], t: float) -> float | None:
    """The curve's value at ``t``, or ``None`` where it cannot be read.

    Only samples that lie inside the axis are used, and only within the span they
    actually cover. A curve that has left the plot is not extrapolated.
    """
    usable = [
        p for p in points
        if p["value"] is not None and not p["off_scale"]
    ]
    usable.sort(key=lambda p: p["t_h"])
    if len(usable) < 2:
        return None
    if not usable[0]["t_h"] <= t <= usable[-1]["t_h"]:
        return None
    for index in range(len(usable) - 1):
        a, b = usable[index], usable[index + 1]
        if a["t_h"] <= t <= b["t_h"]:
            if b["t_h"] == a["t_h"]:
                return a["value"]
            fraction = (t - a["t_h"]) / (b["t_h"] - a["t_h"])
            return a["value"] + fraction * (b["value"] - a["value"])
    return None


def off_scale_at(points: list[dict], t: float) -> bool:
    """True where the curve has already left the plot through the top spine."""
    beyond = [
        float(p["t_h"]) for p in points
        if p["off_scale"] and not p["no_trace"]
    ]
    if not beyond:
        return False
    return t >= min(beyond)


def main() -> int:
    results = json.loads(RESULTS.read_text(encoding="utf-8"))
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))

    biomass_curve, biomass_y_max, _ = curve_for(reference, BIOMASS_PANEL)
    glycerol_curve, glycerol_y_max, _ = curve_for(reference, GLYCEROL_PANEL)

    report: dict = {
        "analysis_id": "ganjave2022.comparison_with_authors_curve",
        "version": "1.0.0",
        "paper_figure": 3,
        "purpose": (
            "Establishes whether the paper's own plotted model shows the same "
            "disagreement with the held-out measurements as this implementation does. "
            "This is what separates a defect here from a property of the published "
            "model."
        ),
        "axis_limits": {
            "biomass_g_per_L": biomass_y_max,
            "glycerol_g_per_L": glycerol_y_max,
        },
        "off_scale_note": (
            "Where the paper's curve runs above the axis maximum it is clipped by the "
            "plot frame. No value is inferred there; the point is recorded as "
            "off_scale with the axis maximum as a lower bound on the disagreement."
        ),
        "scenarios": {},
    }

    for scenario in results["scenarios"]:
        entry: dict = {"sets": {}}
        for set_name, comparison in scenario["observation_sets"].items():
            is_biomass = comparison["quantity"] == "biomass_concentration"
            curve = biomass_curve if is_biomass else glycerol_curve
            y_max = biomass_y_max if is_biomass else glycerol_y_max

            rows: list[dict] = []
            for row in comparison["rows"]:
                record = {
                    "observation_id": row["observation_id"],
                    "t_h": row["t_h"],
                    "observed_g_per_L": row["observed"],
                    "digitisation_uncertainty": row["combined_uncertainty"],
                    "compared": row.get("compared", False),
                }
                if not row.get("compared"):
                    record["note"] = row.get("exclusion_reason", "")
                    rows.append(record)
                    continue

                authors_value = interpolate(curve, row["t_h"])
                clipped = off_scale_at(curve, row["t_h"])
                record.update({
                    "frozen_prediction_g_per_L": row["predicted"],
                    "frozen_residual_g_per_L": row["residual"],
                    "authors_curve_g_per_L": authors_value,
                    "authors_off_scale": clipped,
                    "authors_axis_maximum_g_per_L": y_max,
                })
                if authors_value is not None:
                    record["authors_residual_g_per_L"] = round(
                        authors_value - row["observed"], 6)
                elif clipped:
                    record["authors_residual_g_per_L"] = None
                    record["authors_residual_lower_bound_g_per_L"] = round(
                        y_max - row["observed"], 6)
                else:
                    record["authors_residual_g_per_L"] = None

                rows.append(record)
            entry["sets"][set_name] = {
                "quantity": comparison["quantity"],
                "unit": comparison["unit"],
                "rows": rows,
            }

            scored = [
                r for r in rows
                if r.get("authors_residual_g_per_L") is not None
            ]
            if scored:
                entry["sets"][set_name]["authors_rmse_g_per_L"] = round(
                    math.sqrt(sum(r["authors_residual_g_per_L"] ** 2
                                  for r in scored) / len(scored)), 6)
            bounded = [r for r in rows if r.get("compared")]
            entry["sets"][set_name]["n_compared"] = len(bounded)
            entry["sets"][set_name]["n_authors_readable"] = len(scored)
            entry["sets"][set_name]["n_authors_off_scale"] = sum(
                1 for r in bounded if r.get("authors_off_scale"))
        report["scenarios"][scenario["scenario_id"]] = entry

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    primary = report["scenarios"]["heldout_fig3"]["sets"][
        "ganjave2022.heldout_observations.fig3b"]
    print("held-out biomass (paper Fig. 3b): frozen vs the authors' own plotted curve")
    print("%9s %10s %12s %12s %12s %10s" % (
        "t (h)", "observed", "frozen pred", "frozen res", "authors", "auth res"))
    for row in primary["rows"]:
        if not row.get("compared"):
            continue
        authors = row["authors_curve_g_per_L"]
        shown = f">{row['authors_axis_maximum_g_per_L']:.0f}*" if row["authors_off_scale"] \
            else (f"{authors:.3f}" if authors is not None else "unreadable")
        auth_res = row["authors_residual_g_per_L"]
        if auth_res is None and row.get("authors_residual_lower_bound_g_per_L") is not None:
            auth_res = row["authors_residual_lower_bound_g_per_L"]
        print("%9.3f %10.3f %12.3f %+12.3f %12s %10s" % (
            row["t_h"], row["observed_g_per_L"], row["frozen_prediction_g_per_L"],
            row["frozen_residual_g_per_L"], shown,
            f"{auth_res:+.3f}" if auth_res is not None else "-"))
    print(f"\nauthors' curve RMSE over the readable points: "
          f"{primary.get('authors_rmse_g_per_L')}")
    print(f"points where the authors' curve is clipped by the axis: "
          f"{primary['n_authors_off_scale']}")
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
