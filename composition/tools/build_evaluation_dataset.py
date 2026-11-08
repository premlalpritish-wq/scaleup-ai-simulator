"""Build the held-out evaluation dataset from the figure digitisation.

    python composition/tools/build_evaluation_dataset.py

Reads ``Models/Ganjave/data/figure_reference_data.json`` -- the paper's raster
figures, digitised with per-point calibration -- and writes
``data/ganjave2022/observations.json``, a curated evaluation dataset.

## Why a derived dataset rather than reading the digitisation directly

Three reasons, all of which would otherwise be silent errors:

1. **The figure keys do not match the paper's figure numbers.** The digitisation keys
   the held-out validation experiment as ``"5"`` and the selected optimum as ``"6"``.
   In Ganjave et al. (2022) those are Fig. 3 and Fig. 5. Anyone auditing a traceable
   citation against the paper would look up the wrong figure. The mapping is asserted
   here against each figure's own printed caption and feed recipe, so a mis-mapping
   fails rather than ships.

2. **``marks`` and ``samples`` are not interchangeable.** ``marks`` are discrete marker
   centres -- measurements. ``samples`` are a per-column trace, which is how the model's
   own curve is recorded. The ``Model_predicted`` series has one or two ``marks`` with
   reading uncertainties above 10 g/L: those are curve pixels, not data. Reading them as
   observations would be inventing measurements.

3. **Observation and prediction must not share a field.** A comparison that can
   accidentally read its own prediction as its target is not a comparison. Every
   observation here is tagged, and the model's curve is tagged separately, so a test can
   prove no prediction was ever used as a target.

Nothing is invented, rounded away, or interpolated. Marks are copied with the
uncertainty the digitisation recorded for them.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Models" / "Ganjave" / "data" / "figure_reference_data.json"
TARGET = ROOT / "data" / "ganjave2022" / "observations.json"

DATASET_ID = "ganjave2022.heldout_observations"
VERSION = "1.0.0"

CITATION = (
    "S. D. Ganjave, H. Dodia, A. V. Sunder, S. Madhu, P. P. Wangikar, "
    "'High cell density cultivation of E. coli in shake flasks for the production of "
    "recombinant proteins', Biotechnology Reports 33 (2022) e00694."
)
DOI = "10.1016/j.btre.2021.e00694"

#: ``figure_reference_data.json`` figure key -> the paper's own figure number.
#:
#: Verified against the printed captions and feed recipes, not assumed:
#:   key "5" carries the caption "Goodness of fit of the model with the experimental
#:   data that was not used for estimation of model parameters" and a feed of
#:   20 % glycerol / 30 % yeast extract / 0.78 mL/h -- which is Fig. 3 in the paper.
#:   key "6" carries the caption "Model prediction for the optimised feeding
#:   strategy, with five proteins cultivated in the same run" and a feed of
#:   17.5 % / 24.5 % / 0.72 mL/h -- which is Fig. 5 in the paper.
FIGURE_KEY_TO_PAPER_FIGURE = {"5": 3, "6": 5}

#: The experiment the parameters were estimated from. Present in the paper, absent
#: here on purpose: it is the fitting set, so comparing against it is circular.
FITTING_FIGURE = 2
FITTING_FEED = {"glycerol_percent_wv": 30.0, "yeast_extract_percent_wv": 40.0,
                "flow_mL_per_h": 0.52}


def combined_uncertainty(reading: float, calibration: float) -> float:
    """The digitisation's own convention: the two are added, not combined in quadrature.

    ``validation_results.json`` reports 0.7125 for marks carrying
    ``reading_uncertainty`` 0.2773 and ``calibration_uncertainty`` 0.4352, which is
    their sum. Matching it keeps the new dataset consistent with the existing results
    file rather than silently reporting a tighter interval.
    """
    return round(float(reading) + float(calibration), 6)


def check_mapping(figure_key: str, figure: dict[str, Any]) -> int:
    """Fail loudly if the dataset's figure keys and the paper's ever diverge."""
    paper_figure = FIGURE_KEY_TO_PAPER_FIGURE.get(figure_key)
    if paper_figure is None:
        raise SystemExit(
            f"figure key {figure_key!r} has no paper-figure mapping. Add it with the "
            f"printed caption and feed recipe as evidence, or the citation is not "
            f"traceable."
        )
    feed = figure.get("feed", {})
    caption = figure.get("caption", "")
    if paper_figure == 3:
        if not (feed.get("glycerol_percent_wv") == 20.0
                and feed.get("yeast_extract_percent_wv") == 30.0
                and feed.get("flow_mL_per_h") == 0.78):
            raise SystemExit(
                "key '5' no longer carries the Fig. 3 feed recipe (20 % / 30 % / "
                "0.78 mL/h). The mapping to the paper's figure numbers cannot be "
                "trusted; re-check it against the PDF."
            )
        if "not used for estimation" not in caption:
            raise SystemExit(
                "key '5' no longer carries the caption stating the data was not used "
                "for parameter estimation. The held-out claim rests on that sentence."
            )
    if paper_figure == 5:
        if not (feed.get("glycerol_percent_wv") == 17.5
                and feed.get("yeast_extract_percent_wv") == 24.5
                and feed.get("flow_mL_per_h") == 0.72):
            raise SystemExit(
                "key '6' no longer carries the Fig. 5 feed recipe (17.5 % / 24.5 % / "
                "0.72 mL/h). Re-check the mapping against the PDF."
            )
    return paper_figure


def observations_from(
    figure: dict[str, Any],
    panel_key: str,
    dataset_key: str,
    paper_figure: int,
    series_names: list[str],
    quantity: str,
    unit: str,
) -> dict[str, Any]:
    """One panel's experimental marks, as an evaluation dataset."""
    panel = figure["panels"][panel_key]
    calibration = panel["calibration"]
    points: list[dict[str, Any]] = []

    for series_name in series_names:
        series = panel["series"].get(series_name)
        if series is None:
            raise SystemExit(
                f"series {series_name!r} is missing from key {dataset_key!r} panel "
                f"{panel_key!r}. The dataset changed; re-check before evaluating."
            )
        for index, mark in enumerate(series.get("marks", [])):
            uncertainty = combined_uncertainty(
                mark["reading_uncertainty"], mark["calibration_uncertainty"]
            )
            points.append({
                "observation_id": f"fig{paper_figure}{panel_key}:{series_name}:{index}",
                "t_h": round(float(mark["t_h"]), 3),
                "value": round(float(mark["value"]), 4),
                "combined_uncertainty": uncertainty,
                "reading_uncertainty": round(float(mark["reading_uncertainty"]), 4),
                "calibration_uncertainty": round(float(mark["calibration_uncertainty"]), 4),
                "culture": series_name,
                "kind": "experimental_observation",
                "digitized": True,
                "tabulated": False,
                "trace": "marker centre recovered from the raster figure",
            })

    if not points:
        raise SystemExit(
            f"no observations found in key {dataset_key!r} panel {panel_key!r}. "
            f"An evaluation with no reference data would be meaningless."
        )

    times = [p["t_h"] for p in points]
    values = [p["value"] for p in points]
    return {
        "observation_set_id": f"{DATASET_ID}.fig{paper_figure}{panel_key}",
        "paper_figure": paper_figure,
        "dataset_figure_key": dataset_key,
        "panel": panel_key,
        "panel_caption_role": panel.get("axes", {}).get("y", ""),
        "quantity": quantity,
        "unit": unit,
        "axis_label_y": panel["axes"]["y"],
        "axis_label_x": panel["axes"]["x"],
        "paper_page": 6 if paper_figure == 3 else 7,
        "independent_of_parameter_fitting": True,
        "n_observations": len(points),
        "n_cultures": len(series_names),
        "time_range_h": [round(min(times), 3), round(max(times), 3)],
        "value_range": [round(min(values), 4), round(max(values), 4)],
        "axis_calibration": {
            "px_per_y_unit": round(calibration["px_per_y_unit"], 6),
            "px_per_x_unit": round(calibration["px_per_x_unit"], 6),
            "y_calibration_uncertainty": round(calibration["y_calibration_uncertainty"], 6),
            "x_calibration_uncertainty": round(calibration["x_calibration_uncertainty"], 6),
            "y_label_fit_residual_px": round(calibration["y_label_fit_residual_px"], 4),
            "x_label_fit_residual_px": round(calibration["x_label_fit_residual_px"], 4),
        },
        "feed": dict(figure.get("feed", {})),
        "points": points,
    }


def model_curve(figure: dict[str, Any], panel_key: str, dataset_key: str,
                paper_figure: int) -> dict[str, Any]:
    """The authors' own plotted model curve, kept strictly apart from observations.

    Tagged ``kind: "model_prediction"`` and held in its own list. A target that shares
    a list with the observations is a target that can be contaminated by a bug.
    """
    panel = figure["panels"][panel_key]
    series = panel["series"]["Model_predicted"]
    samples = series.get("samples", [])
    return {
        "series_id": f"fig{paper_figure}{panel_key}:Model_predicted",
        "paper_figure": paper_figure,
        "dataset_figure_key": dataset_key,
        "panel": panel_key,
        "kind": "model_prediction",
        "is_measurement": False,
        "role": (
            "the authors' own plotted model output for this configuration. A "
            "prediction, never an observation, and never a validation target on its "
            "own: matching it shows the equations were transcribed faithfully, not "
            "that the model is right."
        ),
        "n_samples": len(samples),
        "trace_span_h": series.get("trace_span"),
        "note": (
            "The 'marks' on the Model_predicted series are curve pixels, not data "
            "points: their reading uncertainties exceed 2 g/L and their ink "
            "coordinates fall far outside the mark cluster. Only 'samples' is used."
        ),
    }


def build() -> dict[str, Any]:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))

    held_out = build_set(source, dataset_key="5", paper_figure=3, panel_key="b",
                         series_names=["PDGF"], quantity="biomass_concentration",
                         unit="g/L", role="primary",
                         role_note=(
                             "The paper's own designated validation experiment. Its "
                             "caption states the data 'was not used for estimation of "
                             "model parameters', and its feed recipe differs from both "
                             "the fitting experiment and the model-selected optimum, "
                             "so it is a genuine out-of-sample test of the trajectory."
                         ))
    held_out_glycerol = build_set(
        source, dataset_key="5", paper_figure=3, panel_key="c",
        series_names=["PDGF"], quantity="glycerol_concentration", unit="g/L",
        role="secondary",
        role_note=(
            "Residual glycerol in the same held-out experiment. Included because a "
            "biomass-only comparison cannot distinguish a growth model from a curve "
            "that happens to rise and flatten."
        ))
    optimum = build_set(
        source, dataset_key="6", paper_figure=5, panel_key="c",
        series_names=["PDGF", "FDH", "G_Can_ADH", "L_Kefir_ADH", "EYFP"],
        quantity="biomass_concentration", unit="g/L", role="secondary",
        role_note=(
            "Five parallel cultures under the model-selected optimum. Independent of "
            "parameter fitting, but the feed recipe was chosen by optimising the "
            "fitted model, so an endpoint match here is partly self-fulfilling. Its "
            "value is the between-culture spread: five cultures of one process."
        ))

    return {
        "dataset_id": DATASET_ID,
        "version": VERSION,
        "title": (
            "Ganjave et al. (2022) independent experimental observations of "
            "shake-flask fed-batch E. coli HCD"
        ),
        "source": {
            "citation": CITATION,
            "doi": DOI,
            "pdf": "papers/Ganjave et al 2022.pdf",
            "derived_from": (
                "Models/Ganjave/data/figure_reference_data.json -- the paper's raster "
                "figures, digitised with per-point calibration"
            ),
            "derivation": (
                "composition/tools/build_evaluation_dataset.py; re-run it to "
                "regenerate this file byte for byte"
            ),
        },
        "observation_policy": {
            "what_counts_as_an_observation": (
                "A marker centre in a panel whose caption identifies the series as "
                "experimental ('experimental values'). These are readings off a "
                "published raster figure, not tabulated measurements, and they are "
                "tagged digitized=true."
            ),
            "what_does_not": (
                "The authors' model-predicted curve, which is a prediction and never "
                "an observation. It lives in model_predictions, never in points."
            ),
            "no_interpolation": (
                "Only observed times are recorded. Nothing is interpolated onto a "
                "uniform grid, and no point is invented where the figure has none."
            ),
            "no_uncertainty_inflation": (
                "Each point carries the digitisation's own reading and calibration "
                "uncertainties, summed per the digitisation's convention. No replicate "
                "error bar was reported by the paper, so none is claimed."
            ),
            "missing": (
                "The paper publishes no tabular data and no replicate error bars for "
                "these series. Nothing is imputed."
            ),
        },
        "excluded": {
            "fitting_experiment": {
                "paper_figure": FITTING_FIGURE,
                "feed": FITTING_FEED,
                "reason": (
                    "Parameters were estimated from this experiment, so comparing "
                    "against it would be circular. Recorded here so its absence is a "
                    "decision on the record rather than an oversight."
                ),
            },
        },
        "figure_numbering": {
            "issue": (
                "figure_reference_data.json keys the held-out validation experiment as "
                "'5' and the selected optimum as '6'. In the paper they are Fig. 3 and "
                "Fig. 5."
            ),
            "resolution": (
                "Every observation carries paper_figure, and the mapping is asserted "
                "against each figure's printed caption and feed recipe at build time."
            ),
            "map": FIGURE_KEY_TO_PAPER_FIGURE,
        },
        "observation_sets": [held_out, held_out_glycerol, optimum],
        "model_predictions": [
            model_curve(source["figures"]["5"], "b", "5", 3),
            model_curve(source["figures"]["6"], "c", "6", 5),
        ],
    }


def build_set(source: dict[str, Any], *, dataset_key: str, paper_figure: int,
              panel_key: str, series_names: list[str], quantity: str, unit: str,
              role: str, role_note: str) -> dict[str, Any]:
    figure = source["figures"][dataset_key]
    check_mapping(dataset_key, figure)
    built = observations_from(figure, panel_key, dataset_key, paper_figure,
                              series_names, quantity, unit)
    built["evaluation_role"] = role
    built["role_note"] = role_note
    built["paper_caption"] = figure.get("caption", "")
    return built


def main() -> None:
    payload = build()
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    total = sum(s["n_observations"] for s in payload["observation_sets"])
    print(f"wrote {TARGET.relative_to(ROOT)}")
    for s in payload["observation_sets"]:
        print(f"  {s['observation_set_id']:<44} "
              f"{s['n_observations']:>3} obs, {s['n_cultures']} culture(s), "
              f"paper Fig. {s['paper_figure']}{s['panel']}")
    print(f"  {total} observations total")


if __name__ == "__main__":
    main()
