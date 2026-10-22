"""Adapter interface between the composition engine and a scientific model.

An adapter's job is narrow: load the model, publish a :class:`ModelManifest`,
and turn one run into :class:`ModelOutput` values.  It is *not* allowed to do
science.  If an adapter needs a number the model did not produce, that is a
diagnostic, not a default.

Adapters talk to models over a JSON boundary in a subprocess, because both
models ship a top-level ``models`` package and cannot be imported into one
interpreter without colliding (see ``_workers/morris_worker.py``).
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..contracts import (
    ModelInput,
    ModelManifest,
    ModelOutput,
    PortDirection,
    PortRef,
    ProvenanceRequirement,
    TemporalBasis,
    ValueProvenance,
)
from ..diagnostics import DiagnosticCode, ModelDiagnostic, Origin, Severity

#: How long a worker may take before it is treated as a failure rather than a hang.
WORKER_TIMEOUT_SECONDS = 120


class AdapterError(RuntimeError):
    """The adapter could not talk to its model at all."""


@dataclass(frozen=True)
class WorkerResponse:
    ok: bool
    payload: dict[str, Any]
    exit_code: int
    stderr: str

    def error_diagnostic(
        self, instance_id: str, model_id: str, model_version: str
    ) -> ModelDiagnostic:
        detail = (
            self.payload.get("error")
            or self.payload.get("message")
            or "the model returned no explanation"
        )
        diagnostics = self.payload.get("diagnostics") or []
        extra = ""
        if diagnostics and isinstance(diagnostics[0], Mapping):
            extra = str(diagnostics[0].get("message", ""))
        return ModelDiagnostic(
            code=DiagnosticCode.EXECUTION_MODEL_FAILED,
            severity=Severity.ERROR,
            message=(
                f"{model_id} did not produce a result: {detail}"
                + (f" ({extra})" if extra and extra != detail else "")
                + ". The model was not silently skipped and no downstream "
                "instance received a value."
            ),
            where=("instance", instance_id),
            origin=Origin.EXECUTION,
            remediation=(
                "Read the worker traceback in the diagnostics view. This is a model "
                "or declaration failure, not a composition failure."
            ),
            model_id=model_id,
            model_version=model_version,
            detail={
                "exit_code": self.exit_code,
                "stderr": self.stderr[-4000:],
                "traceback": self.payload.get("traceback", ""),
            },
        )


#: Process-wide cache of worker responses, keyed by
#: ``(worker module, model root, canonical request)``.
#:
#: Both models are deterministic -- Morris's README states "the same system
#: always produces bit-identical results" and the Zielinski engine walks a fixed
#: topological order with pure functions -- so an identical request can only
#: produce an identical response.  Without this, every manifest lookup and every
#: example run would spawn a fresh interpreter, and a test suite that runs the
#: same graph forty times would take forty times as long for no new information.
#: It is a performance cache, not a memo of judgement: a failed call is cached
#: too, so a broken model does not turn into a hang.
_WORKER_CACHE: dict[tuple[str, str, str], "WorkerResponse"] = {}
# API clients can submit many distinct, validated operating configurations. Keep
# the deterministic-response cache useful without letting an unbounded request
# history retain trajectories for the lifetime of the hosted process.
WORKER_CACHE_MAX_ENTRIES = 16


def clear_worker_cache() -> None:
    """Drop every cached worker response. Used by the tests."""
    _WORKER_CACHE.clear()


class JsonWorker:
    """Runs ``python -m composition._workers.<name>`` against a model package."""

    def __init__(self, worker_module: str, model_root: Path) -> None:
        self.worker_module = worker_module
        self.model_root = Path(model_root)
        #: per-instance view of the process-wide cache
        self._cache: dict[str, WorkerResponse] = {}

    @property
    def available(self) -> bool:
        return (self.model_root / "pyproject.toml").is_file()

    @staticmethod
    def _child_env() -> dict[str, str]:
        """The worker's environment.

        The worker is invoked as ``python -m composition._workers.<name>`` with
        the *model* directory as its working directory, so the model package is
        importable through the cwd.  This package is not in that directory, so
        its parent is put on PYTHONPATH explicitly rather than relying on the
        caller's environment.
        """
        import os

        env = dict(os.environ)
        package_parent = str(Path(__file__).resolve().parents[2])
        existing = env.get("PYTHONPATH", "")
        parts = [p for p in existing.split(os.pathsep) if p]
        if package_parent not in parts:
            env["PYTHONPATH"] = os.pathsep.join([package_parent, *parts])
        return env

    def _key(self, request: Mapping[str, Any]) -> str:
        return json.dumps(request, sort_keys=True, separators=(",", ":"))

    def call(self, request: Mapping[str, Any]) -> WorkerResponse:
        key = self._key(request)
        global_key = (self.worker_module, str(self.model_root), key)
        if key in self._cache:
            return self._cache[key]
        if global_key in _WORKER_CACHE:
            response = _WORKER_CACHE[global_key]
            self._cache[key] = response
            return response
        response = self._call_uncached(request)
        self._cache[key] = response
        if len(_WORKER_CACHE) >= WORKER_CACHE_MAX_ENTRIES:
            _WORKER_CACHE.pop(next(iter(_WORKER_CACHE)))
        _WORKER_CACHE[global_key] = response
        return response

    def _call_uncached(self, request: Mapping[str, Any]) -> WorkerResponse:
        if not self.model_root.is_dir():
            return WorkerResponse(
                ok=False,
                payload={"error": f"model root {self.model_root} does not exist"},
                exit_code=127,
                stderr="",
            )
        argv = [
            sys.executable, "-m", self.worker_module,
            "--model-root", str(self.model_root),
        ]
        try:
            completed = subprocess.run(
                argv,
                input=json.dumps(request),
                capture_output=True,
                text=True,
                cwd=str(self.model_root),
                env=self._child_env(),
                timeout=WORKER_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return WorkerResponse(
                ok=False,
                payload={"error": (
                    f"the model did not respond within {WORKER_TIMEOUT_SECONDS}s"
                )},
                exit_code=124,
                stderr="",
            )
        except OSError as exc:
            return WorkerResponse(
                ok=False,
                payload={"error": f"could not start the model worker: {exc}"},
                exit_code=126,
                stderr="",
            )

        stdout = (completed.stdout or "").strip()
        if not stdout:
            return WorkerResponse(
                ok=False,
                payload={"error": (
                    "the model worker produced no output at all; treating that as a "
                    "failure rather than as an empty success"
                )},
                exit_code=completed.returncode,
                stderr=(completed.stderr or "")[-4000:],
            )
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            return WorkerResponse(
                ok=False,
                payload={"error": f"the model worker emitted malformed JSON: {exc}",
                         "stdout_head": stdout[:4000]},
                exit_code=completed.returncode,
                stderr=(completed.stderr or "")[-4000:],
            )
        return WorkerResponse(
            ok=bool(payload.get("ok")) and completed.returncode == 0,
            payload=payload,
            exit_code=completed.returncode,
            stderr=(completed.stderr or "")[-4000:],
        )


# --------------------------------------------------------------------------- #
# adapter protocol
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AdapterRun:
    """What one adapter produced for one instance."""

    outputs: tuple[ModelOutput, ...]
    diagnostics: tuple[ModelDiagnostic, ...] = ()
    residuals: tuple[Any, ...] = ()
    unresolved: tuple[Mapping[str, Any], ...] = ()
    summary: Mapping[str, Any] = field(default_factory=dict)


class ModelAdapter:
    """Base class. Subclasses implement :meth:`manifest` and :meth:`run`."""

    model_id: str = ""
    model_version: str = ""
    #: the port of a `ModelInstance` that carries this adapter's parameters
    parameters_key: str = "system"

    def __init__(self, worker: JsonWorker) -> None:
        self.worker = worker

    # -- manifest ------------------------------------------------------------

    def manifest(self, parameters: Mapping[str, Any]) -> tuple[ModelManifest | None,
                                                               list[ModelDiagnostic]]:
        raise NotImplementedError

    # -- run -----------------------------------------------------------------

    def run(
        self,
        instance_id: str,
        parameters: Mapping[str, Any],
        inputs: Mapping[str, ModelOutput],
        literal_inputs: Mapping[str, ModelInput],
    ) -> AdapterRun:
        raise NotImplementedError

    # -- shared helpers ------------------------------------------------------

    @staticmethod
    def _temporal_basis_for(quantity: str) -> TemporalBasis:
        if quantity in ("mass_flow", "amount_flow", "volume_flow"):
            return TemporalBasis.RATE
        if quantity in ("mass", "amount", "volume"):
            return TemporalBasis.INVENTORY
        if quantity in ("time",):
            return TemporalBasis.DURATION
        return TemporalBasis.NOT_APPLICABLE

    @staticmethod
    def _requirements_from_provenance(provenance: str) -> ProvenanceRequirement:
        if provenance in ("reported", "digitized"):
            return ProvenanceRequirement.CITED
        if provenance == "assumed":
            return ProvenanceRequirement.EXPLAINED
        return ProvenanceRequirement.NONE
