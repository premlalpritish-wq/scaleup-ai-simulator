"""Shared fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.zielinski_2019 import build_engine, build_graph  # noqa: E402
from scaleup_ai import ExecutionMode  # noqa: E402
from scaleup_ai.report import ModelBundle  # noqa: E402


@pytest.fixture(scope="session")
def graph():
    return build_graph()


@pytest.fixture(scope="session")
def engine():
    return build_engine()


@pytest.fixture(scope="session")
def replay(engine):
    return engine.run(mode=ExecutionMode.EVIDENCE_REPLAY)


@pytest.fixture(scope="session")
def bundle(engine):
    return ModelBundle.build(engine)