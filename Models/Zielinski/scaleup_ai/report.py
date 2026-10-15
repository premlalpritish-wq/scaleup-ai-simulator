"""ScaleUp AI core: serialization of a graph and its runs to machine-readable form.

Produces three artifacts:

  <out>/graph.json          the process definition alone
  <out>/evidence_record.json  graph + evidence replay + predictive attempt
  <out>/quantities.csv      one row per quantity, flat, with full provenance
  <out>/run_summary.md      a short generated digest
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .engine import ExecutionEngine, ExecutionMode, RunResult
from .process import ProcessGraph
from .provenance import Provenance


def _default(obj: Any) -> Any:
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, (set, frozenset)):
        return sorted(obj)
    raise TypeError(f"cannot serialize {type(obj)!r}")


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, indent=2, default=_default, ensure_ascii=False)
        fh.write("\n")
    return path


@dataclass
class ModelBundle:
    """A graph, its engine, and both execution modes, captured once."""

    graph: ProcessGraph
    engine: ExecutionEngine
    replay: RunResult
    predictive: RunResult

    @classmethod
    def build(cls, engine: ExecutionEngine) -> "ModelBundle":
        graph = engine.graph
        return cls(
            graph=graph,
            engine=engine,
            replay=engine.run(mode=ExecutionMode.EVIDENCE_REPLAY),
            # Predictive mode runs with no inputs: it must fail closed.
            predictive=engine.run(mode=ExecutionMode.PREDICTIVE),
        )

    # ------------------------------------------------------------------ #
    def evidence_record(self) -> dict[str, Any]:
        from .equations import EQUATIONS, MISSING_MODELS

        return {
            "record_type": "scaleup_ai_evidence_record",
            "schema_version": 1,
            "source": {
                "id": self.graph.source_id,
                "citation": self.graph.description,
                "doi": self.graph.doi,
            },
            "graph": self.graph.to_dict(),
            "equation_registry": {k: v.to_dict() for k, v in EQUATIONS.items()},
            "declared_missing_models": {k: v.to_dict() for k, v in MISSING_MODELS.items()},
            "runs": {
                "evidence_replay": self.replay.to_dict(),
                "predictive": self.predictive.to_dict(),
            },
            "interpretation": {
                "evidence_replay_is_predictive": self.replay.summary.to_dict()[
                    "graph_is_predictive"
                ],
                "predictive_values_produced": self.predictive.summary.predicted_values,
                "statement": (
                    "Evidence replay reproduces the paper's reported observations and "
                    "evaluates only transparent accounting identities on top of them. "
                    "It produces no predictions: every computed value in that mode is "
                    "tagged basis='computed' and every reported value is tagged "
                    "basis='observed_reference'. A predictive run with no declared "
                    "inputs resolves nothing, by design."
                ),
            },
        }

    # ------------------------------------------------------------------ #
    def quantity_rows(self) -> list[dict[str, Any]]:
        """One flat row per declared quantity in the graph."""
        rows: list[dict[str, Any]] = []
        for location, qid, q in self.graph.iter_quantities():
            ev = q.evidence[0] if q.evidence else None
            rows.append(
                {
                    "location": location,
                    "quantity_id": qid,
                    "label": q.label,
                    "provenance": q.provenance.value,
                    "basis": q.basis.value,
                    "value": "" if q.value is None else repr(q.value),
                    "value_low": "" if q.value_range is None else repr(q.value_range[0]),
                    "value_high": "" if q.value_range is None else repr(q.value_range[1]),
                    "unit": q.unit or "",
                    "original_text": q.original_text or "",
                    "source_id": ev.source_id if ev else "",
                    "pdf_page": ev.pdf_page if ev else "",
                    "printed_page": ev.printed_page if ev else "",
                    "section": (ev.section or "") if ev else "",
                    "figure": (ev.figure or "") if ev else "",
                    "method": q.method or "",
                    "inputs": "; ".join(q.inputs),
                    "uncertainty": (
                        f"{q.uncertainty.lo:g}..{q.uncertainty.hi:g}"
                        if q.uncertainty
                        else ""
                    ),
                    "notes": q.notes,
                }
            )
        return rows

    def computed_rows(self) -> list[dict[str, Any]]:
        """One row per value the engine actually computed, with its trace."""
        rows: list[dict[str, Any]] = []
        for nr in self.replay.node_results:
            by_qid = {q.quantity_id: q for q in nr.computed}
            for tr in nr.traces:
                q = by_qid[tr.output_quantity_id]
                rows.append(
                    {
                        "node_id": nr.node_id,
                        "node_name": nr.name,
                        "quantity_id": q.quantity_id,
                        "value": repr(q.value),
                        "unit": q.unit,
                        "provenance": q.provenance.value,
                        "equation_id": tr.equation_id,
                        "statement": tr.statement,
                        "inputs": "; ".join(
                            f"{k}={v['ref']}={v['value_used']!r}{v['normalized_unit']}"
                            for k, v in tr.input_values.items()
                        ),
                        "notes": q.notes,
                    }
                )
        return rows


CSV_FIELDS = [
    "location", "quantity_id", "label", "provenance", "basis", "value",
    "value_low", "value_high", "unit", "original_text", "source_id",
    "pdf_page", "printed_page", "section", "figure", "method", "inputs",
    "uncertainty", "notes",
]

COMPUTED_FIELDS = [
    "node_id", "node_name", "quantity_id", "value", "unit", "provenance",
    "equation_id", "statement", "inputs", "notes",
]


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]], fields: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_all(bundle: ModelBundle, out_dir: Path) -> dict[str, Path]:
    record = bundle.evidence_record()

    out_dir.mkdir(parents=True, exist_ok=True)
    written = {
        "graph": write_json(out_dir / "graph.json", bundle.graph.to_dict()),
        "evidence_record": write_json(out_dir / "evidence_record.json", record),
        "quantities": _write_csv(
            out_dir / "quantities.csv", bundle.quantity_rows(), CSV_FIELDS
        ),
        "computed": _write_csv(
            out_dir / "computed.csv", bundle.computed_rows(), COMPUTED_FIELDS
        ),
        "summary_md": write_text(out_dir / "run_summary.md", render_summary(bundle)),
    }
    return written


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def render_summary(bundle: ModelBundle) -> str:
    g = bundle.graph
    r, p = bundle.replay.summary, bundle.predictive.summary
    lines: list[str] = []
    add = lines.append

    add(f"# {g.title}")
    add("")
    add(g.description)
    if g.doi:
        add(f"DOI: {g.doi}")
    add("")
    add("## Execution summary")
    add("")
    add("| metric | evidence replay | predictive (no inputs) |")
    add("|---|---:|---:|")
    for key in (
        "nodes_executed", "nodes_partial", "nodes_observed_only", "nodes_unresolved",
        "observed_reference_values", "digitized_values", "computed_values",
        "predicted_values", "unknown_values", "unresolved_targets",
        "validation_errors", "validation_warnings",
    ):
        add(f"| {key} | {getattr(r, key)} | {getattr(p, key)} |")
    add(f"| **graph_is_predictive** | **{r.to_dict()['graph_is_predictive']}** | "
        f"**{p.to_dict()['graph_is_predictive']}** |")
    add("")
    add("> A `true` here would mean the model predicted something from its own "
        "equations. Evidence replay reports `false` by construction: it only "
        "restates observations and applies transparent accounting identities.")
    add("")

    add("## Computed values (evidence replay)")
    add("")
    add("| node | quantity | value | equation |")
    add("|---|---|---|---|")
    for row in bundle.computed_rows():
        add(f"| {row['node_id']} | `{row['quantity_id']}` | "
            f"{float(row['value']):.6g} {row['unit']} | `{row['equation_id']}` |")
    add("")

    add("## Cross-checks")
    add("")
    for m in bundle.replay.cross_checks:
        add(f"- **{m.severity.value}** `{m.code}` — {m.message}")
    add("")

    add("## Declared validation messages")
    add("")
    for node in g.topological_order():
        for msg in node.validation_messages:
            add(f"- **{msg.severity.value}** `{msg.code}` ({node.node_id}) — {msg.message}")
    add("")

    add("## Unresolved targets")
    add("")
    for u in bundle.replay.unresolved:
        add(f"- `{u.target}` — {u.reason}")
        if u.missing_equations:
            add(f"  - missing equation: {', '.join(u.missing_equations)}")
    add("")

    counts: dict[Provenance, int] = {}
    for _, _, q in g.iter_quantities():
        counts[q.provenance] = counts.get(q.provenance, 0) + 1
    add("## Provenance census (declared quantities)")
    add("")
    add("| provenance | count |")
    add("|---|---:|")
    for prov in Provenance:
        add(f"| {prov.value} | {counts.get(prov, 0)} |")
    add("")
    return "\n".join(lines)