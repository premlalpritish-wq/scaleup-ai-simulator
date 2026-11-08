"""Shared paths and repository discovery for the Baez test suite.

A uniquely named helper module, deliberately *not* called `conftest.py` and
deliberately not imported as one. Two problems this avoids, both found by
collecting this suite in the same pytest process as the sibling model suites:

  * every model package here has a `conftest.py`, so a test module doing
    `from conftest import ...` gets whichever one was imported first -- here it
    silently picked up `Models/Zielinski/tests/conftest.py`;
  * a helper named like any other package's helper can collide in pytest's
    prepend import mode, which keys test modules on their basename.

The underscore prefix keeps this out of pytest's default `test_*.py`
collection, and the `_baez_` prefix makes a collision with any other package's
helper impossible in practice.

Repository discovery is by structure, never by fixed depth. This package sits
at `<repo>/Models/Baez`, but a model must not encode the repository's layout:
hard-coded `parents[n]` arithmetic is precisely what silently disabled two
isolation tests when the package was relocated. `find_repository_root()` walks
upward and looks for the thing it actually needs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

#: .../Models/Baez
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
#: .../Models/Baez/baez2014
PACKAGE_DIR = PACKAGE_ROOT / "baez2014"
#: .../Models/Baez/tests
TESTS_DIR = Path(__file__).resolve().parent

DATA_DIR = PACKAGE_DIR / "data"
FIXTURE_PATH = PACKAGE_ROOT / "fixtures" / "feed_rate_fixtures.json"
MANIFEST_PATH = PACKAGE_ROOT / "manifest.json"
PAPER_PAGES_PATH = DATA_DIR / "paper_pages.json"

#: Make both directories importable, whichever order pytest reaches them in:
#: this helper must be findable before it can configure anything, and the
#: package must be findable once it is. pytest's prepend import mode inserts
#: the test file's own directory; doing it explicitly as well keeps the suite
#: runnable on its own and inside a combined collection.
for _path in (TESTS_DIR, PACKAGE_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


class RepositoryRootNotFound(RuntimeError):
    """The repository layout this suite needs could not be located.

    Deliberately raised instead of skipping. A skip here once hid two
    isolation guards that had stopped running because the path arithmetic was
    wrong -- a silent green that meant nothing was being checked.
    """

    def __init__(self, start: Path, searched: list[Path]) -> None:
        listing = "\n  ".join(str(p) for p in searched)
        super().__init__(
            "could not locate the repository root by walking up from "
            f"{start}.\nLooked for a directory containing both "
            "'composition/composition/adapters/__init__.py' and 'Models/'.\n"
            f"Searched:\n  {listing}\n"
            "Run the Baez suite from inside the repository checkout, or point "
            "these tests at a checkout. This failure is deliberate: the "
            "isolation checks must inspect the real composition layer rather "
            "than quietly skip."
        )
        self.start = start
        self.searched = tuple(searched)


def _looks_like_repository_root(candidate: Path) -> bool:
    return (
        (candidate / "composition" / "composition" / "adapters" / "__init__.py").is_file()
        and (candidate / "Models").is_dir()
    )


def find_repository_root(start: Path | None = None) -> Path:
    """Walk up from `start` until the repository layout is recognised.

    Structural, not depth-based: a candidate is the root when it holds the
    composition layer's adapter registration *and* the `Models/` directory.
    Raises `RepositoryRootNotFound` rather than returning `None`, so a caller
    cannot mistake "not found" for "found something else".
    """
    origin = (start or PACKAGE_ROOT).resolve()
    searched: list[Path] = []
    for candidate in origin.parents:
        searched.append(candidate)
        if _looks_like_repository_root(candidate):
            return candidate
    raise RepositoryRootNotFound(origin, searched)


def composition_adapters_dir(repository_root: Path | None = None) -> Path:
    """The adapter registration directory of the real composition layer."""
    root = repository_root or find_repository_root()
    return root / "composition" / "composition" / "adapters"


def load_fixture_document() -> dict:
    with FIXTURE_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_paper_pages() -> dict[int, str]:
    with PAPER_PAGES_PATH.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return {int(k): v for k, v in raw.items()}