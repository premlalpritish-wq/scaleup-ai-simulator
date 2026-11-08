"""Compare the workshop configuration at two feed rates.

A throwaway diagnostic, not a test: it answers one question -- does the
workshop's own configuration actually react to a feed-rate change, and by how
much? The acceptance harness needs to know which input it can use to prove the
scene re-executes and the result moves.

    python composition/tools/workshop_feed_probe.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "composition"))

from composition.runner import run_graph  # noqa: E402

INSTANCE = "workshop_culture"

LITERALS = {
    "initial_biomass_concentration": ("mass_concentration", 0.05, "g/L", "assumed"),
    "initial_complex_substrate_concentration": ("mass_concentration", 25.0, "g/L", "derived"),
    "initial_dissolved_oxygen": ("dimensionless", 100.0, "%", "assumed"),
    "initial_glycerol_concentration": ("mass_concentration", 2.76, "g/L", "reported"),
    "initial_culture_volume": ("volume", 0.1, "L", "reported"),
    "feed_glycerol_concentration": ("mass_concentration", 175.0, "g/L", "reported"),
    "feed_complex_substrate_concentration": ("mass_concentration", 245.0, "g/L", "reported"),
    "feed_flow_rate": ("volume_flow", 0.72, "mL/h", "reported"),
    "feed_start_time": ("time", 6.0, "h", "reported"),
}


def document(overrides: dict[str, float]) -> dict:
    literals = {}
    for port, (quantity, value, unit, provenance) in LITERALS.items():
        literals[f"{INSTANCE}/{port}"] = {
            "state": "number", "quantity": quantity,
            "value": overrides.get(port, value), "unit": unit,
            "provenance": provenance, "source_ref": "x", "method": "m", "reason": "r",
        }
    return {
        "contract_version": "0.1.0",
        "graph_id": "workshop-probe",
        "title": "t", "description": "d", "source_ref": "s", "notes": "n",
        "instances": [{
            "instance_id": INSTANCE, "model_id": "ganjave", "model_version": "0.1.0",
            "label": "l", "role": "r", "position": {"x": 240.0, "y": 160.0},
            "parameters": {"simulation": {
                "mode": "fed_batch", "duration_h": 24.0,
                "output_times_h": [0.0, 6.0, 12.0, 18.0, 24.0, 24.0],
                "solver": {"rtol": 1e-06, "atol": 1e-09, "h_max": 0.01},
            }},
        }],
        "connections": [], "literal_inputs": literals, "defaults": {},
    }


def sample(payload: dict) -> dict:
    out = {}
    for output in payload["results"][0]["outputs"]:
        extra = output["value"]["extra"]
        if "trajectory" not in extra:
            continue
        times = np.asarray(extra["trajectory"]["time_axis"]["values"], dtype=float)
        values = np.asarray(extra["trajectory"]["values"], dtype=float)
        out[output["ref"]["port_id"]] = (times, values)
    return out


def at(series: dict, port: str, t: float) -> float:
    times, values = series[port]
    return float(np.interp(t, times, values))


def main() -> int:
    for label, overrides in [
        ("baseline", {}),
        ("feed 1.50 mL/h", {"feed_flow_rate": 1.50}),
        ("feed 0.30 mL/h", {"feed_flow_rate": 0.30}),
        ("S2_0 5 g/L", {"initial_complex_substrate_concentration": 5.0}),
    ]:
        payload, code = run_graph(
            copy.deepcopy(document(overrides)), base=ROOT)
        if code != 0:
            print("%-18s exit %d" % (label, code))
            continue
        series = sample(payload)
        print("%-18s biomass@12h=%7.4f  @20h=%8.4f  @24h=%8.4f  "
              "glycerol@24h=%7.4f  DO@24h=%7.3f" % (
                  label,
                  at(series, "biomass_concentration", 12.0),
                  at(series, "biomass_concentration", 20.0),
                  at(series, "biomass_concentration", 24.0),
                  at(series, "glycerol_concentration", 24.0),
                  at(series, "dissolved_oxygen", 24.0)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
