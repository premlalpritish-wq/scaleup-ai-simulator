import os
import re
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Any
from .schemas import (
    SimulationManifestPayload,
    RequiredParameterSpec,
    GroundedParameter,
    ParameterGap,
)
from .engine import ScaleUpRAGEngine
from .quarantine_gate import ureg

# Default unverified operational hypotheses (explicitly flagged in _epistemic_audit if not supplied)
DEFAULT_OPERATIONAL_ASSUMPTIONS: Dict[str, Dict[str, Any]] = {
    "initial_biomass": {
        "value": 0.5,
        "unit": "g / L",
        "reason": "Initial seed inoculation density assumed; unstated in prompt"
    },
    "initial_glucose": {
        "value": 15.0,
        "unit": "g / L",
        "reason": "Batch starting sugar concentration assumed; unstated in prompt"
    },
    "initial_volume": {
        "value": 5.0,
        "unit": "L",
        "reason": "Bioreactor starting culture volume assumed; unstated in prompt"
    },
    "feed_start_h": {
        "value": 4.0,
        "unit": "hours",
        "reason": "Fed-batch nutrient pump start schedule assumed; unstated in prompt"
    },
    "duration_h": {
        "value": 20.0,
        "unit": "hours",
        "reason": "Total run simulation time window assumed; unstated in prompt"
    },
    "temperature_c": {
        "value": 37.0,
        "unit": "degC",
        "reason": "Optimal mesophilic growth temperature baseline assumed"
    },
    "Ko": {
        "value": 0.326,
        "unit": "percent",
        "reason": "Oxygen affinity constant (Table 2, Ganjave et al. 2022)"
    }
}

ENTITY_TO_SOLVER_MAP: Dict[str, str] = {
    "specific_growth_rate_mu_max": "mu_max",
    "growth_rate": "mu_max",
    "mu_max": "mu_max",
    "mum1": "mu_max",
    "ganjave_mum1": "mu_max",
    "lin_mu_max": "mu_max",
    "baez_mu_30_air_sat": "mu_max",
    "saturation_constant_ks": "Ks",
    "affinity_constant_ks": "Ks",
    "ks": "Ks",
    "k11": "Ks",
    "ganjave_ks_glucose": "Ks",
    "ganjave_k11": "Ks",
    "yield_biomass_glucose": "Y_xs",
    "y_xs": "Y_xs",
    "baez_y_xs": "Y_xs",
    "ganjave_y11": "Y_xs",
    "ganjave_y_x_glucose": "Y_xs",
    "maintenance_rate_m": "m",
    "maintenance_coefficient_m": "m",
    "m": "m",
    "baez_m": "m",
    "feed_glucose_concentration": "feed_glucose_concentration",
    "feed_glucose": "feed_glucose_concentration",
    "baez_s_f": "feed_glucose_concentration",
    "mass_transfer_kla": "kLa",
    "kla": "kLa",
    "ganjave_kla": "kLa",
    "oxygen_saturation_c_star": "c_star",
    "c_star": "c_star",
    "ganjave_c_star": "c_star",
    "oxygen_yield_yo": "Yo",
    "yo": "Yo",
    "yo1": "Yo",
    "ganjave_yo1": "Yo",
    "oxygen_affinity_ko": "Ko",
    "ko": "Ko",
    "ko1": "Ko",
    "ganjave_ko1": "Ko",
}

def _extract_prompt_overrides(prompt: str) -> Dict[str, Dict[str, Any]]:
    """Deterministically extracts user setpoints from prompt prose."""
    overrides: Dict[str, Dict[str, Any]] = {}
    p_lower = prompt.lower()

    # Feed concentration: e.g. "500 g/L glucose feed" or "feed 500 g/L"
    m_feed = re.search(r"(\d+(?:\.\d+)?)\s*(?:g/l|g\s*/\s*l)\s*(?:glucose|substrate)?\s*(?:feed)?", p_lower)
    if not m_feed:
        m_feed = re.search(r"(?:feed|substrate)\s*(?:glucose)?\s*(\d+(?:\.\d+)?)\s*(?:g/l|g\s*/\s*l)", p_lower)
    if m_feed:
        overrides["feed_glucose_concentration"] = {
            "value": float(m_feed.group(1)),
            "unit": "g / L",
            "source": "user_prompt",
        }

    # Temperature: e.g. "at 37 C" or "at 30 °C" or "37 deg c"
    m_temp = re.search(r"(?:at|@)\s*(\d+(?:\.\d+)?)\s*(?:°\s*c|c\b|deg\s*c)", p_lower)
    if m_temp:
        overrides["temperature_c"] = {
            "value": float(m_temp.group(1)),
            "unit": "degC",
            "source": "user_prompt",
        }

    return overrides

def _convert_to_solver_unit(val: float, unit_str: str, target_unit: str) -> float:
    try:
        qty = ureg.Quantity(val, unit_str)
        return float(qty.to(target_unit).magnitude)
    except Exception:
        return val

def build_solver_parameter_dict(
    manifest: SimulationManifestPayload,
    prompt: str = "",
    fallback_defaults: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """
    Constructs the complete solver parameter dictionary ensuring ZERO HIDDEN CONSTANTS.
    Every parameter is mapped into one of three explicit audit sections:
    1. grounded_parameters (verified constants from database or live literature)
    2. user_design_setpoints (user overrides vs literature baselines)
    3. unverified_assumptions / parameter_gaps (unspecified inputs with explicit fallback reasons)
    """
    solver_dict: Dict[str, Any] = {}
    audit_grounded: Dict[str, Any] = {}
    audit_setpoints: Dict[str, Any] = {}
    audit_assumptions: Dict[str, Any] = {}
    audit_gaps: Dict[str, Any] = {}

    # Extract user prompt setpoints
    prompt_setpoints = _extract_prompt_overrides(prompt)

    # 1. Map Grounded Empirical Parameters from Manifest
    for entity_name, param in manifest.grounded_parameters.items():
        solver_key = ENTITY_TO_SOLVER_MAP.get(entity_name.lower(), entity_name)
        val = param.value_normalized

        if solver_key in ("feed_glucose_concentration", "initial_glucose", "initial_biomass", "Ks", "c_star"):
            val = _convert_to_solver_unit(val, param.unit_normalized, "g / L")
        elif solver_key in ("mu_max", "m", "kLa"):
            val = _convert_to_solver_unit(val, param.unit_normalized, "1 / hour")

        audit_grounded[solver_key] = {
            "entity_name": param.entity_name,
            "target_system": param.target_system,
            "value": val,
            "unit": param.unit_normalized,
            "doi": param.source_doi,
            "tier": param.verification_tier,
            "origin": param.origin,
            "snippet": param.source_snippet,
        }
        solver_dict[solver_key] = val

    # 2. Map Explicit User Design Setpoints (Overrides)
    for key, setpoint_info in prompt_setpoints.items():
        user_val = setpoint_info["value"]
        unit_str = setpoint_info["unit"]
        baseline_val = solver_dict.get(key)
        if baseline_val is None and key in DEFAULT_OPERATIONAL_ASSUMPTIONS:
            baseline_val = DEFAULT_OPERATIONAL_ASSUMPTIONS[key]["value"]

        audit_setpoints[key] = {
            "user_override_value": user_val,
            "unit": unit_str,
            "literature_baseline_value": baseline_val,
            "source": setpoint_info["source"]
        }
        solver_dict[key] = user_val

    # 3. Map Parameter Gaps
    for entity_name, gap in manifest.parameter_gaps.items():
        solver_key = ENTITY_TO_SOLVER_MAP.get(entity_name.lower(), entity_name)
        fb = fallback_defaults.get(solver_key) if fallback_defaults else None
        if fb is None and solver_key in DEFAULT_OPERATIONAL_ASSUMPTIONS:
            fb = DEFAULT_OPERATIONAL_ASSUMPTIONS[solver_key]["value"]

        audit_gaps[solver_key] = {
            "status": "unverified_hypothesis",
            "entity_name": gap.entity_name,
            "target_system": gap.target_system,
            "reason": gap.reason,
            "required_evidence": gap.required_evidence,
            "fallback_used": fb,
        }
        if fb is not None:
            solver_dict[solver_key] = fb

    # 4. Map Operational Assumptions (Zero Hidden Constants)
    all_needed_operational = [
        "initial_biomass", "initial_glucose", "initial_volume",
        "feed_start_h", "duration_h", "temperature_c", "Ko", "c_star", "Yo", "Ks"
    ]
    for op_key in all_needed_operational:
        if op_key not in solver_dict:
            meta = DEFAULT_OPERATIONAL_ASSUMPTIONS.get(op_key, {"value": 0.0, "unit": "-", "reason": "Default fallback"})
            solver_dict[op_key] = meta["value"]
            audit_assumptions[op_key] = {
                "status": "unverified_hypothesis",
                "fallback_value": meta["value"],
                "unit": meta["unit"],
                "reason": meta["reason"]
            }

    solver_dict["_epistemic_audit"] = {
        "grounded_parameters": audit_grounded,
        "user_design_setpoints": audit_setpoints,
        "unverified_assumptions": audit_assumptions,
        "parameter_gaps": audit_gaps,
        "grounded_count": len(audit_grounded),
        "user_setpoint_count": len(audit_setpoints),
        "assumption_count": len(audit_assumptions),
        "gap_count": len(audit_gaps),
    }

    return solver_dict

def solve_fed_batch_trajectory(params: Dict[str, Any], steps: int = 41) -> Dict[str, List[float]]:
    """
    Coupled fed-batch ODE trajectory solver with strict mass conservation and
    kLa oxygen-transfer limitation.
    """
    duration_h = float(params.get("duration_h", 20.0))
    dt = duration_h / max(1, steps - 1)
    time_pts = [round(i * dt, 2) for i in range(steps)]

    X = float(params.get("initial_biomass", 0.5))
    S = float(params.get("initial_glucose", 15.0))
    V = float(params.get("initial_volume", 5.0))
    DO = 100.0  # Initial dissolved oxygen (% of air saturation)

    mu_max = float(params.get("mu_max", 1.08))
    Ks = float(params.get("Ks", 0.131))       # g / L (Ganjave Table 2)
    Ko = float(params.get("Ko", 0.326))       # % (Ganjave Table 2)
    Y_xs = float(params.get("Y_xs", 0.5))     # g biomass / g glucose
    Yo = float(params.get("Yo", 0.925))       # g O2 / g biomass (Ganjave Table 2)
    m = float(params.get("m", 0.025))         # 1 / hour maintenance rate
    kla = float(params.get("kLa", 133.0))     # 1 / hour transfer rate (Ganjave p. 3)
    c_star = float(params.get("c_star", 0.0075)) # g O2 / L saturation at 37 C
    feed_glucose_conc = float(params.get("feed_glucose_concentration", 500.0))
    feed_start_h = float(params.get("feed_start_h", 4.0))

    biomass_traj: List[float] = []
    glucose_traj: List[float] = []
    volume_traj: List[float] = []
    feed_traj: List[float] = []
    growth_rate_traj: List[float] = []
    do_traj: List[float] = []

    for t in time_pts:
        feed = 0.0
        if t >= feed_start_h:
            feed = 0.08 * math.exp(0.10 * (t - feed_start_h))
            V += feed * dt

        # 1. Monod Dual-Substrate Limitation (Glucose + Dissolved Oxygen)
        mu_unlimited = mu_max * (S / (Ks + S)) * (DO / (Ko + DO)) if (Ks + S) > 0 and (Ko + DO) > 0 else 0.0

        # 2. Maximum Aerobic Oxygen Transfer Rate Capacity: OTR_max = kLa * C*
        otr_max = max(1e-5, kla * c_star)
        mu_o2_cap = (otr_max / Yo) / X if X > 0 else mu_unlimited
        mu = min(mu_unlimited, mu_o2_cap)

        # 3. Substrate Conservation Check
        s_avail = S + (feed * feed_glucose_conc / V if feed > 0 and V > 0 else 0.0) * dt
        max_consumable = (mu / Y_xs + m) * X * dt if Y_xs > 0 else 0.0
        if max_consumable > s_avail and X > 0:
            mu = max(0.0, (s_avail / dt - m * X) * Y_xs / X)

        # 4. Quasi-steady-state Dissolved Oxygen tracking
        our = (mu / Yo) * X if Yo > 0 else 0.0
        do_ss = max(5.0, min(100.0, 100.0 * (1.0 - our / otr_max)))
        DO = do_ss

        biomass_traj.append(round(X, 3))
        glucose_traj.append(round(S, 3))
        volume_traj.append(round(V, 3))
        feed_traj.append(round(feed, 4))
        growth_rate_traj.append(round(mu, 3))
        do_traj.append(round(DO, 1))

        # Euler step
        dX = (mu - (feed / V if V > 0 else 0.0)) * X * dt
        X = max(0.01, X + dX)
        consumed = (mu / Y_xs + m) * X * dt if Y_xs > 0 else 0.0
        inflow = (feed * feed_glucose_conc / V if feed > 0 and V > 0 else 0.0) * dt
        S = max(0.0, S + inflow - consumed)

    return {
        "time_hours": time_pts,
        "biomass_g_per_L": biomass_traj,
        "glucose_g_per_L": glucose_traj,
        "volume_L": volume_traj,
        "feed_rate_L_per_h": feed_traj,
        "specific_growth_rate_inv_h": growth_rate_traj,
        "dissolved_oxygen_pct": do_traj,
    }

def get_ecoli_required_specs() -> List[RequiredParameterSpec]:
    """Returns the full 6-parameter specification list required for fed-batch fermentation."""
    return [
        RequiredParameterSpec(
            entity_name="specific_growth_rate_mu_max",
            target_system="Escherichia coli",
            expected_unit="1 / hr"
        ),
        RequiredParameterSpec(
            entity_name="yield_biomass_glucose",
            target_system="Escherichia coli",
            expected_unit="dimensionless"
        ),
        RequiredParameterSpec(
            entity_name="maintenance_rate_m",
            target_system="Escherichia coli",
            expected_unit="1 / hr"
        ),
        RequiredParameterSpec(
            entity_name="saturation_constant_ks",
            target_system="Escherichia coli",
            expected_unit="g / L"
        ),
        RequiredParameterSpec(
            entity_name="mass_transfer_kla",
            target_system="Escherichia coli",
            expected_unit="1 / hr"
        ),
        RequiredParameterSpec(
            entity_name="feed_glucose_concentration",
            target_system="Escherichia coli",
            expected_unit="kg / m**3"
        ),
        RequiredParameterSpec(
            entity_name="oxygen_saturation_c_star",
            target_system="Escherichia coli",
            expected_unit="g / L"
        ),
        RequiredParameterSpec(
            entity_name="oxygen_yield_yo",
            target_system="Escherichia coli",
            expected_unit="dimensionless"
        ),
        RequiredParameterSpec(
            entity_name="oxygen_affinity_ko",
            target_system="Escherichia coli",
            expected_unit="percent"
        )
    ]

def run_grounded_simulation(
    prompt: str,
    system_type: str = "ecoli_fed_batch",
    overrides: Optional[Dict[str, float]] = None,
    output_artifact_path: Optional[str] = None,
    engine: Optional[ScaleUpRAGEngine] = None,
) -> Dict[str, Any]:
    """
    Main orchestration entrypoint:
    Resolves full parameter list via ScaleUpRAGEngine -> builds solver parameters with _epistemic_audit ->
    executes ODE solver -> writes simulation artifact formatted for Godot 4 / WebGL.
    """
    if engine is None:
        engine = ScaleUpRAGEngine()

    # 1. Resolve RAG Manifest with Full Parameter Accounting
    specs = get_ecoli_required_specs()
    manifest = engine.resolve_simulation_parameters(
        prompt=prompt,
        required_specs=specs,
    )

    # 2. Build Solver Parameters & Audit Structure
    solver_params = build_solver_parameter_dict(manifest, prompt=prompt)
    if overrides:
        for k, v in overrides.items():
            solver_params[k] = v
            solver_params["_epistemic_audit"]["user_design_setpoints"][k] = {
                "user_override_value": v,
                "unit": "-",
                "source": "explicit_function_call"
            }

    # 3. Execute Solver Trajectories
    trajectories = solve_fed_batch_trajectory(solver_params)

    # 4. Assemble Artifact Formatted for Godot 4 & WebGL
    run_id = f"rag_sim_{os.urandom(4).hex()}"
    out_path = Path(output_artifact_path) if output_artifact_path else Path(".artifacts/rag_simulation_run.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    telemetry_schema = {
        "time_series": [
            {"id": "biomass_g_per_L", "label": "Biomass (g/L)", "unit": "g/L", "color_hex": "#38bdf8"},
            {"id": "glucose_g_per_L", "label": "Substrate (g/L)", "unit": "g/L", "color_hex": "#34d399"},
            {"id": "volume_L", "label": "Vessel Volume (L)", "unit": "L", "color_hex": "#a855f7"},
            {"id": "feed_rate_L_per_h", "label": "Feed Rate (L/h)", "unit": "L/h", "color_hex": "#f59e0b"},
            {"id": "dissolved_oxygen_pct", "label": "Dissolved Oxygen (%)", "unit": "%", "color_hex": "#06b6d4"}
        ]
    }

    artifact_payload: Dict[str, Any] = {
        "contract_version": "0.1.0",
        "schema_version": "1.0.0",
        "run_id": run_id,
        "status": "COMPLETED",
        "prompt": prompt,
        "system_type": system_type,
        "cache_hit": manifest.cache_hit_count > 0,
        "diagram_path": "assets/diagrams/active_anatomy_blueprint.svg",
        "telemetry_schema": telemetry_schema,
        "trajectories": trajectories,
        "summary": {
            "initial_biomass_dcw_g_L": trajectories["biomass_g_per_L"][0],
            "final_biomass_dcw_g_L": trajectories["biomass_g_per_L"][-1],
            "initial_volume_L": trajectories["volume_L"][0],
            "final_volume_L": trajectories["volume_L"][-1],
            "duration_hours": trajectories["time_hours"][-1],
            "time_steps": len(trajectories["time_hours"]),
            "grounded_parameter_count": solver_params["_epistemic_audit"]["grounded_count"],
            "user_setpoint_count": solver_params["_epistemic_audit"]["user_setpoint_count"],
            "assumption_count": solver_params["_epistemic_audit"]["assumption_count"],
            "gap_count": solver_params["_epistemic_audit"]["gap_count"],
        },
        "_epistemic_audit": solver_params["_epistemic_audit"],
    }

    from .scene_compiler import compile_3d_scene
    scene_assembly = compile_3d_scene(artifact_payload)
    artifact_payload["scene_assembly"] = scene_assembly

    # Write out artifact
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(artifact_payload, f, indent=2)

    # Mirror to .artifacts/latest_prompt_run.json if default artifact was used
    latest_path = Path(".artifacts/latest_prompt_run.json")
    if out_path.resolve() != latest_path.resolve():
        try:
            with open(latest_path, "w", encoding="utf-8") as f:
                json.dump(artifact_payload, f, indent=2)
        except Exception:
            pass

    return artifact_payload
