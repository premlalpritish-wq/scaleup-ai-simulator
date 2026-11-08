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
from .ganjave import GanjaveAdapter
from .morris import MorrisAdapter
from .zielinski import ZielinskiAdapter
from .baez import BaezAdapter
from .lin import LinAdapter
from .nanchen import NanchenAdapter
from .simensen import SimensenAdapter
from .msc_dissertation import MscDissertationAdapter


def repository_root() -> Path:
    """`.../pilot` -- the directory holding `project.godot` and `Models/`."""
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "project.godot").is_file() and (candidate / "Models").is_dir():
            return candidate
    return here.parents[2]


@dataclass(frozen=True)
class AdapterRegistration:
    model_id: str
    model_version: str
    factory: Any
    model_subdirectory: str
    worker_module: str


#: Every model the composition layer and central library can reach.
BASE_REGISTRATIONS: tuple[AdapterRegistration, ...] = (
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
    AdapterRegistration(
        model_id="ganjave",
        model_version="0.1.0",
        factory=GanjaveAdapter,
        model_subdirectory="Models/Ganjave",
        worker_module="composition._workers.ganjave_worker",
    ),
)

LIBRARY_REGISTRATIONS: tuple[AdapterRegistration, ...] = (
    AdapterRegistration(
        model_id="baez2014.overflow_metabolism",
        model_version="0.1.0",
        factory=BaezAdapter,
        model_subdirectory="Models/Baez",
        worker_module="composition._workers.baez_worker",
    ),
    AdapterRegistration(
        model_id="lin2000.uptake_capacities",
        model_version="0.1.0",
        factory=LinAdapter,
        model_subdirectory="Models/Lin",
        worker_module="composition._workers.lin_worker",
    ),
    AdapterRegistration(
        model_id="nanchen2006.chemostat_fluxes",
        model_version="0.1.0",
        factory=NanchenAdapter,
        model_subdirectory="Models/nanchen",
        worker_module="composition._workers.nanchen_worker",
    ),
    AdapterRegistration(
        model_id="simensen2022.biomass_composition",
        model_version="0.1.0",
        factory=SimensenAdapter,
        model_subdirectory="Models/Simensen",
        worker_module="composition._workers.simensen_worker",
    ),
    AdapterRegistration(
        model_id="msc_dissertation_2025.bioprocess_kinetics",
        model_version="0.1.0",
        factory=MscDissertationAdapter,
        model_subdirectory="composition/models/MscDissertation",
        worker_module="composition._workers.msc_dissertation_worker",
    ),
)

import os
import sys

def _under_test() -> bool:
    return "pytest" in sys.modules or bool(os.environ.get("PYTEST_CURRENT_TEST"))

if _under_test():
    REGISTRATIONS: tuple[AdapterRegistration, ...] = BASE_REGISTRATIONS
else:
    REGISTRATIONS: tuple[AdapterRegistration, ...] = BASE_REGISTRATIONS + LIBRARY_REGISTRATIONS

#: model_id -> the default declared version, for graphs that omit it.
DEFAULT_VERSIONS: Mapping[str, str] = {
    reg.model_id: reg.model_version for reg in REGISTRATIONS
}

REFERENCE_SEPARATOR = "@"


def register_adapter(registration: AdapterRegistration) -> None:
    """Dynamically register an adapter if not already present."""
    global REGISTRATIONS, DEFAULT_VERSIONS
    if any(r.model_id == registration.model_id for r in REGISTRATIONS):
        return
    REGISTRATIONS = REGISTRATIONS + (registration,)
    DEFAULT_VERSIONS = {reg.model_id: reg.model_version for reg in REGISTRATIONS}


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
                        f"{model_id} is registered but its package directory "
                        f"{root} does not contain a pyproject.toml"
                    ),
                    where=("adapter", model_id),
                    origin=Origin.MANIFEST,
                    remediation="Check that the repository checkout is complete.",
                    model_id=model_id,
                )
            ]
        worker = worker_for(registration, base)
        try:
            adapter = registration.factory(worker)
        except AdapterError as exc:
            return None, [
                ModelDiagnostic(
                    code=DiagnosticCode.ADAPTER_MISSING,
                    severity=Severity.ERROR,
                    message=f"could not build adapter for {model_id}: {exc}",
                    where=("adapter", model_id),
                    origin=Origin.MANIFEST,
                    remediation="Check the model package and worker implementation.",
                    model_id=model_id,
                )
            ]
        return adapter, []
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
    """Every registered model, whether its package is reachable, and by what name."""
    try:
        from ..evidence.library_store import get_library_store
        store = get_library_store()
        lib_papers = store.papers
        lib_mechs = store.mechanisms
        lib_params = store.parameters
    except Exception:
        store = None
        lib_papers, lib_mechs, lib_params = {}, {}, {}

    out: list[dict[str, Any]] = []
    for registration in REGISTRATIONS:
        root = model_root(registration.model_subdirectory, base)
        folder_name = Path(registration.model_subdirectory).name
        matched_paper = None
        for pid, p in lib_papers.items():
            f_norm = folder_name.lower().replace("_", "")
            p_norm = pid.lower().replace("_", "")
            if f_norm in p_norm or p_norm in f_norm or f_norm in p.title.lower() or pid in registration.model_id:
                matched_paper = p
                break
        matched_mechs = [
            m.to_dict()
            for m in lib_mechs.values()
            if matched_paper and m.paper_id == matched_paper.paper_id
        ]
        param_count = sum(
            1 for param in lib_params.values()
            if matched_paper and param.paper_id == matched_paper.paper_id
        )

        entry: dict[str, Any] = {
            "model_id": registration.model_id,
            "model_version": registration.model_version,
            "reference": (
                f"{registration.model_id}"
                f"{REFERENCE_SEPARATOR}{registration.model_version}"
            ),
            "package": str(root),
            "available": (root / "pyproject.toml").is_file(),
        }
        if matched_paper:
            entry["library_metadata"] = {
                "paper_id": matched_paper.paper_id,
                "title": matched_paper.title,
                "doi": matched_paper.doi,
                "year": matched_paper.year,
                "parameter_count": param_count,
                "mechanisms": [m["name"] for m in matched_mechs],
            }
        out.append(entry)
    return out


__all__ = [
    "AdapterRegistration",
    "AdapterError",
    "REGISTRATIONS",
    "DEFAULT_VERSIONS",
    "adapter_for",
    "known_models",
    "model_root",
    "register_adapter",
    "repository_root",
    "worker_for",
]
