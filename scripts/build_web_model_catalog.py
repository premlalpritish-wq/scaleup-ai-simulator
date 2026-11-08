"""Generate the small public web catalogue from the composition registry."""
from __future__ import annotations

import json
import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "composition"))

from composition.registry.__main__ import report  # noqa: E402
from composition.cross_model import describe  # noqa: E402


def value(record: dict, key: str):
    item = record.get(key)
    return item.get("value") if isinstance(item, dict) else item


def build() -> dict:
    registry = report()
    models = []
    for model_id, record in registry["models"].items():
        ports = record.get("ports", {})
        models.append({
            "model_id": model_id,
            "model_version": record["model_version"],
            "title": value(record, "title"),
            "source_paper": value(record, "source_paper"),
            "capabilities": value(record, "capabilities"),
            "ports_dependence": ports.get("dependence", "unknown"),
            "port_counts": ports.get("counts", {}),
            "ports": ports.get("records", []),
            "unknown_fields": record.get("unknown_fields", []),
            "scientific_status": record.get("scientific_status", {}),
            "reference": record.get("reference"),
            "browser_mode": {
                "ganjave": "pyodide_live",
                "zielinski2019.rhi_process": "stored_evidence_replay",
                "morris2011.material_balance": "registered_no_fixed_port_surface",
            }.get(model_id, "not_available"),
        })
    baez = json.loads((ROOT / "Models/Baez/manifest.json").read_text(encoding="utf-8"))
    if baez.get("registration", {}).get("registered_in_composition_registry") is not False:
        raise ValueError("Baez manifest no longer explicitly confirms its absent composition registration")
    compatibility = describe()
    return {
        "catalogue_version": 1,
        "registry_version": registry.get("registry_version"),
        "registry_scientific_status": registry.get("scientific_status"),
        "registry_issues": registry.get("issues", []),
        "models": models,
        "inspection_only": [{
            "model_id": baez["artefact_id"],
            "title": baez["source"]["title"],
            "source_paper": baez["source"]["citation"],
            "registration": "not_registered_in_composition_registry",
            "browser_mode": "inspection_only",
            "reason": "No composition adapter is registered. The package documents one printed formula and explicitly excludes a growth/oxygen/GFP predictive model.",
            "disclaimer": baez["disclaimer"],
            "equations": [{"label": e["label"], "printed_expression": e["printed_expression"], "output_key": e["output_key"], "output_unit": e["output_unit"], "required_run_inputs": e["required_run_inputs"], "source_reference": e["source_reference"]} for e in baez["equations"]],
            "excluded_capabilities": baez["exclusions"],
        }],
        "compatibility": {
            "contract_version": compatibility["contract_version"],
            "claim_scope": compatibility["claim_scope"],
            "validation_status": compatibility["validation_status"],
            "boundaries": compatibility["boundaries"],
            "quantity_pairs_examined": compatibility["quantity_pairs_examined"],
        },
    }


def build_zielinski_replay() -> dict:
    recorded = json.loads((ROOT / "web/data/zielinski_replay_result.json").read_text(encoding="utf-8"))
    figure = json.loads((ROOT / "Models/Zielinski/models/data/fig3_growth_trajectory.json").read_text(encoding="utf-8"))
    outputs = recorded["results"][0]["outputs"]
    od = []
    rest = []
    for output in outputs:
        ref = output["ref"]["port_id"]
        val = output["value"]
        if ref.startswith("stream:S02_culture_broth#od600_h"):
            hour = int(ref.rsplit("h", 1)[1])
            od.append({"hour": hour, "value": val["value"], "unit": val["unit"], "provenance": val["provenance"], "source_ref": val["source_ref"], "method": val["method"], "chain": output.get("provenance_chain", [])})
        elif len(rest) < 16:
            rest.append({"label": ref, "display": val.get("display", val.get("reason", "unknown")), "provenance": val["provenance"], "source_ref": val["source_ref"], "is_resolved": val["is_resolved"]})
    od.sort(key=lambda item: item["hour"])
    if len(od) != len(figure["trajectory"]):
        raise ValueError(f"Expected {len(figure['trajectory'])} replay points in stored runner output; found {len(od)}")
    if [(p["hour"], p["value"]) for p in od] != [(int(p["hour"]), p["od600"]) for p in figure["trajectory"]]:
        raise ValueError("Stored composition-runner trajectory does not match the committed digitized figure evidence")
    diagnostics = [{"severity": d.get("severity"), "code": d.get("code"), "message": d.get("message")} for d in recorded.get("diagnostics", [])]
    return {
        "run_id": recorded["run_id"],
        "status": recorded["status"],
        "digest": recorded["reproducibility"].get("digest", "") if isinstance(recorded.get("reproducibility"), dict) else str(recorded.get("reproducibility", "")),
        "scientific_status": "not_yet_validated",
        "evidence_summary": {key: recorded["results"][0]["raw_summary"].get(key) for key in ("mode", "observed_reference_values", "digitized_values", "computed_values", "predicted_values", "unknown_values", "unresolved_targets", "validation_errors", "validation_warnings", "cross_check_errors", "graph_is_predictive")},
        "source": {
            "citation": "Zielinski et al. (2019), Protein Expression and Purification 157: 63–69, doi:10.1016/j.pep.2019.02.002",
            "doi_url": "https://doi.org/10.1016/j.pep.2019.02.002",
            "figure": figure["source"]["figure"], "pdf_page": figure["source"]["pdf_page"], "printed_page": figure["source"]["printed_page"],
            "uncertainty": figure["digitization_method"]["declared_uncertainty"],
            "method": figure["digitization_method"]["summary"],
        },
        "points": od,
        "summary": rest,
        "diagnostics": diagnostics,
        "limitations": figure["notes"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if checked-in JSON differs from current source metadata")
    args = parser.parse_args()
    target = ROOT / "web/data/model_catalog.json"
    replay_target = ROOT / "web/data/zielinski_replay_view.json"
    expected = {
        target: json.dumps(build(), indent=2, ensure_ascii=False) + "\n",
        replay_target: json.dumps(build_zielinski_replay(), indent=2, ensure_ascii=False) + "\n",
    }
    if args.check:
        stale = [path.relative_to(ROOT).as_posix() for path, text in expected.items() if not path.exists() or path.read_text(encoding="utf-8") != text]
        if stale:
            raise SystemExit("Generated web metadata is stale or missing: " + ", ".join(stale))
        print("PASS — catalogue matches composition registry and compatibility engine; replay matches runner result and digitized source trajectory")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        for path, text in expected.items():
            path.write_text(text, encoding="utf-8")
        print(f"Wrote {target.relative_to(ROOT)}")
        print(f"Wrote {replay_target.relative_to(ROOT)}")
