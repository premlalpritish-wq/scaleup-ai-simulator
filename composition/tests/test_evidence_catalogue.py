"""Tests for literature-based discovery of missing evidence.

Separate from ``test_acceptance.py``: these cover the *investigation* workflow,
not the composition criteria CG-01..CG-15. The existing suites are untouched.

The properties that matter here are the conservative ones. It must be hard, and
ideally impossible, to make this module claim that a generic literature number
applies to the Zielinski fermentation -- or to make it claim that two papers
agree when the comparison is circular.
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
    TARGET_PASSAGES,
    TARGET_PROCESS,
    TARGETS,
    VALIDATION_CRITERIA,
    ZIELINSKI_RECORD,
    CandidateFinding,
    Condition,
    Conflict,
    ConflictKind,
    ExtractionConfidence,
    Independence,
    Provenance,
    SourceLocation,
    UncertaintyRecord,
    Verdict,
    compare,
    detect,
    findings_for_port,
    inventory,
    validate,
)

TARGET_PORT = "node:N01#specific_growth_rate"

#: The package root, i.e. the directory Godot runs Python from.
_COMPOSITION_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The findings whose supporting passages do NOT occur in the target publication.
INDEPENDENT = {"CF-001", "CF-002"}


def _cond(dim: str, value: str, quote: str = "a passage", src: str = "x") -> Condition:
    return Condition(dim, value, quote, src)


def _external_conditions(**overrides) -> dict[str, Condition]:
    """Conditions carrying text that appears nowhere in the target publication."""
    base = {
        "organism": Condition("organism", "Klebsiella pneumoniae",
                              "Klebsiella pneumoniae was cultivated throughout.", "test"),
        "strain": Condition("strain", "Klebsiella pneumoniae K12",
                            "The K12 derivative was used for all inocula.", "test"),
    }
    base.update(overrides)
    return base


def _finding(**overrides) -> CandidateFinding:
    """A candidate whose conditions are copied from the *target* records.

    This is the shape that produced the circular-verdict defect. It exists so
    the tests can assert such a finding is still handled honestly.
    """
    kwargs = dict(
        finding_id="TEST",
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
            quote="mu = 0.5 h-1 stated nowhere in the target paper",
        ),
        conditions={k: Condition(v.dimension, v.value, v.quote, "test")
                    for k, v in TARGET_PROCESS.items()},
        method="test method",
        uncertainty=UncertaintyRecord("reported_range", 0.4, 0.6, "test"),
        extraction_confidence=ExtractionConfidence.HIGH,
    )
    kwargs.update(overrides)
    return CandidateFinding(**kwargs)


def _external_finding(**overrides) -> CandidateFinding:
    """A candidate whose passages are genuinely not the target's."""
    kwargs = dict(
        finding_id="TEST-EXT",
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
            quote="a growth rate measured on an unrelated organism",
        ),
        conditions=_external_conditions(),
        method="test method",
        uncertainty=UncertaintyRecord("reported_range", 0.4, 0.6, "test"),
        extraction_confidence=ExtractionConfidence.HIGH,
    )
    kwargs.update(overrides)
    return CandidateFinding(**kwargs)


# --------------------------------------------------------------------------- #
# The circularity defect, and its regression test
# --------------------------------------------------------------------------- #


class TestVerdictsAreNotCircular:
    """A verdict must rest on two independently checkable passages.

    An earlier version recorded the target process once, then wrote candidate
    conditions as strings identical to it. Every dimension then reported
    ``match``, which looked like verification but was a tautology -- both sides
    were written by the same person. These tests are the regression guard.
    """

    def test_every_stated_target_condition_is_bound_to_a_passage(self):
        """Stated means quoted. Unstated must carry no quote at all.

        The second half matters just as much: attaching a passage to a
        condition the paper never states would manufacture support for it.
        """
        for dim, cond in TARGET_PROCESS.items():
            assert cond.source_id == "zielinski2019"
            if cond.is_stated():
                assert cond.quote, "target %s is stated but carries no passage" % dim
            else:
                assert cond.quote == "", (
                    "target %s is not reported yet carries a passage" % dim
                )

    def test_the_papers_unreported_conditions_are_recorded_as_such(self):
        """Oxygen transfer is not in the Zielinski methods; say so, don't guess."""
        assert TARGET_PROCESS["oxygen_transfer"].value == "not reported"
        assert not TARGET_PROCESS["oxygen_transfer"].is_stated()

    def test_target_quotes_all_come_from_the_declared_source_file(self):
        texts = {p.text for p in TARGET_PASSAGES}
        for dim, cond in TARGET_PROCESS.items():
            if cond.quote:
                assert cond.quote in texts, "target %s quotes a passage not on file" % dim

    def test_candidate_conditions_are_not_copies_of_the_target(self):
        """No candidate may simply restate the target's wording wholesale."""
        for f in FINDINGS:
            identical = [
                dim for dim, cond in f.conditions.items()
                if dim in TARGET_PROCESS and cond.value == TARGET_PROCESS[dim].value
            ]
            # Some agreement on short factual strings is legitimate, but a finding
            # whose *every* condition is a verbatim copy is a transcription bug.
            assert len(identical) < len(TARGET_PROCESS), (
                "%s copies the target conditions wholesale: %s"
                % (f.finding_id, identical)
            )

    def test_a_finding_built_from_the_target_records_is_not_silently_found(self):
        """The exact defect, reproduced deliberately."""
        f = _finding()
        a = f.assess()
        # Its conditions DO match the target on every dimension...
        assert all(d.match in ("match", "partial")
                   for d in a.dimensions if d.dimension in CRITICAL_DIMENSIONS)
        # ...and it is still not FOUND, because the main quote is external text
        # that happens not to overlap. What must never happen is a silent FOUND
        # resting on copied strings with no record of where they came from.
        assert a.verdict is not Verdict.VALIDATED
        assert f.validate().validated is False

    def test_the_closest_match_is_not_reported_as_found(self):
        """CF-003 matches the process on many dimensions and is still not found.

        It is the same institute, strain, vector, medium and fermenter. It was
        previously recorded as a ``found`` external source. It is not one.
        """
        f = next(x for x in FINDINGS if x.finding_id == "CF-003")
        a = f.assess()
        assert a.independence is Independence.TARGET
        assert a.verdict is not Verdict.FOUND
        assert f.validate().validated is False

    def test_no_finding_is_reported_as_found(self):
        for f in FINDINGS:
            assert f.assess().verdict is not Verdict.FOUND, (
                "%s claims FOUND but is not independent evidence" % f.finding_id
            )


# --------------------------------------------------------------------------- #
# Independence
# --------------------------------------------------------------------------- #


class TestIndependence:
    def test_independence_is_decided_for_every_finding(self):
        for f in FINDINGS:
            assert f.assess().independence in Independence

    def test_independent_findings_are_the_expected_ones(self):
        got = {f.finding_id: f.assess().independence for f in FINDINGS}
        for fid in INDEPENDENT:
            assert got[fid] is Independence.EXTERNAL, f"{fid}: {got[fid]}"

    def test_a_passage_occurring_in_the_target_is_not_external(self):
        f = next(x for x in FINDINGS if x.finding_id == "CF-003")
        reasons = " ".join(f.assess().reasons)
        assert "occurs in the target publication" in reasons

    def test_independence_is_required_for_validation(self):
        """VC-10: a non-independent finding can never validate."""
        ids = [c.criterion_id for c in VALIDATION_CRITERIA]
        assert "VC-10" in ids
        f = next(x for x in FINDINGS if x.finding_id == "CF-003")
        report = f.validate()
        assert not report.validated
        assert "VC-10" in report.failures()

    def test_overlap_detection_ignores_trivially_short_quotes(self):
        """A short fragment must not trip the check by accident."""
        f = _external_finding(source=SourceLocation(
            citation="t", doi="10.0/x", url="u", section="s", quote="37"))
        assert f.assess().independence is Independence.EXTERNAL

    def test_an_external_finding_is_external(self):
        assert _external_finding().assess().independence is Independence.EXTERNAL

    def test_a_copied_conditions_finding_is_caught_as_non_independent(self):
        """The defect reproduced: conditions copied from the target, verbatim.

        Its condition passages are the target's own, so the independence check
        must catch it even though every condition 'matches'.
        """
        a = _finding().assess()
        assert a.independence is Independence.TARGET
        assert a.verdict is not Verdict.FOUND


# --------------------------------------------------------------------------- #
# Comparison rules
# --------------------------------------------------------------------------- #


class TestComparisonRules:
    def test_identical_statements_match(self):
        m = compare(_cond("organism", "Escherichia coli"), _cond("organism", "Escherichia coli"))
        assert m.verdict == "match"

    def test_numbers_compare_numerically_not_as_text(self):
        m = compare(_cond("temperature_c", "37"), _cond("temperature_c", "37 degrees Celsius"))
        assert m.verdict == "match"
        m = compare(_cond("temperature_c", "30"), _cond("temperature_c", "37"))
        assert m.verdict == "mismatch"

    def test_vessel_volume_is_not_confused_with_an_instrument_model_number(self):
        m = compare(_cond("scale_l", "7.5 L"),
                    _cond("scale_l", "Bioflo Celligen 310 7.5 L fermenter"))
        assert m.verdict == "match"

    def test_different_named_strains_are_a_mismatch_not_an_unknown(self):
        m = compare(_cond("strain", "Escherichia coli ML30"),
                    _cond("strain", "E. coli 20 IBA 1"))
        assert m.verdict == "mismatch"

    def test_the_same_strain_described_two_ways_is_partial(self):
        m = compare(_cond("strain", "Escherichia coli 20 (IBA 1)"),
                    _cond("strain", "E. coli 20 IBA 1, a derivative of CSH50R"))
        assert m.verdict == "partial"

    def test_a_closed_vocabulary_distinguishes_modes(self):
        assert compare(_cond("mode", "continuous chemostat"),
                       _cond("mode", "batch culture, pH-stat")).verdict == "mismatch"
        assert compare(_cond("mode", "batch culture; pH-stat fed"),
                       _cond("mode", "batch culture, glucose fed by pH-stat")).verdict == "match"

    def test_no_construct_cannot_match_a_named_one(self):
        m = compare(_cond("construct", "none; wild type"),
                    _cond("construct", "plasmid pIBAINS"))
        assert m.verdict == "mismatch"

    def test_substrate_concentration_is_not_taken_for_identity(self):
        """glucose at 1% and glucose at 40% are the same substance."""
        m = compare(_cond("substrate", "glucose, 1% (w/v)"),
                    _cond("substrate", "40% glucose, exponentially added"))
        assert m.verdict == "match"

    def test_not_stated_never_reads_as_a_match(self):
        m = compare(_cond("ph", "not stated"), _cond("ph", "pH-stat, dead band 0.01"))
        assert m.verdict == "unknown"
        m = compare(_cond("ph", ""), _cond("ph", "pH-stat"))
        assert m.verdict == "unknown"

    def test_similar_but_different_is_never_a_match(self):
        """The defect in one sentence: resemblance is not agreement."""
        for cand, targ in [
            ("GMS medium", "GMS medium plus 2x yeast extract"),
            ("pIBAINS", "pIBAINS derivative with a T7 promoter"),
            ("Escherichia coli", "Escherichia coli 20"),
        ]:
            assert compare(_cond("medium", cand), _cond("medium", targ)).verdict != "match"


# --------------------------------------------------------------------------- #
# Traceability of the records themselves
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
            assert len(f.source.quote) > 40

    def test_every_condition_carries_a_quote_from_its_own_source(self):
        for f in FINDINGS:
            for dim, cond in f.conditions.items():
                if cond.is_stated():
                    assert cond.quote, (
                        "%s states %s but records no passage for it"
                        % (f.finding_id, dim)
                    )
                assert cond.source_id, "%s/%s has no source id" % (f.finding_id, dim)

    def test_every_condition_belongs_to_the_finding_s_own_source(self):
        """Conditions must not be transcribed from a different paper."""
        for f in FINDINGS:
            for dim, cond in f.conditions.items():
                assert cond.source_id != "zielinski2019", (
                    "%s/%s was transcribed from the target source"
                    % (f.finding_id, dim)
                )

    def test_every_finding_states_a_unit_and_a_method(self):
        for f in FINDINGS:
            assert f.unit
            assert len(f.method) > 20

    def test_a_reported_range_is_not_collapsed_to_a_midpoint(self):
        f = next(x for x in FINDINGS if x.finding_id == "CF-001")
        assert f.uncertainty is not None
        assert (f.uncertainty.lo, f.uncertainty.hi) == (40.0, 88.0)
        assert f.value in (f.uncertainty.lo, f.uncertainty.hi)

    def test_each_finding_says_what_it_does_not_resolve(self):
        for f in FINDINGS:
            assert f.does_not_resolve


# --------------------------------------------------------------------------- #
# Records examined
# --------------------------------------------------------------------------- #


class TestRecordsExamined:
    def test_a_record_is_examined(self):
        r = ZIELINSKI_RECORD
        assert r.model_id and r.model_doi and r.model_source
        assert r.run_id

    def test_the_digest_is_recorded_and_described_accurately(self):
        r = ZIELINSKI_RECORD.to_dict()
        assert len(r["graph_reproducibility_digest"]) == 64
        assert "graph" in r["digest_covers"].lower()
        assert "not the numeric results" in r["digest_covers"]

    def test_the_digest_matches_the_actual_replay_run(self):
        """The digest must be the real one, not a remembered prefix."""
        import glob
        import os

        hits = glob.glob(os.path.expanduser(
            "~/AppData/Roaming/Godot/app_userdata/*/results/zielinski_replay.result.json"))
        if not hits:
            pytest.skip("no replay result on this machine")
        with open(hits[0], encoding="utf-8") as fh:
            doc = json.load(fh)
        assert doc["reproducibility"] == ZIELINSKI_RECORD.graph_reproducibility_digest

    def test_missing_parameters_examined_are_real(self):
        assert "MP-GROWTH-KINETICS" in ZIELINSKI_RECORD.missing_parameters_examined

    def test_the_report_publishes_the_record(self):
        assert inventory()["records_examined"]["model_id"] == ZIELINSKI_RECORD.model_id


# --------------------------------------------------------------------------- #
# Conflicts
# --------------------------------------------------------------------------- #


class TestConflictDetection:
    def test_no_conflict_is_invented(self):
        assert all(c.resolved is False for c in detect(FINDINGS))

    def test_a_non_independent_finding_raises_a_conflict(self):
        found = [c for c in detect(FINDINGS) if c.kind is ConflictKind.SOURCE_OVERLAP]
        assert [c.participants[0] for c in found] == ["CF-003"]
        assert "target publication" in found[0].explanation

    def test_disjoint_intervals_for_one_quantity_are_a_value_conflict(self):
        a = _finding(finding_id="A", quantity_id="q",
                     uncertainty=UncertaintyRecord("range", 1.0, 2.0, "x"))
        b = _finding(finding_id="B", quantity_id="q",
                     uncertainty=UncertaintyRecord("range", 50.0, 90.0, "y"))
        kinds = [c.kind for c in detect((a, b))]
        assert ConflictKind.VALUE in kinds

    def test_overlapping_intervals_are_not_a_conflict(self):
        a = _finding(finding_id="A", quantity_id="q",
                     uncertainty=UncertaintyRecord("range", 1.0, 10.0, "x"))
        b = _finding(finding_id="B", quantity_id="q",
                     uncertainty=UncertaintyRecord("range", 5.0, 20.0, "y"))
        assert ConflictKind.VALUE not in [c.kind for c in detect((a, b))]

    def test_different_units_are_never_compared(self):
        a = _finding(finding_id="A", quantity_id="q", unit="ug_per_L",
                     uncertainty=UncertaintyRecord("range", 1.0, 2.0, "x"))
        b = _finding(finding_id="B", quantity_id="q", unit="per_h",
                     uncertainty=UncertaintyRecord("range", 50.0, 90.0, "y"))
        assert ConflictKind.VALUE not in [c.kind for c in detect((a, b))]

    def test_a_conflict_names_the_records_it_affects(self):
        for c in detect(FINDINGS):
            assert c.affected_records
            assert c.explanation
            assert c.requires == "explicit human direction"

    def test_a_conflict_is_never_marked_resolved(self):
        """The system reports conflicts; it does not settle them."""
        a = _finding(finding_id="A", quantity_id="q",
                     uncertainty=UncertaintyRecord("range", 1.0, 2.0, "x"))
        b = _finding(finding_id="B", quantity_id="q",
                     uncertainty=UncertaintyRecord("range", 50.0, 90.0, "y"))
        assert all(not c.resolved for c in detect((a, b)))


# --------------------------------------------------------------------------- #
# The validation gate
# --------------------------------------------------------------------------- #


class TestValidationGate:
    def test_criteria_are_registered_and_unique(self):
        ids = [c.criterion_id for c in VALIDATION_CRITERIA]
        assert len(ids) == len(set(ids))
        assert len(ids) >= 10

    def test_no_registered_finding_is_validated(self):
        for f in FINDINGS:
            report = f.validate()
            assert not report.validated, (
                f"{f.finding_id} claims validation but failed {report.failures()}"
            )

    def test_a_missing_source_prevents_validation(self):
        f = _finding(source=SourceLocation(citation="x", doi="", url="",
                                            section="", quote=""))
        report = f.validate()
        assert not report.validated
        assert "VC-1" in report.failures()

    def test_validation_reports_which_criterion_failed(self):
        f = _finding(uncertainty=UncertaintyRecord("range", 9.0, 10.0, "narrow"))
        report = f.validate()
        assert not report.validated
        assert "VC-8" in report.failures()

    def test_validation_cannot_be_waived(self):
        """There is no parameter that lets a caller force VALIDATED."""
        import inspect

        sig = inspect.signature(validate)
        assert list(sig.parameters) == ["finding"]
        # and the same finding fails again once evidence is removed
        assert not validate(_finding(source=SourceLocation(
            citation="x", doi="", url="", section="", quote=""))).validated


# --------------------------------------------------------------------------- #
# The catalogue and the report
# --------------------------------------------------------------------------- #


class TestCatalogueAndReport:
    def test_targets_name_what_is_missing(self):
        for port, info in TARGETS.items():
            assert info["label"] and info["why_it_matters"]

    def test_findings_attach_to_real_targets(self):
        known = set(TARGETS)
        for f in FINDINGS:
            for port in f.target_quantity_ids:
                assert port in known

    def test_the_growth_rate_target_has_candidates_but_none_compatible(self):
        matched = findings_for_port(TARGET_PORT)
        assert matched
        assert all(f.assess().verdict is not Verdict.FOUND for f in matched)

    def test_empty_results_are_reported_honestly(self):
        inv = inventory()
        for port in ("node:N01#dissolved_oxygen", "node:N01#induction_time"):
            entry = inv["targets"][port]
            assert entry["candidate_count"] == 0
            assert entry["resolved"] is False
            assert entry["search_scope"]["result"]

    def test_missing_information_is_stated_concretely(self):
        inv = inventory()
        need = inv["targets"]["node:N01#dissolved_oxygen"][
            "missing_information_required"]
        assert need
        assert any("kLa" in n for n in need), "should name what is actually missing"

    def test_search_scope_is_recorded(self):
        assert SEARCH_SCOPE["queries"]
        assert "no source" in SEARCH_SCOPE["result"].lower()

    def test_nothing_is_marked_resolved(self):
        for entry in inventory()["targets"].values():
            assert entry["resolved"] is False

    def test_the_report_states_its_own_authority(self):
        auth = inventory()["authority"]
        assert auth["validated_findings"] == 0
        assert auth["registry_changes_applied"] == 0
        assert any("invent" in s for s in auth["may_not_do"])

    def test_the_report_is_json_serialisable(self):
        assert '"verdict"' in json.dumps(inventory())


# --------------------------------------------------------------------------- #
# Boundaries
# --------------------------------------------------------------------------- #


class TestNoModelMutation:
    def test_the_package_does_not_import_a_model_package(self):
        """No run-time dependency on a model, and no path rewriting into one.

        Docstrings may *name* the model vocabulary -- reusing it is the point --
        but nothing may import it or push it onto ``sys.path``.
        """
        import ast

        root = _COMPOSITION_ROOT / "composition" / "evidence"
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not alias.name.startswith(("scaleup_ai", "models")), (
                            f"{path.name} imports {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    root_name = (node.module or "").split(".")[0]
                    assert root_name not in ("scaleup_ai", "models"), (
                        f"{path.name} imports from {node.module}")
                elif isinstance(node, ast.Call):
                    func = getattr(node.func, "attr", "")
                    owner = getattr(node.func, "value", None)
                    if func in ("append", "insert", "extend") and owner is not None:
                        assert getattr(owner, "id", "") != "path", (
                            f"{path.name} mutates sys.path")

    def test_the_only_write_is_the_explicit_result_path(self):
        """Running the catalogue cannot leave a trace in the repository."""
        import ast

        root = _COMPOSITION_ROOT / "composition" / "evidence"
        write_calls: list[tuple[str, str, int]] = []
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
                for node in ast.walk(fn):
                    if not isinstance(node, ast.Call):
                        continue
                    if getattr(node.func, "attr", "") in (
                            "write_text", "write_bytes", "mkdir", "unlink", "rename"):
                        write_calls.append((path.name, fn.name, node.lineno))

        assert {n for n, _, _ in write_calls} == {"catalogue.py"}
        assert {f for _, f, _ in write_calls} == {"main"}
        source = (root / "catalogue.py").read_text(encoding="utf-8")
        guard = next(i for i, line in enumerate(source.splitlines(), 1)
                     if "if args.result:" in line)
        assert guard < min(line for _, _, line in write_calls)
        assert "Path(__file__)" not in source


class TestCli:
    def test_cli_emits_the_catalogue_and_exits_zero(self):
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
        out = subprocess.run(
            [sys.executable, "-m", "composition.evidence"],
            capture_output=True, text=True, timeout=60,
            cwd=str(_COMPOSITION_ROOT),
        )
        assert "RuntimeWarning" not in out.stderr
        json.loads(out.stdout)

    def test_result_contract_writes_the_catalogue_to_disk(self):
        """Godot reads the catalogue from a file, so this contract is tested."""
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
            assert summary["by_verdict"]["validated"] == 0

            assert target.is_file()
            payload = json.loads(target.read_text(encoding="utf-8"))
            for f in payload["findings"]:
                assert f["source"]["doi"] and f["source"]["quote"]
                assert f["validation"]["validated"] is False
                assert f["assessment"]["verdict"] in (
                    "found", "unverified", "incompatible", "validated")