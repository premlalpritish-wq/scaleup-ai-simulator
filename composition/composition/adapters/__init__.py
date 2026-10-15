"""Adapter registry.

Resolves a ``model_id`` to an adapter and locates the model package it wraps.
Paths are discovered relative to the repository root so the Godot editor and the
test suite resolve them identically.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..diagnostics import DiagnosticCode, ModelDiagnostic, Origin, Severity
from .base import AdapterError, JsonWorker, ModelAdapter
from .morris import MorrisAdapter
from .zielinski import ZielinskiAdapter


def repository_root() -> Path:
    """`.../pilot` -- the directory holding `project.godot` and `Models/`."""
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "project.godot").is_file() and (candidate / "Models").is_dir():
            return candidate
    # fall back to composition/.. , which is the layout the package expects
    return here.parents[2]


@dataclass(frozen=True)
class AdapterRegistration:
    model_id: str
    model_version: str
    factory: Any
    model_subdirectory: str
    worker_module: str


#: Every model the composition layer can currently reach.  Adding a model means
#: adding a row here plus a worker; nothing else in the engine changes.
REGISTRATIONS: tuple[AdapterRegistration, ...] = (
    AdapterRegistration(
        model_id="morris2011.material_balance",
        model_version="0.1.0",
        factory=MorrisAdapter,
        model_subdirectory="Models/Morris",
        worker_module="composition._workers.morris_worker",
    ),
    AdapterRegistration(
        model_id="zielinski2019.rhi_process",
        model_version="1.0.0",
        factory=ZielinskiAdapter,
        model_subdirectory="Models/Zielinski",
        worker_module="composition._workers.zielinski_worker",
    ),
)

#: model_id -> the default declared version, for graphs that omit it.
DEFAULT_VERSIONS: Mapping[str, str] = {
    reg.model_id: reg.model_version for reg in REGISTRATIONS
}


def model_root(model_subdirectory: str, base: Path | None = None) -> Path:
    return (base or repository_root()) / model_subdirectory


def worker_for(registration: AdapterRegistration, base: Path | None = None) -> JsonWorker:
    return JsonWorker(
        registration.worker_module,
        model_root(registration.model_subdirectory, base),
    )


def adapter_for(
    model_id: str, base: Path | None = None
) -> tuple[ModelAdapter | None, list[ModelDiagnostic]]:
    """Build the adapter for `model_id`, or explain precisely why there is none."""
    for registration in REGISTRATIONS:
        if registration.model_id != model_id:
            continue
        root = model_root(registration.model_subdirectory, base)
        if not (root / "pyproject.toml").is_file():
            return None, [
                ModelDiagnostic(
                    code=DiagnosticCode.ADAPTER_MISSING,
                    severity=Severity.ERROR,
                    message=(
                        f"the {model_id} package was not found at {root}. The "
                        f"composition layer did not substitute another model."
                    ),
                    where=("adapter", model_id),
                    origin=Origin.MANIFEST,
                    remediation=(
                        f"Restore {registration.model_subdirectory} or point the "
                        f"runner at a different repository root."
                    ),
                    model_id=model_id,
                    model_version=registration.model_version,
                )
            ]
        return registration.factory(worker_for(registration, base)), []
    known = sorted(reg.model_id for reg in REGISTRATIONS)
    return None, [
        ModelDiagnostic(
            code=DiagnosticCode.ADAPTER_MISSING,
            severity=Severity.ERROR,
            message=(
                f"no adapter is registered for {model_id!r}. Available: {known}. "
                f"The composition layer never guesses which model was meant."
            ),
            where=("adapter", model_id),
            origin=Origin.MANIFEST,
            remediation="Register an adapter, or use one of the listed model ids.",
            model_id=model_id,
        )
    ]


def known_models(base: Path | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for registration in REGISTRATIONS:
        root = model_root(registration.model_subdirectory, base)
        out.append({
            "model_id": registration.model_id,
            "model_version": registration.model_version,
            "package": str(root),
            "available": (root / "pyproject.toml").is_file(),
        })
    return out


__all__ = [
    "AdapterRegistration",
    "AdapterError",
    "REGISTRATIONS",
    "DEFAULT_VERSIONS",
    "adapter_for",
    "known_models",
    "model_root",
    "repository_root",
    "worker_for",
]