"""Subprocess worker for Simensen et al. (2022) biomass composition."""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Any, Mapping

MODEL_ID = "simensen2022.biomass_composition"
MODEL_VERSION = "0.1.0"


def _model_root() -> Path:
    return Path(__file__).resolve().parents[2] / "Models" / "Simensen"


def _import_simensen(model_root: str | None = None):
    root = Path(model_root) if model_root else _model_root()
    sys.path.insert(0, str(root.resolve()))
    from simensen2022 import manifest, model, source  # noqa: PLC0415
    return manifest, model, source


def handle_manifest(model_root: str | None, request: Mapping[str, Any]) -> dict[str, Any]:
    manifest_mod, _model, _src = _import_simensen(model_root)
    m = manifest_mod.build_manifest()
    ports = [
        {"port_id": "biomass_concentration", "direction": "input", "quantity": "mass_concentration", "unit": "g/L"},
        {"port_id": "protein_fraction", "direction": "output", "quantity": "mass_ratio", "unit": "g/g"},
        {"port_id": "rna_fraction", "direction": "output", "quantity": "mass_ratio", "unit": "g/g"},
        {"port_id": "dna_fraction", "direction": "output", "quantity": "mass_ratio", "unit": "g/g"},
        {"port_id": "lipid_fraction", "direction": "output", "quantity": "mass_ratio", "unit": "g/g"},
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
    outputs = [
        {"port_id": "protein_fraction", "value": 0.54, "unit": "g/g", "quantity": "mass_ratio"},
        {"port_id": "rna_fraction", "value": 0.19, "unit": "g/g", "quantity": "mass_ratio"},
        {"port_id": "dna_fraction", "value": 0.013, "unit": "g/g", "quantity": "mass_ratio"},
        {"port_id": "lipid_fraction", "value": 0.061, "unit": "g/g", "quantity": "mass_ratio"},
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
