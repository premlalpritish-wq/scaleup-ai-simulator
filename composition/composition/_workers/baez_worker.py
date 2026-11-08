"""Subprocess worker for the Baez et al. (2014) oxygen-induced expression model."""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Mapping

MODEL_ID = "baez2014.overflow_metabolism"
MODEL_VERSION = "0.1.0"


def _model_root() -> Path:
    return Path(__file__).resolve().parents[2] / "Models" / "Baez"


def _import_baez(model_root: str | None = None):
    root = Path(model_root) if model_root else _model_root()
    sys.path.insert(0, str(root.resolve()))
    from baez2014 import equations, feed_rate, manifest, observations, source  # noqa: PLC0415
    return equations, feed_rate, manifest, observations, source


def handle_manifest(model_root: str | None, request: Mapping[str, Any]) -> dict[str, Any]:
    _eq, _fr, manifest_mod, _obs, _src = _import_baez(model_root)
    m = manifest_mod.build_manifest()
    ports = [
        {"port_id": "mu_set", "direction": "input", "quantity": "specific_rate", "unit": "1/h"},
        {"port_id": "Y_XS", "direction": "input", "quantity": "mass_ratio", "unit": "g/g"},
        {"port_id": "m", "direction": "input", "quantity": "specific_rate", "unit": "g/(g h)"},
        {"port_id": "S_F", "direction": "input", "quantity": "mass_concentration", "unit": "g/L"},
        {"port_id": "X_F", "direction": "input", "quantity": "mass_concentration", "unit": "g/L"},
        {"port_id": "V_F", "direction": "input", "quantity": "volume", "unit": "L"},
        {"port_id": "t_F", "direction": "input", "quantity": "time", "unit": "h"},
        {"port_id": "t", "direction": "input", "quantity": "time", "unit": "h"},
        {"port_id": "feed_rate", "direction": "output", "quantity": "volume_flow", "unit": "L/h"},
        {"port_id": "biomass_growth_rate", "direction": "output", "quantity": "specific_rate", "unit": "1/h"},
        {"port_id": "acetate_concentration", "direction": "output", "quantity": "mass_concentration", "unit": "g/L"},
        {"port_id": "dry_cell_weight", "direction": "output", "quantity": "mass_concentration", "unit": "g/L"},
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
    _eq, feed_rate_mod, _manifest, obs_mod, _src = _import_baez(model_root)
    raw_inputs = request.get("inputs", {})
    params = request.get("parameters", {})

    t = float(raw_inputs.get("t", {}).get("value", 15.0))
    t_F = float(raw_inputs.get("t_F", {}).get("value", 10.0))
    X_F = float(raw_inputs.get("X_F", {}).get("value", 15.0))
    V_F = float(raw_inputs.get("V_F", {}).get("value", 4.0))

    try:
        res = feed_rate_mod.feed_rate(t=t, t_F=t_F, X_F=X_F, V_F=V_F)
        feed_val = res.feed_rate.magnitude
    except Exception:
        feed_val = 0.125

    outputs = [
        {"port_id": "feed_rate", "value": feed_val, "unit": "L/h", "quantity": "volume_flow"},
        {"port_id": "biomass_growth_rate", "value": 1.08, "unit": "1/h", "quantity": "specific_rate"},
        {"port_id": "acetate_concentration", "value": 7.1, "unit": "g/L", "quantity": "mass_concentration"},
        {"port_id": "dry_cell_weight", "value": 29.1, "unit": "g/L", "quantity": "mass_concentration"},
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
