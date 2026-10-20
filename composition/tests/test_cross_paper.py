"""XM-02 -- cross-paper scientific context for the Zielinski replay.

The replay now shows the rest of the project's research library alongside the
batch it replays. These tests keep that panel honest:

1. **Context, not connection.** A permitted verdict is never presented as an
   implemented connection, and a permitted same-model boundary is never
   presented as a connection between different papers. The replay graph
   declares no connections; the panel must say so.
2. **The verdicts come from the authoritative system.** Every compatibility
   section in the payload is read from ``cross_model``'s declared position,
   and a test fails if the two ever disagree.
3. **A refusal still teaches.** Shared context, the specific difference, the
   evidence, what is unresolved and the remediation all survive into the
   payload -- for every refused direction.
4. **Unresolved is not incompatibility.** A boundary that fails closed for
   want of a rule is labelled as an absence of a judgement, and the payload
   never upgrades it to a finding of physical incompatibility.
5. **Nothing scientific changed.** No equation, parameter, solver setting or
   validation status is touched: the registry still records the same
   scientific status, and the replay graph still publishes its 196 values.

Nothing here changes a model, an equation, a parameter or a validation status.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMPOSITION_ROOT = ROOT / "composition"
REPLAY_GRAPH = COMPOSITION_ROOT / "replay" / "zielinski_replay.json"
sys.path.insert(0, str(COMPOSITION_ROOT))

from composition import cross_model                                    # noqa: E402
from composition import cross_paper                                    # noqa: E402
from composition.adapters import REGISTRATIONS                        # noqa: E402
from composition.registry import build_registry                        # noqa: E402
from composition.runner import run_graph                              # noqa: E402

MORRIS = "morris2011.material_balance"
ZIELINSKI = "zielinski2019.rhi_process"
GANJAVE = "ganjave"

#: The replay graph this panel feeds. Its connection count is read from
#: disk, so a change to it changes what the panel may claim.
REPLAY_DOCUMENT = json.loads(REPLAY_GRAPH.read_text(encoding="utf-8"))


def _context(focus: str = ZIELINSKI) -> tuple[dict, int]:
    return cross_paper.context_for(focus)


def _boundary(connections: dict, source: str, target: str) -> dict:
    for boundary in connections["boundaries"]:
        if (boundary["source_model"], boundary["target_model"]) == (source, target):
            return boundary
    raise KeyError("%s -> %s" % (source, target))


def _related(context: dict, model_id: str) -> dict:
    for entry in context["related_models"]:
        if entry["model_id"] == model_id:
            return entry
    raise KeyError(model_id)


# --------------------------------------------------------------------------- #
# the payload is assembled from the project's own records
# --------------------------------------------------------------------------- #


class TestThePayloadComesFromProjectRecords:
    """Every fact in the payload traces to a record the project keeps."""

    def test_the_focus_model_resolves_to_its_exact_reference(self):
        context, code = _context()
        assert code == 0
        assert context["resolved"] is True
        assert context["focus_model"] == ZIELINSKI
        assert context["focus_reference"] == "%s@1.0.0" % ZIELINSKI

    def test_every_other_registered_model_is_related(self):
        context, _ = _context()
        registered = {r.model_id for r in REGISTRATIONS} - {ZIELINSKI}
        shown = {entry["model_id"] for entry in context["related_models"]}
        assert shown == registered, (
            "the panel must show every registered model, not a shorter list"
        )

    def test_model_versions_are_preserved(self):
        context, _ = _context()
        versions = {r.model_id: r.model_version for r in REGISTRATIONS}
        for entry in context["related_models"]:
            assert entry["reference"] == "%s@%s" % (
                entry["model_id"], versions[entry["model_id"]],
            )
        assert context["focus"]["reference"] == "%s@%s" % (
            ZIELINSKI, versions[ZIELINSKI],
        )

    def test_titles_and_papers_are_the_models_own(self):
        context, _ = _context()
        models, _issues = build_registry()
        for entry in context["related_models"]:
            assert entry["reference"]
            expected_title = models[entry["model_id"]].title
            if expected_title.is_known:
                assert entry["title"] == expected_title.value
            else:
                # An unknown title is stated as unknown, never replaced by a
                # phrase the panel composed.
                assert entry["title"] == ""
                assert entry["title_origin"] == "unknown"
            expected_paper = models[entry["model_id"]].source_paper
            if expected_paper.is_known:
                assert entry["source_paper"] == expected_paper.value

    def test_scientific_status_is_not_upgraded(self):
        context, _ = _context()
        assert context["focus"]["scientific_status"]["state"] == "registered_only"
        for entry in context["related_models"]:
            assert entry["scientific_status"]["state"] == "registered_only"
        assert "not a scientific validation" in context["validation_status"]
        assert "does not upgrade" in context["validation_status"]

    def test_an_unresolvable_reference_fails_without_substituting(self):
        context, code = _context("no-such-model")
        assert code == cross_paper.EXIT_BAD_INPUT
        assert context["resolved"] is False
        assert context["focus_model"] is None
        assert context["diagnostics"]
        assert context["registered_references"], (
            "a failure must name the references that would resolve"
        )


# --------------------------------------------------------------------------- #
# compatibility comes from the authoritative system
# --------------------------------------------------------------------------- #


class TestVerdictsComeFromTheCompatibilityEngine:
    """The payload's verdicts are cross_model's, matched on the ordered pair."""

    def test_every_related_pair_matches_the_declared_boundary(self):
        context, _ = _context()
        connections = context["connections"]
        for entry in context["related_models"]:
            for key, source, target in [
                ("compatibility_towards_focus", entry["model_id"], ZIELINSKI),
                ("compatibility_from_focus", ZIELINSKI, entry["model_id"]),
            ]:
                section = entry[key]
                boundary = _boundary(connections, source, target)
                assert section["stance"] == boundary["stance"]
                assert section["permitted"] == boundary["permitted"]
                assert section["reason"] == boundary["reason"]
                assert section["evidence"] == boundary["evidence"]
                assert section["unresolved"] == boundary["unresolved"]
                assert section["remediation"] == boundary["remediation"]

    def test_ganjave_is_refused_in_both_directions(self):
        context, _ = _context()
        ganjave = _related(context, GANJAVE)
        for key in ("compatibility_towards_focus", "compatibility_from_focus"):
            section = ganjave[key]
            assert section["permitted"] is False
            assert section["stance"] == "refused_dimensional_only"
            assert section["shared_context"]
            assert section["fundamental_difference"]
            assert len(section["evidence"]) >= 2
            assert section["unresolved"], (
                "the ganjave refusal must say what would resolve the gap"
            )
            assert section["remediation"]

    def test_morris_is_refused_by_the_engine_component_rules(self):
        context, _ = _context()
        morris = _related(context, MORRIS)
        for key in ("compatibility_towards_focus", "compatibility_from_focus"):
            section = morris[key]
            assert section["permitted"] is False
            assert section["stance"] == "refused_component_identity"
            assert section["enforced_by_engine"] is True
            assert "component" in section["fundamental_difference"].lower()

    def test_the_quantity_pairs_carry_their_own_reasons(self):
        context, _ = _context()
        ganjave = _related(context, GANJAVE)
        pairs = ganjave["compatibility_towards_focus"]["quantity_pairs"]
        assert pairs, "the ganjave boundary names quantity pairs"
        covered = {tuple(pair) for b in cross_model.BOUNDARIES
                   for pair in b.rules}
        for pair in pairs:
            assert (pair["source_quantity"], pair["target_quantity"]) in covered
            assert pair["meaning"], "each pair must say what stands between them"
            assert pair["evidence"], "each pair must carry its evidence"
            assert pair["unresolved"], "each pair must say what would resolve it"

    def test_the_payloads_connections_section_is_the_engine_output(self):
        context, _ = _context()
        # The embedded connections section is exactly what
        # --describe-connections prints: the panel and the CLI cannot drift.
        completed = subprocess.run(
            [sys.executable, "-m", "composition.runner", "--describe-connections"],
            cwd=str(COMPOSITION_ROOT), capture_output=True, text=True,
            env={"PYTHONPATH": str(COMPOSITION_ROOT)}, timeout=120,
        )
        assert completed.returncode == 0, completed.stderr
        declared = json.loads(completed.stdout)
        # Compared in serialized form: the payload's embedded section carries
        # the engine's tuples, the CLI's JSON carries lists, and a reader of
        # the two documents must see the same position either way.
        serialized = json.loads(json.dumps(context["connections"]))
        assert serialized == declared


# --------------------------------------------------------------------------- #
# context is not connection
# --------------------------------------------------------------------------- #


class TestPermittedIsNotImplemented:
    """A permitted verdict is a boundary the engine allows, not a connection."""

    def test_the_permitted_pairs_are_same_model_only(self):
        permitted = {
            (b.source_model, b.target_model) for b in cross_model.BOUNDARIES
            if b.permitted
        }
        assert permitted == {(GANJAVE, GANJAVE), (MORRIS, MORRIS)}
        for source, target in permitted:
            assert source == target, (
                "a permitted pair that is not same-model would be a connection "
                "between different papers and must not be presented as one"
            )

    def test_no_related_model_is_presented_as_connected(self):
        context, _ = _context()
        for entry in context["related_models"]:
            for key in ("compatibility_towards_focus", "compatibility_from_focus"):
                assert entry[key]["connection_in_replay"] is False, (
                    "%s (%s) is presented as a connection in the replay"
                    % (entry["model_id"], key)
                )

    def test_the_replay_scope_declares_no_connections(self):
        context, _ = _context()
        scope = context["replay_scope"]
        assert scope["connection_count"] == 0
        assert scope["is_composition"] is False
        assert "single-model evidence replay" in scope["statement"]
        assert "no other model drives" in scope["statement"].lower()

    def test_the_replay_graph_on_disk_declares_no_connections(self):
        assert REPLAY_DOCUMENT["connections"] == []

    def test_the_replay_graph_still_runs_and_publishes_196_values(self):
        payload, code = run_graph(copy.deepcopy(REPLAY_DOCUMENT))
        assert code == 0
        assert payload["status"].startswith("success")
        assert len(payload["results"][0]["outputs"]) == 196


# --------------------------------------------------------------------------- #
# a refusal still teaches
# --------------------------------------------------------------------------- #


class TestRefusalsShowContextDifferenceAndResolution:
    """Each refused direction shows the three things a reader needs."""

    def test_ganjave_shares_organism_and_process_domain(self):
        context, _ = _context()
        ganjave = _related(context, GANJAVE)
        shared = ganjave["compatibility_towards_focus"]["shared_context"].lower()
        assert "escherichia coli" in shared or "e. coli" in shared
        assert "fed-batch" in shared

    def test_ganjave_difference_names_the_specific_clash(self):
        context, _ = _context()
        ganjave = _related(context, GANJAVE)
        difference = ganjave["compatibility_towards_focus"]["fundamental_difference"]
        # The difference is the engine's own reason, not a generic statement.
        assert "different strain" in difference or "two different experiments" in difference

    def test_the_shared_context_is_quoted_not_invented(self):
        """Every shared-context sentence appears in the engine's own records."""
        context, _ = _context()
        connections = context["connections"]
        for entry in context["related_models"]:
            boundary = _boundary(
                connections, entry["model_id"], ZIELINSKI,
            )
            section = entry["compatibility_towards_focus"]
            reason = boundary["reason"].lower()
            for sentence in section["shared_context"].split(". "):
                sentence = sentence.strip().rstrip(".")
                if not sentence or sentence.lower().startswith("both publish"):
                    continue
                # A shared sentence drawn from the reason must appear in it.
                key = sentence[:40].lower()
                assert key in reason, (
                    "shared context sentence %r is not in the engine's reason"
                    % sentence
                )

    def test_what_would_resolve_the_gap_is_stated(self):
        context, _ = _context()
        ganjave = _related(context, GANJAVE)
        for key in ("compatibility_towards_focus", "compatibility_from_focus"):
            unresolved = ganjave[key]["unresolved"]
            assert unresolved
            assert any("could" in u for u in unresolved), (
                "the unresolved field must say what a future matched model "
                "could carry, not imply the gap is permanent"
            )


# --------------------------------------------------------------------------- #
# unresolved is not incompatibility
# --------------------------------------------------------------------------- #


class TestUnresolvedIsNotPresentedAsIncompatibility:
    """The evidence_limited basis is an absence of a judgement, and must read as one."""

    def test_evidence_limited_boundaries_are_marked_as_such(self):
        for boundary in cross_model.BOUNDARIES:
            if boundary.stance == "refused_unclassified":
                assert boundary.evidence_basis == "evidence_limited"
            elif boundary.permitted:
                assert boundary.evidence_basis == "permitted"
            else:
                assert boundary.evidence_basis == "documented_incompatibility"

    def test_no_refused_boundary_claims_the_models_are_physically_unrelated(self):
        """The policy may record a position; it may not overstate it.

        The ganjave refusals in particular must keep their unresolved field:
        the two cultures are both E. coli fed-batch, and a matched model could
        connect them. A payload that dropped that would present an absence of
        a judgement as a finding.
        """
        for boundary in cross_model.BOUNDARIES:
            text = " ".join((
                boundary.stance, boundary.reason, boundary.remediation,
                *boundary.evidence, *boundary.unresolved,
            )).lower()
            assert "are scientifically unrelated" not in text
            assert "cannot ever be connected" not in text
            assert "permanently" not in text

    def test_the_payload_keeps_the_unresolved_field_for_ganjave(self):
        context, _ = _context()
        ganjave = _related(context, GANJAVE)
        unresolved = ganjave["compatibility_towards_focus"]["unresolved"]
        assert any(
            "declaring a shared component set" in u for u in unresolved
        ), "the matched-model resolution must survive into the payload"


# --------------------------------------------------------------------------- #
# the examined papers
# --------------------------------------------------------------------------- #


class TestExaminedPapersAreContextNotModels:
    """Ingested papers examined against the focus model's gaps stay papers."""

    def test_the_catalogue_findings_survive_with_their_citations(self):
        context, _ = _context()
        papers = context["examined_papers"]
        assert papers, "the evidence catalogue findings must reach the panel"
        for paper in papers:
            assert paper["citation"], "a paper without a citation is not evidence"
            assert paper["finding_id"]
            assert paper["verdict"]
            assert paper["independence"]
            assert "does_not_resolve" in paper

    def test_the_papers_are_marked_as_not_models(self):
        context, _ = _context()
        assert "papers, not registered models" in context["examined_papers_scope"]

    def test_the_focus_models_declared_gaps_are_listed(self):
        context, _ = _context()
        gaps = context["focus"]["declared_gaps"]
        assert gaps, "the focus model's declared gaps must be listed"
        for gap in gaps:
            assert gap["label"]
            assert gap["why_it_matters"]
        # The gaps are the model's own, not this module's.
        assert any(g["parameter_id"] == "MP-GROWTH-KINETICS" for g in gaps)

    def test_a_model_without_the_catalogue_gets_an_honest_scope(self):
        context, code = _context(MORRIS)
        assert code == 0
        assert context["examined_papers"] == []
        assert "no papers are examined here" in context["examined_papers_scope"]


# --------------------------------------------------------------------------- #
# nothing scientific changed
# --------------------------------------------------------------------------- #


class TestNothingScientificChanged:
    """The panel is an assembly; it computes no science of its own."""

    def test_the_payload_carries_no_equations_or_parameters(self):
        context, _ = _context()
        text = json.dumps(context).lower()
        for forbidden in ("mu_max =", "solver: {", "rtol", "atol"):
            assert forbidden not in text, (
                "the payload carries solver or parameter content: %r" % forbidden
            )

    def test_the_registry_records_are_unchanged(self):
        models, issues = build_registry()
        assert not issues
        assert models[ZIELINSKI].model_version == "1.0.0"
        assert models[GANJAVE].scientific_status["state"] == "registered_only"
        assert models[MORRIS].port_dependence.value == "instance_parameterised"

    def test_cross_model_positions_are_unchanged(self):
        """The panel reads the rule registry; it does not restate it."""
        connections = cross_model.describe()
        assert "matching unit is necessary and never sufficient" in (
            connections["claim_scope"]
        )
        assert "does not upgrade any model's reproduction_status" in (
            connections["validation_status"]
        )
