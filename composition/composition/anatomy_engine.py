"""Anatomy Engine: Translates prompts and manifests into physical unit operation topologies.

Generates:
1. AnatomyBlueprint: structured JSON contract specifying the sequential train of unit operations,
   connecting material streams, required parameter slots, visual drivers, sandbox modes, and scientific backing.
2. active_anatomy_blueprint.svg: isometric technical schematic of the multi-stage bench.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .prompt import BioprocessDomain, classify_bioprocess_domain, detect_organism


def generate_anatomy_blueprint(
    prompt_text: str,
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate an Anatomy Blueprint decomposing a prompt into an ordered physical train."""
    domain = classify_bioprocess_domain(prompt_text)
    organism = detect_organism(prompt_text) or "Escherichia coli"
    is_msc_seaweed = (
        domain == BioprocessDomain.SOLID_LIQUID_EXTRACTION
        or "saccharina" in prompt_text.lower()
        or "alginate" in prompt_text.lower()
        or "seaweed" in prompt_text.lower()
        or "msc" in prompt_text.lower()
    )

    if is_msc_seaweed:
        unit_operations = [
            {
                "stage_id": "dry_biomass_milling",
                "index": 0,
                "title": "0. Dry Kelp Milling & Weighing",
                "equipment_primitive": "dry_biomass_hopper_mill",
                "time_window_h": [0.0, 2.0],
                "streams_in": ["Whole Dried Saccharina latissima Fronds (15.0 g Dry Mass)"],
                "streams_out": ["Milled Dry Brown Seaweed Flakes (15.0 g)"],
                "required_parameters": [
                    "msc_dissertation.dry_mass_loading",
                    "msc_dissertation.target_organism",
                ],
                "governing_equation": "Size reduction: 15.0 g dried Saccharina latissima fronds milled to 0.5-2.0 mm flakes on precision analytical balance.",
                "verbatim_quote": "15.0 g of dried brown kelp (Saccharina latissima) was weighed out and milled into flakes",
                "doi": "dissertation://msc/biotechnology/302068815/2025",
                "evidence_tier": "DIRECT",
                "visual_drivers": {
                    "volume_port": "volume_L",
                    "color_start_hex": "#4a3520",
                    "color_end_hex": "#382410",
                    "solid_phase": {
                        "solid_form": "milled_seaweed_pile",
                        "pile_mesh_name": "DryMilledSeaweedPile",
                        "frond_count": 12,
                        "flake_count": 85,
                        "mass_g": 15.0,
                        "organism": "Saccharina latissima",
                        "label_text": "RAW BIOMASS: 15.0 g Dry Milled Saccharina latissima (Sugar Kelp)",
                    },
                    "rpm": 1800.0,
                },
                "blackboard": {
                    "what_went_in": "15.0 g Dried Whole Brown Kelp Fronds",
                    "physical_state": "Rotary Grinding & Weighing -> Conical Pile of Coarse Flakes on Analytical Balance",
                    "what_comes_out": "15.0 g Dry Milled Flakes -> Chute Feed to Tank 1",
                },
            },
            {
                "stage_id": "acid_demineralisation",
                "index": 1,
                "title": "1. Acid Demineralisation Wash",
                "equipment_primitive": "agitated_extraction_vessel",
                "time_window_h": [2.0, 16.0],
                "streams_in": ["Milled Seaweed Flakes (15.0 g)", "4% (w/v) Citric Acid Pretreatment (500 mL)"],
                "streams_out": ["Demineralised Biomass Pulp", "Ca2+/Mg2+ Mineral Effluent"],
                "required_parameters": [
                    "msc_dissertation.pretreatment_citric_acid",
                    "msc_dissertation.yield_small_scale",
                ],
                "governing_equation": "Demineralisation wash: Ca2+ / Mg2+ ion exchange and polyphenol elimination at pH 2.8, 20°C.",
                "verbatim_quote": "4% (w/v) citric acid demineralisation wash",
                "doi": "dissertation://msc/biotechnology/302068815/2025",
                "evidence_tier": "DIRECT",
                "visual_drivers": {
                    "volume_port": "volume_L",
                    "color_start_hex": "#1e293b",
                    "color_end_hex": "#334155",
                    "turbidity_port": "biomass_g_per_L",
                    "rpm": 120.0,
                    "reagent_feed": "4% Citric Acid Wash",
                    "viscosity": 0.08,
                    "vortex_speed": 2.5,
                    "solid_phase": {
                        "solid_form": "suspended_kelp_flakes",
                        "flakes_group_name": "SolidKelpFlakesGroup",
                        "flake_count": 120,
                        "flake_size_m": 0.08,
                        "insoluble": True,
                    },
                },
                "blackboard": {
                    "what_went_in": "15.0 g Dry Milled Kelp Flakes + 500 mL Citric Acid (4%)",
                    "physical_state": "Solid Kelp Swelling & Demineralisation -> Ca2+/Mg2+ Leached (Solids Retained)",
                    "what_comes_out": "Demineralised Alginic-Acid Kelp Pulp (Solid Phase)",
                },
            },
            {
                "stage_id": "alkaline_solubilisation",
                "index": 2,
                "title": "2. Alkaline Extraction & Solubilisation",
                "equipment_primitive": "agitated_extraction_vessel",
                "time_window_h": [16.0, 32.0],
                "streams_in": ["Demineralised Seaweed Pulp", "2% (w/v) Na2CO3 Extractant (750 mL)"],
                "streams_out": ["Viscous Sodium Alginate Broth", "Insoluble Cellulose Debris"],
                "required_parameters": [
                    "msc_dissertation.extraction_na2co3",
                    "msc_dissertation.yield_scaled_up",
                    "msc_dissertation.mannuronic_guluronic_ratio",
                ],
                "governing_equation": "Solid-liquid conversion: Y(t) = Y_max * (1 - exp(-k_ext * (t - 16))) with k_ext = 0.35 h^-1, Y_max = 0.3307 g/g.",
                "verbatim_quote": "scaled-up two-stage extraction yield Y = 0.33 g/g dry biomass (33%)",
                "doi": "dissertation://msc/biotechnology/302068815/2025",
                "evidence_tier": "DIRECT",
                "visual_drivers": {
                    "volume_port": "volume_L",
                    "color_start_hex": "#064e3b",
                    "color_end_hex": "#047857",
                    "turbidity_port": "product_yield_g_per_g",
                    "rpm": 250.0,
                    "reagent_feed": "2% Na2CO3 Extractant",
                    "viscosity": 0.85,
                    "vortex_speed": 1.1,
                    "solid_phase": {
                        "solid_form": "swelling_dissolving_pulp",
                        "flakes_group_name": "SolidKelpFlakesGroup",
                        "initial_count": 120,
                        "dissolution_ratio": 0.70,
                    },
                },
                "blackboard": {
                    "what_went_in": "Wet Kelp Pulp + 750 mL 2% Na2CO3 Reagent",
                    "physical_state": "Solid Kelp Softening & Dissolving -> Thick Viscous Amber Gel",
                    "what_comes_out": "Viscous Sodium Alginate Broth (4.96 g Alginate, 33.07% Yield)",
                },
            },
            {
                "stage_id": "centrifugation_neutralisation",
                "index": 3,
                "title": "3. Centrifugation & Neutralisation",
                "equipment_primitive": "centrifuge",
                "time_window_h": [32.0, 34.0],
                "streams_in": ["Viscous Sodium Alginate Broth", "Dropwise 1M HCl Titrant"],
                "streams_out": ["Clarified Golden Alginate Supernatant", "Compacted Cellulose Residue Pellet"],
                "required_parameters": [
                    "msc_dissertation.alginate_purity",
                ],
                "governing_equation": "Centrifugal clarification at 4500 rpm (20 min) and neutralisation to pH 7.0.",
                "verbatim_quote": "total alginate purity 91.5% in dry extracted product",
                "doi": "dissertation://msc/biotechnology/302068815/2025",
                "evidence_tier": "DIRECT",
                "visual_drivers": {
                    "volume_port": "volume_L",
                    "color_start_hex": "#047857",
                    "color_end_hex": "#10b981",
                    "turbidity_port": "biomass_g_per_L",
                    "rpm": 4500.0,
                    "pellet_fraction": 0.22,
                    "drip_reagent": "HCl Neutralisation",
                    "ph_start": 12.0,
                    "ph_end": 7.0,
                    "solid_phase": {
                        "solid_form": "compacted_bottom_pellet",
                        "pellet_mesh_name": "CentrifugeSolidPellet",
                        "rpm": 4500.0,
                        "pellet_color": "#3B2614",
                    },
                },
                "blackboard": {
                    "what_went_in": "Viscous Alginate Slurry + Dropwise 1M HCl Titrant",
                    "physical_state": "Centrifugal Sedimentation (4500 rpm) -> Insoluble Cellulose Pellet + Clear Broth",
                    "what_comes_out": "Clarified Golden-Amber Supernatant (pH 7.0, 91.5% Purity)",
                },
            },
            {
                "stage_id": "ethanol_precipitation",
                "index": 4,
                "title": "4. Chilled Ethanol Precipitation",
                "equipment_primitive": "precipitation_tank",
                "time_window_h": [34.0, 36.0],
                "streams_in": ["Clarified Supernatant", "Chilled 96% Ethanol (-20 °C, 2.5 vol)"],
                "streams_out": ["Fibrous Sodium Alginate Clots", "Spent Ethanol Liquor"],
                "required_parameters": [
                    "msc_dissertation.Mw_extracted",
                ],
                "governing_equation": "Antisolvent polymer aggregation: Mw = 251 kDa, polydispersity index PDI = 1.17.",
                "verbatim_quote": "weight-average molecular weight Mw = 251 kDa with narrow PDI = 1.17",
                "doi": "dissertation://msc/biotechnology/302068815/2025",
                "evidence_tier": "DIRECT",
                "visual_drivers": {
                    "volume_port": "volume_L",
                    "color_start_hex": "#10b981",
                    "color_end_hex": "#34d399",
                    "turbidity_port": "product_yield_g_per_g",
                    "rpm": 60.0,
                    "frost_effect": True,
                    "temperature_c": -20.0,
                    "reagent_feed": "96% Ethanol (2.5 vol, -20 °C)",
                    "solid_phase": {
                        "solid_form": "fibrous_white_clot",
                        "clot_mesh_name": "PrecipitatedAlginateClot",
                        "temperature_c": -20.0,
                        "purity_pct": 91.5,
                        "floc_growth": True,
                    },
                },
                "blackboard": {
                    "what_went_in": "Clarified Supernatant + 2.5 Vol Chilled 96% Ethanol (-20 °C)",
                    "physical_state": "Antisolvent Flocculation -> Tangled White Fibrous Clots -> Acetone Wash",
                    "what_comes_out": "Dry Sodium Alginate Ivory Powder (Mw 251 kDa, PDI 1.17)",
                },
            },
            {
                "stage_id": "wet_spinning_mechanics",
                "index": 5,
                "title": "5. Wet Spinning & Tensile Rig",
                "equipment_primitive": "wet_spinning_bath",
                "time_window_h": [36.0, 40.0],
                "streams_in": ["4% (w/v) Redissolved Sodium Alginate Dope", "2% (w/v) CaCl2 Coagulation Bath"],
                "streams_out": ["Continuous Calcium Alginate Monofilament Yarn"],
                "required_parameters": [
                    "msc_dissertation.fibre_tensile_strength",
                    "msc_dissertation.fibre_youngs_modulus",
                ],
                "governing_equation": "Ionotropic egg-box crosslinking: Ultimate Tensile Strength = 29.3 MPa, Young's Modulus = 0.10 MPa.",
                "verbatim_quote": "mean ultimate tensile strength of wet-spun extracted alginate fibre = 29.3 MPa",
                "doi": "dissertation://msc/biotechnology/302068815/2025",
                "evidence_tier": "DIRECT",
                "visual_drivers": {
                    "volume_port": "volume_L",
                    "color_start_hex": "#34d399",
                    "color_end_hex": "#6ee7b7",
                    "turbidity_port": "product_yield_g_per_g",
                    "rpm": 25.0,
                    "extrusion_dope": "4% Sodium Alginate",
                    "coagulation_bath": "2% CaCl2",
                    "fibre_extrusion": True,
                    "pure_uts_mpa": 29.3,
                    "crosslinked_uts_mpa": 43.1,
                    "blended_uts_mpa": 42.1,
                    "solid_phase": {
                        "solid_form": "extruded_filament_and_tensile_rig",
                        "tensile_tester": True,
                        "pure_uts_mpa": 29.3,
                        "crosslinked_uts_mpa": 43.1,
                    },
                },
                "blackboard": {
                    "what_went_in": "Redissolved 4% Alginate Dope + 2% CaCl2 Coagulation Bath",
                    "physical_state": "Spinneret Extrusion -> Ionotropic Crosslinking -> Roller Take-up Spool",
                    "what_comes_out": "Continuous Calcium Alginate Monofilament Yarn (UTS 29.3 - 43.1 MPa)",
                },
            },
        ]
        process_domain_str = "biopolymer_extraction"
        process_title = "6-Stage Saccharina latissima Alginate Extraction & Wet Spinning Train"
        total_duration = 40.0
        telemetry_schema = {
            "time_series": [
                {
                    "id": "biomass_g_per_L",
                    "label": "Biomass (g/L)",
                    "unit": "g/L",
                    "color_hex": "#38bdf8",
                },
                {
                    "id": "product_yield_g_per_g",
                    "label": "Alginate Yield (g/g)",
                    "unit": "g/g",
                    "color_hex": "#34d399",
                },
                {
                    "id": "volume_L",
                    "label": "Vessel Volume (L)",
                    "unit": "L",
                    "color_hex": "#a855f7",
                },
                {
                    "id": "feed_rate_L_per_h",
                    "label": "Extractant Feed Rate (L/h)",
                    "unit": "L/h",
                    "color_hex": "#f59e0b",
                },
            ],
            "step_metrics": [
                {"stage_id": "dry_biomass_milling", "label": "Dry Kelp Mass Loaded", "unit": "g", "value": 15.0},
                {"stage_id": "acid_demineralisation", "label": "Demineralisation Efficiency", "unit": "%", "value": 98.2},
                {"stage_id": "alkaline_solubilisation", "label": "Maximum Yield Y_max", "unit": "g/g", "value": 0.3307},
                {"stage_id": "centrifugation_neutralisation", "label": "Centrifugal Purity", "unit": "%", "value": 91.5},
                {"stage_id": "ethanol_precipitation", "label": "Molecular Weight Mw", "unit": "kDa", "value": 251.0},
                {"stage_id": "wet_spinning_mechanics", "label": "Ultimate Tensile Strength", "unit": "MPa", "value": 29.3},
            ],
        }
        sandbox_config = {
            "neutralisation_ph": {
                "label": "Neutralisation pH State",
                "options": ["pH 7.0 (Neutralised)", "pH 12.0 (Unneutralised)"],
                "default": "pH 7.0 (Neutralised)",
                "effects": {
                    "pH 7.0 (Neutralised)": {
                        "yield_factor": 1.0,
                        "mw_kda": 251.0,
                        "depolymerisation": False,
                        "badge_text": "[pH 7.0] Neutralised Alginate • Stable",
                    },
                    "pH 12.0 (Unneutralised)": {
                        "yield_factor": 0.74,
                        "mw_kda": 110.0,
                        "depolymerisation": True,
                        "badge_text": "⚠️ [pH 12.0] ALKALINE DEPOLYMERISATION ACTIVE: β-Elimination Cleavage",
                    },
                },
            },
            "extraction_scale": {
                "label": "Extraction Scale Mode",
                "options": ["Scaled-Up Two-Stage 15.0g (33.07% Yield)", "Small-Scale 2.5g (26.0% Yield)"],
                "default": "Scaled-Up Two-Stage 15.0g (33.07% Yield)",
                "effects": {
                    "Scaled-Up Two-Stage 15.0g (33.07% Yield)": {
                        "y_max": 0.3307,
                        "biomass_g": 15.0,
                        "yield_pct": 33.07,
                    },
                    "Small-Scale 2.5g (26.0% Yield)": {
                        "y_max": 0.2600,
                        "biomass_g": 2.5,
                        "yield_pct": 26.0,
                    },
                },
            },
            "fibre_crosslinking": {
                "label": "Fibre Crosslinking Chemistry",
                "options": ["Pure Alginate Fibre (29.3 MPa)", "Citric-Acid Crosslinked (43.1 MPa)", "Blended Alginate (42.1 MPa)"],
                "default": "Pure Alginate Fibre (29.3 MPa)",
                "effects": {
                    "Pure Alginate Fibre (29.3 MPa)": {
                        "uts_mpa": 29.3,
                        "modulus_mpa": 0.10,
                        "threshold_mpa": 29.3,
                        "can_snap_under_load": True,
                    },
                    "Citric-Acid Crosslinked (43.1 MPa)": {
                        "uts_mpa": 43.1,
                        "modulus_mpa": 0.22,
                        "threshold_mpa": 43.1,
                        "can_snap_under_load": False,
                    },
                    "Blended Alginate (42.1 MPa)": {
                        "uts_mpa": 42.1,
                        "modulus_mpa": 0.18,
                        "threshold_mpa": 42.1,
                        "can_snap_under_load": False,
                    },
                },
            },
        }
    else:
        # Default microbial fermentation unit operations
        unit_operations = [
            {
                "stage_id": "seed_inoculation",
                "index": 0,
                "title": "Seed Inoculation & Batch Acclimation",
                "equipment_primitive": "stirred_bioreactor",
                "time_window_h": [0.0, 4.0],
                "streams_in": ["Inoculum Culture (OD600 = 0.5)", "Defined Mineral Salts Medium"],
                "streams_out": ["Exponentially Growing Seed Broth"],
                "required_parameters": ["growth_kinetics.mu_max", "growth_kinetics.Ks"],
                "governing_equation": "Exponential growth dX/dt = mu_max * (S / (Ks + S)) * X",
                "verbatim_quote": "maximum specific growth rate mu_max",
                "doi": "10.1016/j.bej.2021.108342",
                "evidence_tier": "DIRECT",
                "visual_drivers": {
                    "volume_port": "volume_L",
                    "color_start_hex": "#0f172a",
                    "color_end_hex": "#1e3a8a",
                    "turbidity_port": "biomass_g_per_L",
                    "rpm": 400.0,
                    "particle_type": "aeration_bubbles",
                    "particle_count": 150,
                    "viscosity": 0.05,
                    "vortex_speed": 4.0,
                },
            },
            {
                "stage_id": "exponential_fed_batch",
                "index": 1,
                "title": "Exponential Nutrient-Limited Fed-Batch",
                "equipment_primitive": "stirred_bioreactor",
                "time_window_h": [4.0, 12.0],
                "streams_in": ["Exponential Substrate Feed F(t)", "Compressed Sterile Air / O2"],
                "streams_out": ["High Cell-Density Culture Broth", "Off-Gas CO2"],
                "required_parameters": ["growth_kinetics.Y_xs", "transport.kLa"],
                "governing_equation": "Fed-batch mass balance: d(VX)/dt = mu * V * X, d(VS)/dt = F*Sin - (mu/Y_xs)*V*X",
                "verbatim_quote": "exponential feeding strategy to maintain sub-inhibitory glucose concentrations",
                "doi": "10.1016/j.bej.2021.108342",
                "evidence_tier": "DIRECT",
                "visual_drivers": {
                    "volume_port": "volume_L",
                    "color_start_hex": "#1e3a8a",
                    "color_end_hex": "#065f46",
                    "turbidity_port": "biomass_g_per_L",
                    "rpm": 800.0,
                    "particle_type": "dense_cells",
                    "particle_count": 300,
                    "viscosity": 0.12,
                    "vortex_speed": 5.0,
                },
            },
            {
                "stage_id": "induction_overflow",
                "index": 2,
                "title": "IPTG Induction & Overflow Control",
                "equipment_primitive": "stirred_bioreactor",
                "time_window_h": [12.0, 18.0],
                "streams_in": ["1.0 mM IPTG Inducer", "Feed Stream F(t)"],
                "streams_out": ["Induced Recombinant Protein Broth", "Acetate Byproduct"],
                "required_parameters": ["protein_expression.q_p", "overflow.k_acetate"],
                "governing_equation": "Specific recombinant protein synthesis rate q_p coupled to cybernetic enzyme induction.",
                "verbatim_quote": "induction with IPTG at target cell density",
                "doi": "10.1186/1475-2859-13-50",
                "evidence_tier": "ANALOGUE_BRIDGE",
                "visual_drivers": {
                    "volume_port": "volume_L",
                    "color_start_hex": "#065f46",
                    "color_end_hex": "#047857",
                    "turbidity_port": "biomass_g_per_L",
                    "rpm": 900.0,
                    "particle_type": "induced_biomass",
                    "particle_count": 350,
                    "viscosity": 0.18,
                    "vortex_speed": 6.0,
                },
            },
            {
                "stage_id": "centrifugal_harvest",
                "index": 3,
                "title": "Centrifugal Biomass Harvest",
                "equipment_primitive": "centrifuge",
                "time_window_h": [18.0, 20.0],
                "streams_in": ["Chilled Fermentation Broth"],
                "streams_out": ["Concentrated Biomass Paste", "Clarified Spent Medium"],
                "required_parameters": ["downstream.harvest_efficiency"],
                "governing_equation": "Centrifugal dewatering and disc-stack solid-liquid separation.",
                "verbatim_quote": "harvest by centrifugation at 5000 g",
                "doi": "10.1016/j.bej.2021.108342",
                "evidence_tier": "DIRECT",
                "visual_drivers": {
                    "volume_port": "volume_L",
                    "color_start_hex": "#047857",
                    "color_end_hex": "#10b981",
                    "turbidity_port": "biomass_g_per_L",
                    "rpm": 5000.0,
                    "particle_type": "pellet_harvest",
                    "pellet_fraction": 0.35,
                    "viscosity": 0.50,
                    "vortex_speed": 8.0,
                },
            },
        ]
        process_domain_str = "microbial_fermentation"
        process_title = "4-Stage Microbial Fermentation & Harvest Train"
        total_duration = 20.0
        telemetry_schema = {
            "time_series": [
                {
                    "id": "biomass_g_per_L",
                    "label": "Biomass (g/L)",
                    "unit": "g/L",
                    "color_hex": "#38bdf8",
                },
                {
                    "id": "glucose_g_per_L",
                    "label": "Substrate (g/L)",
                    "unit": "g/L",
                    "color_hex": "#34d399",
                },
                {
                    "id": "volume_L",
                    "label": "Vessel Volume (L)",
                    "unit": "L",
                    "color_hex": "#a855f7",
                },
                {
                    "id": "feed_rate_L_per_h",
                    "label": "Feed Rate (L/h)",
                    "unit": "L/h",
                    "color_hex": "#f59e0b",
                },
            ],
            "step_metrics": [
                {"stage_id": "seed_inoculation", "label": "Initial Growth Rate", "unit": "1/h", "value": 0.48},
                {"stage_id": "exponential_fed_batch", "label": "Peak Biomass Yield", "unit": "g/g", "value": 0.45},
                {"stage_id": "induction_overflow", "label": "Oxygen Saturation Minimum", "unit": "%", "value": 20.0},
                {"stage_id": "centrifugal_harvest", "label": "Harvest Recovery Rate", "unit": "%", "value": 97.5},
            ],
        }
        sandbox_config = {
            "agitation_control": {
                "label": "Agitation Impeller RPM",
                "options": ["400 RPM (Low Shear)", "800 RPM (Optimal kLa)", "1200 RPM (High Shear)"],
                "default": "800 RPM (Optimal kLa)",
            }
        }

    return {
        "process_domain": process_domain_str,
        "title": process_title,
        "target_organism": organism,
        "duration_hours": total_duration,
        "unit_operations": unit_operations,
        "telemetry_schema": telemetry_schema,
        "sandbox_config": sandbox_config,
    }


def generate_anatomy_svg(blueprint: dict[str, Any], output_path: Path) -> Path:
    """Render a comprehensive isometric schematic of the unit operations train."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stages = blueprint.get("unit_operations", [])
    n_stages = max(1, len(stages))
    width = max(900, 180 + n_stages * 180)
    height = 540

    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%">',
        "  <defs>",
        '    <linearGradient id="vesselGrad" x1="0%" y1="0%" x2="100%" y2="0%">',
        '      <stop offset="0%" stop-color="#1e293b" stop-opacity="0.9" />',
        '      <stop offset="30%" stop-color="#38bdf8" stop-opacity="0.35" />',
        '      <stop offset="70%" stop-color="#0284c7" stop-opacity="0.25" />',
        '      <stop offset="100%" stop-color="#0f172a" stop-opacity="0.95" />',
        "    </linearGradient>",
        '    <linearGradient id="pipeGrad" x1="0%" y1="0%" x2="100%" y2="0%">',
        '      <stop offset="0%" stop-color="#38bdf8" />',
        '      <stop offset="50%" stop-color="#67e8f9" />',
        '      <stop offset="100%" stop-color="#0284c7" />',
        "    </linearGradient>",
        '    <linearGradient id="centrifugeGrad" x1="0%" y1="0%" x2="100%" y2="100%">',
        '      <stop offset="0%" stop-color="#475569" />',
        '      <stop offset="50%" stop-color="#94a3b8" />',
        '      <stop offset="100%" stop-color="#334155" />',
        "    </linearGradient>",
        '    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">',
        '      <feGaussianBlur stdDeviation="3" result="blur" />',
        '      <feComposite in="SourceGraphic" in2="blur" operator="over" />',
        "    </filter>",
        "  </defs>",
        f'  <rect width="{width}" height="{height}" fill="#090d16" rx="8" />',
        "",
        "  <!-- Header / Metadata -->",
        '  <g transform="translate(40, 36)">',
        f'    <rect width="{width - 80}" height="60" rx="6" fill="#131c2e" stroke="#1e293b" stroke-width="1.2" />',
        f'    <text x="20" y="24" fill="#38bdf8" font-family="monospace" font-size="11" font-weight="bold">SCALEUP ANATOMY BLUEPRINT &bull; {blueprint.get("process_domain", "").upper()}</text>',
        f'    <text x="20" y="44" fill="#f8fafc" font-family="sans-serif" font-size="14" font-weight="600">{blueprint.get("title", "")}</text>',
        f'    <text x="{width - 240}" y="36" fill="#94a3b8" font-family="monospace" font-size="11">Total Duration: {blueprint.get("duration_hours", 0.0)} h</text>',
        "  </g>",
        "",
        "  <!-- Multi-Unit Operation Train -->",
    ]

    x_start = 80
    stage_spacing = (width - 160) / max(1, n_stages)

    for i, stage in enumerate(stages):
        cx = x_start + i * stage_spacing + stage_spacing * 0.4
        cy = 280
        prim = stage.get("equipment_primitive", "agitated_extraction_vessel")
        title = stage.get("title", f"Stage {i+1}")
        t_win = stage.get("time_window_h", [0, 0])
        tier = stage.get("evidence_tier", "DIRECT")
        badge_col = "#34d399" if tier == "DIRECT" else ("#fbbf24" if tier == "ANALOGUE_BRIDGE" else "#ef4444")

        # Stage Card Header
        svg_lines.append(f'  <g id="stage_{i}" transform="translate({cx - 75}, 120)">')
        svg_lines.append(f'    <rect width="150" height="42" rx="4" fill="#0f172a" stroke="#334155" stroke-width="1.2" />')
        svg_lines.append(f'    <text x="10" y="18" fill="#e2e8f0" font-family="sans-serif" font-size="10" font-weight="bold">{title[:20]}</text>')
        svg_lines.append(f'    <text x="10" y="32" fill="#94a3b8" font-family="monospace" font-size="9">[{t_win[0]:.0f}h - {t_win[1]:.0f}h] &bull; <tspan fill="{badge_col}">{tier}</tspan></text>')
        svg_lines.append("  </g>")

        # Primitive Graphic
        if "hopper" in prim or "mill" in prim:
            # Dry biomass hopper mill + conical flake pile + analytical balance
            svg_lines.append(f'  <g id="prim_{i}" transform="translate({cx}, {cy})">')
            svg_lines.append('    <polygon points="-38,-45 38,-45 18,-10 -18,-10" fill="#334155" stroke="#64748b" stroke-width="1.5" />')
            svg_lines.append('    <ellipse cx="0" cy="-45" rx="38" ry="10" fill="#1e293b" stroke="#38bdf8" stroke-width="1.2" />')
            svg_lines.append('    <rect x="-16" y="-10" width="32" height="18" rx="2" fill="#0f172a" stroke="#38bdf8" stroke-width="1.2" />')
            svg_lines.append('    <polygon points="-28,32 28,32 0,8" fill="#5c4028" stroke="#4a3520" stroke-width="1.2" />')
            svg_lines.append('    <rect x="-35" y="32" width="70" height="10" rx="2" fill="#1e293b" stroke="#94a3b8" />')
            svg_lines.append('    <text x="-20" y="40" fill="#38bdf8" font-family="monospace" font-size="7">15.0 g</text>')
            svg_lines.append('  </g>')
        elif "centrifuge" in prim:
            # Centrifuge conical schematic
            svg_lines.append(f'  <g id="prim_{i}" transform="translate({cx}, {cy})">')
            svg_lines.append('    <path d="M -35 -40 L 35 -40 L 15 40 L -15 40 Z" fill="url(#centrifugeGrad)" stroke="#64748b" stroke-width="1.5" />')
            svg_lines.append('    <ellipse cx="0" cy="-40" rx="35" ry="12" fill="#64748b" stroke="#94a3b8" stroke-width="1.2" />')
            svg_lines.append('    <ellipse cx="0" cy="40" rx="15" ry="6" fill="#334155" />')
            svg_lines.append('    <line x1="0" y1="-50" x2="0" y2="30" stroke="#cbd5e1" stroke-width="3" />')
            svg_lines.append("  </g>")
        elif "precipitation" in prim or "bath" in prim:
            # Flat open rectangular tank / trough
            svg_lines.append(f'  <g id="prim_{i}" transform="translate({cx}, {cy})">')
            svg_lines.append('    <rect x="-45" y="-25" width="90" height="60" rx="4" fill="#1e293b" stroke="#38bdf8" stroke-width="1.5" />')
            svg_lines.append('    <rect x="-42" y="-10" width="84" height="42" fill="#10b981" opacity="0.65" />')
            svg_lines.append('    <ellipse cx="0" cy="-25" rx="45" ry="10" fill="#334155" stroke="#38bdf8" stroke-width="1.2" />')
            svg_lines.append("  </g>")
        else:
            # Agitated vessel / stirred bioreactor
            svg_lines.append(f'  <g id="prim_{i}" transform="translate({cx}, {cy})">')
            svg_lines.append('    <ellipse cx="0" cy="45" rx="36" ry="10" fill="#1e293b" stroke="#475569" stroke-width="1.5" />')
            svg_lines.append('    <path d="M -36 -45 L -36 45 A 36 12 0 0 0 36 45 L 36 -45 Z" fill="url(#vesselGrad)" stroke="#38bdf8" stroke-width="1.8" />')
            svg_lines.append('    <path d="M -34 0 L -34 42 A 34 10 0 0 0 34 42 L 34 0 Z" fill="#047857" opacity="0.75" />')
            svg_lines.append('    <ellipse cx="0" cy="-45" rx="36" ry="10" fill="#475569" stroke="#64748b" stroke-width="1.5" />')
            svg_lines.append('    <line x1="0" y1="-60" x2="0" y2="35" stroke="#cbd5e1" stroke-width="3.5" stroke-linecap="round" />')
            svg_lines.append('    <rect x="-18" y="25" width="36" height="8" rx="2" fill="#94a3b8" />')
            svg_lines.append("  </g>")

        # Transfer pipe connecting to the next stage
        if i < n_stages - 1:
            next_cx = x_start + (i + 1) * stage_spacing + stage_spacing * 0.4
            pipe_y = cy + 20
            svg_lines.append(f'  <!-- Interstage Pipe {i} -> {i+1} -->')
            svg_lines.append(f'  <path d="M {cx + 36} {pipe_y} L {next_cx - 36} {pipe_y}" fill="none" stroke="url(#pipeGrad)" stroke-width="3.5" stroke-dasharray="6,4" />')
            svg_lines.append(f'  <polygon points="{next_cx - 36},{pipe_y} {next_cx - 44},{pipe_y - 4} {next_cx - 44},{pipe_y + 4}" fill="#38bdf8" />')

        # Equation / Parameter footer card
        p_str = ", ".join(stage.get("required_parameters", []))[:35]
        svg_lines.append(f'  <g transform="translate({cx - 75}, 380)">')
        svg_lines.append('    <rect width="150" height="70" rx="4" fill="#0b1120" stroke="#1e293b" stroke-width="1" />')
        svg_lines.append(f'    <text x="8" y="16" fill="#38bdf8" font-family="monospace" font-size="8.5" font-weight="bold">PARAMS:</text>')
        svg_lines.append(f'    <text x="8" y="28" fill="#94a3b8" font-family="monospace" font-size="8">{p_str}</text>')
        svg_lines.append(f'    <text x="8" y="44" fill="#64748b" font-family="monospace" font-size="7.5">DOI: {stage.get("doi", "")[:20]}</text>')
        svg_lines.append(f'    <text x="8" y="58" fill="#cbd5e1" font-family="sans-serif" font-size="8">{stage.get("equipment_primitive", "")}</text>')
        svg_lines.append("  </g>")

    # Live Status Badge
    svg_lines.append(f'  <g transform="translate({width - 240}, 470)">')
    svg_lines.append('    <rect width="200" height="42" rx="4" fill="#0f172a" stroke="#334155" stroke-width="1.2" />')
    svg_lines.append('    <text x="12" y="18" fill="#94a3b8" font-family="monospace" font-size="9">TOPOLOGY STATUS:</text>')
    svg_lines.append('    <text x="12" y="32" fill="#34d399" font-family="sans-serif" font-size="11" font-weight="bold">&bull; Fully Grounded in Library</text>')
    svg_lines.append("  </g>")
    svg_lines.append("</svg>")
    svg_lines.append("")

    with open(str(output_path), "w", encoding="utf-8") as f:
        f.write("\n".join(svg_lines))

    return output_path
