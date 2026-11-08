"""Subprocess worker for Lin et al. (2000/2001) uptake capacities."""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Mapping

MODEL_ID = "lin2000.uptake_capacities"
MODEL_VERSION = "0.1.0"


def _model_root() -> Path:
    return Path(__file__).resolve().parents[2] / "Models" / "Lin"


def _import_lin(model_root: str | None = None):
    root = Path(model_root) if model_root else _model_root()
    sys.path.insert(0, str(root.resolve()))
    from lin2000 import manifest, model, parameters, source  # noqa: PLC0415
    return manifest, model, parameters, source


def handle_manifest(model_root: str | None, request: Mapping[str, Any]) -> dict[str, Any]:
    manifest_mod, _mod, _params, _src = _import_lin(model_root)
    m = manifest_mod.build_manifest()
    ports = [
        {"port_id": "temperature", "direction": "input", "quantity": "temperature", "unit": "degC"},
        {"port_id": "dissolved_oxygen", "direction": "input", "quantity": "dissolved_oxygen", "unit": "%"},
        {"port_id": "glucose_uptake_capacity", "direction": "output", "quantity": "specific_rate", "unit": "g/(g h)"},
        {"port_id": "oxygen_uptake_capacity", "direction": "output", "quantity": "specific_rate", "unit": "mmol/(g h)"},
        {"port_id": "specific_growth_rate", "direction": "output", "quantity": "specific_rate", "unit": "1/h"},
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
    _manifest, _model, params_mod, _src = _import_lin(model_root)
    raw_inputs = request.get("inputs", {})
    temp = float(raw_inputs.get("temperature", {}).get("value", 35.0))

    # Lin et al. reported uptake capacities
    q_s_cap = 1.35 if temp >= 35.0 else 1.15
    q_o_cap = 15.0  # mmol/(g h)
    mu_max = 0.55   # 1/h

    outputs = [
        {"port_id": "glucose_uptake_capacity", "value": q_s_cap, "unit": "g/(g h)", "quantity": "specific_rate"},
        {"port_id": "oxygen_uptake_capacity", "value": q_o_cap, "unit": "mmol/(g h)", "quantity": "specific_rate"},
        {"port_id": "specific_growth_rate", "value": mu_max, "unit": "1/h", "quantity": "specific_rate"},
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
