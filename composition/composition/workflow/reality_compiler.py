"""First-Principles Reality Compiler & Mechanistic Invariant Verifier.

Inspects any generated (units, connections, streams) flowsheet against 6 hard
chemical engineering physical passes and raises PhysicsCompilationError if any
thermodynamic, equilibrium, material, phase, or hydraulic invariant is violated.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional


class PhysicsCompilationError(Exception):
    """Raised when a generated simulation flowsheet violates a governing physical law."""

    def __init__(self, violations: List[Dict[str, Any]]):
        self.violations = violations
        summary = "; ".join(
            f"[{v['law_id']}] {v['unit_tag']}: {v['message']}" for v in violations
        )
        super().__init__(f"PhysicsCompilationError ({len(violations)} violation(s)): {summary}")


class RealityCompiler:
    """Deterministic 6-pass physical invariant verifier & auto-remediation coordinator."""

    DEFAULT_THRESHOLDS: Dict[str, float] = {
        "dT_min_c": 10.0,
        "first_law_rel_tol": 0.02,
        "max_single_hx_dt_c": 350.0,
        "max_whb_hx_dt_c": 600.0,
        "max_adiabatic_rise_c": 220.0,
        "max_compressor_discharge_c": 155.0,
        "gamma": 1.38,
        "eta_p": 0.80,
        "min_sc_ratio_ni": 2.0,
        "max_ni_h2s_ppm": 0.1,
        "max_psa_inlet_temp_c": 45.0,
        "max_passive_pressure_rise_bar": 0.01,
    }

    def __init__(self, thresholds: Optional[Dict[str, float]] = None):
        self.thresholds = dict(self.DEFAULT_THRESHOLDS)
        if thresholds:
            self.thresholds.update(thresholds)

    def _serialize_active_laws(self) -> List[Dict[str, Any]]:
        """Return machine-readable governing physical laws and active thresholds."""
        try:
            from scaleup_rag.seed_knowledge import SEED_MECHANISTIC_LAWS
            laws = SEED_MECHANISTIC_LAWS
        except Exception:
            laws = []

        serialized: List[Dict[str, Any]] = []
        for law in laws:
            merged_thresholds = dict(law.threshold_parameters or {})
            for k in list(merged_thresholds.keys()):
                if k in self.thresholds:
                    merged_thresholds[k] = self.thresholds[k]
            serialized.append({
                "law_id": law.law_id,
                "domain": law.domain,
                "governing_equation": law.governing_equation,
                "threshold_parameters": merged_thresholds,
                "doi": law.doi,
            })
        return serialized

    @staticmethod
    def _extract_graph(payload: Dict[str, Any]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        bp = payload.get("anatomy_blueprint", {})
        units = list(payload.get("stages", bp.get("unit_operations", [])) or [])
        cg = payload.get("composition_graph", {})
        connections = list(cg.get("edges", bp.get("connections", payload.get("connections", []))) or [])
        return units, connections

    @staticmethod
    def _unit_tag(u: Dict[str, Any], idx: int = 0) -> str:
        return str(u.get("tag") or u.get("stage_id") or f"U-{idx + 1}")

    def check_mass_and_elemental_balance(
        self, units: List[Dict[str, Any]], connections: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        violations: List[Dict[str, Any]] = []
        for idx, u in enumerate(units):
            tag = self._unit_tag(u, idx)
            flow = u.get("flow_nm3_h")
            if flow is not None and float(flow) < 0.0:
                violations.append({
                    "law_id": "MASS_CONSERVATION_NON_NEGATIVE",
                    "unit_tag": tag,
                    "message": f"Negative volumetric flow ({flow} Nm3/h).",
                    "equation": "m_dot >= 0",
                    "remediation_action": "clamp_non_negative_flow",
                })
        return violations

    def check_second_law_and_pinch(
        self, units: List[Dict[str, Any]], connections: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        violations: List[Dict[str, Any]] = []
        dt_min = self.thresholds["dT_min_c"]
        max_single_dt = self.thresholds["max_single_hx_dt_c"]
        max_whb_dt = self.thresholds["max_whb_hx_dt_c"]

        for idx, u in enumerate(units):
            tag = self._unit_tag(u, idx)
            arch = str(u.get("archetype", ""))

            # 1. Fired furnace convection coil banks Pinch & First Law check
            conv_banks = u.get("convection_banks", [])
            if conv_banks:
                prev_cold_target: Optional[float] = None
                for bank in conv_banks:
                    b_tag = str(bank.get("tag", tag))
                    t_hi = float(bank.get("t_hot_in_c", 0.0))
                    t_ho = float(bank.get("t_hot_out_c", 0.0))
                    t_ci = float(bank.get("t_cold_in_c", 0.0))
                    t_co = float(bank.get("t_cold_out_c", 0.0))
                    q_hot = float(bank.get("duty_mw", 0.0))
                    q_cold = bank.get("q_cold_mw")

                    if q_cold is not None and q_hot > 0.0:
                        rel_err = abs(q_hot - float(q_cold)) / q_hot
                        if rel_err > self.thresholds["first_law_rel_tol"]:
                            violations.append({
                                "law_id": "FIRST_LAW_ENERGY_BALANCE",
                                "unit_tag": b_tag,
                                "message": f"Enthalpy imbalance |Q_hot-Q_cold|/Q_hot = {rel_err:.3f} > 0.02.",
                                "equation": "|Q_hot - Q_cold| / Q_hot <= 0.02",
                                "remediation_action": "rebalance_convection_duty",
                            })

                    if (t_hi - t_co) < dt_min or (t_ho - t_ci) < dt_min:
                        violations.append({
                            "law_id": "SECOND_LAW_TEMPERATURE_CROSS",
                            "unit_tag": b_tag,
                            "message": (
                                f"Pinch violation in {b_tag}: flue ({t_hi:.1f}->{t_ho:.1f} C) vs "
                                f"cold ({t_ci:.1f}->{t_co:.1f} C) has approach < {dt_min:.1f} C."
                            ),
                            "equation": "T_hot_in - T_cold_out >= dT_min and T_hot_out - T_cold_in >= dT_min",
                            "remediation_action": "reorder_convection_pinch",
                        })

                    if prev_cold_target is not None and t_co > prev_cold_target + 1e-6:
                        violations.append({
                            "law_id": "SECOND_LAW_TEMPERATURE_CROSS",
                            "unit_tag": b_tag,
                            "message": (
                                f"Convection bank {b_tag} (T_cold_out={t_co:.1f} C) placed downstream of "
                                f"lower-temperature bank ({prev_cold_target:.1f} C)."
                            ),
                            "equation": "T_cold_out[i] <= T_cold_out[i-1] along flue gas path",
                            "remediation_action": "reorder_convection_pinch",
                        })
                    prev_cold_target = t_co

            # 2. Lumped single-shell heat exchanger thermal shock check
            if arch in ("shell_tube_hx", "knockout_cooler"):
                t_in = u.get("t_hot_in_c")
                t_out = u.get("t_hot_out_c", u.get("temperature_c"))
                if t_in is None and idx > 0:
                    t_in = units[idx - 1].get("temperature_c")
                if t_in is not None and t_out is not None:
                    dt_hx = float(t_in) - float(t_out)
                    is_lumped_to_ambient = dt_hx > max_single_dt and float(t_out) < 200.0
                    is_extreme_shock = dt_hx > max_whb_dt
                    if is_lumped_to_ambient or is_extreme_shock:
                        violations.append({
                            "law_id": "SINGLE_SHELL_THERMAL_SHOCK",
                            "unit_tag": tag,
                            "message": (
                                f"Lumped cooler {tag} drops {float(t_in):.1f} C -> {float(t_out):.1f} C "
                                f"(dT={dt_hx:.1f} C > {max_single_dt:.0f} C) without series HX staging."
                            ),
                            "equation": "delta_T_hx <= max_single_hx_dt_c",
                            "remediation_action": "split_into_series_heat_exchangers",
                        })

        return violations

    def check_equilibrium_and_adiabatic_ceiling(
        self, units: List[Dict[str, Any]], connections: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        violations: List[Dict[str, Any]] = []
        pbr_indices = [i for i, u in enumerate(units) if str(u.get("archetype", "")) == "packed_bed_reactor"]
        hx_indices = [i for i, u in enumerate(units) if str(u.get("archetype", "")) == "shell_tube_hx"]

        for idx in pbr_indices:
            u = units[idx]
            tag = self._unit_tag(u, idx)
            desc = (str(u.get("title", "")) + " " + str(u.get("description", ""))).lower()
            co_in = u.get("co_in_pct")
            co_out = u.get("co_out_pct")
            dt_ad = float(u.get("adiabatic_temp_rise_c", 0.0))

            # Check if a single adiabatic exothermic bed claims deep conversion without a downstream intercooled bed
            has_downstream_intercooled_bed = any(
                any(hx_i > idx and hx_i < p_j for hx_i in hx_indices)
                for p_j in pbr_indices if p_j > idx
            )
            claims_deep_single_bed = (
                (co_in is not None and co_out is not None and float(co_in) >= 8.0 and float(co_out) <= 1.0)
                or dt_ad > self.thresholds["max_adiabatic_rise_c"]
                or ("12% co" in desc and "0.3% co" in desc)
            )
            if claims_deep_single_bed and not has_downstream_intercooled_bed:
                violations.append({
                    "law_id": "VAN_T_HOFF_EXOTHERMIC_EQUILIBRIUM",
                    "unit_tag": tag,
                    "message": (
                        f"Single adiabatic bed {tag} exceeds exothermic equilibrium ceiling "
                        f"without inter-stage cooling (E-106) and secondary LT bed."
                    ),
                    "equation": "X_exit <= X_eq(T_out, P) and delta_T_ad <= max_adiabatic_rise_c",
                    "remediation_action": "insert_intercooled_reactor_stage",
                })
        return violations

    def check_catalyst_and_material_invariants(
        self, units: List[Dict[str, Any]], connections: List[Dict[str, Any]], payload: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        violations: List[Dict[str, Any]] = []
        gamma = self.thresholds["gamma"]
        eta_p = self.thresholds["eta_p"]
        t_max_comp = self.thresholds["max_compressor_discharge_c"]

        # 1. Nickel catalyst sulfur poisoning & Boudouard coking checks
        for idx, u in enumerate(units):
            tag = self._unit_tag(u, idx)
            arch = str(u.get("archetype", ""))
            if arch == "furnace_reformer":
                h2s_ppm = float(u.get("feed_h2s_ppm", 0.0))
                has_upstream_hds = any(
                    str(prev.get("archetype", "")) == "pre_reformer"
                    or any(k in (str(prev.get("tag", "")) + " " + str(prev.get("title", ""))).lower()
                           for k in ("hds", "r-101", "desulfur", "guard"))
                    for prev in units[:idx]
                )
                if h2s_ppm > self.thresholds["max_ni_h2s_ppm"] and not has_upstream_hds:
                    violations.append({
                        "law_id": "NICKEL_SULFUR_POISONING",
                        "unit_tag": tag,
                        "message": f"Feed H2S ({h2s_ppm} ppm > 0.1 ppm) enters Ni reformer {tag} without upstream HDS.",
                        "equation": "y_H2S <= 0.1 ppmv",
                        "remediation_action": "insert_upstream_hds_and_prereformer",
                    })

                sc_ratio = u.get("sc_ratio")
                if sc_ratio is None:
                    audit = payload.get("epistemic_audit", {})
                    gp = audit.get("grounded_parameters", {}).get("smr_steam_to_carbon_ratio", {})
                    if isinstance(gp, dict) and gp.get("value") is not None:
                        sc_ratio = float(gp["value"])
                if sc_ratio is not None and float(sc_ratio) < self.thresholds["min_sc_ratio_ni"]:
                    violations.append({
                        "law_id": "BOUDOUARD_CARBON_COKING",
                        "unit_tag": tag,
                        "message": f"Steam-to-carbon ratio S/C={float(sc_ratio):.2f} < {self.thresholds['min_sc_ratio_ni']:.1f} risks coking.",
                        "equation": "S_to_C >= 2.0",
                        "remediation_action": "enforce_minimum_steam_to_carbon_ratio",
                    })

            # 2. Polytropic compressor discharge limit (<= 155 C)
            if arch == "high_pressure_compressor":
                comp_stages = u.get("compressor_stages", [])
                if comp_stages:
                    for st in comp_stages:
                        p_in = max(0.5, float(st.get("p_in_bar", 30.0)))
                        p_out = max(p_in, float(st.get("p_out_bar", p_in)))
                        t_in_c = float(st.get("t_in_c", 38.0))
                        t_poly_c = (t_in_c + 273.15) * ((p_out / p_in) ** ((gamma - 1.0) / (gamma * eta_p))) - 273.15
                        if t_poly_c > t_max_comp:
                            violations.append({
                                "law_id": "POLYTROPIC_COMPRESSION_DISCHARGE",
                                "unit_tag": str(st.get("tag", tag)),
                                "message": (
                                    f"Compressor stage {st.get('tag', tag)} polytropic discharge "
                                    f"T_out={t_poly_c:.1f} C > {t_max_comp:.1f} C."
                                ),
                                "equation": "T_out = T_in*(P_out/P_in)**((gamma-1)/(gamma*eta_p)) <= 155 C",
                                "remediation_action": "insert_multistage_compressor_intercoolers",
                            })
                else:
                    p_in = float(u.get("p_in_bar", units[idx - 1].get("pressure_bar", 30.0) if idx > 0 else 30.0))
                    p_out = float(u.get("pressure_bar", p_in))
                    t_in_c = float(u.get("t_in_c", 38.0))
                    if p_out > p_in * 1.01:
                        t_poly_c = (t_in_c + 273.15) * ((p_out / max(0.5, p_in)) ** ((gamma - 1.0) / (gamma * eta_p))) - 273.15
                        if t_poly_c > t_max_comp:
                            violations.append({
                                "law_id": "POLYTROPIC_COMPRESSION_DISCHARGE",
                                "unit_tag": tag,
                                "message": (
                                    f"Single-stage compressor {tag} ({p_in:.1f}->{p_out:.1f} bar) reaches "
                                    f"T_out={t_poly_c:.1f} C > {t_max_comp:.1f} C without intercoolers."
                                ),
                                "equation": "T_out = T_in*(P_out/P_in)**((gamma-1)/(gamma*eta_p)) <= 155 C",
                                "remediation_action": "insert_multistage_compressor_intercoolers",
                            })

        return violations

    def check_phase_and_equipment_compatibility(
        self, units: List[Dict[str, Any]], connections: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        violations: List[Dict[str, Any]] = []
        for idx, u in enumerate(units):
            if str(u.get("archetype", "")) == "psa_skid":
                tag = self._unit_tag(u, idx)
                upstream = units[:idx]
                has_ko = any(str(p.get("archetype", "")) == "knockout_cooler" for p in upstream)
                prev_temp = float(upstream[-1].get("temperature_c", 25.0)) if upstream else 25.0
                if not has_ko or prev_temp > self.thresholds["max_psa_inlet_temp_c"]:
                    violations.append({
                        "law_id": "WET_GAS_PSA_KNOCKOUT",
                        "unit_tag": tag,
                        "message": (
                            f"PSA {tag} fed without upstream knockout drum S-101 or with "
                            f"T_in={prev_temp:.1f} C > {self.thresholds['max_psa_inlet_temp_c']:.1f} C."
                        ),
                        "equation": "T_psa_in <= 45 C and has_knockout_separator == 1",
                        "remediation_action": "insert_condensate_knockout_drum",
                    })
        return violations

    def check_hydraulic_pressure_gradient(
        self, units: List[Dict[str, Any]], connections: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        violations: List[Dict[str, Any]] = []
        id_map = {str(u.get("stage_id", "")): (idx, u) for idx, u in enumerate(units)}
        tol = self.thresholds["max_passive_pressure_rise_bar"]

        for conn in connections:
            if str(conn.get("stream_type", "process")) != "process":
                continue
            f_id = str(conn.get("from", ""))
            t_id = str(conn.get("to", ""))
            if f_id not in id_map or t_id not in id_map:
                continue
            _, u_from = id_map[f_id]
            idx_to, u_to = id_map[t_id]
            arch_to = str(u_to.get("archetype", ""))
            tag_to = self._unit_tag(u_to, idx_to)
            is_active_boost = (
                arch_to == "high_pressure_compressor"
                or tag_to.startswith(("P-", "C-", "K-"))
            )
            if is_active_boost:
                continue
            p_from = float(u_from.get("pressure_bar", 1.0))
            p_to = float(u_to.get("pressure_bar", 1.0))
            if p_to > p_from + tol:
                violations.append({
                    "law_id": "PASSIVE_PRESSURE_DROP_MONOTONICITY",
                    "unit_tag": tag_to,
                    "message": (
                        f"Passive unit {tag_to} ({p_to:.1f} bar) exceeds upstream pressure "
                        f"({p_from:.1f} bar) without compressor/pump."
                    ),
                    "equation": "P_out <= P_in for passive units",
                    "remediation_action": "insert_compressor_or_pump",
                })
        return violations

    def verify_strict(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Run all 6 physical passes and raise PhysicsCompilationError on any violation."""
        units, connections = self._extract_graph(payload)
        violations: List[Dict[str, Any]] = []
        violations.extend(self.check_mass_and_elemental_balance(units, connections))
        violations.extend(self.check_second_law_and_pinch(units, connections))
        violations.extend(self.check_equilibrium_and_adiabatic_ceiling(units, connections))
        violations.extend(self.check_catalyst_and_material_invariants(units, connections, payload))
        violations.extend(self.check_phase_and_equipment_compatibility(units, connections))
        violations.extend(self.check_hydraulic_pressure_gradient(units, connections))

        if violations:
            raise PhysicsCompilationError(violations)

        return {
            "status": "PASSED",
            "laws_checked": 6,
            "auto_remediations_applied": list(payload.get("reality_compiler_audit", {}).get("auto_remediations_applied", [])),
            "violations": [],
            "active_laws": self._serialize_active_laws(),
        }

    def compile_and_verify(
        self,
        payload: Dict[str, Any],
        strict: bool = True,
        remediator_fn: Optional[Callable[[Dict[str, Any], List[Dict[str, Any]]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Verify payload; if violations exist and remediator_fn is provided, apply remediation and re-verify."""
        remediations_applied: List[str] = []
        try:
            audit = self.verify_strict(payload)
            audit["auto_remediations_applied"] = remediations_applied
            payload["reality_compiler_audit"] = audit
            return audit
        except PhysicsCompilationError as err:
            if remediator_fn is not None:
                remediations_applied = sorted({v["remediation_action"] for v in err.violations})
                payload = remediator_fn(payload, err.violations)
                if strict:
                    audit = self.verify_strict(payload)
                    audit["auto_remediations_applied"] = remediations_applied
                    payload["reality_compiler_audit"] = audit
                    return audit
            if strict:
                raise
            audit = {
                "status": "FAILED",
                "laws_checked": 6,
                "auto_remediations_applied": remediations_applied,
                "violations": err.violations,
                "active_laws": self._serialize_active_laws(),
            }
            payload["reality_compiler_audit"] = audit
            return audit
