"""Which papers have a standalone model, and what that model is.

``Models/`` holds a literature corpus. Some papers have an executable model and
some do not. :mod:`composition.evidence.papers` records *that* mapping (a
determination and a reason per paper); this module records the *models
themselves* -- which package implements a paper, what kind of thing it is, and
how its fidelity to the paper is checked.

**Standalone is not the same as composable.** Nothing here is registered with the
composition layer, nothing declares ports, and nothing is scored for
compatibility. A standalone model runs on its own, in the paper's own
experimental context, and stops there. ``composition.cross_model`` classifies
registered models; a standalone package has no position in it. The checks below
assert exactly that: every standalone package must be absent from the adapter
registry.

Two kinds of entry appear:

* ``equation_model`` -- the paper prints a quantitative model (equations the
  package evaluates);
* ``dataset_model``  -- the paper prints a quantitative dataset (a table of
  measured values).

``validate_entry`` names a module-level callable that returns a report with an
``ok`` flag. Baez's package predates this gate and its own suite pins its exact
module set, so it is checked structurally here (package, manifest, equation
evaluation) rather than by adding a function to it.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Repository root: this file is <root>/composition/composition/evidence/standalone.py
ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class StandaloneModel:
    """One paper's standalone model package."""

    paper_folder: str
    """The corpus folder under ``Models/`` this model implements."""

    package: str
    """The package directory, relative to the repository root."""

    module: str
    """The importable module name inside that directory."""

    artefact_id: str
    """The ``artefact_id`` the package's manifest declares."""

    kind: str
    """``equation_model`` or ``dataset_model``."""

    scope: str
    """One line: what the package implements, in the paper's own terms."""

    validate_entry: str = "validate"
    """Module-level callable returning ``{"ok": bool, ...}``; "" for none."""

    def package_dir(self, base: Path | None = None) -> Path:
        return (base or ROOT) / self.package

    def module_dir(self, base: Path | None = None) -> Path:
        return self.package_dir(base) / self.module

    def manifest_path(self, base: Path | None = None) -> Path:
        return self.package_dir(base) / "manifest.json"

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_folder": self.paper_folder,
            "package": self.package,
            "module": self.module,
            "artefact_id": self.artefact_id,
            "kind": self.kind,
            "scope": self.scope,
            "validate_entry": self.validate_entry,
            "registered_in_composition_registry": False,
        }


#: Every standalone model in this repository, in corpus order.
STANDALONE_MODELS: tuple[StandaloneModel, ...] = (
    StandaloneModel(
        paper_folder="Baez",
        package="Models/Baez",
        module="baez2014",
        artefact_id="baez2014-oxygen-induced",
        kind="equation_model",
        scope=(
            "the printed exponential fed-batch feed equation and the reported "
            "growth-rate and endpoint observations of Baez et al. (2014)"
        ),
        validate_entry="",
    ),
    StandaloneModel(
        paper_folder="Lin",
        package="Models/Lin",
        module="lin2000",
        artefact_id="lin2000-uptake-capacities",
        kind="equation_model",
        scope=(
            "the complete simulation model of the Appendix of Lin et al. (2001): "
            "seven printed differential equations, the subsidiary chain, the two "
            "correction branches and the pulse method"
        ),
    ),
    StandaloneModel(
        paper_folder="nanchen",
        package="Models/nanchen",
        module="nanchen2006",
        artefact_id="nanchen2006-pirt-chemostat",
        kind="equation_model",
        scope=(
            "Pirt's chemostat relation, printed as equation (3) of Nanchen et al. "
            "(2006), with that paper's own fitted maintenance parameters"
        ),
    ),
    StandaloneModel(
        paper_folder="Simensen",
        package="Models/Simensen",
        module="simensen2022",
        artefact_id="simensen2022-biomass-composition",
        kind="dataset_model",
        scope=(
            "Table 1 of Simensen et al. (2022): the measured macromolecular "
            "biomass composition, in g gCDW-1, with every printed SD and marker"
        ),
    ),
)


def by_paper(folder: str) -> StandaloneModel | None:
    for entry in STANDALONE_MODELS:
        if entry.paper_folder == folder:
            return entry
    return None


def by_module(module: str) -> StandaloneModel | None:
    for entry in STANDALONE_MODELS:
        if entry.module == module:
            return entry
    return None


def packages() -> tuple[str, ...]:
    return tuple(entry.package for entry in STANDALONE_MODELS)


def modules() -> tuple[str, ...]:
    return tuple(entry.module for entry in STANDALONE_MODELS)


# --------------------------------------------------------------------------- #
# structural checks
# --------------------------------------------------------------------------- #

#: Every way the registry can disagree with the tree, in printed order.
PROBLEM_KEYS = (
    "missing_package_dirs",
    "missing_module_dirs",
    "missing_manifests",
    "manifest_artefact_mismatch",
    "duplicate_paper_folders",
    "duplicate_modules",
    "unknown_kinds",
)

KNOWN_KINDS = ("equation_model", "dataset_model")


def problems(base: Path | None = None) -> dict[str, list[str]]:
    """Structural disagreements between this registry and the tree."""
    root = base or ROOT
    missing_pkg: list[str] = []
    missing_mod: list[str] = []
    missing_man: list[str] = []
    mismatch: list[str] = []
    unknown_kind: list[str] = []
    for entry in STANDALONE_MODELS:
        if not entry.package_dir(root).is_dir():
            missing_pkg.append(entry.package)
        elif not (entry.module_dir(root) / "__init__.py").is_file():
            missing_mod.append(f"{entry.package}/{entry.module}")
        manifest = entry.manifest_path(root)
        if not manifest.is_file():
            missing_man.append(entry.package)
        else:
            try:
                payload = json.loads(manifest.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                mismatch.append(f"{entry.package}: manifest is not JSON ({exc})")
            else:
                if payload.get("artefact_id") != entry.artefact_id:
                    mismatch.append(
                        f"{entry.package}: manifest declares "
                        f"{payload.get('artefact_id')!r}, registry says "
                        f"{entry.artefact_id!r}"
                    )
                if payload.get("registration", {}).get(
                    "registered_in_composition_registry"
                ):
                    mismatch.append(
                        f"{entry.package}: manifest claims a composition "
                        f"registration, which a standalone model must not have"
                    )
        if entry.kind not in KNOWN_KINDS:
            unknown_kind.append(f"{entry.package}: {entry.kind!r}")

    folders = [e.paper_folder for e in STANDALONE_MODELS]
    mods = [e.module for e in STANDALONE_MODELS]
    return {
        "missing_package_dirs": sorted(missing_pkg),
        "missing_module_dirs": sorted(missing_mod),
        "missing_manifests": sorted(missing_man),
        "manifest_artefact_mismatch": sorted(mismatch),
        "duplicate_paper_folders": sorted(
            f for f in set(folders) if folders.count(f) > 1
        ),
        "duplicate_modules": sorted(m for m in set(mods) if mods.count(m) > 1),
        "unknown_kinds": sorted(unknown_kind),
    }


def problem_messages(report: dict[str, list[str]]) -> list[str]:
    """Every structural problem, as one list of messages."""
    return [f"{key}: {item}" for key in PROBLEM_KEYS for item in report[key]]



# --------------------------------------------------------------------------- #
# fidelity checks
# --------------------------------------------------------------------------- #


def _ensure_importable(entry: StandaloneModel, base: Path | None = None) -> None:
    """Put the package directory on ``sys.path`` so `entry.module` can import."""
    path = str(entry.package_dir(base))
    if path not in sys.path:
        sys.path.insert(0, path)


def load(entry: StandaloneModel, base: Path | None = None) -> Any:
    """Import the entry's module from its own checkout, not from site-packages."""
    _ensure_importable(entry, base)
    return importlib.import_module(entry.module)


def _legacy_structural_check(
    entry: StandaloneModel, base: Path | None = None
) -> dict[str, Any]:
    """A package without a ``validate()`` gate is checked through its own API.

    Baez's package predates this registry and its suite pins its exact module
    set, so no function is added to it. Three things are asserted instead, all
    through the package's own public surface: the manifest it builds today equals
    the committed ``manifest.json``, its one executable equation evaluates to a
    finite value at named inputs, and it still reports no composition
    registration.
    """
    module = load(entry, base)
    committed = entry.manifest_path(base).read_text(encoding="utf-8")
    built = json.dumps(
        module.build_manifest(), indent=2, sort_keys=True, ensure_ascii=False
    ) + "\n"
    equation = module.equations.executable_equations()[0]
    value = equation.evaluate(
        {"mu_set": 0.35, "Y_XS": 1.28, "m": 0.12, "S_F": 141.0,
         "X_F": 10.0, "V_F": 4.0, "t_F": 5.0, "t": 6.0}
    )
    ok = (
        committed == built
        and value == value
        and module.build_manifest()["registration"][
            "registered_in_composition_registry"
        ] is False
    )
    return {
        "ok": ok,
        "module": entry.module,
        "kind": entry.kind,
        "detail": (
            f"manifest matches the committed snapshot; feed equation evaluates to "
            f"{value:.6f} L/h; registration declared False"
        ),
        "checks": [],
    }


def fidelity(entry: StandaloneModel, base: Path | None = None) -> dict[str, Any]:
    """Run one entry's fidelity gate and return its report.

    A package that cannot even be imported is a failed gate, reported as data
    rather than raised, so a caller checking twelve papers sees which one broke.
    """
    if not entry.validate_entry:
        return _legacy_structural_check(entry, base)
    runner = None
    try:
        module = load(entry, base)
    except Exception as exc:  # import error, syntax error, missing manifest...
        return {
            "ok": False,
            "module": entry.module,
            "kind": entry.kind,
            "detail": (
                f"{entry.package}/{entry.module} could not be imported, so its "
                f"fidelity is unknown: {type(exc).__name__}: {exc}"
            ),
            "checks": [],
        }
    runner = getattr(module, entry.validate_entry, None)
    if runner is None:
        return {
            "ok": False,
            "module": entry.module,
            "kind": entry.kind,
            "detail": (
                f"the package exports no {entry.validate_entry!r}; the fidelity "
                f"gate has nothing to run"
            ),
            "checks": [],
        }
    report = runner()
    return {
        "ok": bool(report.get("ok")),
        "module": entry.module,
        "kind": entry.kind,
        "detail": "; ".join(report.get("failures") or ["all checks passed"]),
        "checks": report.get("checks", []),
    }


def fidelity_all(base: Path | None = None) -> dict[str, dict[str, Any]]:
    """The fidelity report for every standalone model, keyed by paper folder."""
    return {entry.paper_folder: fidelity(entry, base) for entry in STANDALONE_MODELS}


def fidelity_failures(base: Path | None = None) -> list[str]:
    return [
        f"{folder}: {report['detail']}"
        for folder, report in fidelity_all(base).items()
        if not report["ok"]
    ]



# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m composition.evidence.standalone",
        description=(
            "Report which papers have a standalone model and whether each still "
            "matches its paper."
        ),
    )
    parser.add_argument("--check", action="store_true",
                        help="fail when the registry, the tree or a model disagree")
    parser.add_argument("--fidelity", action="store_true",
                        help="run each package's own fidelity checks")
    args = parser.parse_args(argv)

    structural = problems()
    print(f"standalone models: {len(STANDALONE_MODELS)}")
    for entry in STANDALONE_MODELS:
        print(f"  {entry.paper_folder:12s} {entry.package:22s} "
              f"{entry.module:14s} {entry.kind}")

    failures = problem_messages(structural)
    for message in failures:
        print(("FAIL " if args.check else "NOTE ") + message)

    fidelity_failed: list[str] = []
    if args.fidelity:
        for folder, report in fidelity_all().items():
            mark = "ok  " if report["ok"] else "FAIL"
            print(f"  {mark} {folder:12s} {report['module']:14s} {report['detail']}")
            if not report["ok"]:
                fidelity_failed.append(folder)

    if args.check:
        if failures or fidelity_failed:
            return 1
        if args.fidelity:
            print("PASS -- every standalone model is present and matches its paper")
    return 0


if __name__ == "__main__":
    sys.exit(main())

