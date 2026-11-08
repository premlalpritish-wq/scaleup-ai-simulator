"""Fixtures for the Lin et al. (2001) package's own test suite.

The package directory is put on `sys.path` here so the tests import `lin2000`
from the checkout rather than from an installed copy. Nothing else is defined:
the tests import what they need directly, so a fixture cannot hide a failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))
