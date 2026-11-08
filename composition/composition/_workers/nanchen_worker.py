"""Subprocess worker for Nanchen et al. (2006) chemostat fluxes."""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Mapping

MODEL_ID = "nanchen2006.chemostat_fluxes"
MODEL_VERSION = "0.1.0"


def _model_root() -> Path:
    return Path(__file__).resolve().parents[2] / "Models" / "nanchen"


def _import_nanchen(model_root: str | None = None):
    root = Path(model_root) if model_root else _model_root()
    sys.path.insert(0, str(root.resolve()))
    from nanchen2006 import manifest, model, source  # noqa: PLC0415
    return manifest, model, source


def handle_manifest(model_root: str | None, request: Mapping[str, Any]) -> dict[str, Any]:
    manifest_mod, _model, _src = _import_nanchen(model_root)
    m = manifest_mod.build_manifest()
    ports = [
        {"port_id": "specific_growth_rate", "direction": "input", "quantity": "specific_rate", "unit": "1/h"},
        {"port_id": "biomass_yield", "direction": "input", "quantity": "mass_ratio", "unit": "g/g"},
        {"port_id": "glucose_consumption_rate", "direction": "output", "quantity": "specific_rate", "unit": "mmol/(g h)"},
        {"port_id": "maintenance_rate", "direction": "output", "quantity": "specific_rate", "unit": "mmol/(g h)"},
    ]
    return {
        "ok": True,
        "manifest": {
            "model_id": MODEL_ID,
            "model_version": MODEL_VERSION,
            "ports": ports,
            "disclaimer": m.get("disclaimer", ""),
            "scope": m.get("scope", ""),
        },
    }


def handle_run(model_root: str | None, request: Mapping[str, Any]) -> dict[str, Any]:
    _manifest, model_mod, _src = _import_nanchen(model_root)
    raw_inputs = request.get("inputs", {})
    mu = float(raw_inputs.get("specific_growth_rate", {}).get("value", 0.2))

    # Pirt equation: qglc = mu / Yglc_max + mglc
    # Yglc_max = 76 gdw/mol, mglc = 0.37 mmol/(gdw h)
    q_glc = (mu / 76.0) * 1000.0 + 0.37

    outputs = [
        {"port_id": "glucose_consumption_rate", "value": round(q_glc, 4), "unit": "mmol/(g h)", "quantity": "specific_rate"},
        {"port_id": "maintenance_rate", "value": 0.37, "unit": "mmol/(g h)", "quantity": "specific_rate"},
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
