import os
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime, JSON, select, or_, text
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import declarative_base, sessionmaker
from .schemas import (
    DomainSkillSpec,
    GroundedParameter,
    OperatingEnvelope,
    PhysicalInvariantSpec,
    RequiredParameterSpec,
    ValidatedWorkedTraceSpec,
)
from .quarantine_gate import ureg

Base = declarative_base()

ENTITY_ALIASES = {
    "saturation_constant_ks": ["saturation_constant_ks", "affinity_constant_ks", "ganjave_k11", "ganjave_ks_glucose", "ks", "k11"],
    "affinity_constant_ks": ["affinity_constant_ks", "saturation_constant_ks", "ganjave_k11", "ganjave_ks_glucose", "ks"],
    "specific_growth_rate_mu_max": ["specific_growth_rate_mu_max", "mu_max", "mum1", "ganjave_mum1", "lin_mu_max", "baez_mu_30_air_sat"],
    "yield_biomass_glucose": ["yield_biomass_glucose", "y_xs", "baez_y_xs", "ganjave_y11", "ganjave_y_x_glucose"],
    "maintenance_rate_m": ["maintenance_rate_m", "maintenance_coefficient_m", "baez_m", "m"],
    "mass_transfer_kla": ["mass_transfer_kla", "kla", "ganjave_kla"],
    "feed_glucose_concentration": ["feed_glucose_concentration", "feed_glucose", "baez_s_f"],
    "oxygen_saturation_c_star": ["oxygen_saturation_c_star", "c_star", "ganjave_c_star", "ganjave_o2_star"],
    "oxygen_yield_yo": ["oxygen_yield_yo", "yo", "yo1", "ganjave_yo1"],
    "oxygen_affinity_ko": ["oxygen_affinity_ko", "ko", "ko1", "ganjave_ko1"],
}

class ScientificParameterRecord(Base):
    __tablename__ = "scientific_parameters"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_name = Column(String, index=True, nullable=False)
    target_system = Column(String, index=True, nullable=False)
    value_normalized = Column(Float, nullable=False)
    value_min = Column(Float, nullable=True)
    value_max = Column(Float, nullable=True)
    unit_normalized = Column(String, nullable=False)
    raw_value = Column(Float, nullable=False)
    raw_value_min = Column(Float, nullable=True)
    raw_value_max = Column(Float, nullable=True)
    raw_unit = Column(String, nullable=False)
    uncertainty = Column(Float, nullable=True)
    pressure_bar = Column(Float, nullable=True)
    envelope_json = Column(JSON, nullable=False)
    source_doi = Column(String, nullable=False)
    source_snippet = Column(Text, nullable=False)
    verification_tier = Column(String, default="tier_1_quarantine", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


ParameterRecord = ScientificParameterRecord


class MechanisticLawRecord(Base):
    __tablename__ = "mechanistic_laws"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    law_id = Column(String, unique=True, index=True, nullable=False)
    domain = Column(String, index=True, nullable=False)
    governing_equation = Column(Text, nullable=False)
    threshold_parameters_json = Column(JSON, nullable=False)
    remediation_action = Column(String, nullable=False)
    doi = Column(String, nullable=False)
    verbatim_quote = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class DomainSkillRecord(Base):
    __tablename__ = "domain_skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain_id = Column(String, nullable=False, unique=True, index=True)
    governing_laws_json = Column(JSON, nullable=False)
    rag_scope_json = Column(JSON, nullable=False)
    allowed_archetypes_json = Column(JSON, nullable=False)
    few_shot_derivations_json = Column(JSON, nullable=False)
    invariant_checks_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class ValidatedWorkedTraceRecord(Base):
    __tablename__ = "validated_worked_traces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String, nullable=False, unique=True, index=True)
    domain_id = Column(String, nullable=False, index=True)
    prompt = Column(Text, nullable=False)
    derivation_trace = Column(Text, nullable=False)
    topology_manifest_json = Column(JSON, nullable=False)
    perturbation_passed = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class ParameterDatabase:
    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or os.getenv("SCALEUP_DATABASE_URL", "sqlite:///scaleup_knowledge.db")
        if self.db_url == "sqlite:///:memory:":
            self.engine = create_engine(
                self.db_url,
                future=True,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        else:
            self.engine = create_engine(self.db_url, future=True)
        Base.metadata.create_all(self.engine)
        self._ensure_sqlite_columns()
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def _ensure_sqlite_columns(self) -> None:
        if not self.db_url.startswith("sqlite"):
            return
        needed = {
            "value_min": "FLOAT",
            "value_max": "FLOAT",
            "raw_value_min": "FLOAT",
            "raw_value_max": "FLOAT",
            "pressure_bar": "FLOAT",
        }
        with self.engine.begin() as conn:
            rows = conn.execute(text("PRAGMA table_info(scientific_parameters)")).fetchall()
            existing = {r[1] for r in rows}
            for col_name, col_type in needed.items():
                if col_name not in existing:
                    conn.execute(text(f"ALTER TABLE scientific_parameters ADD COLUMN {col_name} {col_type}"))

    def _record_to_grounded(
        self,
        rec: ScientificParameterRecord,
        entity_name_override: Optional[str] = None,
        expected_unit: Optional[str] = None,
    ) -> GroundedParameter:
        val_norm = rec.value_normalized
        val_min = rec.value_min
        val_max = rec.value_max
        unit_norm = rec.unit_normalized
        if expected_unit and expected_unit != unit_norm:
            try:
                val_norm = float(ureg.Quantity(val_norm, unit_norm).to(expected_unit).magnitude)
                if val_min is not None:
                    val_min = float(ureg.Quantity(val_min, unit_norm).to(expected_unit).magnitude)
                if val_max is not None:
                    val_max = float(ureg.Quantity(val_max, unit_norm).to(expected_unit).magnitude)
                unit_norm = expected_unit
            except Exception:
                pass
        env_dict = dict(rec.envelope_json or {})
        if env_dict.get("pressure_bar") is None and rec.pressure_bar is not None:
            env_dict["pressure_bar"] = rec.pressure_bar
        return GroundedParameter(
            entity_name=entity_name_override or rec.entity_name,
            target_system=rec.target_system,
            value_normalized=val_norm,
            value_min=val_min,
            value_max=val_max,
            unit_normalized=unit_norm,
            raw_value=rec.raw_value,
            raw_value_min=rec.raw_value_min,
            raw_value_max=rec.raw_value_max,
            raw_unit=rec.raw_unit,
            uncertainty=rec.uncertainty,
            envelope=OperatingEnvelope(**env_dict),
            source_doi=rec.source_doi,
            source_snippet=rec.source_snippet,
            verification_tier=rec.verification_tier,
            origin="database_cache_hit",
        )

    def lookup_parameter(self, spec: RequiredParameterSpec) -> Optional[GroundedParameter]:
        with self.SessionLocal() as session:
            aliases = ENTITY_ALIASES.get(spec.entity_name.lower(), [spec.entity_name.lower()])
            stmt = select(ScientificParameterRecord).where(
                or_(*[ScientificParameterRecord.entity_name.ilike(a) for a in aliases]),
                ScientificParameterRecord.target_system.ilike(f"%{spec.target_system}%")
            )
            records = session.execute(stmt).scalars().all()
            if not records:
                return None

            try:
                target_dim = ureg.Unit(spec.expected_unit).dimensionality
            except Exception:
                target_dim = None

            dim_records = []
            for rec in records:
                try:
                    if target_dim is None or ureg.Unit(rec.unit_normalized).dimensionality == target_dim:
                        dim_records.append(rec)
                except Exception:
                    pass

            if not dim_records:
                return None

            # Prefer exact name match, then closest temperature match
            best_record = None
            for rec in dim_records:
                if rec.entity_name.lower() == spec.entity_name.lower():
                    best_record = rec
                    break
            if best_record is None:
                best_record = dim_records[0]

            if spec.envelope_constraints.temperature_c is not None:
                target_t = spec.envelope_constraints.temperature_c
                for rec in dim_records:
                    rec_t = (rec.envelope_json or {}).get("temperature_c")
                    if rec_t is not None and abs(rec_t - target_t) <= 10.0:
                        best_record = rec
                        break

            return self._record_to_grounded(
                best_record,
                entity_name_override=spec.entity_name,
                expected_unit=spec.expected_unit,
            )

    def write_back_parameter(self, param: GroundedParameter) -> None:
        with self.SessionLocal() as session:
            exists_stmt = select(ScientificParameterRecord).where(
                ScientificParameterRecord.entity_name.ilike(param.entity_name),
                ScientificParameterRecord.target_system.ilike(param.target_system),
                ScientificParameterRecord.source_doi == param.source_doi
            )
            existing = session.execute(exists_stmt).scalar_one_or_none()
            if existing:
                dirty = False
                if existing.value_min is None and param.value_min is not None:
                    existing.value_min = param.value_min
                    existing.raw_value_min = param.raw_value_min
                    dirty = True
                if existing.value_max is None and param.value_max is not None:
                    existing.value_max = param.value_max
                    existing.raw_value_max = param.raw_value_max
                    dirty = True
                if existing.uncertainty is None and param.uncertainty is not None:
                    existing.uncertainty = param.uncertainty
                    dirty = True
                if existing.pressure_bar is None and param.envelope.pressure_bar is not None:
                    existing.pressure_bar = param.envelope.pressure_bar
                    dirty = True
                env_cur = dict(existing.envelope_json or {})
                env_new = param.envelope.model_dump()
                for ek in ("temperature_c", "ph", "pressure_bar", "shear_rate_s_inv", "substrate", "medium_or_catalyst", "notes"):
                    if env_cur.get(ek) is None and env_new.get(ek) is not None:
                        env_cur[ek] = env_new[ek]
                        dirty = True
                if dirty:
                    existing.envelope_json = env_cur
                    session.commit()
                return

            record = ScientificParameterRecord(
                entity_name=param.entity_name.lower(),
                target_system=param.target_system,
                value_normalized=param.value_normalized,
                value_min=param.value_min,
                value_max=param.value_max,
                unit_normalized=param.unit_normalized,
                raw_value=param.raw_value,
                raw_value_min=param.raw_value_min,
                raw_value_max=param.raw_value_max,
                raw_unit=param.raw_unit,
                uncertainty=param.uncertainty,
                pressure_bar=param.envelope.pressure_bar,
                envelope_json=param.envelope.model_dump(),
                source_doi=param.source_doi.strip(),
                source_snippet=param.source_snippet.strip(),
                verification_tier=param.verification_tier
            )
            session.add(record)
            session.commit()

    store_grounded_parameter = write_back_parameter

    def get_parameters_for_system(self, target_system: str) -> list[GroundedParameter]:
        with self.SessionLocal() as session:
            stmt = select(ScientificParameterRecord).where(
                ScientificParameterRecord.target_system.ilike(f"%{target_system}%")
            )
            records = session.execute(stmt).scalars().all()
            return [self._record_to_grounded(rec) for rec in records]

    def upsert_mechanistic_law(self, law: PhysicalInvariantSpec) -> bool:
        """Insert or update a PhysicalInvariantSpec in mechanistic_laws. Returns True if newly inserted."""
        with self.SessionLocal() as session:
            existing = session.execute(
                select(MechanisticLawRecord).where(MechanisticLawRecord.law_id == law.law_id)
            ).scalar_one_or_none()
            if existing is not None:
                existing.domain = law.domain
                existing.governing_equation = law.governing_equation
                existing.threshold_parameters_json = dict(law.threshold_parameters)
                existing.remediation_action = law.remediation_action
                existing.doi = law.doi.strip()
                existing.verbatim_quote = law.verbatim_quote.strip()
                session.commit()
                return False
            rec = MechanisticLawRecord(
                law_id=law.law_id,
                domain=law.domain,
                governing_equation=law.governing_equation,
                threshold_parameters_json=dict(law.threshold_parameters),
                remediation_action=law.remediation_action,
                doi=law.doi.strip(),
                verbatim_quote=law.verbatim_quote.strip(),
            )
            session.add(rec)
            session.commit()
            return True

    def get_mechanistic_law(self, law_id: str) -> Optional[PhysicalInvariantSpec]:
        with self.SessionLocal() as session:
            rec = session.execute(
                select(MechanisticLawRecord).where(MechanisticLawRecord.law_id == law_id)
            ).scalar_one_or_none()
            if rec is None:
                return None
            return PhysicalInvariantSpec(
                law_id=rec.law_id,
                domain=rec.domain,
                governing_equation=rec.governing_equation,
                threshold_parameters=dict(rec.threshold_parameters_json or {}),
                remediation_action=rec.remediation_action,
                doi=rec.doi,
                verbatim_quote=rec.verbatim_quote,
            )

    def list_mechanistic_laws(self, domain: Optional[str] = None) -> List[PhysicalInvariantSpec]:
        with self.SessionLocal() as session:
            stmt = select(MechanisticLawRecord)
            if domain:
                stmt = stmt.where(MechanisticLawRecord.domain == domain)
            records = session.execute(stmt).scalars().all()
            return [
                PhysicalInvariantSpec(
                    law_id=r.law_id,
                    domain=r.domain,
                    governing_equation=r.governing_equation,
                    threshold_parameters=dict(r.threshold_parameters_json or {}),
                    remediation_action=r.remediation_action,
                    doi=r.doi,
                    verbatim_quote=r.verbatim_quote,
                )
                for r in records
            ]

    def upsert_domain_skill(self, skill: DomainSkillSpec) -> bool:
        """Insert or update a DomainSkillSpec in domain_skills. Returns True if newly inserted."""
        with self.SessionLocal() as session:
            existing = session.execute(
                select(DomainSkillRecord).where(DomainSkillRecord.domain_id == skill.domain_id)
            ).scalar_one_or_none()
            if existing is not None:
                existing.governing_laws_json = list(skill.governing_laws)
                existing.rag_scope_json = dict(skill.rag_scope)
                existing.allowed_archetypes_json = list(skill.allowed_archetypes)
                existing.few_shot_derivations_json = list(skill.few_shot_derivations)
                existing.invariant_checks_json = list(skill.invariant_checks)
                session.commit()
                return False
            rec = DomainSkillRecord(
                domain_id=skill.domain_id,
                governing_laws_json=list(skill.governing_laws),
                rag_scope_json=dict(skill.rag_scope),
                allowed_archetypes_json=list(skill.allowed_archetypes),
                few_shot_derivations_json=list(skill.few_shot_derivations),
                invariant_checks_json=list(skill.invariant_checks),
            )
            session.add(rec)
            session.commit()
            return True

    def get_domain_skill(self, domain_id: str) -> Optional[DomainSkillSpec]:
        with self.SessionLocal() as session:
            rec = session.execute(
                select(DomainSkillRecord).where(DomainSkillRecord.domain_id == domain_id)
            ).scalar_one_or_none()
            if rec is None:
                return None
            return DomainSkillSpec(
                domain_id=rec.domain_id,
                governing_laws=list(rec.governing_laws_json or []),
                rag_scope=dict(rec.rag_scope_json or {}),
                allowed_archetypes=list(rec.allowed_archetypes_json or []),
                few_shot_derivations=list(rec.few_shot_derivations_json or []),
                invariant_checks=list(rec.invariant_checks_json or []),
            )

    def list_domain_skills(self) -> List[DomainSkillSpec]:
        with self.SessionLocal() as session:
            records = session.execute(select(DomainSkillRecord)).scalars().all()
            return [
                DomainSkillSpec(
                    domain_id=r.domain_id,
                    governing_laws=list(r.governing_laws_json or []),
                    rag_scope=dict(r.rag_scope_json or {}),
                    allowed_archetypes=list(r.allowed_archetypes_json or []),
                    few_shot_derivations=list(r.few_shot_derivations_json or []),
                    invariant_checks=list(r.invariant_checks_json or []),
                )
                for r in records
            ]

    def archive_validated_trace(self, trace: ValidatedWorkedTraceSpec) -> bool:
        """Archive a peer-reviewed (prompt, derivation_trace, topology_manifest) tuple."""
        with self.SessionLocal() as session:
            existing = session.execute(
                select(ValidatedWorkedTraceRecord).where(ValidatedWorkedTraceRecord.trace_id == trace.trace_id)
            ).scalar_one_or_none()
            if existing is not None:
                existing.domain_id = trace.domain_id
                existing.prompt = trace.prompt
                existing.derivation_trace = trace.derivation_trace
                existing.topology_manifest_json = dict(trace.topology_manifest_json)
                existing.perturbation_passed = 1 if trace.perturbation_passed else 0
                session.commit()
                return False
            rec = ValidatedWorkedTraceRecord(
                trace_id=trace.trace_id,
                domain_id=trace.domain_id,
                prompt=trace.prompt,
                derivation_trace=trace.derivation_trace,
                topology_manifest_json=dict(trace.topology_manifest_json),
                perturbation_passed=1 if trace.perturbation_passed else 0,
            )
            session.add(rec)
            session.commit()
            return True

    def list_validated_traces(self, domain_id: Optional[str] = None) -> List[ValidatedWorkedTraceSpec]:
        with self.SessionLocal() as session:
            stmt = select(ValidatedWorkedTraceRecord)
            if domain_id:
                stmt = stmt.where(ValidatedWorkedTraceRecord.domain_id == domain_id)
            records = session.execute(stmt).scalars().all()
            return [
                ValidatedWorkedTraceSpec(
                    trace_id=r.trace_id,
                    domain_id=r.domain_id,
                    prompt=r.prompt,
                    derivation_trace=r.derivation_trace,
                    topology_manifest_json=dict(r.topology_manifest_json or {}),
                    perturbation_passed=bool(r.perturbation_passed),
                )
                for r in records
            ]
