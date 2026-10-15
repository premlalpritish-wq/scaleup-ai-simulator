"""Tests for literature-based discovery of missing evidence.

Separate from ``test_acceptance.py``: these cover the *investigation* workflow,
not the composition criteria CG-01..CG-15. The existing suites are untouched.

The properties that matter here are the conservative ones. It must be hard, and
ideally impossible, to make this module claim that a generic literature number
applies to the Zielinski fermentation.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

from composition.evidence import (
    CRITICAL_DIMENSIONS,
    FINDINGS,
    SEARCH_SCOPE,
    TARGET_PROCESS,
    TARGETS,
    VALIDATION_CRITERIA,
    CandidateFinding,
    ExperimentalConditions,
    ExtractionConfidence,
    Provenance,
    SourceLocation,
    UncertaintyRecord,
    Verdict,
    assess,
    findings_for_port,
    inventory,
    validate,
)

TARGET_PORT = "node:N01#specific_growth_rate"

#: The ``composition`` package root, i.e. the directory Godot runs Python from.
_COMPOSITION_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _perfect_finding(**overrides) -> CandidateFinding:
    """A candidate whose conditions match the target process exactly."""
    c = TARGET_PROCESS
    kwargs = dict(
        finding_id="TEST-PERFECT",
        target_missing_parameter="MP-GROWTH-KINETICS",
        target_quantity_ids=(TARGET_PORT,),
        quantity_id="specific_growth_rate",
        quantity_label="test",
        value=0.5,
        unit="per_h",
        provenance=Provenance.REPORTED,
        source=SourceLocation(
            citation="test citation",
            doi="10.0000/test",
            url="https://doi.org/10.0000/test",
            section="Methods",
            quote="mu = 0.5 h-1",
        ),
        conditions=ExperimentalConditions(
            organism=c["organism"],
            strain=c["strain"],
            construct=c["construct"],
            product=c["product"],
            medium=c["medium"],
            substrate=c["substrate"],
            mode=c["mode"],
            temperature_c=c["temperature_c"],
            ph=c["ph"],
            oxygen_transfer=c["oxygen_transfer"],
            measurement=c["measurement"],
            scale=c["scale"],
        ),
        method="test method",
        uncertainty=UncertaintyRecord("reported_range", 0.4, 0.6, "test"),
        extraction_confidence=ExtractionConfidence.HIGH,
    )
    kwargs.update(overrides)
    return CandidateFinding(**kwargs)


# --------------------------------------------------------------------------- #
# Provenance of the records themselves
# --------------------------------------------------------------------------- #


class TestEvidenceIsTraceable:
    def test_every_finding_carries_a_resolvable_source(self):
        for f in FINDINGS:
            assert f.source.doi, f"{f.finding_id} has no DOI"
            assert f.source.url, f"{f.finding_id} has no URL"
            assert f.source.citation, f"{f.finding_id} has no citation"

    def test_every_finding_quotes_its_source(self):
        for f in FINDINGS:
            assert f.source.is_verifiable(), (
                f"{f.finding_id} is not verifiable: needs both a DOI and a "
                f"section with a quoted passage"
            )
            assert len(f.source.quote) > 40, f"{f.finding_id} quote is too short to be evidence"

    def test_every_finding_names_a_section_or_figure(self):
        for f in FINDINGS:
            assert f.source.section or f.source.figure, f"{f.finding_id} has no location"

    def test_every_finding_states_conditions(self):
        for f in FINDINGS:
            for dimension, value in f.conditions.dimensions().items():
                assert value, f"{f.finding_id} leaves {dimension} blank"

    def test_every_finding_states_a_unit_and_a_method(self):
        for f in FINDINGS:
            assert f.unit, f"{f.finding_id} has no unit"
            assert len(f.method) > 20, f"{f.finding_id} has no real method description"

    def test_locators_are_human_followable(self):
        for f in FINDINGS:
            loc = f.source.locator()
            assert "doi:" in loc
            assert "sec." in loc or "Fig." in loc


class TestProvenanceIsPreserved:
    def test_provenance_uses_the_model_vocabulary(self):
        allowed = {"reported", "digitized", "derived", "assumed", "unknown"}
        for f in FINDINGS:
            assert f.provenance.value in allowed

    def test_a_source_range_is_not_collapsed_to_a_midpoint(self):
        """A range must never become an invented central value."""
        f = next(x for x in FINDINGS if x.finding_id == "CF-001")
        assert f.uncertainty is not None
        assert f.uncertainty.lo == 40.0 and f.uncertainty.hi == 88.0
        # the carried point sits at a reported bound, never between them
        assert f.value in (f.uncertainty.lo, f.uncertainty.hi)

    def test_each_finding_says_what_it_does_not_resolve(self):
        for f in FINDINGS:
            assert f.does_not_resolve, f"{f.finding_id} claims to resolve everything"


# --------------------------------------------------------------------------- #
# Compatibility
# --------------------------------------------------------------------------- #


class TestCompatibilityIsConservative:
    def test_mode_mismatch_forces_incompatible(self):
        a = assess(next(x for x in FINDINGS if x.finding_id == "CF-001"))
        assert a.verdict is Verdict.INCOMPATIBLE
        assert any("mode differs" in r for r in a.reasons)

    def test_scale_or_measurement_difference_is_reported(self):
        a = assess(next(x for x in FINDINGS if x.finding_id == "CF-002"))
        reasons = " ".join(a.reasons)
        assert "mode differs" in reasons
        assert "measurement" in reasons or "construct" in reasons

    def test_a_perfect_match_reaches_found_but_never_validated(self):
        a = assess(_perfect_finding())
        assert a.verdict is Verdict.FOUND
        assert a.verdict is not Verdict.VALIDATED

    def test_unknown_critical_dimension_caps_at_unverified(self):
        f = _perfect_finding()
        broken = CandidateFinding(**{**f.__dict__, "conditions": ExperimentalConditions(
            organism=TARGET_PROCESS["organism"],
            strain="not stated",
            construct=TARGET_PROCESS["construct"],
            product=TARGET_PROCESS["product"],
            medium=TARGET_PROCESS["medium"],
            substrate=TARGET_PROCESS["substrate"],
            mode=TARGET_PROCESS["mode"],
            temperature_c="37",
            ph="not stated",
            oxygen_transfer="not reported",
            measurement=TARGET_PROCESS["measurement"],
            scale="",
        )})
        a = assess(broken)
        assert a.verdict is Verdict.UNVERIFIED
        assert any("not stated" in r for r in a.reasons)

    def test_not_stated_never_reads_as_a_match(self):
        """The distinction that stops an unreported condition counting as agreement."""
        f = FINDINGS[0]
        target = dict(TARGET_PROCESS)
        assert target["oxygen_transfer"] == "not reported"
        dims = {d.dimension: d for d in assess(f).dimensions}
        assert dims["temperature_c"].match.value == "unknown"
        assert dims["temperature_c"].candidate == "not stated"

    def test_every_critical_dimension_is_reported_for_each_finding(self):
        for f in FINDINGS:
            dims = {d.dimension for d in assess(f).dimensions}
            for critical in CRITICAL_DIMENSIONS:
                assert critical in dims, f"{f.finding_id} omits critical {critical}"

    def test_assessment_is_deterministic(self):
        for f in FINDINGS:
            assert assess(f).verdict is assess(f).verdict


# --------------------------------------------------------------------------- #
# The validation gate
# --------------------------------------------------------------------------- #


class TestValidationGate:
    def test_criteria_are_registered(self):
        assert len(VALIDATION_CRITERIA) >= 8
        ids = [c.criterion_id for c in VALIDATION_CRITERIA]
        assert len(ids) == len(set(ids))

    def test_no_registered_finding_is_validated(self):
        for f in FINDINGS:
            report = validate(f)
            assert not report.validated, (
                f"{f.finding_id} claims validation but failed "
                f"{report.failures()}"
            )

    def test_a_perfect_candidate_is_validated_only_when_all_criteria_pass(self):
        report = validate(_perfect_finding())
        assert report.validated
        assert report.failures() == ()

    def test_validation_reports_which_criterion_failed(self):
        f = _perfect_finding(uncertainty=UncertaintyRecord("reported_range", 9.0, 10.0, "narrow"))
        report = validate(f)
        assert not report.validated
        assert "VC-8" in report.failures()

    def test_a_missing_source_prevents_validation(self):
        f = _perfect_finding(source=SourceLocation(
            citation="x", doi="", url="", section="", quote=""))
        report = validate(f)
        assert not report.validated
        assert "VC-1" in report.failures()

    def test_a_wrong_strain_prevents_validation(self):
        f = _perfect_finding()
        broken = CandidateFinding(**{**f.__dict__, "conditions": ExperimentalConditions(
            **{**dict(f.conditions.dimensions()), "strain": "E. coli BL21(DE3)"}
        )})
        report = validate(broken)
        assert not report.validated
        assert "VC-3" in report.failures()

    def test_validation_cannot_be_waived_by_assertion(self):
        """There is no parameter that lets a caller force VALIDATED."""
        f = _perfect_finding()
        report = validate(f)
        assert report.validated is True
        # and the same object with any evidence removed fails again
        assert not validate(_perfect_finding(
            source=SourceLocation(citation="x", doi="", url="", section="", quote="")
        )).validated


# --------------------------------------------------------------------------- #
# The catalogue
# --------------------------------------------------------------------------- #


class TestCatalogue:
    def test_targets_name_what_is_missing(self):
        for port, info in TARGETS.items():
            assert info["label"]
            assert info["why_it_matters"]

    def test_findings_attach_to_real_targets(self):
        known = set(TARGETS)
        for f in FINDINGS:
            for port in f.target_quantity_ids:
                assert port in known, f"{f.finding_id} targets unknown port {port}"

    def test_the_growth_rate_target_has_candidates_but_none_compatible(self):
        matched = findings_for_port(TARGET_PORT)
        assert matched, "the demonstration target has no candidates at all"
        verdicts = {f.assess().verdict for f in matched}
        assert Verdict.INCOMPATIBLE in verdicts
        assert Verdict.VALIDATED not in verdicts

    def test_the_closest_match_still_does_not_resolve_the_gap(self):
        """CF-003 matches the process and supplies no kinetic parameter."""
        f = next(x for x in FINDINGS if x.finding_id == "CF-003")
        assert f.assess().verdict is Verdict.FOUND
        joined = " ".join(f.does_not_resolve).lower()
        assert "no kinetic parameter" in joined or "specific growth rate" in joined

    def test_targets_without_candidates_report_an_empty_result_honestly(self):
        inv = inventory()
        for port in ("node:N01#dissolved_oxygen", "node:N01#induction_time"):
            entry = inv["targets"][port]
            assert entry["candidate_count"] == 0
            assert entry["resolved"] is False
            assert entry["search_scope"]["result"]

    def test_search_scope_is_recorded(self):
        assert SEARCH_SCOPE["queries"]
        assert "no source" in SEARCH_SCOPE["result"].lower()

    def test_inventory_is_json_serialisable(self):
        payload = json.dumps(inventory())
        assert '"verdict"' in payload

    def test_nothing_is_marked_resolved(self):
        """The workflow never claims to have closed a gap."""
        for entry in inventory()["targets"].values():
            assert entry["resolved"] is False


class TestNoModelMutation:
    def test_evidence_package_does_not_import_a_model_package(self):
        """No run-time dependency on a model, and no path rewriting into one.

        Docstrings may *name* the model vocabulary -- that is the point of
        reusing it -- but nothing may import it or push it onto ``sys.path``.
        """
        import ast
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1] / "composition" / "evidence"
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not alias.name.startswith(("scaleup_ai", "models")), (
                            f"{path.name} imports {alias.name}"
                        )
                elif isinstance(node, ast.ImportFrom):
                    root_name = (node.module or "").split(".")[0]
                    assert root_name not in ("scaleup_ai", "models"), (
                        f"{path.name} imports from {node.module}"
                    )
                elif isinstance(node, ast.Call):
                    func = getattr(node.func, "attr", "")
                    owner = getattr(node.func, "value", None)
                    if func in ("append", "insert", "extend") and owner is not None:
                        target = getattr(owner, "id", "")
                        assert target != "path", f"{path.name} mutates sys.path"

    def test_the_only_write_is_the_explicit_result_path(self):
        """The package never writes into the repository.

        ``main()`` writes exactly one file, and only when the caller named a
        destination with ``--result``. Nothing writes relative to the package
        location, and no other module writes at all -- so running the catalogue
        cannot leave a trace in the repository it ships in.
        """
        import ast

        root = _COMPOSITION_ROOT / "composition" / "evidence"
        write_calls: list[tuple[str, str, int]] = []
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
                for node in ast.walk(fn):
                    if not isinstance(node, ast.Call):
                        continue
                    name = getattr(node.func, "attr", "")
                    if name in ("write_text", "write_bytes", "mkdir", "unlink", "rename"):
                        write_calls.append((path.name, fn.name, node.lineno))

        # exactly two write sites, both in main(): create the parent, write the file
        assert {name for name, _, _ in write_calls} == {"catalogue.py"}
        assert {fn for _, fn, _ in write_calls} == {"main"}
        assert len(write_calls) == 2, f"unexpected filesystem writes: {write_calls}"

        source = (root / "catalogue.py").read_text(encoding="utf-8")
        guard_line = next(
            i for i, line in enumerate(source.splitlines(), start=1)
            if "if args.result:" in line
        )
        first_write = min(line for _, _, line in write_calls)
        assert guard_line < first_write, "the writes are not guarded by --result"
        # the destination is the caller-supplied path, never one derived from here
        assert "Path(__file__)" not in source

    def test_cli_emits_the_catalogue_and_exits_zero(self):
        """Exercised with the exact module path the Godot scene invokes."""
        out = subprocess.run(
            [sys.executable, "-m", "composition.evidence"],
            capture_output=True, text=True, timeout=60,
            cwd=str(_COMPOSITION_ROOT),
        )
        assert out.returncode == 0, out.stderr
        payload = json.loads(out.stdout)
        assert payload["totals"]["findings"] == len(FINDINGS)
        assert payload["totals"]["targets"] == len(TARGETS)

    def test_cli_emits_no_warning_on_stdout(self):
        """stdout must be pure JSON; a RuntimeWarning would break the parse."""
        out = subprocess.run(
            [sys.executable, "-m", "composition.evidence"],
            capture_output=True, text=True, timeout=60,
            cwd=str(_COMPOSITION_ROOT),
        )
        assert "RuntimeWarning" not in out.stderr
        json.loads(out.stdout)  # raises if anything else is mixed in

    def test_result_contract_writes_the_catalogue_to_disk(self):
        """Godot reads the catalogue from a file, not from a captured pipe.

        This is the contract ``replay3d.gd`` depends on, so it is tested rather
        than assumed: ``--result <path>`` must produce a readable file and a
        summary whose counts match the records.
        """
        import pathlib
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "nested" / "evidence_catalogue.json"
            out = subprocess.run(
                [sys.executable, "-m", "composition.evidence", "--result", str(target)],
                capture_output=True, text=True, timeout=60,
                cwd=str(_COMPOSITION_ROOT),
            )
            assert out.returncode == 0, out.stderr
            summary = json.loads(out.stdout)
            assert summary["exit_code"] == 0
            assert summary["findings"] == len(FINDINGS)
            assert summary["by_verdict"]["validated"] == 0

            assert target.is_file(), "--result did not create the file"
            payload = json.loads(target.read_text(encoding="utf-8"))
            assert payload["totals"]["findings"] == len(FINDINGS)
            assert len(payload["findings"]) == len(FINDINGS)
            for f in payload["findings"]:
                assert f["source"]["doi"]
                assert f["source"]["quote"]
                assert f["assessment"]["verdict"] in (
                    "found", "unverified", "incompatible", "validated")
                assert f["validation"]["validated"] is False