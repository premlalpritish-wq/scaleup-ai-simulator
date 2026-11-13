import copy
import hashlib
from typing import Any, Callable, Dict, List, Optional

from .database import ParameterDatabase
from .schemas import ValidatedWorkedTraceSpec


def _default_locked_solver(perturbed_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run the locked Layer C physics & sizing pipeline on a perturbed manifest."""
    from composition.composition.workflow.skill_research_bridge import (
        compute_equipment_and_pipe_sizing,
        synthesize_heat_integration_network,
    )

    p = copy.deepcopy(perturbed_payload)
    bp = p.get("anatomy_blueprint", {})
    units = list(p.get("stages", bp.get("unit_operations", [])) or [])
    if not units:
        return p

    units, _streams, connections, _hen = synthesize_heat_integration_network(units)
    units, connections, sizing_table, layout_metrics = compute_equipment_and_pipe_sizing(units, connections)
    p["stages"] = units
    if isinstance(bp, dict):
        bp["unit_operations"] = units
        bp["connections"] = connections
    p["composition_graph"] = {"nodes": [u.get("stage_id", "") for u in units], "edges": connections}
    p["mass_energy_sizing_table"] = sizing_table
    p["layout_metrics"] = layout_metrics
    return p


class PeerReviewCommittee:
    """Black-box verification gate for declarative topology manifests and simulation payloads."""

    PERTURBATIONS = (
        ("flow_plus_20pct", {"flow_scale": 1.20, "temp_delta_c": 0.0, "press_scale": 1.00}),
        ("temp_minus_50k", {"flow_scale": 1.00, "temp_delta_c": -50.0, "press_scale": 1.00}),
        ("press_minus_15pct", {"flow_scale": 1.00, "temp_delta_c": 0.0, "press_scale": 0.85}),
    )

    def __init__(
        self,
        db_url: Optional[str] = None,
        solver_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ):
        self.db_url = db_url
        self.solver_fn = solver_fn or _default_locked_solver

    @staticmethod
    def _format_symptom_only(violations: List[Dict[str, Any]]) -> List[str]:
        """Format physical violations strictly as symptoms without leaking target thresholds."""
        symptoms: List[str] = []
        for v in violations:
            law_id = str(v.get("law_id", "PHYSICAL_INVARIANT"))
            unit_tag = str(v.get("unit_tag", "UNIT"))
            symptoms.append(f"[{law_id}] on [{unit_tag}]: physical invariant violated.")
        return symptoms

    @staticmethod
    def _extract_signature(payload: Dict[str, Any]) -> Dict[str, float]:
        bp = payload.get("anatomy_blueprint", {})
        units = list(payload.get("stages", bp.get("unit_operations", [])) or [])
        total_duty = 0.0
        total_flow = 0.0
        total_temp = 0.0
        total_press = 0.0
        total_area = 0.0
        for u in units:
            total_duty += float(u.get("thermal_duty_mw", 0.0))
            total_flow += float(u.get("flow_nm3_h", 0.0))
            total_temp += float(u.get("temperature_c", 0.0))
            total_press += float(u.get("pressure_bar", 0.0))
            sizing = u.get("sizing", {})
            if isinstance(sizing, dict):
                total_area += float(sizing.get("area_req_m2", 0.0))
            for bank in u.get("convection_banks", []) or []:
                total_duty += float(bank.get("duty_mw", 0.0))
                b_s = bank.get("sizing", {})
                if isinstance(b_s, dict):
                    total_area += float(b_s.get("area_req_m2", 0.0))
        return {
            "total_duty_mw": total_duty,
            "total_flow_nm3_h": total_flow,
            "total_temp_c": total_temp,
            "total_press_bar": total_press,
            "total_area_m2": total_area,
        }

    @staticmethod
    def _apply_perturbation(payload: Dict[str, Any], spec: Dict[str, float]) -> Dict[str, Any]:
        p = copy.deepcopy(payload)
        bp = p.get("anatomy_blueprint", {})
        units = list(p.get("stages", bp.get("unit_operations", [])) or [])
        flow_scale = float(spec.get("flow_scale", 1.0))
        temp_delta = float(spec.get("temp_delta_c", 0.0))
        press_scale = float(spec.get("press_scale", 1.0))

        for u in units:
            if u.get("flow_nm3_h") is not None:
                u["flow_nm3_h"] = float(u["flow_nm3_h"]) * flow_scale
            if u.get("temperature_c") is not None and (
                u.get("archetype") in ("furnace_reformer", "pre_reformer", "packed_bed_reactor")
                or float(u.get("temperature_c", 0.0)) > 100.0
            ):
                u["temperature_c"] = float(u["temperature_c"]) + temp_delta
            if u.get("flue_in_temp_c") is not None:
                u["flue_in_temp_c"] = float(u["flue_in_temp_c"]) + temp_delta
            if u.get("pressure_bar") is not None:
                u["pressure_bar"] = max(1.0, float(u["pressure_bar"]) * press_scale)
            if u.get("t_hot_in_c") is not None:
                u["t_hot_in_c"] = float(u["t_hot_in_c"]) + temp_delta
            if u.get("t_hot_out_c") is not None:
                u["t_hot_out_c"] = float(u["t_hot_out_c"]) + temp_delta * 0.5
        p["stages"] = units
        if isinstance(bp, dict):
            bp["unit_operations"] = units
        return p

    def run_perturbation_audit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Run 3-point boundary perturbation sensitivity and flat-output detection."""
        base_solved = self.solver_fn(copy.deepcopy(payload))
        base_sig = self._extract_signature(base_solved)

        results: List[Dict[str, Any]] = []
        any_flat = False
        for name, spec in self.PERTURBATIONS:
            pert_in = self._apply_perturbation(payload, spec)
            pert_out = self.solver_fn(pert_in)
            pert_sig = self._extract_signature(pert_out)
            max_delta = max(
                abs(pert_sig[k] - base_sig[k]) for k in base_sig
            )
            responsive = max_delta >= 1e-4
            if not responsive:
                any_flat = True
            results.append({
                "perturbation": name,
                "max_delta": round(max_delta, 6),
                "responsive": responsive,
            })

        return {
            "passed": not any_flat,
            "flag": "HARDCODED_BYPASS_SUSPECTED" if any_flat else "RESPONSIVE",
            "cases": results,
        }

    def evaluate(
        self,
        payload: Dict[str, Any],
        run_perturbations: bool = True,
        archive_on_pass: bool = True,
        domain_id: str = "thermochemical_plant",
    ) -> Dict[str, Any]:
        """Evaluate a declarative manifest/payload against RealityCompiler and 3-point perturbations."""
        from composition.composition.workflow.reality_compiler import (
            PhysicsCompilationError,
            RealityCompiler,
        )

        symptom_reports: List[str] = []
        compiler = RealityCompiler()
        try:
            compiler.verify_strict(payload)
        except PhysicsCompilationError as err:
            symptom_reports.extend(self._format_symptom_only(err.violations))

        perturbation_audit: Dict[str, Any] = {"passed": True, "flag": "SKIPPED", "cases": []}
        if run_perturbations:
            perturbation_audit = self.run_perturbation_audit(payload)
            if not perturbation_audit["passed"]:
                symptom_reports.append(
                    "[HARDCODED_BYPASS_SUSPECTED] on [SOLVER]: physical outputs invariant under boundary perturbation."
                )

        passed = len(symptom_reports) == 0
        trace_archived = False
        trace_id: Optional[str] = None
        if passed and archive_on_pass:
            prompt_txt = str(payload.get("prompt", ""))
            manifest = payload.get("topology_manifest", {})
            deriv_trace = str(
                manifest.get("derivation_trace", payload.get("derivation_trace", ""))
            )
            if prompt_txt:
                trace_id = hashlib.sha256(prompt_txt.encode("utf-8")).hexdigest()[:16]
                db = ParameterDatabase(db_url=self.db_url)
                db.archive_validated_trace(
                    ValidatedWorkedTraceSpec(
                        trace_id=trace_id,
                        domain_id=domain_id,
                        prompt=prompt_txt,
                        derivation_trace=deriv_trace or "Verified via PeerReviewCommittee",
                        topology_manifest_json=manifest if isinstance(manifest, dict) else {},
                        perturbation_passed=bool(perturbation_audit.get("passed", True)),
                    )
                )
                trace_archived = True

        audit = {
            "status": "PASSED" if passed else "FAILED",
            "symptom_reports": symptom_reports,
            "perturbation_audit": perturbation_audit,
            "trace_archived": trace_archived,
            "trace_id": trace_id,
        }
        payload["peer_review_audit"] = audit
        return audit
