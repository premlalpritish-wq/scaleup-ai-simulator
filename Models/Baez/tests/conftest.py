"""Shared fixtures.

Paths and repository discovery live in `_baez_testkit`, imported here by name.
Both this file and the test modules used to reach into a generic `conftest`
module, which only worked because no sibling suite happened to be imported
first; with the Morris and Zielinski suites in the same pytest process that
silently resolved to *their* conftest. `_baez_testkit` is uniquely named and
inserts both this directory and the package directory onto `sys.path`, so the
Baez suite runs on its own and inside a combined collection.

This directory does still contain a `conftest.py`, because that is how pytest
distributes fixtures. It defines no paths that a test module should import.
"""

from __future__ import annotations

import pytest

import _baez_testkit
from _baez_testkit import PACKAGE_ROOT, load_fixture_document

from baez2014 import observations

#: Scratch space for the suite, inside the package rather than in the host's
#: temp directory -- the same reasoning the composition suite documents: a run
#: must not depend on the system temp directory being writable or removable.
#: Gitignored via `Models/Baez/.gitignore`.
ARTIFACTS_DIR = PACKAGE_ROOT / ".artifacts"


def pytest_configure(config: pytest.Config) -> None:
    """Pin pytest's basetemp inside the package.

    Without this, `tmp_path` fails outright on a host whose system temp
    directory cannot be written, which is this one. An explicit `--basetemp`
    on the command line still wins.
    """
    if config.getoption("basetemp", None) is None:
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = str(ARTIFACTS_DIR / "basetemp")


@pytest.fixture(scope="session")
def fixture_document() -> dict:
    return load_fixture_document()


@pytest.fixture(scope="session")
def fixture_cases(fixture_document: dict) -> dict:
    return {case["id"]: case for case in fixture_document["cases"]}


@pytest.fixture(scope="session")
def growth_rates() -> tuple:
    return observations.growth_rate_observations()


@pytest.fixture(scope="session")
def endpoint() -> tuple:
    return observations.fed_batch_endpoint()