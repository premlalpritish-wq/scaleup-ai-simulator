"""Subprocess worker for MSc Dissertation (2025) bioprocess extraction model."""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Mapping

MODEL_ID = "msc_dissertation_2025.bioprocess_kinetics"
MODEL_VERSION = "0.1.0"


def _model_root() -> Path:
    return Path(__file__).resolve().parents[3] / "composition" / "models" / "MscDissertation"


def _import_dissertation(model_root: str | None = None):
    root = Path(model_root) if model_root else _model_root()
    if str(root.resolve()) not in sys.path:
        sys.path.insert(0, str(root.resolve()))
    from msc_dissertation_2025 import manifest, model, parameters, source  # noqa: PLC0415
    return manifest, model, parameters, source


def handle_manifest(model_root: str | None, request: Mapping[str, Any]) -> dict[str, Any]:
    manifest_mod, _model, _params, _src = _import_dissertation(model_root)
    m = manifest_mod.build_manifest()
    return {
        "ok": True,
        "manifest": {
            "model_id": MODEL_ID,
            "model_version": MODEL_VERSION,
            "ports": m.get("ports", []),
            "disclaimer": m.get("disclaimer", ""),
            "scope": m.get("scope", ""),
        },
    }


def handle_run(model_root: str | None, request: Mapping[str, Any]) -> dict[str, Any]:
    _manifest_mod, model_mod, params_mod, _src = _import_dissertation(model_root)
    raw_inputs = request.get("inputs", {})
    t = float(raw_inputs.get("t", {}).get("value", 16.0))
    biomass = float(raw_inputs.get("biomass", {}).get("value", 15.0))
    feed_rate = float(raw_inputs.get("feed_rate", {}).get("value", 0.05))
    biomass_conc = float(raw_inputs.get("biomass_concentration", {}).get("value", 20.0))

    sim_res = model_mod.simulate_extraction(
        t=t,
        biomass=biomass,
        feed_rate=feed_rate,
        biomass_concentration=biomass_conc,
        params=params_mod.DEFAULT_PARAMETERS,
    )

    outputs = [
        {"port_id": "product_yield", "value": sim_res["product_yield"], "unit": "g/g", "quantity": "mass_ratio"},
        {"port_id": "feed_rate", "value": sim_res["feed_rate"], "unit": "L/h", "quantity": "volume_flow"},
        {"port_id": "biomass_concentration", "value": sim_res["biomass_concentration"], "unit": "g/L", "quantity": "mass_concentration"},
        {"port_id": "specific_growth_rate", "value": sim_res["specific_rate"], "unit": "1/h", "quantity": "specific_rate"},
    ]
    return {"ok": True, "outputs": outputs, "diagnostics": []}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-root", default=None)
    args = parser.parse_args()

    try:
        req = json.load(sys.stdin)
        op = req.get("op", "manifest")
        if op == "manifest":
            resp = handle_manifest(args.model_root, req)
        elif op == "run":
            resp = handle_run(args.model_root, req)
        else:
            resp = {"ok": False, "error": f"unknown op {op}"}
    except Exception as exc:
        resp = {"ok": False, "error": str(exc), "traceback": traceback.format_exc()}
    json.dump(resp, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
