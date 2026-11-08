"""Reference conditions and reported results, kept apart from model output.

The paper's operating conditions, its feed experiments, and its reported
outcomes are loaded from ``data/reference_experiments.json``. Three kinds of
thing live there and they are deliberately not mixed:

* **measured outcomes** -- 20.7 g DCW/L in the abstract, the 19.9-21.5 g/L
  range across trials;
* **the authors' model predictions** -- 19.44 g DCW/L. This is a prediction,
  not a measurement, and it is stored as such so that a reproduction attempt
  can be compared against it without the simulator ever returning it;
* **optimisation decisions** -- 17.5 % w/v glycerol, 24.5 % w/v yeast
  extract, 0.72 mL/h.

Nothing here is a simulator output, and no test may pass by returning one of
these numbers from the model.

**What is missing is recorded as missing.** The time courses live in figures,
the optimisation constraints in a supplementary table, and the OD600-to-DCW
calibration nowhere; `unavailable_data()` lists each with the consequence it
has for validation.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from schemas.provenance import Observation, ParameterError, Provenance, SourceRef
from schemas.units import QuantityKind

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
EXPERIMENT_FILE = DATA_DIR / "reference_experiments.json"

DATASET_ID = "ganjave2022.reference_experiments"
DATASET_VERSION = "1.0.0"


def _source(payload: dict[str, Any]) -> SourceRef:
    return SourceRef(
        section=payload["section"],
        locator=payload["locator"],
        printed_page=payload.get("printed_page"),
        quote=payload.get("quote"),
    )


@lru_cache(maxsize=1)
def _document() -> dict[str, Any]:
    with EXPERIMENT_FILE.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def operating_conditions() -> tuple[dict[str, Any], ...]:
    """The paper's cultivation setup, as quoted text with its printed page."""
    return tuple(dict(item) for item in _document()["operating_conditions"])


@lru_cache(maxsize=1)
def feed_experiments() -> tuple[dict[str, Any], ...]:
    """Table 1: the fed-batch experiments used for fitting and validation.

    Rows 5 and 6 print no feed composition; they are kept with ``None`` rather
    than interpolated from their flow rates.
    """
    return tuple(dict(item) for item in _document()["feed_experiments"])


@lru_cache(maxsize=1)
def reported_observations() -> tuple[Observation, ...]:
    """Reported outcomes, predictions and decisions, each labelled."""
    out = []
    for payload in _document()["observations"]:
        out.append(
            Observation(
                observation_id=payload["observation_id"],
                label=payload["label"],
                kind=QuantityKind(payload["kind"]),
                unit=payload["unit"],
                provenance=Provenance(payload["provenance"]),
                value=payload.get("value"),
                value_range=(
                    tuple(payload["value_range"]) if payload.get("value_range") else None
                ),
                source=_source(payload["source"]),
                note=payload.get("note", ""),
            )
        )
    return tuple(out)


@lru_cache(maxsize=1)
def unavailable_data() -> tuple[dict[str, Any], ...]:
    """Data the paper does not supply, and what that costs."""
    return tuple(dict(item) for item in _document()["unavailable_data"])


def observation(observation_id: str) -> Observation:
    for item in reported_observations():
        if item.observation_id == observation_id:
            return item
    raise ParameterError(
        f"unknown reference observation {observation_id!r}; this package holds "
        f"{[o.observation_id for o in reported_observations()]}"
    )


def measured_outcomes() -> tuple[Observation, ...]:
    """Only the experimental results, excluding the authors' model prediction."""
    return tuple(
        o for o in reported_observations()
        if o.observation_id != "results.model_predicted_biomass"
    )


def model_prediction() -> Observation:
    """The authors' model-predicted biomass, 19.44 g/L.

    Named separately because it is easy to mistake for a target output and
    easier still to hard-code. It is a *reported prediction*, retained as a
    comparison point only.
    """
    return observation("results.model_predicted_biomass")


def selected_recipe() -> dict[str, Any]:
    """The feed recipe the paper selected from its Pareto front.

    Glycerol 17.5 % w/v = 175 g/L and yeast extract 24.5 % w/v = 245 g/L, fed
    at 0.72 mL/h = 7.2e-4 L/h. The conversions are applied here, explicitly;
    the selected optimum is reported data, and re-deriving it needs the
    optimisation of eq. (19)-(24), which is out of scope.
    """
    return {
        "glycerol_percent_wv": observation("optimisation.selected_recipe").value,
        "yeast_extract_percent_wv": observation(
            "optimisation.selected_recipe_yeast_extract"
        ).value,
        "flow_mL_per_h": observation("optimisation.selected_recipe_flow").value,
        "S10_g_per_L": 175.0,
        "S20_g_per_L": 245.0,
        "flow_L_per_h": 0.72e-3,
        "conversion_note": "1 % w/v = 10 g/L; 1 mL/h = 1e-3 L/h",
        "derived_by": (
            "multi-objective optimisation of eq. (19)-(24) against a Pareto "
            "front (Fig. 4), reported as the selected optimum (p. 7). The "
            "optimisation itself is NOT implemented here."
        ),
    }


def dataset_manifest() -> dict[str, Any]:
    return {
        "dataset_id": DATASET_ID,
        "version": DATASET_VERSION,
        "source": _document()["source"],
        "operating_conditions": len(operating_conditions()),
        "feed_experiments": len(feed_experiments()),
        "observations": len(reported_observations()),
        "unavailable_items": len(unavailable_data()),
        "paper_reproduction_status": "not achievable with the supplied data",
        "reproduction_note": (
            "The time courses are figures, not numerical data. Validation level "
            "3 (comparison against reported measurements) is therefore NOT met, "
            "and no trajectory here is claimed to reproduce the paper."
        ),
    }