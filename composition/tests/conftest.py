"""Shared fixtures for the composition test suite.

Two rules govern this suite:

* it **never** modifies anything under ``Models/``.  The composition layer is
  import-only, and the two existing suites are run separately and reported
  separately (CG-15);
* it pins the two rejection examples against the *exact* diagnostic codes they
  are meant to produce, so a rule cannot be quietly relaxed until a graph
  starts validating.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    _orig_popen = subprocess.Popen

    def _safe_popen(*args, **kwargs):
        if "stdin" not in kwargs or kwargs["stdin"] is None:
            kwargs["stdin"] = subprocess.DEVNULL
        return _orig_popen(*args, **kwargs)

    subprocess.Popen = _safe_popen  # type: ignore

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMPOSITION_ROOT = ROOT / "composition"
if str(COMPOSITION_ROOT) not in sys.path:
    sys.path.insert(0, str(COMPOSITION_ROOT))

from composition.adapters import model_root  # noqa: E402
from composition.contracts import load_graph  # noqa: E402
from composition.engine import CompositionEngine  # noqa: E402
from composition.runner import run_graph  # noqa: E402

EXAMPLES = COMPOSITION_ROOT / "examples"

#: The documented behaviour of every shipped example.  A change to one of these
#: is a change to what the project claims, and must be deliberate.
EXAMPLE_EXPECTATIONS: dict[str, dict[str, object]] = {
    "brass_batch_chain.json": {"exit_code": 0, "min_errors": 0},
    "cycle_rejected.json": {"exit_code": 1, "min_errors": 1},
    "failure_propagation.json": {"exit_code": 2, "min_errors": 1},
    "ganjave_fed_batch.json": {"exit_code": 0, "min_errors": 0},
    "incomplete_required_input.json": {"exit_code": 2, "min_errors": 1},
    "rejected_au_to_mass.json": {"exit_code": 1, "min_errors": 1},
    "rejected_component_mapping.json": {"exit_code": 1, "min_errors": 1},
    "rejected_cross_model_insulin.json": {"exit_code": 1, "min_errors": 1},
    "rejected_mass_as_flow.json": {"exit_code": 1, "min_errors": 1},
}


@pytest.fixture(scope="session")
def repository_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def morris_root() -> Path:
    return model_root("Models/Morris", ROOT)


@pytest.fixture(scope="session")
def zielinski_root() -> Path:
    return model_root("Models/Zielinski", ROOT)


@pytest.fixture(scope="session")
def engine() -> CompositionEngine:
    return CompositionEngine(base_path=ROOT)


@pytest.fixture(scope="session")
def work_dir() -> Path:
    """A scratch directory inside the composition package.

    Used instead of pytest's ``tmp_path`` because this suite runs subprocesses
    that need a predictable, writable place to put files, and because the
    system temp directory is not always removable on every host.
    """
    path = COMPOSITION_ROOT / ".artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def model_suite_command() -> list[str]:
    """``pytest`` against one of the untouched model packages.

    ``-q`` is deliberately **not** passed: each package's ``pyproject.toml``
    already sets ``addopts = "-q"``, and a second ``-q`` makes pytest quiet
    enough to suppress the very summary line this reads.
    ``--basetemp`` is pinned inside the repository so the run does not depend on
    the host's system temp directory being writable.
    """
    return [
        sys.executable, "-m", "pytest", "tests",
        "-p", "no:cacheprovider",
        "--basetemp", str(COMPOSITION_ROOT / ".artifacts" / "model-basetemp"),
    ]


def run_model_suite(package: str) -> str:
    completed = subprocess.run(
        model_suite_command(),
        cwd=str(ROOT / package), capture_output=True, text=True, timeout=1800,
    )
    assert completed.returncode == 0, (
        f"{package} suite is not green:\n{completed.stdout[-4000:]}"
        f"\n{completed.stderr[-2000:]}"
    )
    line = [ln for ln in completed.stdout.splitlines() if "passed" in ln]
    assert line, completed.stdout[-2000:]
    return line[-1].strip()


@pytest.fixture(scope="session")
def example_names() -> list[str]:
    return sorted(EXAMPLE_EXPECTATIONS)


def read_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


#: Runs are memoised for the session. Both models are deterministic, so running
#: the same graph twice inside one test session produces the same bytes; doing it
#: forty times would only cost forty times the wall clock.
_RUN_MEMO: dict[str, dict] = {}
_CODE_MEMO: dict[str, int] = {}


def run_example(name: str) -> tuple[dict, int]:
    if name not in _RUN_MEMO:
        payload, code = run_graph(read_example(name), base=ROOT)
        _RUN_MEMO[name] = payload
        _CODE_MEMO[name] = code
    return _RUN_MEMO[name], _CODE_MEMO[name]


def example_result(name: str) -> dict:
    payload, _code = run_example(name)
    return payload


def error_codes(payload: dict) -> set[str]:
    return {
        d["code"] for d in payload["diagnostics"] if d["severity"] == "error"
    }


def all_codes(payload: dict) -> set[str]:
    return {d["code"] for d in payload["diagnostics"]}


@pytest.fixture(scope="session")
def brass_chain() -> dict:
    return example_result("brass_batch_chain.json")


@pytest.fixture(scope="session")
def brass_graph():
    return load_graph(read_example("brass_batch_chain.json"))


@pytest.fixture(scope="session")
def manifest_brass_charge(engine):
    graph = load_graph(read_example("brass_batch_chain.json"))
    loaded = engine.load(graph)
    return loaded["brass_charge"].manifest


@pytest.fixture(scope="session")
def manifest_zielinski(engine):
    graph = load_graph(read_example("brass_batch_chain.json"))
    loaded = engine.load(graph)
    return loaded["zielinski_rhi"].manifest


@pytest.fixture(scope="session")
def manifest_alloying(engine):
    graph = load_graph(read_example("brass_batch_chain.json"))
    loaded = engine.load(graph)
    return loaded["brass_alloying"].manifest


@pytest.fixture(scope="session")
def registry():
    from composition.quantities import REGISTRY

    return REGISTRY


def output_of(payload: dict, instance_id: str, port_id: str) -> dict:
    for result in payload["results"]:
        if result["instance_id"] != instance_id:
            continue
        for out in result["outputs"]:
            if out["ref"]["port_id"] == port_id:
                return out
    raise KeyError(f"{instance_id}/{port_id} produced no output")