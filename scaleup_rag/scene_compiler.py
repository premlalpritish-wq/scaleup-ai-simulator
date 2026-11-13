import json
from typing import Dict, Any, List

def compile_3d_scene(artifact: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transforms numerical solver trajectories and _epistemic_audit into an interactive
    3D Scene Assembly consumable by both Three.js/WebGL and Godot 4.
    """
    trajectories = artifact.get("trajectories", {})
    summary = artifact.get("summary", {})
    audit = artifact.get("_epistemic_audit", {})
    grounded = audit.get("grounded_parameters", {})
    setpoints = audit.get("user_design_setpoints", {})
    assumptions = audit.get("unverified_assumptions", {})
    gaps = audit.get("parameter_gaps", {})

    times = trajectories.get("time_hours", [0.0])
    biomass = trajectories.get("biomass_g_per_L", [0.5])
    glucose = trajectories.get("glucose_g_per_L", [15.0])
    volume = trajectories.get("volume_L", [5.0])
    feed_rate = trajectories.get("feed_rate_L_per_h", [0.0])
    growth_rate = trajectories.get("specific_growth_rate_inv_h", [0.0])
    do_pct = trajectories.get("dissolved_oxygen_pct", [100.0])

    components: Dict[str, Any] = {
        "bioreactor_vessel": {
            "id": "bioreactor_vessel",
            "name": "Bioreactor Vessel & Culture Broth",
            "category": "reaction_mass",
            "mesh_type": "cylinder_lathe",
            "dimensions": {"radius": 1.0, "height": 3.0, "base_y": -1.5},
            "dynamic_drivers": {
                "volume_port": "volume_L",
                "turbidity_port": "biomass_g_per_L",
                "min_liquid_y": -1.4,
                "max_liquid_y": 1.2,
                "color_start_hex": "#0e2a47",
                "color_end_hex": "#065f46",
                "initial_volume_L": volume[0],
                "final_volume_L": volume[-1],
                "initial_biomass_g_L": biomass[0],
                "final_biomass_g_L": biomass[-1],
            },
            "governing_equations": [
                "Biomass accumulation: dX/dt = (mu - F/V) * X",
                "Volume balance: dV/dt = F",
                "Monod dual kinetics: mu = mu_max * (S / (Ks + S)) * (DO / (Ko + DO))"
            ],
            "epistemic_payload": {
                "grounded_parameters": {
                    k: grounded[k] for k in ["mu_max", "Y_xs", "m", "Ks"] if k in grounded
                },
                "user_design_setpoints": {
                    k: setpoints[k] for k in ["temperature_c"] if k in setpoints
                },
                "unverified_assumptions": {
                    k: assumptions[k] for k in ["initial_biomass", "initial_volume", "initial_glucose"] if k in assumptions
                },
                "parameter_gaps": gaps,
                "active_telemetry_keys": ["biomass_g_per_L", "volume_L", "specific_growth_rate_inv_h"]
            }
        },

        "rushton_impeller_assembly": {
            "id": "rushton_impeller_assembly",
            "name": "Rushton Turbine Impeller & Drive Shaft",
            "category": "mechanical_agitation",
            "mesh_type": "turbine_shaft_disc",
            "dimensions": {"shaft_radius": 0.05, "shaft_height": 3.4, "blade_radius": 0.38, "blades": 6},
            "dynamic_drivers": {
                "rotation_axis": "Y",
                "base_rpm": 600.0,
                "max_rpm": 1200.0,
                "shear_intensity_port": "specific_growth_rate_inv_h"
            },
            "governing_equations": [
                "Gas-liquid mass transfer: OTR = kLa * (C* - DO)",
                "Impeller power dissipation: P/V = N_p * rho * N^3 * D^5 / V",
                "Transfer scaling: kLa ~ (P/V)^alpha * v_s^beta"
            ],
            "epistemic_payload": {
                "grounded_parameters": {
                    k: grounded[k] for k in ["kLa"] if k in grounded
                },
                "user_design_setpoints": {},
                "unverified_assumptions": {},
                "parameter_gaps": gaps,
                "active_telemetry_keys": ["specific_growth_rate_inv_h"]
            }
        },

        "ring_sparger_and_bubbles": {
            "id": "ring_sparger_and_bubbles",
            "name": "Micro-Porous Ring Sparger & Bubble Plume",
            "category": "gas_dispersion",
            "mesh_type": "torus_and_particles",
            "dimensions": {"ring_radius": 0.45, "tube_radius": 0.03, "elevation_y": -1.35},
            "dynamic_drivers": {
                "bubble_density_port": "dissolved_oxygen_pct",
                "bubble_color_gradient": ["#38bdf8", "#0284c7", "#0f172a"],
                "aeration_active": True,
                "particle_count": 220
            },
            "governing_equations": [
                "Dissolved oxygen balance: d(DO)/dt = kLa * (100 - DO) - (100 / C*) * OUR",
                "Oxygen uptake rate: OUR = (mu / Yo + m_O) * X",
                "Maximum transfer capacity: OTR_max = kLa * C*"
            ],
            "epistemic_payload": {
                "grounded_parameters": {
                    k: grounded[k] for k in ["c_star", "Yo", "Ko", "kLa"] if k in grounded
                },
                "user_design_setpoints": {},
                "unverified_assumptions": {
                    k: assumptions[k] for k in ["Ko"] if k in assumptions
                },
                "parameter_gaps": gaps,
                "active_telemetry_keys": ["dissolved_oxygen_pct"]
            }
        },

        "glucose_feed_pump_and_inlet": {
            "id": "glucose_feed_pump_and_inlet",
            "name": "Peristaltic Glucose Feed Pump & Dosing Line",
            "category": "substrate_dosing",
            "mesh_type": "pipe_nozzle_and_stream",
            "dimensions": {"nozzle_position": [0.45, 1.35, 0.0], "stream_length": 1.2},
            "dynamic_drivers": {
                "flow_port": "feed_rate_L_per_h",
                "feed_start_h": float(assumptions.get("feed_start_h", {}).get("fallback_value", 4.0)),
                "stream_active_when_positive": True
            },
            "governing_equations": [
                "Substrate mass balance: dS/dt = (S_feed - S) * (F/V) - (mu / Y_xs + m) * X",
                "Exponential feeding profile: F(t) = F_0 * exp(mu_set * (t - t_feed))"
            ],
            "epistemic_payload": {
                "grounded_parameters": {
                    k: grounded[k] for k in ["feed_glucose_concentration"] if k in grounded
                },
                "user_design_setpoints": {
                    k: setpoints[k] for k in ["feed_glucose_concentration"] if k in setpoints
                },
                "unverified_assumptions": {
                    k: assumptions[k] for k in ["feed_start_h"] if k in assumptions
                },
                "parameter_gaps": gaps,
                "active_telemetry_keys": ["feed_rate_L_per_h", "glucose_g_per_L"]
            }
        },

        "thermal_jacket_and_probes": {
            "id": "thermal_jacket_and_probes",
            "name": "Thermal Control Jacket & Sensor Probes",
            "category": "process_control",
            "mesh_type": "jacket_cylinder_and_sensors",
            "dimensions": {"jacket_radius": 1.08, "height": 2.2, "probe_y": -0.2},
            "dynamic_drivers": {
                "temperature_setpoint_c": float(setpoints.get("temperature_c", {}).get("user_override_value", 37.0)),
                "jacket_circulation_active": True
            },
            "governing_equations": [
                "Vessel heat balance: q_jacket = U * A * (T_broth - T_jacket)",
                "Optical DO sensor: V_sensor = S_probe * DO_pct",
                "pH glass electrode: E = E_0 - (2.303 * R * T / F) * pH"
            ],
            "epistemic_payload": {
                "grounded_parameters": {},
                "user_design_setpoints": {
                    k: setpoints[k] for k in ["temperature_c"] if k in setpoints
                },
                "unverified_assumptions": {
                    k: assumptions[k] for k in ["duration_h"] if k in assumptions
                },
                "parameter_gaps": gaps,
                "active_telemetry_keys": ["dissolved_oxygen_pct", "volume_L"]
            }
        }
    }

    scene_assembly = {
        "scene_id": f"scene_{artifact.get('run_id', 'latest')}",
        "process_title": "Interactive E. coli Fed-Batch Bioreactor Workbench",
        "timeline": {
            "times_h": times,
            "duration_h": times[-1] if times else 20.0,
            "step_count": len(times),
            "dt_h": round(times[1] - times[0], 4) if len(times) > 1 else 0.5
        },
        "viewpoints": {
            "isometric_overview": {"position": [4.5, 3.2, 5.5], "target": [0, 0.4, 0]},
            "vessel_cutaway": {"position": [0, 0.5, 3.8], "target": [0, 0.2, 0]},
            "impeller_close": {"position": [1.4, -0.6, 1.8], "target": [0, -0.8, 0]},
            "sparger_bottom": {"position": [1.2, -1.8, 1.6], "target": [0, -1.4, 0]}
        },
        "components": components,
        "kpis": {
            "initial_biomass_dcw_g_L": biomass[0],
            "final_biomass_dcw_g_L": biomass[-1],
            "initial_volume_L": volume[0],
            "final_volume_L": volume[-1],
            "feed_start_h": float(assumptions.get("feed_start_h", {}).get("fallback_value", 4.0)),
            "grounded_parameters_count": len(grounded),
            "user_setpoints_count": len(setpoints),
            "assumptions_count": len(assumptions),
            "gaps_count": len(gaps)
        }
    }

    return scene_assembly
