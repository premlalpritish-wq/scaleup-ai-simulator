"""Unified Central Knowledge Library Store.

Manages the persistent central index (central_library.json) connecting:
1. Papers: Metadata, provenance hashes, citations.
2. Parameters: Atomic empirical values with strict biological context.
3. Mechanisms: Reusable mathematical models, equations, and port definitions.

Provides query interfaces for context matching, cross-paper compatibility edge
computation (EXACT_MATCH, ANALOGUE_BRIDGE, INCOMPATIBLE_CONSTRAINTS), and
mechanism alternative discovery for hot-swapping.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[3]
CENTRAL_LIBRARY_PATH = Path(__file__).resolve().parent / "central_library.json"


@dataclass(frozen=True)
class BiologicalContext:
    organism: str = "Escherichia coli"
    strain: str = "unspecified"
    temperature_c: float | None = None
    ph: float | None = None
    medium: str = "unspecified"
    evidence_tier: str = "DIRECT"  # DIRECT | ANALOGUE

    def to_dict(self) -> dict[str, Any]:
        return {
            "organism": self.organism,
            "strain": self.strain,
            "temperature_c": self.temperature_c,
            "ph": self.ph,
            "medium": self.medium,
            "evidence_tier": self.evidence_tier,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BiologicalContext":
        return cls(
            organism=str(data.get("organism", "Escherichia coli")),
            strain=str(data.get("strain", "unspecified")),
            temperature_c=float(data["temperature_c"]) if data.get("temperature_c") is not None else None,
            ph=float(data["ph"]) if data.get("ph") is not None else None,
            medium=str(data.get("medium", "unspecified")),
            evidence_tier=str(data.get("evidence_tier", "DIRECT")),
        )


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    doi: str
    title: str
    authors: list[str] | str
    year: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PaperRecord":
        return cls(
            paper_id=str(data["paper_id"]),
            doi=str(data.get("doi", "")),
            title=str(data.get("title", "")),
            authors=data.get("authors", []),
            year=int(data.get("year", 0)),
            sha256=str(data.get("sha256", "")),
        )


@dataclass(frozen=True)
class ParameterRecord:
    param_id: str
    quantity_type: str
    value: Any
    unit: str
    paper_id: str
    verbatim_quote: str
    section_anchor: str
    biological_context: BiologicalContext

    def to_dict(self) -> dict[str, Any]:
        return {
            "param_id": self.param_id,
            "quantity_type": self.quantity_type,
            "value": self.value,
            "unit": self.unit,
            "paper_id": self.paper_id,
            "verbatim_quote": self.verbatim_quote,
            "section_anchor": self.section_anchor,
            "biological_context": self.biological_context.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ParameterRecord":
        return cls(
            param_id=str(data["param_id"]),
            quantity_type=str(data.get("quantity_type", "")),
            value=data.get("value"),
            unit=str(data.get("unit", "")),
            paper_id=str(data.get("paper_id", "")),
            verbatim_quote=str(data.get("verbatim_quote", "")),
            section_anchor=str(data.get("section_anchor", "")),
            biological_context=BiologicalContext.from_dict(data.get("biological_context", {})),
        )


@dataclass(frozen=True)
class PortSpec:
    port_id: str
    quantity_type: str
    unit: str
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | str) -> "PortSpec":
        if isinstance(data, str):
            return cls(port_id=data, quantity_type="unspecified", unit="")
        return cls(
            port_id=str(data.get("port_id", "")),
            quantity_type=str(data.get("quantity_type", "unspecified")),
            unit=str(data.get("unit", "")),
            description=str(data.get("description", "")),
        )


@dataclass(frozen=True)
class MechanismRecord:
    mechanism_id: str
    name: str
    equation_summary: str
    input_ports: list[PortSpec]
    output_ports: list[PortSpec]
    paper_id: str
    compatible_contexts: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mechanism_id": self.mechanism_id,
            "name": self.name,
            "equation_summary": self.equation_summary,
            "input_ports": [p.to_dict() for p in self.input_ports],
            "output_ports": [p.to_dict() for p in self.output_ports],
            "paper_id": self.paper_id,
            "compatible_contexts": self.compatible_contexts,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MechanismRecord":
        return cls(
            mechanism_id=str(data["mechanism_id"]),
            name=str(data.get("name", "")),
            equation_summary=str(data.get("equation_summary", "")),
            input_ports=[PortSpec.from_dict(p) for p in data.get("input_ports", [])],
            output_ports=[PortSpec.from_dict(p) for p in data.get("output_ports", [])],
            paper_id=str(data.get("paper_id", "")),
            compatible_contexts=list(data.get("compatible_contexts", [])),
        )


class EvidenceTier:
    DIRECT = "DIRECT"
    ANALOGUE_BRIDGE = "ANALOGUE_BRIDGE"
    UNVERIFIED = "UNVERIFIED"


class CompatibilityEdgeTier:
    EXACT_MATCH = "EXACT_MATCH"
    ANALOGUE_BRIDGE = "ANALOGUE_BRIDGE"
    INCOMPATIBLE_CONSTRAINTS = "INCOMPATIBLE_CONSTRAINTS"
    UNVERIFIED = "UNVERIFIED"


def compute_confidence_score(
    edges: Sequence[CompatibilityEdge | Mapping[str, Any]] = (),
    parameters: Sequence[ParameterRecord | Mapping[str, Any]] = (),
) -> tuple[float, str, bool]:
    """Calculate Scientific Confidence Score (0-100) and determine primary tier."""
    for p in parameters:
        t = p.biological_context.evidence_tier if hasattr(p, 'biological_context') else p.get('biological_context', {}).get('evidence_tier', '')
        if t == EvidenceTier.UNVERIFIED:
            return 0.0, EvidenceTier.UNVERIFIED, False

    for e in edges:
        t = e.tier if hasattr(e, 'tier') else e.get('tier', '')
        if t in (EvidenceTier.UNVERIFIED, CompatibilityEdgeTier.INCOMPATIBLE_CONSTRAINTS):
            return 0.0, EvidenceTier.UNVERIFIED, False

    analogue_count = 0
    for e in edges:
        t = e.tier if hasattr(e, 'tier') else e.get('tier', '')
        if t == CompatibilityEdgeTier.ANALOGUE_BRIDGE:
            analogue_count += 1

    for p in parameters:
        t = p.biological_context.evidence_tier if hasattr(p, 'biological_context') else p.get('biological_context', {}).get('evidence_tier', '')
        if t == EvidenceTier.ANALOGUE_BRIDGE:
            analogue_count += 1

    if analogue_count == 0:
        return 100.0, EvidenceTier.DIRECT, False

    score = max(50.0, 100.0 - (15.0 * analogue_count))
    return score, EvidenceTier.ANALOGUE_BRIDGE, True



@dataclass(frozen=True)
class CompatibilityEdge:
    source_mechanism_id: str
    target_mechanism_id: str
    port_id: str
    quantity_type: str
    tier: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CentralLibraryStore:
    """In-memory cache and persistence manager for central_library.json."""

    def __init__(self, file_path: Path = CENTRAL_LIBRARY_PATH) -> None:
        self.file_path = file_path
        self._papers: dict[str, PaperRecord] = {}
        self._parameters: dict[str, ParameterRecord] = {}
        self._mechanisms: dict[str, MechanismRecord] = {}
        if self.file_path.is_file():
            self.load()

    def clear(self) -> None:
        self._papers.clear()
        self._parameters.clear()
        self._mechanisms.clear()

    def add_paper(self, paper: PaperRecord) -> None:
        self._papers[paper.paper_id] = paper

    def add_parameter(self, param: ParameterRecord) -> None:
        self._parameters[param.param_id] = param

    def add_mechanism(self, mech: MechanismRecord) -> None:
        self._mechanisms[mech.mechanism_id] = mech

    @property
    def papers(self) -> dict[str, PaperRecord]:
        return dict(self._papers)

    @property
    def parameters(self) -> dict[str, ParameterRecord]:
        return dict(self._parameters)

    @property
    def mechanisms(self) -> dict[str, MechanismRecord]:
        return dict(self._mechanisms)

    def save(self) -> None:
        os.makedirs(str(self.file_path.parent), exist_ok=True)
        payload = {
            "schema_version": "1.0.0",
            "papers": {k: p.to_dict() for k, p in sorted(self._papers.items())},
            "parameters": {k: p.to_dict() for k, p in sorted(self._parameters.items())},
            "mechanisms": {k: m.to_dict() for k, m in sorted(self._mechanisms.items())},
        }
        with open(str(self.file_path), "w", encoding="utf-8") as f:
            f.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    def load(self) -> None:
        if not self.file_path.is_file():
            return
        data = json.loads(self.file_path.read_text(encoding="utf-8"))
        self._papers = {k: PaperRecord.from_dict(v) for k, v in data.get("papers", {}).items()}
        self._parameters = {k: ParameterRecord.from_dict(v) for k, v in data.get("parameters", {}).items()}
        self._mechanisms = {k: MechanismRecord.from_dict(v) for k, v in data.get("mechanisms", {}).items()}

    def find_mechanisms_for_context(
        self,
        organism: str = "",
        mode: str = "",
        phenomenon: str = "",
    ) -> list[MechanismRecord]:
        results: list[MechanismRecord] = []
        org_norm = organism.lower().strip()
        mode_norm = mode.lower().strip()
        phenom_norm = phenomenon.lower().strip()

        for mech in self._mechanisms.values():
            match = True
            if org_norm:
                org_matched = any(
                    org_norm in str(ctx.get("organism", "")).lower()
                    for ctx in mech.compatible_contexts
                )
                if not org_matched:
                    match = False
            if match and mode_norm:
                mode_matched = any(
                    mode_norm in str(ctx.get("mode", "")).lower()
                    for ctx in mech.compatible_contexts
                )
                if not mode_matched:
                    match = False
            if match and phenom_norm:
                p_matched = (
                    phenom_norm in mech.name.lower()
                    or phenom_norm in mech.equation_summary.lower()
                    or any(phenom_norm in p.port_id.lower() for p in mech.output_ports)
                )
                if not p_matched:
                    match = False
            if match:
                results.append(mech)
        return results

    def find_parameters_for_context(
        self,
        organism: str = "",
        quantity_type: str = "",
        paper_id: str = "",
    ) -> list[ParameterRecord]:
        results: list[ParameterRecord] = []
        org_norm = organism.lower().strip()
        qty_norm = quantity_type.lower().strip()

        for param in self._parameters.values():
            if paper_id and param.paper_id != paper_id:
                continue
            if org_norm and org_norm not in param.biological_context.organism.lower():
                continue
            if qty_norm and qty_norm not in param.quantity_type.lower():
                continue
            results.append(param)
        return results

    def find_alternatives_for_port(
        self,
        port_id: str,
        quantity_type: str = "",
        exclude_mechanism_id: str = "",
    ) -> list[dict[str, Any]]:
        """Find other mechanisms in the library that produce or consume the same quantity."""
        alternatives: list[dict[str, Any]] = []
        p_norm = port_id.lower().replace("_", "")
        qty_norm = quantity_type.lower().strip()

        for mech in self._mechanisms.values():
            if mech.mechanism_id == exclude_mechanism_id:
                continue
            matched_port = None
            for p in mech.output_ports:
                if (qty_norm and p.quantity_type.lower() == qty_norm) or (
                    p.port_id.lower().replace("_", "") in p_norm or p_norm in p.port_id.lower().replace("_", "")
                ):
                    matched_port = p
                    break
            if matched_port:
                paper = self._papers.get(mech.paper_id)
                alternatives.append({
                    "mechanism_id": mech.mechanism_id,
                    "name": mech.name,
                    "port_id": matched_port.port_id,
                    "quantity_type": matched_port.quantity_type,
                    "paper_id": mech.paper_id,
                    "paper_title": paper.title if paper else "",
                    "doi": paper.doi if paper else "",
                    "equation_summary": mech.equation_summary,
                })
        return alternatives

    def compute_compatibility_edge(
        self,
        source_mech_id: str,
        target_mech_id: str,
        shared_port_id: str,
    ) -> CompatibilityEdge:
        """Assess compatibility edge between two mechanisms."""
        source = self._mechanisms.get(source_mech_id)
        target = self._mechanisms.get(target_mech_id)

        if not source or not target:
            return CompatibilityEdge(
                source_mechanism_id=source_mech_id,
                target_mechanism_id=target_mech_id,
                port_id=shared_port_id,
                quantity_type="unknown",
                tier=CompatibilityEdgeTier.INCOMPATIBLE_CONSTRAINTS,
                reason="One or both mechanisms not registered in central library.",
            )

        src_port = next((p for p in source.output_ports if p.port_id == shared_port_id), None)
        tgt_port = next((p for p in target.input_ports if p.port_id == shared_port_id), None)

        qty = src_port.quantity_type if src_port else (tgt_port.quantity_type if tgt_port else "unspecified")

        src_ctx = source.compatible_contexts[0] if source.compatible_contexts else {}
        tgt_ctx = target.compatible_contexts[0] if target.compatible_contexts else {}

        src_org = str(src_ctx.get("organism", "")).lower()
        tgt_org = str(tgt_ctx.get("organism", "")).lower()

        # Check organism conflict
        if src_org and tgt_org and src_org != tgt_org and (src_org not in tgt_org and tgt_org not in src_org):
            return CompatibilityEdge(
                source_mechanism_id=source_mech_id,
                target_mechanism_id=target_mech_id,
                port_id=shared_port_id,
                quantity_type=qty,
                tier=CompatibilityEdgeTier.INCOMPATIBLE_CONSTRAINTS,
                reason=f"Organism conflict: '{src_ctx.get('organism')}' vs '{tgt_ctx.get('organism')}'.",
            )

        # Check strain match
        src_strain = str(src_ctx.get("strain", "")).lower()
        tgt_strain = str(tgt_ctx.get("strain", "")).lower()
        strain_exact = (src_strain == tgt_strain) if (src_strain and tgt_strain) else False

        # Check temperature match
        src_temp = src_ctx.get("temperature_c")
        tgt_temp = tgt_ctx.get("temperature_c")
        temp_delta = abs(float(src_temp) - float(tgt_temp)) if (src_temp is not None and tgt_temp is not None) else 0.0

        if strain_exact and temp_delta <= 1.0:
            tier = CompatibilityEdgeTier.EXACT_MATCH
            reason = f"Exact biological context match: organism {src_ctx.get('organism')}, strain {src_ctx.get('strain')}."
        else:
            tier = CompatibilityEdgeTier.ANALOGUE_BRIDGE
            reasons = []
            if src_strain != tgt_strain and src_strain and tgt_strain:
                reasons.append(f"strain bridge ({src_ctx.get('strain')} -> {tgt_ctx.get('strain')})")
            if temp_delta > 1.0:
                reasons.append(f"temperature difference ({src_temp}C -> {tgt_temp}C)")
            reason = f"Analogue bridge across related contexts: {'; '.join(reasons) if reasons else 'compatible E. coli contexts'}."

        return CompatibilityEdge(
            source_mechanism_id=source_mech_id,
            target_mechanism_id=target_mech_id,
            port_id=shared_port_id,
            quantity_type=qty,
            tier=tier,
            reason=reason,
        )


_DEFAULT_STORE: CentralLibraryStore | None = None


def get_library_store() -> CentralLibraryStore:
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = CentralLibraryStore()
    return _DEFAULT_STORE
