"""Shared fixtures for the API tests.

`tmp_path` is avoided deliberately: on this host pytest's system temporary
directory is not writable, which would turn a working test into an environment
error. Scratch space goes inside the repository's ignored `.artifacts/` instead.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRATCH_ROOT = ROOT / "composition" / ".artifacts" / "api-tests"


@pytest.fixture
def scratch() -> Path:
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(dir=SCRATCH_ROOT))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
