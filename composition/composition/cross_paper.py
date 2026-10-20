"""Cross-paper scientific context for one registered model.

The Zielinski 3D replay shows one published batch. This module answers a
different question a reader of that replay will ask: what else has this
project already ingested, what does it share with that batch, and what does the
compatibility engine say about composing it with them?

Everything below is assembled from records the project already keeps:

* :mod:`composition.registry` -- who is registered and what each model
  declares about itself: title, source paper, DOI, ports, capabilities,
  assumptions, required conditions;
* :mod:`composition.cross_model` -- the authoritative compatibility position:
  every ordered pair of registered models, its stance, its evidence, what is
  unresolved, and what would have to exist before a connection could be made
  honestly;
* :mod:`composition.evidence.catalogue` -- the assessed candidate-evidence
  records for the Zielinski model's declared gaps, when the focus model is
  the one that catalogue was built for.

Nothing here is a rule of its own. The compatibility verdicts are read from
``cross_model`` and never restated or re-derived; the model descriptions are
read from the registry and the models' own manifests and never invented. A
model whose metadata is missing is reported as missing, carrying the
registry's own reason.

## What this module does not do

It does not propose a connection. It does not convert a refusal into a
suggestion that the models are interchangeable, and it does not present a
permitted same-model boundary as a connection between different papers. The
replay this feeds declares no connections; that fact is checked on disk and
stated in the payload (``replay_scope``) rather than assumed, and every
related model record carries ``connection_in_replay: false`` unless a
connection in the focus graph actually names it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from .adapters import adapter_for, repository_root
from . import cross_model
from .dimensions import (
    GANJAVE_KIND_TO_QUANTITY,
    MORRIS_KIND_TO_QUANTITY,
    ZIELINSKI_DIMENSION_TO_QUANTITY,
)
from .registry import audit_references, build_registry
from .registry.schema import RegisteredModel

#: Each model's declared kind vocabulary, for the quantity-overlap check where
#: a model publishes no model-level port set (Morris). These are the project's
#: own declared vocabularies, kept as data in ``dimensions.py`` -- never inferred
#: from a unit.
_KIND_VOCABULARIES: dict[str, dict[str, Any]] = {
    "morris2011.material_balance": MORRIS_KIND_TO_QUANTITY,
    "ganjave": GANJAVE_KIND_TO_QUANTITY,
    "zielinski2019.rhi_process": ZIELINSKI_DIMENSION_TO_QUANTITY,
}


def _quantity_name(quantity: Any) -> str:
    """A quantity's contract name, whether it arrives as an enum or a string."""
    if quantity is None:
        return ""
    value = getattr(quantity, "value", quantity)
    return str(value)

#: Exit codes, matching `composition.runner`.
EXIT_OK = 0
EXIT_BAD_INPUT = 3

#: Where every sentence in the payload came from. Stated once, up front, so a
#: reader does not have to guess which claims are the engine's and which are
#: this module's assembly.
SOURCES = (
    "composition.registry.builder.build_registry -- model identity, titles, "
    "source papers, DOIs, ports, capabilities, assumptions, as declared by "
    "each model and tracked with its provenance",
    "the models' own manifests -- summary, capabilities, unsupported "
    "capabilities, assumptions",
    "composition.cross_model.describe -- the authoritative compatibility "
    "position for every ordered pair of registered models",
    "composition.evidence.catalogue -- assessed candidate-evidence records "
    "for the Zielinski model's declared gaps (focus model only)",
)

#: The replay graph the 3D replay scene executes. Its connection count is read
#: from disk so the panel's claim about the replay is checked, not assumed.
REPLAY_GRAPH_PATH = "composition/replay/zielinski_replay.json"


def _diagnostic(code: str, message: str, remediation: str) -> dict[str, str]:
    return {
        "code": code,
        "severity": "error",
        "message": message,
        "where": ("runner", "--describe-cross-paper-context"),
        "origin": "runner",
        "remediation": remediation,
    }


def _diagnostic_dict(diagnostic: Any) -> dict[str, Any]:
    """One manifest diagnostic as data, in the shape the contract uses.

    A diagnostic that carries its own ``to_dict`` uses it; anything else is
    reduced to its message rather than rendered as a Python repr, which a
    reader of the JSON could not act on.
    """
    if isinstance(diagnostic, Mapping):
        return dict(diagnostic)
    to_dict = getattr(diagnostic, "to_dict", None)
    if callable(to_dict):
        return dict(to_dict())
    return {"message": str(diagnostic)}


def _catalogue_model_id() -> str:
    """The registered model the curated evidence catalogue assesses.

    Imported lazily so this module stays importable in a repository where the
    evidence catalogue is absent, and so the catalogue is attached only to
    the model it was actually built against.
    """
    from .evidence.catalogue import REGISTERED_MODEL_ID

    return REGISTERED_MODEL_ID


def _field_text(field: Any) -> str:
    """A tracked field's value, or an explicit statement that it is absent.

    An unknown field is never rendered as an empty string: that would read as
    "the model has no title" rather than "the project does not know it".
    """
    if field is None:
        return ""
    if not field.is_known:
        return "not declared (%s)" % str(field.basis)
    return str(field.value)


# --------------------------------------------------------------------------- #
# model descriptions
# --------------------------------------------------------------------------- #


def _manifest_for(model_id: str, base: Path | None = None
                  ) -> tuple[Any, list[Any]]:
    """The model's own manifest, or `(None, diagnostics)` with its reason.

    A model that declines to publish a manifest without instance parameters
    is not a failure: `None` is returned with the adapter's own diagnostics,
    exactly as the registry builder treats it.
    """
    adapter, load_diagnostics = adapter_for(model_id, base)
    if adapter is None:
        return None, list(load_diagnostics)
    try:
        manifest, manifest_diagnostics = adapter.manifest({})
    except Exception as exc:                                # noqa: BLE001
        manifest, manifest_diagnostics = None, [
            _diagnostic(
                "manifest.invalid",
                "%s raised %s when asked for its manifest: %s. No port set was "
                "inferred from the failure." % (model_id, type(exc).__name__, exc),
                "Read the traceback in the runner output. This is a model or "
                "adapter failure, not a missing declaration.",
            )
        ]
    return manifest, list(manifest_diagnostics)


def _join(items: Sequence[str]) -> str:
    cleaned = [str(i).strip() for i in items if str(i).strip()]
    return "; ".join(cleaned)


def _evidence_key(model_id: str) -> str:
    """Which of the compatibility module's evidence blocks describes a model."""
    if "morris" in model_id:
        return "morris"
    if "ganjave" in model_id:
        return "ganjave"
    if "zielinski" in model_id:
        return "zielinski"
    return ""


def _what_it_addresses(model_id: str, manifest: Any,
                       registry_model: RegisteredModel | None) -> dict[str, Any]:
    """What process or scientific question the model addresses, in its own words.

    Every clause is read from a record the project keeps: the model's manifest
    summary, its declared title, its declared capabilities, or -- when the
    model publishes no model-level description -- the compatibility module's
    cited evidence about it. When nothing at all is declared, that is stated,
    with the registry's own reason, rather than replaced by a phrase this
    module composed.
    """
    if manifest is not None:
        summary = str(getattr(manifest, "summary", "") or "").strip()
        title = str(getattr(manifest, "title", "") or "").strip()
        capabilities = [str(c) for c in
                        (getattr(manifest, "capabilities", None) or [])]
        if summary:
            text = summary
        elif title:
            text = title
        elif capabilities:
            text = _join(capabilities)
        else:
            text = ""
        if text:
            return {"text": text, "origin": "the model's own manifest"}

    if registry_model is not None and registry_model.title.is_known:
        return {
            "text": str(registry_model.title.value),
            "origin": "the model's own manifest, via the registry",
        }

    # No model-level description exists. Say so, and lend the compatibility
    # module's cited evidence rather than a phrase of this module's own.
    basis = str(registry_model.title.basis) if registry_model is not None else ""
    evidence = cross_model.EVIDENCE.get(_evidence_key(model_id))
    if evidence:
        return {
            "text": (
                "No model-level title or summary is declared%s. The "
                "composition layer's declared evidence describes it as: %s"
                % (" (" + basis + ")" if basis else "", evidence[0])
            ),
            "origin": "composition.cross_model's cited evidence for this model",
        }
    return {
        "text": "Not declared%s." % (": " + basis if basis else ""),
        "origin": "nothing in the project describes this model beyond its identity",
    }


def _port_surface(model_id: str, manifest: Any,
                  registry_model: RegisteredModel | None) -> dict[str, Any]:
    """The quantities and port counts the model publishes, as declared."""
    if manifest is not None:
        ports = list(getattr(manifest, "ports", None) or [])
        quantities: dict[str, set[str]] = {}
        for port in ports:
            quantities.setdefault(_quantity_name(port.quantity), set()).add(
                str(port.unit or "")
            )
        return {
            "port_dependence": "fixed",
            "port_counts": {
                "input": sum(
                    1 for p in ports if str(getattr(p.direction, "value", p.direction))
                    == "input"
                ),
                "output": sum(
                    1 for p in ports if str(getattr(p.direction, "value", p.direction))
                    == "output"
                ),
            },
            "published_quantities": sorted(quantities),
            "units_by_quantity": {q: sorted(u) for q, u in sorted(quantities.items())},
        }
    dependence = (
        str(registry_model.port_dependence.value) if registry_model is not None
        and registry_model.port_dependence is not None else ""
    )
    out: dict[str, Any] = {
        "port_dependence": dependence or "unknown",
        "port_counts": (
            dict(registry_model.port_counts) if registry_model is not None
            else {"input": 0, "output": 0}
        ),
        "published_quantities": [],
        "units_by_quantity": {},
    }
    if dependence == "instance":
        out["note"] = (
            "the manifest requires an instance declaration, so no model-level "
            "port set is fixed; its quantities are declared per instance"
        )
    return out


def _capabilities(manifest: Any, registry_model: RegisteredModel | None
                  ) -> dict[str, Any]:
    """What the model says it can do and cannot do, in its own words."""
    if manifest is not None:
        unsupported = getattr(manifest, "unsupported_capabilities", None) or {}
        return {
            "capabilities": [str(c) for c in
                             (getattr(manifest, "capabilities", None) or [])],
            "unsupported_capabilities": {str(k): str(v) for k, v in unsupported.items()},
        }
    if registry_model is not None and registry_model.capabilities.is_known:
        return {
            "capabilities": [str(c) for c in registry_model.capabilities.value],
            "unsupported_capabilities": {},
        }
    return {"capabilities": [], "unsupported_capabilities": {}}


# --------------------------------------------------------------------------- #
# compatibility, read from the authoritative module
# --------------------------------------------------------------------------- #


def _boundary_map(connections: Mapping[str, Any]) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for boundary in connections.get("boundaries", []):
        out[(str(boundary.get("source_model", "")),
             str(boundary.get("target_model", "")))] = boundary
    return out


def _quantity_overlap(source_id: str, source_surface: Mapping[str, Any],
                     target_id: str, target_surface: Mapping[str, Any]
                     ) -> list[str]:
    """Quantities both models publish, from their declared vocabularies.

    This is the mechanical half of "what they have in common": a connection
    between these two models would be dimensionally constructible for these
    quantities. It is a statement about the vocabularies only -- never a claim
    that the quantities mean the same thing in the two models.

    Where a model publishes no model-level port set (Morris), its declared
    kind vocabulary is used instead, and the source says so: an instance model's
    per-run ports are unknown here, so the overlap is a statement about what
    the model *can* publish, not what one instance did.
    """
    source_quantities = set(source_surface.get("published_quantities", []))
    if not source_quantities and source_id in _KIND_VOCABULARIES:
        source_quantities = {
            _quantity_name(q) for q in _KIND_VOCABULARIES[source_id].values()
        }
    target_quantities = set(target_surface.get("published_quantities", []))
    if not target_quantities and target_id in _KIND_VOCABULARIES:
        target_quantities = {
            _quantity_name(q) for q in _KIND_VOCABULARIES[target_id].values()
        }
    return sorted(source_quantities & target_quantities)


def _assessment(boundary: Mapping[str, Any], overlap: Sequence[str]
                ) -> tuple[str, str]:
    """Split one boundary's declared reason into shared context and difference.

    The shared context is only what a record states: the overlap clause the
    reason itself opens with (for the biological pairs), plus the computed
    quantity overlap. The fundamental difference is the remainder of the
    engine's own reason, never a paraphrase of this module's.
    """
    stance = str(boundary.get("stance", ""))
    reason = str(boundary.get("reason", ""))
    dimensional = str(boundary.get("dimensional_note", ""))

    if stance == "no_shared_quantity":
        shared = (
            "None. %s" % dimensional if dimensional else
            "The two models publish no quantity in common, so no connection "
            "between them is mechanically constructible."
        )
        difference = reason
        return shared, difference

    shared_parts: list[str] = []
    reason_shared = ""
    if stance.startswith("permitted"):
        # The whole reason is the premise of a permitted boundary; nothing
        # stands between the two instances, so there is no difference to show.
        shared_parts.append(reason)
    else:
        # The biological refusals open with an explicit common-ground
        # statement -- "Both models describe...", "The two cultures share...".
        # Only a sentence that actually says the two have something in common
        # is treated as shared context; a reason that opens with the refusal
        # itself ("Zielinski publishes process roles...") has none, and says so.
        first_sentence = reason.split(". ")[0].strip().rstrip(",")
        # "... fed-batch culture, and neither quantity ..." keeps the gap in
        # the "shared" clause; a common-ground statement ends at the ", and ".
        if ", and " in first_sentence:
            first_sentence = first_sentence.split(", and ")[0].strip()
        if "both " in first_sentence.lower() or "share" in first_sentence.lower():
            reason_shared = first_sentence
            shared_parts.append(first_sentence)
    difference = reason
    if reason_shared:
        remainder = reason[len(reason_shared):].lstrip(" ,.")
        # "..., and neither quantity nor unit is what stands between them"
        # leaves a leading "and " on the remainder; drop it so the
        # difference reads as a sentence, not a conjunction.
        if remainder.lower().startswith("and "):
            remainder = remainder[4:]
        if remainder:
            difference = remainder[0].upper() + remainder[1:]
    if overlap:
        shared_parts.append(
            "Both publish %s, so a connection between them would be "
            "mechanically constructible for these quantities; the refusal is "
            "semantic, not dimensional."
            % ", ".join(overlap)
        )
    shared = " ".join(p.strip() for p in shared_parts if p.strip())
    if not shared:
        shared = "None stated by the compatibility engine; see the difference below."
    return shared, difference.strip()


def _pair_verdicts(source_model: str, target_model: str,
                   boundary: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """The authoritative standing of each quantity pair the policy names.

    The per-pair reasons live in ``cross_model``'s table; they are read here
    through ``cross_model.check`` so the rules themselves are never duplicated.
    Pairs the rules do not name are not silently dropped: ``check`` fails them
    closed with ``evidence_limited``, which is the engine's own answer for an
    unclassified pair -- an absence of a judgement, not evidence of physical
    incompatibility.
    """
    if boundary is None:
        return []
    out: list[dict[str, Any]] = []
    for pair in boundary.get("quantity_pairs", []):
        source_q, target_q = str(pair[0]), str(pair[1])
        verdict = cross_model.check(
            source_model, "port", source_q,
            target_model, "port", target_q,
        )
        if verdict is None:
            # The engine's own mechanical rules already own this boundary
            # (CG-08/CG-09); cross_model records the position and deliberately
            # emits no second diagnostic. Say so rather than inventing one.
            out.append({
                "source_quantity": source_q,
                "target_quantity": target_q,
                "verdict": "engine_refused",
                "permitted": False,
                "meaning": (
                    "The engine's own mechanical rules already refuse every "
                    "connection this boundary could carry; the compatibility "
                    "module records the position without a duplicate diagnostic."
                ),
                "evidence": [str(e) for e in boundary.get("evidence", [])],
                "unresolved": [],
                "what_would_resolve": "",
                "connection_in_replay": False,
            })
            continue
        out.append({
            "source_quantity": source_q,
            "target_quantity": target_q,
            "verdict": verdict.stance,
            "permitted": verdict.permitted,
            "meaning": verdict.reason,
            "evidence": [str(e) for e in verdict.evidence],
            "unresolved": [str(u) for u in verdict.unresolved],
            "what_would_resolve": verdict.remediation,
            "connection_in_replay": False,
        })
    return out


def _compatibility_section(source_model: str, target_model: str,
                           boundary: Mapping[str, Any] | None,
                           overlap: Sequence[str]) -> dict[str, Any]:
    """One direction of the relationship, as the engine declared it."""
    if boundary is None:
        return {
            "declared": False,
            "direction": "%s -> %s" % (source_model, target_model),
            "stance": "undeclared",
            "permitted": False,
            "reason": (
                "No boundary is declared for this ordered pair. An undeclared "
                "pair is not permitted: it has simply not been assessed."
            ),
            "shared_context": "",
            "fundamental_difference": "",
            "evidence": [],
            "unresolved": [],
            "remediation": "",
            "assumptions": [],
            "enforced_by_engine": False,
            "quantity_pairs": [],
            "connection_in_replay": False,
        }
    shared, difference = _assessment(boundary, overlap)
    return {
        "declared": True,
        "direction": "%s -> %s" % (source_model, target_model),
        "stance": str(boundary.get("stance", "")),
        "permitted": bool(boundary.get("permitted", False)),
        "reason": str(boundary.get("reason", "")),
        "shared_context": shared,
        "fundamental_difference": difference,
        "evidence": [str(e) for e in boundary.get("evidence", [])],
        "unresolved": [str(u) for u in boundary.get("unresolved", [])],
        "remediation": str(boundary.get("remediation", "")),
        "assumptions": [str(a) for a in boundary.get("assumptions", [])],
        "enforced_by_engine": bool(boundary.get("enforced_by_engine", False)),
        "dimensional_note": str(boundary.get("dimensional_note", "")),
        "quantity_pairs": _pair_verdicts(source_model, target_model, boundary),
        "connection_in_replay": False,
    }


# --------------------------------------------------------------------------- #
# the evidence catalogue, for the model it was built against
# --------------------------------------------------------------------------- #


def _focus_gaps() -> list[dict[str, Any]]:
    """What the focus model itself declares it cannot resolve."""
    from .evidence.catalogue import TARGETS

    out: list[dict[str, Any]] = []
    for port_id, info in TARGETS.items():
        out.append({
            "parameter_id": str(info.get("missing_parameter", "")),
            "label": str(info.get("label", "")),
            "port_id": port_id,
            "why_it_matters": str(info.get("why_it_matters", "")),
            "blocks": [str(b) for b in (info.get("blocks", []) or [])],
        })
    return out


def _examined_papers() -> list[dict[str, Any]]:
    """Ingested papers examined against the focus model's gaps.

    These are papers, not models: each carries a citation, the quantity it
    was examined for, the extracted value with its unit, the assessment
    verdict, and its independence from the target publication. They are
    included as context for the focus model's gaps only; none of them is
    connected to it, and none is presented as a registered model.
    """
    from .evidence.catalogue import FINDINGS

    out: list[dict[str, Any]] = []
    for f in FINDINGS:
        assessment = f.assess()
        out.append({
            "finding_id": f.finding_id,
            "citation": f.source.citation,
            "doi": f.source.doi,
            "locator": f.source.locator(),
            "quote": f.source.quote,
            "quantity_label": f.quantity_label,
            "value": f.value,
            "unit": f.unit,
            "target_parameter": f.target_missing_parameter,
            "verdict": assessment.verdict.value,
            "independence": assessment.independence.value,
            "does_not_resolve": [str(d) for d in f.does_not_resolve],
        })
    return out


# --------------------------------------------------------------------------- #
# the payload
# --------------------------------------------------------------------------- #


def context_for(reference: str, base: Path | None = None
                ) -> tuple[dict[str, Any], int]:
    """Assemble the cross-paper context for one registered model.

    Returns ``(payload, exit_code)`` following ``describe_model``'s contract:
    an unresolvable reference exits 3 and names the references that would
    resolve; no model is substituted.
    """
    models, issues = build_registry(base)
    raw = (reference or "").strip()
    model_id, _, version = raw.partition("@")
    model_id = model_id.strip()
    version = version.strip()

    payload: dict[str, Any] = {
        "contract_version": "0.1.0",
        "report_version": "1.0.0",
        "requested": raw,
        "sources": list(SOURCES),
        "replay_scope": _replay_scope(base),
    }

    resolved = audit_references(model_id, models, version)
    if not resolved.is_known:
        diagnostics = [
            _diagnostic(
                "runner.bad_input",
                str(resolved.basis),
                "Pass one of: %s." % ", ".join(
                    sorted(m.reference for m in models.values())
                ),
            )
        ]
        diagnostics.extend(
            _diagnostic("runner.bad_input", str(i.detail), "Fix the registration.")
            for i in issues
        )
        payload.update({
            "resolved": False,
            "focus_model": None,
            "focus_reference": None,
            "focus": None,
            "related_models": [],
            "focus_gaps": [],
            "examined_papers": [],
            "diagnostics": diagnostics,
            "registered_references": sorted(m.reference for m in models.values()),
        })
        return payload, EXIT_BAD_INPUT

    focus = models[model_id]
    connections = cross_model.describe()
    boundaries = _boundary_map(connections)

    focus_manifest, _focus_diags = _manifest_for(model_id, base)
    focus_surface = _port_surface(model_id, focus_manifest, focus)

    related: list[dict[str, Any]] = []
    for other_id in sorted(models):
        if other_id == model_id:
            continue
        other = models[other_id]
        manifest, manifest_diagnostics = _manifest_for(other_id, base)
        other_surface = _port_surface(other_id, manifest, other)
        overlap = _quantity_overlap(
            other_id, other_surface, model_id, focus_surface
        )
        related.append({
            "model_id": other_id,
            "reference": other.reference,
            "title": _field_text(other.title) if other.title.is_known else "",
            "title_origin": other.title.origin.value,
            "source_paper": _field_text(other.source_paper),
            "doi": _field_text(other.doi),
            "scientific_status": dict(other.scientific_status),
            "what_it_addresses": _what_it_addresses(other_id, manifest, other),
            "port_surface": other_surface,
            "capabilities_block": _capabilities(manifest, other),
            "compatibility_towards_focus": _compatibility_section(
                other_id, model_id, boundaries.get((other_id, model_id)), overlap
            ),
            "compatibility_from_focus": _compatibility_section(
                model_id, other_id, boundaries.get((model_id, other_id)), overlap
            ),
            "manifest_diagnostics": [
                _diagnostic_dict(d) for d in manifest_diagnostics
            ],
        })

    catalogue_focus = model_id == _catalogue_model_id()
    payload.update({
        "resolved": True,
        "focus_model": model_id,
        "focus_reference": focus.reference,
        "focus": {
            "model_id": model_id,
            "reference": focus.reference,
            "title": _field_text(focus.title) if focus.title.is_known else "",
            "title_origin": focus.title.origin.value,
            "source_paper": _field_text(focus.source_paper),
            "doi": _field_text(focus.doi),
            "scientific_status": dict(focus.scientific_status),
            "what_it_addresses": _what_it_addresses(model_id, focus_manifest, focus),
            "port_surface": focus_surface,
            "capabilities_block": _capabilities(focus_manifest, focus),
            "declared_gaps": _focus_gaps() if catalogue_focus else [],
        },
        "related_models": related,
        "connections": connections,
        "examined_papers": _examined_papers() if catalogue_focus else [],
        "examined_papers_scope": (
            "candidate evidence assessed against this model's declared gaps; "
            "these are papers, not registered models, and none is connected "
            "to this replay"
            if catalogue_focus else
            "the curated evidence catalogue is built for %s, not for this "
            "model; no papers are examined here" % _catalogue_model_id()
        ),
        "validation_status": (
            "This is an assembly of the project's own registry, compatibility "
            "and evidence records. It is not a scientific validation of any "
            "model, and producing it does not upgrade any model's "
            "reproduction_status."
        ),
    })
    return payload, EXIT_OK


def _replay_scope(base: Path | None) -> dict[str, Any]:
    """What this panel may and may not claim about the replay it feeds.

    Read from the replay graph on disk where it can be found, so the statement
    is checked rather than assumed. The graph declares no connections; the
    panel therefore presents every related model as context, never as a
    driver of the replay trajectory.
    """
    root = base if base is not None else repository_root()
    graph_path = root / REPLAY_GRAPH_PATH
    connections: Any = []
    graph_id = ""
    readable = False
    if graph_path.is_file():
        try:
            document = json.loads(graph_path.read_text(encoding="utf-8"))
            connections = document.get("connections", []) or []
            graph_id = str(document.get("graph_id", ""))
            readable = True
        except (OSError, json.JSONDecodeError):
            connections = []
    return {
        "replay_graph": REPLAY_GRAPH_PATH,
        "graph_id": graph_id,
        "connection_count": len(connections) if readable else "unreadable",
        "is_composition": bool(readable and connections),
        "statement": (
            "This replay is a single-model evidence replay. It declares no "
            "connections, so no other model drives, corrects or extends any "
            "number on screen; every related model shown alongside it is "
            "scientific context, read from the project's own records."
        ),
    }


# --------------------------------------------------------------------------- #
# CLI entry
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    """Emit the cross-paper context for one model as JSON.

    Takes the same ``--result <path>`` contract as ``composition.evidence``,
    so the Godot side reads it from disk exactly as it reads a model result
    and the evidence catalogue, rather than capturing a subprocess's stdout.
    """
    parser = argparse.ArgumentParser(
        prog="python -m composition.cross_paper",
        description=(
            "Report the cross-paper scientific context for one registered "
            "model: the other registered models, what they share, and what the "
            "compatibility engine says about composing them."
        ),
    )
    parser.add_argument("model", help="model id or <model_id>@<version>")
    parser.add_argument("--result", help="path to write the context JSON")
    args = parser.parse_args(argv)

    payload, code = context_for(args.model)
    text = json.dumps(payload, indent=2, default=str) + "\n"
    if args.result:
        path = Path(args.result)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        json.dump(
            {
                "context_file": str(path),
                "focus_model": payload.get("focus_model"),
                "related_models": len(payload.get("related_models", [])),
                "examined_papers": len(payload.get("examined_papers", [])),
                "exit_code": code,
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
    else:
        sys.stdout.write(text)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
