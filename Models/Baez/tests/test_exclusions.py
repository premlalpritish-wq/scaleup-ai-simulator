"""The exclusions, checked as absences.

Each item the specification forbids is asserted in two ways: there is no code
that implements it, and there is a recorded reason saying why not. An absence
that is merely undocumented is indistinguishable from an oversight.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import baez2014
from _baez_testkit import (
    PACKAGE_ROOT,
    RepositoryRootNotFound,
    composition_adapters_dir,
    find_repository_root,
)
from baez2014 import equations, manifest, observations, source

PACKAGE_DIR = Path(baez2014.__file__).resolve().parent

#: The specification's exclusions, in its order.
EXCLUSIONS = (
    "kinetics.growth_law",
    "kinetics.dissolved_oxygen_balance",
    "transfer.oxygen_uptake",
    "expression.gfp_kinetics",
    "calibration.fluorescence_to_gfp_mass",
    "data.digitised_trajectory",
    "coupling.other_models",
)

FORBIDDEN_IMPORTS = (
    "composition",
    "morris",
    "zielinski",
    "models",
    "schemas",
    "scaleup_ai",
)


# --------------------------------------------------------------------------- #
# no implementation of the excluded models
# --------------------------------------------------------------------------- #


def test_the_only_equation_is_the_printed_feed_equation() -> None:
    assert list(equations.EQUATIONS) == ["source_formula.exponential_feed_rate"]
    equation = equations.executable_equations()[0]
    assert equation.output_key == "feed_rate"
    assert equation.output_unit == "L/h"


def test_the_package_holds_only_its_declared_modules() -> None:
    present = sorted(p.stem for p in PACKAGE_DIR.glob("*.py") if p.stem != "__init__")
    assert present == [
        "__main__",
        "equations",
        "feed_rate",
        "manifest",
        "observations",
        "provenance",
        "source",
        "units",
    ]


def test_no_module_implements_the_excluded_models() -> None:
    """No module exists for kinetics, oxygen transfer, expression or coupling."""
    forbidden_stems = {
        "monod", "growth", "oxygen", "transfer", "kla", "expression", "gfp",
        "kinetics", "digitised", "digitized", "coupling", "adapter", "bridge",
    }
    for path in PACKAGE_DIR.glob("*.py"):
        assert path.stem not in forbidden_stems, path.name


@pytest.mark.parametrize("exclusion", EXCLUSIONS)
def test_every_exclusion_is_declared_with_a_reason(exclusion: str) -> None:
    missing = equations.MISSING_MODELS[exclusion]
    assert missing.label
    assert missing.why_needed
    assert missing.why_not_implemented
    assert missing.missing_inputs
    assert len(missing.missing_inputs) >= 2


def test_the_missing_models_are_exactly_the_seven_exclusions() -> None:
    assert tuple(equations.MISSING_MODELS) == EXCLUSIONS


def test_manifest_restates_the_exclusions_in_plain_language() -> None:
    assert len(manifest.EXCLUSIONS) == 7
    joined = " ".join(manifest.EXCLUSIONS).lower()
    for phrase in ("monod", "dissolved-oxygen", "oxygen-transfer", "gfp",
                   "fluorescence", "digitised", "coupling"):
        assert phrase in joined


def test_the_package_declares_exactly_the_functions_it_needs() -> None:
    """The whole function surface of the package, listed and no larger.

    A growth law, an oxygen-transfer model or a coupling adapter would have to
    appear here as a new function. Listing the surface is what makes "this is
    everything it can do" checkable instead of a claim.
    """
    names = set()
    for path in PACKAGE_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(node.name)
    assert names == {
        # source.py
        "citation_for", "reference", "footer_for", "paper_pages", "page_text",
        "normalise", "page_contains", "rebuild_paper_pages", "_loose",
        "repository_root", "pdf_candidates", "resolve_source_pdf",
        # units.py
        "unit", "dimension_of", "is_convertible", "convert", "require_dimension",
        "_reg",
        # provenance.py
        "reported", "derived", "unknown",
        # equations.py
        "_exponential_feed_rate", "_register", "equation", "executable_equations",
        # feed_rate.py
        "_p6", "_finite", "_resolve_units", "_in_unit", "feed_rate",
        # observations.py
        "_batch_mode", "growth_rate_observations", "fed_batch_endpoint",
        "experimental_conditions", "all_observations", "observations_as_dict",
        "quantity_for",
        # manifest.py
        "build_manifest",
        # __main__.py
        "_dump", "main",
    }


def test_no_dissolved_oxygen_equation_or_oxygen_balance() -> None:
    """Oxygen appears only as a reported condition, never as a variable."""
    equation_inputs = {
        i.key for i in equations.executable_equations()[0].inputs
    }
    assert not equation_inputs & {"dO2", "do2", "kla", "our", "otr", "oxygen"}


def test_fluorescence_is_never_converted_to_a_mass() -> None:
    from baez2014.units import is_convertible

    assert not is_convertible("FU", "mg/L")
    ratio = 109000.0 / 494.0
    haystack = "\n".join(
        p.read_text(encoding="utf-8") for p in PACKAGE_DIR.glob("*.py")
    )
    haystack += (PACKAGE_DIR / "data" / "paper_pages.json").read_text(encoding="utf-8")
    haystack += source.page_text(3)
    assert str(ratio)[:8] not in haystack
    assert "FU_per_mg" not in haystack and "fu_per_mg" not in haystack


def test_no_digitised_series_is_shipped() -> None:
    for path in (PACKAGE_DIR / "data").glob("*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        assert not isinstance(document, list), path.name
        assert set(document) == {"1", "2", "3", "4", "5", "6", "7"}, path.name
    for path in PACKAGE_DIR.glob("*.json"):
        assert "paper_pages" in path.name


# --------------------------------------------------------------------------- #
# no coupling to the other model packages
# --------------------------------------------------------------------------- #


def _imported_modules() -> set[str]:
    names: set[str] = set()
    for path in PACKAGE_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names.add(node.module)
    return names


def test_the_package_imports_nothing_from_the_other_models() -> None:
    for name in _imported_modules():
        assert name.split(".")[0] not in FORBIDDEN_IMPORTS, name


def test_the_package_has_no_third_party_runtime_dependency() -> None:
    """The only non-stdlib import is pypdf, inside the page-text rebuild."""
    import sys

    standard = set(sys.stdlib_module_names)
    third_party: set[tuple[str, str]] = set()
    for path in PACKAGE_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Import):
                        third_party |= {
                            (alias.name.split(".")[0], node.name)
                            for alias in inner.names
                            if alias.name.split(".")[0] not in standard
                        }
                    elif isinstance(inner, ast.ImportFrom) and inner.module:
                        if inner.module.split(".")[0] not in standard:
                            third_party.add((inner.module.split(".")[0], node.name))
    assert third_party == {("pypdf", "rebuild_paper_pages")}


def test_the_page_text_rebuild_is_never_called_by_the_package() -> None:
    """Regeneration is a developer step; nothing in a run reaches it.

    The rebuild is still tested -- in `tests/test_source_provenance.py`, which
    directs it at a temporary output so the tracked snapshot cannot be
    overwritten. What must stay true is that the package itself never calls
    it: a normal run reads the committed page text and nothing else.
    """
    callers = [
        path.name
        for path in PACKAGE_DIR.glob("*.py")
        if "rebuild_paper_pages(" in path.read_text(encoding="utf-8")
        and path.name != "source.py"
    ]
    assert callers == []


# --------------------------------------------------------------------------- #
# isolation from the composition layer
#
# These used to be guarded by `skipif`, behind a `parents[1]` path that broke
# when this package moved from `Baez/` to `Models/Baez/`: the guards resolved
# to `Models/`, found no composition layer there, and skipped. Two isolation
# checks that do not run are indistinguishable from two that pass, so the
# repository root is now discovered by structure and a missing layout is a
# failure with an actionable message, never a skip.
# --------------------------------------------------------------------------- #


def test_the_repository_root_is_discovered_structurally() -> None:
    root = find_repository_root()
    assert root.is_dir()
    assert (root / "Models").is_dir(), f"{root} has no Models/ directory"
    assert (root / "papers").is_dir(), f"{root} has no papers/ directory"
    assert (PACKAGE_ROOT == root / "Models" / "Baez"), (
        f"discovery returned {root}, which does not contain this package at "
        f"Models/Baez"
    )


def test_discovery_is_not_fixed_depth() -> None:
    """It finds the root from an arbitrary starting point, not from an index."""
    root = find_repository_root()
    from_deeper = find_repository_root(PACKAGE_DIR / "data")
    from_parent = find_repository_root(PACKAGE_ROOT)
    assert from_deeper == root
    assert from_parent == root


def test_discovery_fails_loudly_when_the_layout_is_absent(tmp_path) -> None:
    """A missing layout raises with an actionable message instead of skipping.

    The starting point has to be genuinely outside the repository: this
    suite's own `tmp_path` lives inside the package, and walking up from there
    *should* find the root.
    """
    outside = Path(tmp_path.anchor) / "baez-nonexistent-checkout" / "pkg" / "tests"
    with pytest.raises(RepositoryRootNotFound) as excinfo:
        find_repository_root(outside)
    message = str(excinfo.value)
    assert "could not locate the repository root" in message
    assert "composition/composition/adapters/__init__.py" in message
    assert str(outside) in message
    assert "isolation checks must inspect the real composition layer" in message


def test_the_isolation_guards_executed_rather_than_skipped() -> None:
    """The guards below must be real tests, not skipped stand-ins."""
    module = sys.modules[__name__]
    for name in (
        "test_the_composition_layer_does_not_register_this_package",
        "test_no_adapter_worker_was_added_for_this_model",
        "test_the_composition_registry_lists_only_the_pre_existing_models",
    ):
        marker = getattr(module, name)
        own = {
            m for m in getattr(marker, "pytestmark", []) if "skip" in str(m).lower()
        }
        assert not own, f"{name} carries a skip marker: {own}"


def test_the_composition_layer_does_not_register_this_package() -> None:
    """Nothing outside Models/Baez/ was changed to point at it."""
    adapters = composition_adapters_dir()
    assert adapters.is_dir(), f"composition adapters not found at {adapters}"
    text = (adapters / "__init__.py").read_text(encoding="utf-8").lower()
    assert "baez" not in text


def test_no_adapter_worker_was_added_for_this_model() -> None:
    adapters = composition_adapters_dir()
    workers = sorted(p.name for p in (adapters.parent / "_workers").glob("*_worker.py"))
    assert not any("baez" in name for name in workers)
    assert workers == ["morris_worker.py", "zielinski_worker.py"]


def test_the_composition_registry_lists_only_the_pre_existing_models() -> None:
    """The registry is built by discovery; this package must not appear in it."""
    result = subprocess.run(
        [sys.executable, "-m", "composition.registry"],
        cwd=find_repository_root() / "composition",
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    model_ids = re.findall(r'"model_id": "([^"]+)"', result.stdout)
    assert sorted(model_ids) == [
        "morris2011.material_balance",
        "zielinski2019.rhi_process",
    ], model_ids
    assert "baez" not in result.stdout.lower()


def test_the_manifest_says_registration_was_not_done() -> None:
    registration = manifest.build_manifest()["registration"]
    assert registration["registered_in_composition_registry"] is False
    assert "not guessed" in registration["reason"]


def test_observations_carry_no_predicted_quantity() -> None:
    for observation in observations.all_observations():
        assert observation.quantity.provenance.value == "reported"