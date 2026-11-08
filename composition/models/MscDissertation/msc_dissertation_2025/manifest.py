"""Manifest builder for MSc Dissertation (2025)."""
from typing import Any

MODEL_ID = "msc_dissertation_2025.bioprocess_kinetics"
MODEL_VERSION = "0.1.0"

def build_manifest() -> dict[str, Any]:
    return {
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "ports": [
            {"port_id": "t", "direction": "input", "quantity": "time", "unit": "h", "label": "Elapsed extraction time"},
            {"port_id": "biomass", "direction": "input", "quantity": "mass", "unit": "g", "label": "Initial biomass dry mass"},
            {"port_id": "product_yield", "direction": "output", "quantity": "mass_ratio", "unit": "g/g", "label": "Extracted biopolymer product yield"},
            {"port_id": "feed_rate", "direction": "output", "quantity": "volume_flow", "unit": "L/h", "label": "Extractant effluent flow rate"},
            {"port_id": "biomass_concentration", "direction": "output", "quantity": "mass_concentration", "unit": "g/L", "label": "Residual biomass concentration"},
            {"port_id": "specific_growth_rate", "direction": "output", "quantity": "specific_rate", "unit": "1/h", "label": "Equivalent specific rate"},
        ],
        "disclaimer": "Empirically measured biopolymer extraction yields, HPAEC monomer composition, GPC molecular weight distribution, and tensile stress-strain properties under controlled neutralisation.",
        "scope": "Bioprocess extraction kinetics, purification, and mechanical properties of alginate from Saccharina latissima",
    }
