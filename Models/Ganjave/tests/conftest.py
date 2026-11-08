"""Shared fixtures for the Ganjave model test suite.

The fixed state used by the hand-calculation tests is chosen so that every
intermediate value can be written out by hand:

    X = 2.0 g/L, S1 = 4.0 g/L, S2 = 10.0 g/L, DO = 50 %, V = 0.1 L,
    e1 = 0.30, e2 = 0.60

The parameter set is the Table 2 one, unmodified. Nothing here re-derives a
paper value; the tests that check arithmetic do it from the printed numbers.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: Scratch space for the suite, inside the package rather than in the host's
#: temp directory -- the same reasoning the composition suite documents.
ARTIFACTS_DIR = ROOT / ".artifacts"


def pytest_configure(config: pytest.Config) -> None:
    """Pin pytest's basetemp inside the package.

    `tmp_path` fails outright on a host whose system temp directory cannot be
    written. An explicit `--basetemp` on the command line still wins.
    """
    if config.getoption("basetemp", None) is None:
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = str(ARTIFACTS_DIR / "basetemp")


from schemas.parameters import table2_parameter_set  # noqa: E402
from schemas.state import State  # noqa: E402
from models.initial import build_initial_conditions  # noqa: E402


@pytest.fixture(scope="session")
def parameters():
    return table2_parameter_set()


@pytest.fixture()
def fixed_state() -> State:
    """The state every hand-calculated derivative test starts from."""
    return State(t=0.0, X=2.0, S1=4.0, S2=10.0, DO=50.0, e1=0.30, e2=0.60, V=0.1)


@pytest.fixture()
def batch_conditions():
    """Resolved batch initial conditions, from the paper where it states them."""
    return build_initial_conditions(X=0.05, S2=5.0, DO=100.0, mode="batch")


@pytest.fixture()
def fed_batch_conditions():
    return build_initial_conditions(X=0.05, S2=5.0, DO=100.0, mode="fed_batch")