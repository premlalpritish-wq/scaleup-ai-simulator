import math
from typing import Any, Dict, List, Optional


class LevenspielToolkit:
    """Executable thermochemical & reactor-design diagnostics for Octave Levenspiel."""

    @staticmethod
    def compute_adiabatic_equilibrium_trajectory(
        t_in_c: float,
        delta_h_rxn_kj_mol: float,
        cp_j_mol_k: float,
        k_eq_ref: float,
        t_ref_k: float,
        target_conversion: float = 0.90,
    ) -> Dict[str, Any]:
        """Compare adiabatic operating line X(T) against Van 't Hoff equilibrium X_eq(T)."""
        r_gas = 8.314
        t_in_k = max(200.0, t_in_c + 273.15)
        dh_j = delta_h_rxn_kj_mol * 1000.0
        cp = max(10.0, cp_j_mol_k)

        # Evaluate adiabatic line X_op = cp * (T - T_in) / (-dH) for exothermic reactions (dH < 0)
        best_x_eq = 0.0
        best_t_c = t_in_c
        for step in range(41):
            frac = step / 40.0
            x_op = frac
            dt_ad = (-dh_j / cp) * x_op if dh_j < 0.0 else 0.0
            t_k = max(200.0, t_in_k + dt_ad)
            k_eq = k_eq_ref * math.exp((-dh_j / r_gas) * ((1.0 / t_k) - (1.0 / max(200.0, t_ref_k))))
            x_eq = k_eq / (1.0 + k_eq)
            if x_op <= x_eq:
                best_x_eq = x_op
                best_t_c = t_k - 273.15
            else:
                break

        needs_intercooling = dh_j < 0.0 and best_x_eq < target_conversion
        required_stages = 2 if needs_intercooling else 1
        return {
            "t_in_c": round(t_in_c, 2),
            "adiabatic_exit_c": round(best_t_c, 2),
            "single_bed_max_conversion": round(best_x_eq, 4),
            "target_conversion": target_conversion,
            "needs_intercooling": needs_intercooling,
            "required_stages": required_stages,
        }

    @staticmethod
    def compute_damkohler_and_thiele(
        rate_const: float,
        tau_s: float,
        pellet_radius_m: float,
        d_eff_m2_s: float,
    ) -> Dict[str, Any]:
        """Compute Damkohler number Da_I, Thiele modulus phi, and effectiveness factor eta."""
        k = max(0.0, rate_const)
        tau = max(0.0, tau_s)
        r_p = max(1e-5, pellet_radius_m)
        d_eff = max(1e-12, d_eff_m2_s)

        da_i = k * tau
        phi = r_p * math.sqrt(k / d_eff)
        eta = 1.0 if phi < 1e-4 else math.tanh(phi) / phi
        return {
            "damkohler_da1": round(da_i, 4),
            "thiele_modulus_phi": round(phi, 4),
            "effectiveness_factor_eta": round(eta, 4),
            "diffusion_limited": bool(eta < 0.70),
        }

    @staticmethod
    def compute_pinch_composite_intervals(
        hot_streams: List[Dict[str, float]],
        cold_streams: List[Dict[str, float]],
        dt_min_c: float = 10.0,
    ) -> Dict[str, Any]:
        """Solve Pinch temperature intervals and LMTD shell-and-tube area."""
        q_hot_mw = sum(
            max(0.0, float(s.get("m_cp_mw_k", 0.05)) * (float(s.get("t_in_c", 0.0)) - float(s.get("t_out_c", 0.0))))
            for s in hot_streams
        )
        q_cold_mw = sum(
            max(0.0, float(s.get("m_cp_mw_k", 0.05)) * (float(s.get("t_out_c", 0.0)) - float(s.get("t_in_c", 0.0))))
            for s in cold_streams
        )
        t_h_in = max((float(s.get("t_in_c", 0.0)) for s in hot_streams), default=900.0)
        t_h_out = min((float(s.get("t_out_c", 0.0)) for s in hot_streams), default=130.0)
        t_c_in = min((float(s.get("t_in_c", 0.0)) for s in cold_streams), default=25.0)
        t_c_out = max((float(s.get("t_out_c", 0.0)) for s in cold_streams), default=627.0)

        dt1 = max(dt_min_c, t_h_in - t_c_out)
        dt2 = max(dt_min_c, t_h_out - t_c_in)
        lmtd = (dt1 + dt2) * 0.5 if abs(dt1 - dt2) < 0.5 else (dt1 - dt2) / math.log(dt1 / dt2)
        u_w_m2k = 45.0
        f_t = 0.90
        a_req = (min(q_hot_mw, q_cold_mw) * 1e6) / (u_w_m2k * f_t * max(1.0, lmtd))
        return {
            "q_hot_mw": round(q_hot_mw, 2),
            "q_cold_mw": round(q_cold_mw, 2),
            "dt_lmtd_k": round(lmtd, 2),
            "pinch_dt_min_c": dt_min_c,
            "estimated_area_m2": round(a_req, 1),
        }

    def diagnose_manifest(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Run Levenspiel's thermochemical diagnostics on a declarative manifest."""
        eq_traj = self.compute_adiabatic_equilibrium_trajectory(
            t_in_c=340.0,
            delta_h_rxn_kj_mol=-41.2,
            cp_j_mol_k=36.5,
            k_eq_ref=11.8,
            t_ref_k=673.15,
            target_conversion=0.90,
        )
        thiele = self.compute_damkohler_and_thiele(
            rate_const=1.2,
            tau_s=2.4,
            pellet_radius_m=0.004,
            d_eff_m2_s=2.5e-6,
        )
        stages = list(payload.get("stages", payload.get("anatomy_blueprint", {}).get("unit_operations", [])) or [])
        hot_s = [
            {
                "t_in_c": float(u.get("t_hot_in_c", u.get("temperature_c", 400.0))),
                "t_out_c": float(u.get("t_hot_out_c", 200.0)),
                "m_cp_mw_k": 0.08,
            }
            for u in stages
            if u.get("archetype") == "shell_tube_hx"
        ]
        cold_s = [{"t_in_c": 25.0, "t_out_c": 627.0, "m_cp_mw_k": 0.07}]
        pinch = self.compute_pinch_composite_intervals(hot_s or [{"t_in_c": 1010.0, "t_out_c": 130.0, "m_cp_mw_k": 0.08}], cold_s)
        return {
            "toolkit": "LevenspielToolkit",
            "adiabatic_equilibrium": eq_traj,
            "catalyst_diffusion": thiele,
            "pinch_composite": pinch,
        }


class GadenToolkit:
    """Executable bioprocess & oxygen/heat scale-up diagnostics for Elmer Gaden."""

    @staticmethod
    def evaluate_gaden_oxygen_and_heat_scaleup(
        our_mmol_l_h: float,
        kla_1_h: float,
        c_star_mmol_l: float,
        vessel_vol_m3: float,
        impeller_tip_speed_m_s: float,
        c_crit_mmol_l: float = 0.03,
        gaden_type: str = "Type I (Growth-Associated)",
    ) -> Dict[str, Any]:
        """Evaluate Gaden O2 transfer, metabolic heat vs jacket area, and tip-speed shear."""
        otr_max = max(0.0, kla_1_h) * max(0.0, c_star_mmol_l - c_crit_mmol_l)
        o2_sufficient = otr_max >= our_mmol_l_h

        # Metabolic heat: ~460 kJ per mol O2 consumed
        q_met_kw = (our_mmol_l_h * 1e-3 * (vessel_vol_m3 * 1000.0) * 460.0) / 3600.0
        # Assume cylindrical H/D = 2 vessel -> A_jacket / V ~ 4.5 / D
        d_vessel = max(0.2, ((4.0 * vessel_vol_m3) / (2.0 * math.pi)) ** (1.0 / 3.0))
        a_jacket_m2 = math.pi * d_vessel * (2.0 * d_vessel)
        a_over_v = a_jacket_m2 / max(1e-4, vessel_vol_m3)
        shear_warning = impeller_tip_speed_m_s > 5.5

        return {
            "gaden_fermentation_type": gaden_type,
            "otr_max_mmol_l_h": round(otr_max, 2),
            "our_mmol_l_h": round(our_mmol_l_h, 2),
            "oxygen_transfer_sufficient": o2_sufficient,
            "metabolic_heat_kw": round(q_met_kw, 2),
            "jacket_area_m2": round(a_jacket_m2, 2),
            "jacket_area_to_volume_1_m": round(a_over_v, 2),
            "impeller_tip_speed_m_s": round(impeller_tip_speed_m_s, 2),
            "shear_stress_warning": shear_warning,
        }

    def diagnose_manifest(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        gp = payload.get("grounded_parameters", {}) or {}
        kla = float(gp.get("mass_transfer_kla", {}).get("value", 240.0)) if isinstance(gp.get("mass_transfer_kla"), dict) else 240.0
        c_star = float(gp.get("oxygen_saturation_c_star", {}).get("value", 0.22)) if isinstance(gp.get("oxygen_saturation_c_star"), dict) else 0.22
        res = self.evaluate_gaden_oxygen_and_heat_scaleup(
            our_mmol_l_h=38.0,
            kla_1_h=kla,
            c_star_mmol_l=c_star,
            vessel_vol_m3=1.0,
            impeller_tip_speed_m_s=3.8,
        )
        return {"toolkit": "GadenToolkit", "scaleup_audit": res}


class TeslaToolkit:
    """Executable electromechanical & coupled transient diagnostics for Nikola Tesla."""

    @staticmethod
    def evaluate_electromechanical_transients(
        inductance_h: float,
        resistance_ohm: float,
        mass_kg: float,
        stiffness_n_m: float,
        damping_n_s_m: float,
    ) -> Dict[str, Any]:
        """Compute tau_e = L/R, omega_n = sqrt(k/m), damping ratio zeta, and efficiency."""
        r = max(1e-4, resistance_ohm)
        m = max(1e-4, mass_kg)
        k = max(1e-4, stiffness_n_m)
        tau_e = max(0.0, inductance_h) / r
        omega_n = math.sqrt(k / m)
        zeta = max(0.0, damping_n_s_m) / (2.0 * math.sqrt(k * m))
        regime = "underdamped" if zeta < 0.99 else ("critically_damped" if zeta <= 1.01 else "overdamped")
        coupling_eff = max(0.0, min(1.0, 1.0 - (r / (r + 12.0)) * 0.35 - 0.05 * max(0.0, zeta - 1.0)))
        return {
            "electrical_tau_s": round(tau_e, 5),
            "mechanical_omega_n_rad_s": round(omega_n, 3),
            "damping_ratio_zeta": round(zeta, 4),
            "damping_regime": regime,
            "coupling_efficiency": round(coupling_eff, 4),
        }

    def diagnose_manifest(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        res = self.evaluate_electromechanical_transients(
            inductance_h=0.045,
            resistance_ohm=2.4,
            mass_kg=1.8,
            stiffness_n_m=420.0,
            damping_n_s_m=18.0,
        )
        return {"toolkit": "TeslaToolkit", "electromechanical_transients": res}


class FeynmanProctorToolkit:
    """Order-of-magnitude Fermi limits & asymptotic boundary proctor for Richard Feynman."""

    MAX_GAS_HX_FLUX_KW_M2 = 150.0
    MAX_PACKED_BED_VELOCITY_M_S = 1.5

    def run_asymptotic_and_flux_audit(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        """Check asymptotic F->0, Kelvin positivity, Fermi heat flux q'' <= 150 kW/m2, and u_s <= 1.5 m/s."""
        anomalies: List[Dict[str, Any]] = []
        stages = list(manifest.get("stages", manifest.get("anatomy_blueprint", {}).get("unit_operations", [])) or [])
        max_flux_seen = 0.0
        max_vel_seen = 0.0

        for u in stages:
            tag = str(u.get("tag") or u.get("stage_id") or "UNIT")
            t_c = u.get("temperature_c")
            p_bar = u.get("pressure_bar")
            flow = u.get("flow_nm3_h")
            if t_c is not None and float(t_c) <= -273.15:
                anomalies.append({
                    "code": "ASYMPTOTIC_KELVIN_VIOLATION",
                    "unit_tag": tag,
                    "detail": f"Absolute temperature <= 0 K ({t_c} C).",
                })
            if p_bar is not None and float(p_bar) <= 0.0:
                anomalies.append({
                    "code": "ASYMPTOTIC_PRESSURE_VIOLATION",
                    "unit_tag": tag,
                    "detail": f"Non-positive pressure ({p_bar} bar).",
                })
            if flow is not None and float(flow) == 0.0 and float(u.get("thermal_duty_mw", 0.0)) > 0.1:
                anomalies.append({
                    "code": "ASYMPTOTIC_ZERO_FLOW_DUTY",
                    "unit_tag": tag,
                    "detail": "Non-zero thermal duty at zero flowrate (F -> 0).",
                })

            sizing = u.get("sizing", {})
            if isinstance(sizing, dict):
                area = float(sizing.get("area_req_m2", 0.0))
                duty_mw = float(u.get("thermal_duty_mw", sizing.get("duty_mw", 0.0)))
                if area > 0.0 and duty_mw > 0.0:
                    q_flux = (duty_mw * 1000.0) / area
                    max_flux_seen = max(max_flux_seen, q_flux)
                    if q_flux > self.MAX_GAS_HX_FLUX_KW_M2:
                        anomalies.append({
                            "code": "FERMI_HEAT_FLUX_EXCEEDED",
                            "unit_tag": tag,
                            "detail": f"Heat flux q''={q_flux:.1f} kW/m2 > {self.MAX_GAS_HX_FLUX_KW_M2:.1f} kW/m2 gas HX limit.",
                        })

                u_s = float(sizing.get("u_superficial_m_s", 0.0))
                if u_s > 0.0:
                    max_vel_seen = max(max_vel_seen, u_s)
                    if u_s > self.MAX_PACKED_BED_VELOCITY_M_S:
                        anomalies.append({
                            "code": "CATALYST_FLUIDIZATION_RISK",
                            "unit_tag": tag,
                            "detail": f"Superficial velocity u_s={u_s:.2f} m/s > {self.MAX_PACKED_BED_VELOCITY_M_S:.2f} m/s.",
                        })

        return {
            "toolkit": "FeynmanProctorToolkit",
            "passed": len(anomalies) == 0,
            "anomalies": anomalies,
            "metrics": {
                "max_heat_flux_kw_m2": round(max_flux_seen, 2),
                "max_superficial_velocity_m_s": round(max_vel_seen, 2),
            },
        }
