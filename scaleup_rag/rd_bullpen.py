import copy
import hashlib
import re
import uuid
from typing import Any, Callable, Dict, List, Optional

from .database import ParameterDatabase, ScientificParameterRecord
from .peer_review_gate import PeerReviewCommittee
from .personas.toolkits import (
    FeynmanProctorToolkit,
    GadenToolkit,
    LevenspielToolkit,
    TeslaToolkit,
)
from .schemas import (
    CritiquePayload,
    DomainSkillSpec,
    InternalPersonaProfile,
    PersonaEpisodicMemorySpec,
)
from .seed_knowledge import SEED_AGENT_PROFILES, SEED_DOMAIN_SKILLS
from sqlalchemy import select

PUBLIC_EXPORT_ALLOWLIST = {
    "contract_version",
    "schema_version",
    "run_id",
    "status",
    "prompt",
    "cache_hit",
    "confidence_score",
    "has_analogue_bridge",
    "researched_papers",
    "diagram_path",
    "stages",
    "anatomy_blueprint",
    "telemetry_schema",
    "sandbox_config",
    "literature_review_manifest",
    "composition_graph",
    "hen_summary",
    "layout_metrics",
    "mass_energy_sizing_table",
    "trajectories",
    "grounded_parameters",
    "epistemic_audit",
    "epistemic_provenance",
    "summary",
    "reality_compiler_audit",
    "peer_review_audit",
    "topology_manifest",
    "engine_attribution",
}

_FORBIDDEN_LEAKAGE_PATTERNS = [
    re.compile(r"\belmer_gaden\b", re.IGNORECASE),
    re.compile(r"\boctave_levenspiel\b", re.IGNORECASE),
    re.compile(r"\bnikola_tesla\b", re.IGNORECASE),
    re.compile(r"\brichard_feynman\b", re.IGNORECASE),
    re.compile(r"\bElmer\s+Gaden\b", re.IGNORECASE),
    re.compile(r"\bOctave\s+Levenspiel\b", re.IGNORECASE),
    re.compile(r"\bNikola\s+Tesla\b", re.IGNORECASE),
    re.compile(r"\bRichard\s+Feynman\b", re.IGNORECASE),
    re.compile(r"\bbullpen_trace\b", re.IGNORECASE),
    re.compile(r"\bCritiquePayload\b"),
]

_CITED_QUOTE_KEYS = {"verbatim_quote", "source_snippet"}


def _load_persona_and_skill(
    db: ParameterDatabase, primary_persona_id: str
) -> tuple[InternalPersonaProfile, InternalPersonaProfile, DomainSkillSpec]:
    primary = db.get_agent_profile(primary_persona_id)
    if primary is None:
        primary = next((p for p in SEED_AGENT_PROFILES if p.persona_id == primary_persona_id), None)
    if primary is None:
        raise ValueError(f"Unknown primary_persona_id: {primary_persona_id!r}")

    proctor = db.get_agent_profile("richard_feynman")
    if proctor is None:
        proctor = next(p for p in SEED_AGENT_PROFILES if p.persona_id == "richard_feynman")

    skill = db.get_domain_skill(primary.linked_domain_skill_id)
    if skill is None:
        skill = next(
            (s for s in SEED_DOMAIN_SKILLS if s.domain_id == primary.linked_domain_skill_id),
            SEED_DOMAIN_SKILLS[0],
        )
    return primary, proctor, skill


def _count_lazy_abstentions(db: ParameterDatabase, unverified: Dict[str, Any]) -> int:
    if not unverified:
        return 0
    count = 0
    with db.SessionLocal() as session:
        for key in unverified.keys():
            norm_key = str(key).lower()
            exists = session.execute(
                select(ScientificParameterRecord).where(
                    ScientificParameterRecord.entity_name == norm_key
                )
            ).first()
            if exists is not None:
                count += 1
    return count


def _run_primary_toolkit(persona_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if persona_id == "octave_levenspiel":
        return LevenspielToolkit().diagnose_manifest(payload)
    if persona_id == "elmer_gaden":
        return GadenToolkit().diagnose_manifest(payload)
    if persona_id == "nikola_tesla":
        return TeslaToolkit().diagnose_manifest(payload)
    return {"toolkit": "none", "metrics": {}}


def run_bullpen_review(
    manifest_payload: Dict[str, Any],
    primary_persona_id: str,
    db_url: Optional[str] = None,
    proctor_fn: Optional[
        Callable[[Dict[str, Any], InternalPersonaProfile, InternalPersonaProfile], List[CritiquePayload]]
    ] = None,
) -> Dict[str, Any]:
    """Execute capped 2-round R&D bullpen review and PeerReviewCommittee verification."""
    from composition.composition.workflow.reality_compiler import (
        PhysicsCompilationError,
        RealityCompiler,
    )

    db = ParameterDatabase(db_url=db_url)
    primary, proctor, skill = _load_persona_and_skill(db, primary_persona_id)
    payload = copy.deepcopy(manifest_payload)

    # ------------------------------------------------------------------
    # Dormant Wake-Up: load historical episodic memories for primary & proctor
    # ------------------------------------------------------------------
    primary_memories = db.list_episodic_memories(persona_id=primary.persona_id)
    proctor_memories = db.list_episodic_memories(persona_id=proctor.persona_id)
    loaded_memory_ids = [m.memory_id for m in primary_memories + proctor_memories]

    # ------------------------------------------------------------------
    # Round 1: Pioneer Toolkit Derivation & Proctor Attack (Hard-capped at 2 rounds)
    # ------------------------------------------------------------------
    toolkit_diagnostics = _run_primary_toolkit(primary.persona_id, payload)

    topo = payload.setdefault("topology_manifest", {})
    if isinstance(topo, dict):
        topo.setdefault("domain_id", skill.domain_id)
        topo.setdefault("linked_domain_skill_id", skill.domain_id)

    critiques: List[CritiquePayload] = []

    # 1a. Check archetypes against linked DomainSkillSpec
    stages = list(payload.get("stages", payload.get("anatomy_blueprint", {}).get("unit_operations", [])) or [])
    for st in stages:
        arch = str(st.get("archetype", ""))
        if arch and arch not in skill.allowed_archetypes:
            critiques.append(
                CritiquePayload(
                    critique_id=f"crit_{uuid.uuid4().hex[:8]}",
                    author_persona_id=proctor.persona_id,
                    target_field=f"stages.{st.get('tag', st.get('stage_id', '?'))}.archetype",
                    severity="CRITICAL",
                    symptom=f"Archetype {arch!r} is outside locked skill {skill.domain_id} archetypes.",
                    recommended_reclassification=None,
                )
            )

    # 1b. Hunt ungrounded parameters without DOI / quarantine backing
    grounded = dict(payload.get("grounded_parameters", {}) or {})
    for p_key, p_val in list(grounded.items()):
        has_doi = isinstance(p_val, dict) and bool(str(p_val.get("source_doi", "")).strip())
        if not has_doi:
            critiques.append(
                CritiquePayload(
                    critique_id=f"crit_{uuid.uuid4().hex[:8]}",
                    author_persona_id=proctor.persona_id,
                    target_field=p_key,
                    severity="CRITICAL",
                    symptom=f"Parameter {p_key!r} lacks a peer-reviewed source_doi.",
                    recommended_reclassification="unverified_assumptions",
                )
            )

    for p_key, p_val in list((payload.get("proposed_parameters", {}) or {}).items()):
        has_doi = isinstance(p_val, dict) and bool(str(p_val.get("source_doi", "")).strip())
        if not has_doi and p_key not in grounded:
            critiques.append(
                CritiquePayload(
                    critique_id=f"crit_{uuid.uuid4().hex[:8]}",
                    author_persona_id=proctor.persona_id,
                    target_field=p_key,
                    severity="CRITICAL",
                    symptom=f"Proposed parameter {p_key!r} is ungrounded in scaleup_rag.",
                    recommended_reclassification="unverified_assumptions",
                )
            )

    # 1c. Feynman Proctor asymptotic & Fermi flux attack
    feynman_audit = FeynmanProctorToolkit().run_asymptotic_and_flux_audit(payload)
    for anomaly in feynman_audit.get("anomalies", []):
        critiques.append(
            CritiquePayload(
                critique_id=f"crit_{uuid.uuid4().hex[:8]}",
                author_persona_id=proctor.persona_id,
                target_field=str(anomaly.get("unit_tag", "UNIT")),
                severity="CRITICAL",
                symptom=f"[{anomaly.get('code', 'FERMI_AUDIT')}] {anomaly.get('detail', '')}",
                recommended_reclassification=None,
            )
        )

    # 1d. RealityCompiler physical invariant attack
    try:
        RealityCompiler().verify_strict(payload)
    except PhysicsCompilationError as err:
        for v in err.violations:
            critiques.append(
                CritiquePayload(
                    critique_id=f"crit_{uuid.uuid4().hex[:8]}",
                    author_persona_id=proctor.persona_id,
                    target_field=str(v.get("unit_tag", "UNIT")),
                    severity="CRITICAL",
                    symptom=f"[{v.get('law_id', 'INVARIANT')}] physical invariant violated.",
                    recommended_reclassification=None,
                )
            )

    if proctor_fn is not None:
        critiques.extend(proctor_fn(payload, primary, proctor))

    # ------------------------------------------------------------------
    # Round 2: Resolve & Lock (Hard Stop — never loops past Round 2)
    # ------------------------------------------------------------------
    ep_audit = payload.setdefault("epistemic_audit", {})
    unverified = dict(ep_audit.get("unverified_assumptions", {}) or {})
    proposed = dict(payload.get("proposed_parameters", {}) or {})

    for crit in critiques:
        if crit.recommended_reclassification == "unverified_assumptions":
            fld = crit.target_field
            if fld in grounded:
                unverified[fld] = grounded.pop(fld)
                crit.resolved = True
            elif fld in proposed:
                unverified[fld] = proposed.pop(fld)
                crit.resolved = True
            else:
                unverified[fld] = {"status": "reclassified_by_proctor", "symptom": crit.symptom}
                crit.resolved = True

    payload["grounded_parameters"] = grounded
    ep_audit["grounded_parameters"] = grounded
    ep_audit["unverified_assumptions"] = unverified
    if isinstance(topo, dict):
        topo["grounded_parameters"] = list(grounded.keys())
        topo["unverified_assumptions"] = unverified
    if "proposed_parameters" in payload:
        payload["proposed_parameters"] = proposed

    # ------------------------------------------------------------------
    # Gatekeeper: PeerReviewCommittee + Anti-Gaming Elo Update
    # ------------------------------------------------------------------
    committee = PeerReviewCommittee(db_url=db_url)
    peer_audit = committee.evaluate(
        payload,
        run_perturbations=True,
        archive_on_pass=True,
        domain_id=primary.linked_domain_skill_id,
    )

    total_params = len(grounded) + len(unverified)
    grounding_ratio = (len(grounded) / total_params) if total_params > 0 else 1.0
    lazy_abstentions = _count_lazy_abstentions(db, unverified)
    physics_passed = peer_audit["status"] == "PASSED"
    pert_responsive = bool(peer_audit.get("perturbation_audit", {}).get("passed", False))

    new_elo = db.update_persona_elo(
        persona_id=primary.persona_id,
        physics_passed=physics_passed,
        grounding_ratio=grounding_ratio,
        perturbation_responsive=pert_responsive,
        lazy_abstention_count=lazy_abstentions,
    )

    # ------------------------------------------------------------------
    # Memory Consolidation & Sleep: persist newly learned episodic rules
    # ------------------------------------------------------------------
    learned_memory_ids: List[str] = []
    for crit in critiques:
        sig_raw = f"{primary.persona_id}:{crit.target_field}:{crit.symptom}"
        mem_hash = hashlib.sha256(sig_raw.encode("utf-8")).hexdigest()[:10]
        mem_id = f"mem_{mem_hash}"
        trigger_sig = f"{skill.domain_id}:{crit.target_field}"
        diag = (
            f"Detected by {crit.author_persona_id} during Round 1 against {skill.domain_id} "
            f"(toolkit={toolkit_diagnostics.get('toolkit', 'none')}, physics_passed={physics_passed})."
        )
        rule = (
            f"Prevent {crit.target_field} failure: {crit.symptom}"
            if not crit.recommended_reclassification
            else f"Reclassify {crit.target_field} to {crit.recommended_reclassification} when ungrounded: {crit.symptom}"
        )
        db.upsert_episodic_memory(
            PersonaEpisodicMemorySpec(
                memory_id=mem_id,
                persona_id=primary.persona_id,
                trigger_signature=trigger_sig,
                failure_observed=crit.symptom,
                first_principles_diagnosis=diag,
                generalized_rule_derived=rule,
            )
        )
        learned_memory_ids.append(mem_id)

    return {
        "manifest_payload": payload,
        "public_engine_alias": primary.public_engine_alias,
        "peer_review_audit": peer_audit,
        "bullpen_trace": {
            "rounds_executed": 2,
            "hard_stop_enforced": True,
            "primary_persona_id": primary.persona_id,
            "internal_display_name": primary.internal_display_name,
            "proctor_persona_id": proctor.persona_id,
            "toolkit_diagnostics": toolkit_diagnostics,
            "feynman_proctor_audit": feynman_audit,
            "episodic_memories_loaded": loaded_memory_ids,
            "episodic_memories_learned": learned_memory_ids,
            "critiques": [c.model_dump() for c in critiques],
            "grounding_ratio": round(grounding_ratio, 4),
            "lazy_abstention_count": lazy_abstentions,
            "elo_after": new_elo,
        },
    }


def _scan_for_leakage(obj: Any, path: str = "") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_str = str(k)
            if key_str in _CITED_QUOTE_KEYS:
                continue
            for pat in _FORBIDDEN_LEAKAGE_PATTERNS:
                if pat.search(key_str):
                    raise ValueError(f"Persona leakage detected in key at {path}.{key_str}")
            _scan_for_leakage(v, f"{path}.{key_str}" if path else key_str)
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            _scan_for_leakage(item, f"{path}[{idx}]")
    elif isinstance(obj, str):
        for pat in _FORBIDDEN_LEAKAGE_PATTERNS:
            if pat.search(obj):
                raise ValueError(f"Persona leakage detected in string value at {path}: {obj[:80]!r}")


def sanitize_for_public_export(internal_bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Strict allowlist export stripping all internal persona IDs, names, and bullpen traces."""
    raw_payload = internal_bundle.get("manifest_payload", internal_bundle)
    public_alias = str(
        internal_bundle.get("public_engine_alias")
        or raw_payload.get("engine_attribution")
        or "ScaleUp Physics & Process Engine"
    )

    sanitized: Dict[str, Any] = {}
    for key in PUBLIC_EXPORT_ALLOWLIST:
        if key in raw_payload:
            sanitized[key] = copy.deepcopy(raw_payload[key])
    sanitized["engine_attribution"] = public_alias

    _scan_for_leakage(sanitized)
    return sanitized
