"""Deterministic registration.

Registration is a pure function of what is on disk. Given the same repository
it produces the same registry, byte for byte, and it never writes to a model
package -- it hashes files, it does not touch them.

Discovery follows the artefacts the repository already establishes: the adapter
registrations in :mod:`composition.adapters`, and the manifests those adapters
publish. No model is described here that the composition layer cannot already
reach, and nothing about a model is written by hand.

A model whose manifest cannot be built without instance parameters is still
registered, but its port set is recorded as instance-parameterised and its
model-level ports are left explicitly unknown. That is the difference between a
model that declares no ports and a model whose ports are not fixed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..adapters import (
    REGISTRATIONS,
    AdapterRegistration,
    model_root,
    repository_root,
    worker_for,
)
from ..contracts import PortDirection
from .schema import (
    ArtefactDigest,
    DeclaredCondition,
    IssueKind,
    Origin,
    PortDependence,
    PortRecord,
    RegisteredModel,
    RegistrationIssue,
    TrackedField,
    collect_unknowns,
    declared,
    derived,
    summarise_variables,
    unknown,
)

#: Exactly what the package digest covers. Stated once here and repeated on
#: every digest so no reader has to infer scope.
DIGEST_COVERAGE = (
    "SHA-256 over the exact bytes of every .py file under the model package "
    "root, excluding test modules, caches and generated output. The package "
    "digest is SHA-256 over the sorted '<relative-path>:<file-digest>' lines "
    "of that same set. Neither digest covers data fixtures, example graphs, "
    "the adapter that wraps the model, or any execution result."
)

FILE_COVERAGE = "SHA-256 over the exact bytes of this file, unmodified."

#: Directories and name fragments excluded from the digest set.
_EXCLUDE_DIRS = ("tests", "__pycache__", "out", ".artifacts", ".git")
_EXCLUDE_STEMS = ("conftest",)


def _included(root: Path) -> list[Path]:
    files = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if any(part in _EXCLUDE_DIRS for part in rel.parts[:-1]):
            continue
        if rel.stem in _EXCLUDE_STEMS:
            continue
        files.append(path)
    return files


def digest_file(path: Path, base: Path) -> ArtefactDigest:
    data = path.read_bytes()
    return ArtefactDigest(
        path=path.relative_to(base).as_posix(),
        algorithm="sha256",
        digest=hashlib.sha256(data).hexdigest(),
        byte_length=len(data),
        covers=FILE_COVERAGE,
    )


def digest_package(root: Path, base: Path) -> tuple[tuple[ArtefactDigest, ...], TrackedField]:
    files = _included(root)
    if not files:
        return (), unknown("no .py files found under %s" % root)
    artefacts = tuple(digest_file(p, base) for p in files)
    lines = sorted("%s:%s" % (a.path, a.digest) for a in artefacts)
    combined = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    return artefacts, derived(
        combined,
        "SHA-256 over the sorted '<path>:<digest>' lines of %d included files. %s"
        % (len(artefacts), DIGEST_COVERAGE),
    )


def _port_records(manifest: Any) -> tuple[PortRecord, ...]:
    out = []
    for p in manifest.ports:
        meta = p.metadata if isinstance(p.metadata, Mapping) else {}
        out.append(PortRecord(
            port_id=p.port_id,
            direction=p.direction.value,
            quantity=str(p.quantity),
            unit=p.unit or "",
            required=bool(p.required),
            role=str(meta.get("role", "")),
            location=str(meta.get("location", "")),
        ))
    return tuple(sorted(out, key=lambda r: r.port_id))


def _declared_conditions(manifest: Any) -> tuple[DeclaredCondition, ...]:
    """What the model itself says it needs in order to be able to do its job."""
    sections = manifest.parameter_sections or {}
    items = sections.get("declared missing models") or []
    out = []
    for item in items:
        data = item if isinstance(item, Mapping) else {}
        out.append(DeclaredCondition(
            condition_id=str(data.get("model_id", "")),
            label=str(data.get("label", "")),
            why_needed=str(data.get("why_needed", "")),
            why_not_implemented=str(data.get("why_not_implemented", "")),
            missing_inputs=tuple(data.get("missing_inputs", ()) or ()),
        ))
    return tuple(sorted(out, key=lambda c: c.condition_id))


def register_one(
    registration: AdapterRegistration,
    base: Path | None = None,
) -> tuple[RegisteredModel | None, list[RegistrationIssue]]:
    """Register one model from its established artefacts."""
    base = base or repository_root()
    root = model_root(registration.model_subdirectory, base)
    issues: list[RegistrationIssue] = []

    package_present = (root / "pyproject.toml").is_file()
    if not package_present:
        issues.append(RegistrationIssue(
            IssueKind.MISSING_ARTEFACT, registration.model_id,
            "no model package at %s; registration is recorded as failed rather "
            "than substituted from elsewhere." % root,
        ))
        return None, issues

    artefacts, package_digest = digest_package(root, base)

    # The manifest is what the model declares about itself. Ask for it with no
    # instance parameters; a model that refuses is instance-parameterised.
    try:
        adapter = registration.factory(worker_for(registration, base))
        manifest, diags = adapter.manifest({})
    except Exception as exc:                                  # noqa: BLE001
        manifest, diags = None, [exc]

    basis = "composition.adapters: the model declares this in its own manifest"

    if manifest is None:
        reason = _manifest_refusal(diags)
        dependence = PortDependence.INSTANCE
        ports: tuple[PortRecord, ...] = ()
        counts = {"input": 0, "output": 0}
        variables = unknown("the manifest requires an instance 'system' declaration")
        units = unknown("no model-level port set is fixed")
        title_f = unknown("the title is declared per instance, not per model")
        conditions: tuple[DeclaredCondition, ...] = ()
        assumptions = unknown("declared per instance")
        capabilities = unknown("declared per instance")
    else:
        dependence = PortDependence.FIXED
        ports = _port_records(manifest)
        counts = {
            "input": sum(1 for p in ports if p.direction == PortDirection.INPUT.value),
            "output": sum(1 for p in ports if p.direction == PortDirection.OUTPUT.value),
        }
        variables = declared(summarise_variables(ports), basis)
        units = derived(
            sorted({p.unit for p in ports if p.unit}),
            "units declared on the model's own ports; a port with no unit is "
            "recorded with an empty unit rather than an assumed one",
        )
        title_f = declared(manifest.title, basis)
        conditions = _declared_conditions(manifest)
        assumptions = declared(len(manifest.assumptions), basis)
        capabilities = declared(list(manifest.capabilities), basis)

    source_paper = _source_paper(manifest)
    doi = _doi(manifest)

    model = RegisteredModel(
        model_id=registration.model_id,
        model_version=registration.model_version,
        title=title_f,
        source_paper=source_paper,
        doi=doi,
        specification_path=declared(
            registration.model_subdirectory, basis),
        artefact_digests=artefacts,
        package_digest=package_digest,
        ports=ports,
        port_dependence=dependence,
        port_counts=counts,
        variables=variables,
        units=units,
        required_conditions=conditions,
        assumptions=assumptions,
        capabilities=capabilities,
        adapter=declared(registration.worker_module, "composition.adapters"),
    )
    # Unknowns are derived from the finished record, not tracked by hand, so a
    # field cannot be reported known when it was never populated.
    model = RegisteredModel(**{**model.__dict__, "unknown_fields": collect_unknowns(model)})
    return model, issues


def _manifest_refusal(diags: Sequence[Any]) -> str:
    for d in diags:
        message = getattr(d, "message", None) or str(d)
        return str(message)
    return "the model declined to publish a manifest without instance parameters"


def _source_paper(manifest: Any) -> TrackedField:
    if manifest is None:
        return unknown(
            "declared per instance; the model's own citation is not exposed in a "
            "manifest that requires instance parameters"
        )
    ref = (manifest.source_ref or "").strip()
    if not ref:
        return unknown("the manifest declares no source reference")
    return declared(ref, "composition.adapters: the model's own source_ref")


def _doi(manifest: Any) -> TrackedField:
    if manifest is None:
        return unknown(
            "no model-level manifest exposes a DOI, and none is inferred from "
            "the author, title or repository"
        )
    doi = (manifest.parameters or {}).get("doi")
    if not doi:
        return unknown(
            "the artefact declares no DOI. No DOI is inferred from the author "
            "or title."
        )
    return declared(str(doi), "composition.adapters: the model's own doi parameter")


# --------------------------------------------------------------------------- #
# The registry
# --------------------------------------------------------------------------- #


def build_registry(base: Path | None = None) -> tuple[dict[str, RegisteredModel],
                                                       list[RegistrationIssue]]:
    """Register every model the composition layer can reach, then audit it."""
    base = base or repository_root()
    models: dict[str, RegisteredModel] = {}
    issues: list[RegistrationIssue] = []

    for registration in REGISTRATIONS:
        model, model_issues = register_one(registration, base)
        issues.extend(model_issues)
        if model is None:
            continue
        if model.model_id in models:
            issues.append(RegistrationIssue(
                IssueKind.DUPLICATE_ID, model.model_id,
                "registered more than once; the registry keeps the first and "
                "does not merge or choose.",
            ))
            continue
        models[model.model_id] = model

    issues.extend(_audit_versions(models))
    return models, issues


def _audit_versions(models: Mapping[str, RegisteredModel]) -> list[RegistrationIssue]:
    issues: list[RegistrationIssue] = []
    declared: dict[str, set[str]] = {}
    for registration in REGISTRATIONS:
        declared.setdefault(registration.model_id, set()).add(
            registration.model_version)
    for model_id, versions in sorted(declared.items()):
        if len(versions) > 1:
            issues.append(RegistrationIssue(
                IssueKind.AMBIGUOUS_VERSION, model_id,
                "declared at more than one version (%s). A bare model_id does "
                "not resolve to one model; use %s@<version>."
                % (sorted(versions), model_id),
            ))
    for model in models.values():
        if not model.model_version:
            issues.append(RegistrationIssue(
                IssueKind.AMBIGUOUS_VERSION, model.model_id,
                "registered with no version; its reference is not unambiguous.",
            ))
    return issues


def audit_references(model_id: str, models: Mapping[str, RegisteredModel],
                     version: str = "") -> TrackedField:
    """Resolve a reference to a registered model, or say precisely why not.

    Used by compatibility reports: an unregistered or ambiguous reference must
    not be able to carry a definitive verdict.
    """
    if model_id not in models:
        return unknown(
            "model_id %r is not in the registry (registered: %s). No verdict "
            "may rest on it." % (model_id, sorted(models))
        )
    model = models[model_id]
    if version and version != model.model_version:
        return unknown(
            "%s@%s is not registered; the registry holds %s@%s. The reference "
            "is ambiguous." % (model_id, version, model_id, model.model_version)
        )
    if not model.model_version:
        return unknown("model %s has no unambiguous version" % model_id)
    return declared(model.reference, "composition.registry")


def check_references(references: Mapping[str, str],
                     models: Mapping[str, RegisteredModel]) -> list[RegistrationIssue]:
    """Report every reference that does not resolve to a registered model."""
    issues = []
    for subject, model_id in sorted(references.items()):
        field = audit_references(model_id, models)
        if field.origin is Origin.UNKNOWN:
            issues.append(RegistrationIssue(
                IssueKind.UNREGISTERED_REFERENCE, subject,
                "%s (referenced model_id %r)" % (field.basis, model_id),
            ))
    return issues