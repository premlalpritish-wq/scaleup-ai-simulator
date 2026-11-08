"""CR-01 -- the evidence-backed composition report.

The report is the place where the project stops conflating four questions that
happen to share a vocabulary:

1. Did the connection hold **mechanically**? (quantity, unit, direction, component)
2. Does it **mean** anything between these two models?
3. Did it **run**?
4. Is any of it **scientifically validated**?

Only the first is a statement about whether the software worked. A graph can be
mechanically clean, semantically refused, unrun and entirely unvalidated all at
once, and the tests here hold every one of those four apart in the output.

Three failure modes drive this suite, and each would be a way of quietly
laundering a missing judgement into a scientific claim:

* **A vague refusal covering a precise failure.** If a unit mismatch also
  triggers a cross-model refusal, the diagnostic that names the actual problem
  is lost behind one that does not. The report must show the mechanical reason
  and must not present a semantic objection in its place.
* **Absence of a rule read as a finding of incompatibility.** The policy fails
  closed on an unclassified quantity pair. That is a refusal to guess, not a
  claim that the two quantities cannot be connected, and the report has to say
  which it is.
* **Execution read as validation.** A graph that runs is evidence that the
  pipeline works. It is not evidence that the numbers are right, and the
  combined graph must never inherit a validation status from its parts.

Nothing here modifies a model, an equation, a parameter or a validation status,
and nothing here adds a rule: the report *describes* decisions the engine and
``cross_model`` already made, and a test asserts it introduces none of its own.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMPOSITION_ROOT = ROOT / "composition"
EXAMPLES = COMPOSITION_ROOT / "examples"
sys.path.insert(0, str(COMPOSITION_ROOT))

from composition import cross_model, report                        # noqa: E402
from composition.adapters.ganjave_contract import INPUT_CONTRACT  # noqa: E402
from composition.contracts import ModelDiagnostic                  # noqa: E402
from composition.diagnostics import DiagnosticCode, Severity       # noqa: E402
from composition.runner import run_graph                          # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cross_model import (                                   # noqa: E402
    _shared_published_quantities,
)

MORRIS = "morris2011.material_balance"
ZIELINSKI = "zielinski2019.rhi_process"
GANJAVE = "ganjave"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def read_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def execute(document: dict) -> tuple[dict, int]:
    payload, code = run_graph(copy.deepcopy(document), base=ROOT)
    return json.loads(json.dumps(payload, default=str)), code


def rep_of(payload: dict) -> dict:
    assert "composition_report" in payload, (
        "every document the runner writes must carry a report; an absent one "
        "is indistinguishable from a clean run"
    )
    return payload["composition_report"]


def connections_of(payload: dict) -> list[dict]:
    return rep_of(payload)["connections"]


def only_connection(payload: dict) -> dict:
    rows = connections_of(payload)
    assert len(rows) == 1, f"expected one connection, got {len(rows)}"
    return rows[0]


def diagnostics(payload: dict) -> list[dict]:
    return list(payload.get("diagnostics", []))


def codes(payload: dict) -> set[str]:
    return {str(d.get("code")) for d in diagnostics(payload)}


# --------------------------------------------------------------------------- #
# shared fixtures: the three graphs whose outcomes differ in kind
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def permitted_payload() -> dict:
    """Morris -> Morris -> Zielinski. Permitted, and it runs."""
    payload, code = execute(read_example("brass_batch_chain.json"))
    assert code == 0
    return payload


@pytest.fixture(scope="module")
def refused_payload() -> dict:
    """Ganjave dry-cell-weight -> Zielinski wet biomass. Refused before running."""
    payload, code = execute(read_example("rejected_cross_model_dcw.json"))
    assert code != 0, "the whole point of this graph is that it does not run"
    return payload


@pytest.fixture(scope="module")
def unit_mismatch_payload() -> dict:
    """A connection that fails on shape, on a boundary where a rule exists.

    Deliberately built on the Ganjave/Zielinski boundary rather than a private
    one: a careless implementation would consult the compatibility rule and
    report a scientific refusal, burying the specific mechanical problem that
    actually stopped the connection.
    """
    document = read_example("rejected_cross_model_dcw.json")
    document["graph_id"] = "report-mechanical-failure"
    document["connections"] = [{
        "connection_id": "concentration-into-a-volume",
        "source": {
            "instance_id": document["connections"][0]["source"]["instance_id"],
            "port_id": "biomass_concentration",
        },
        # mass_concentration in g/L into a port that wants a volume in L.
        "target": {
            "instance_id": document["connections"][0]["target"]["instance_id"],
            "port_id": "node:N01#starting_medium_volume",
        },
    }]
    payload, code = execute(document)
    assert code != 0
    return payload


@pytest.fixture(scope="module")
def cascade_payload() -> dict:
    """Ganjave -> Ganjave: the one permitted boundary that carries an assumption."""
    payload, code = execute(_ganjave_cascade_graph())
    assert code == 0, json.dumps(payload.get("diagnostics", []), indent=2)[:2000]
    return payload


# --------------------------------------------------------------------------- #
# the report exists, on every document, whatever the outcome
# --------------------------------------------------------------------------- #


class TestEveryGraphLeavesARecord:
    def test_a_successful_graph_carries_a_report(self, permitted_payload: dict) -> None:
        rep = rep_of(permitted_payload)
        assert rep["schema"] == report.REPORT_SCHEMA
        assert rep["graph"]["graph_id"] == "brass-batch-chain"
        assert rep["graph"]["connection_count"] == 3

    def test_a_refused_graph_carries_a_report(self, refused_payload: dict) -> None:
        rep = rep_of(refused_payload)
        assert rep["schema"] == report.REPORT_SCHEMA
        assert len(rep["connections"]) == 1

    def test_an_unreadable_document_still_carries_a_report(self) -> None:
        payload, code = run_graph(["this", "is", "not", "a", "graph"], base=ROOT)
        assert code != 0
        rep = rep_of(payload)
        assert rep["connections"] == []
        assert rep["execution"]["attempted"] is False
        assert rep["execution"]["results_produced"] is False
        # A graph nobody could read has no verdict, and saying so beats
        # emitting an empty assessment that reads like a clean bill of health.
        assert rep["graph"]["notes"] != report.NOT_DOCUMENTED

    def test_the_report_is_built_for_a_plan_only_run(self, permitted_payload: dict) -> None:
        document = read_example("brass_batch_chain.json")
        payload, _ = run_graph(document, base=ROOT, plan_only=True)
        rep = rep_of(payload)
        assert rep["execution"]["attempted"] is False
        assert rep["execution"]["results_produced"] is False
        assert "plan-only" in rep["execution"]["note"]
        # The connections were still assessed: refusing to execute is not a
        # reason to stop explaining what the graph says.
        assert len(rep["connections"]) == 3

    def test_the_report_does_not_change_the_reproducibility_digest(
        self, permitted_payload: dict
    ) -> None:
        """The digest is over numbers. Folding prose into it would be a bug."""
        again, _ = execute(read_example("brass_batch_chain.json"))
        assert (
            permitted_payload["reproducibility"] == again["reproducibility"]
        ), "the report must not perturb the digest"

    def test_the_report_lists_every_participating_model(
        self, permitted_payload: dict
    ) -> None:
        models = rep_of(permitted_payload)["science"]["models"]
        assert len(models) == 3
        assert {m["instance_id"] for m in models} == {
            "brass_charge", "brass_alloying", "zielinski_rhi",
        }
        for row in models:
            assert row["model_version"] != report.NOT_DOCUMENTED


# --------------------------------------------------------------------------- #
# Case 1 -- a mechanical failure stays mechanical, and stays specific
# --------------------------------------------------------------------------- #


class TestMechanicallyInvalidConnections:
    def test_the_specific_mechanical_reason_survives(self, unit_mismatch_payload: dict) -> None:
        row = only_connection(unit_mismatch_payload)
        assert row["disposition"] == "mechanically_invalid"
        assert row["diagnostic"]["code"] in {
            "connection.unit_mismatch",
            "connection.non_convertible",
            "connection.quantity_mismatch",
            "value.unit_unregistered",
        }

    def test_a_mechanical_refusal_is_not_dressed_up_as_a_scientific_one(
        self, unit_mismatch_payload: dict
    ) -> None:
        """No vague semantic objection may cover a precise mechanical one."""
        row = only_connection(unit_mismatch_payload)
        assert row["disposition"] == "mechanically_invalid"
        assert row["disposition_explanation"].startswith(
            "The engine's own contract rules refused this connection"
        )
        assert "not about whether the two models could" in row["disposition_explanation"]

    def test_the_engine_diagnostic_is_preserved_verbatim(
        self, unit_mismatch_payload: dict
    ) -> None:
        """The report describes; it does not re-word or replace the reason."""
        row = only_connection(unit_mismatch_payload)
        code = row["diagnostic"]["code"]
        engine_message = next(
            d["message"] for d in diagnostics(unit_mismatch_payload)
            if d.get("code") == code
        )
        assert row["diagnostic"]["message"] == engine_message

    def test_the_existing_diagnostic_is_not_duplicated_by_a_new_one(
        self, unit_mismatch_payload: dict
    ) -> None:
        """One refusal, one diagnostic. A second would double the noise."""
        row = only_connection(unit_mismatch_payload)
        assert row["diagnostic"]["code"] != "connection.cross_model_refused"
        assert "connection.cross_model_refused" not in codes(unit_mismatch_payload)

    def test_dimensional_incompatibility_is_reported_as_such(
        self, unit_mismatch_payload: dict
    ) -> None:
        assert only_connection(unit_mismatch_payload)["dimensional"]["result"] in {
            "incompatible", "unknown",
        }

    def test_a_connection_that_cannot_be_ordered_is_mechanical(self) -> None:
        """A cycle is a statement about the graph, not about the models."""
        payload, code = execute(read_example("cycle_rejected.json"))
        assert code != 0
        rows = connections_of(payload)
        assert rows, "a cyclic graph's connections must still be described"
        for row in rows:
            assert row["disposition"] == "mechanically_invalid"
            assert row["diagnostic"]["code"] == "order.cycle_detected"
            # No dimensional verdict is claimed: nobody assessed the dimensions.
            assert row["dimensional"]["result"] == "unknown"


# --------------------------------------------------------------------------- #
# Case 2 -- the dry-to-wet biomass refusal
# --------------------------------------------------------------------------- #


class TestTheDryToWetBiomassRefusal:
    def test_both_quantity_definitions_are_named(self, refused_payload: dict) -> None:
        row = only_connection(refused_payload)
        assert row["source"]["model_id"] == GANJAVE
        assert row["destination"]["model_id"] == ZIELINSKI
        # Both are mass concentrations in g/L. That is the trap, and it is why
        # the report has to show the quantities rather than just the verdict.
        assert row["source"]["quantity"] == "mass_concentration"
        assert row["destination"]["quantity"] == "mass_concentration"
        assert row["source"]["unit"] == row["destination"]["unit"]
        assert row["source"]["port_id"] != row["destination"]["port_id"]

    def test_it_is_dimensionally_compatible_and_semantically_refused(
        self, refused_payload: dict
    ) -> None:
        """The dangerous case: everything mechanical passed, and it still means
        nothing. Collapsing these two would hide the entire reason for the rule."""
        row = only_connection(refused_payload)
        assert row["dimensional"]["result"] == "compatible"
        assert row["semantic"]["result"] == "refused"
        assert row["disposition"] == "scientifically_refused"

    def test_the_applied_rule_and_its_stance_are_named(self, refused_payload: dict) -> None:
        row = only_connection(refused_payload)
        assert row["semantic"]["rule"] == "composition.cross_model"
        assert row["semantic"]["stance"] == "refused_dimensional_only:mass_concentration"
        # The rule keys on the quantity pair, not on port ids, so it cannot go
        # stale the next time a model publishes a new port.
        assert row["semantic"]["quantity_pair"] == ["mass_concentration", "mass_concentration"]

    def test_the_refusal_cites_traceable_evidence(self, refused_payload: dict) -> None:
        row = only_connection(refused_payload)
        assert row["evidence"], "a refusal with no citation is an opinion"
        joined = " ".join(row["evidence"])
        assert "ganjave" in joined.lower()
        assert any(
            token in joined.lower() for token in ("2018", "model", "form", "doi", "doi.org")
        ), f"evidence must point at a real source: {row['evidence']!r}"

    def test_the_unresolved_conversion_question_is_surfaced(
        self, refused_payload: dict
    ) -> None:
        row = only_connection(refused_payload)
        assert row["unresolved"], "the open question must not be dropped from the report"
        joined = " ".join(row["unresolved"]).lower()
        assert "dry" in joined or "wet" in joined

    def test_the_rule_reasons_are_carried_through(self, refused_payload: dict) -> None:
        row = only_connection(refused_payload)
        reason = row["semantic"]["reason"]
        assert len(reason) > 80, "a refusal must explain itself in more than a slug"

    def test_nothing_executed(self, refused_payload: dict) -> None:
        rep = rep_of(refused_payload)
        assert rep["execution"]["attempted"] is False
        assert rep["execution"]["results_produced"] is False
        assert rep["execution"]["result_count"] == 0
        assert refused_payload["results"] == []

    def test_the_diagnostic_reaches_the_document(self, refused_payload: dict) -> None:
        """The report explains; the diagnostic still refuses, with remediation."""
        refusals = [
            d for d in diagnostics(refused_payload)
            if d.get("code") == "connection.cross_model_refused"
        ]
        assert len(refusals) == 1
        assert refusals[0]["severity"] == "error"
        assert refusals[0]["remediation"]


# --------------------------------------------------------------------------- #
# Case 3 -- a permitted connection keeps its assumptions and gains no status
# --------------------------------------------------------------------------- #


class TestPermittedConnections:
    def test_morris_connections_are_permitted_and_unconditional(
        self, permitted_payload: dict
    ) -> None:
        """The Morris boundary rests on Ch.4's own conservation premise, which is
        the same across every hop, so it carries no per-connection assumption."""
        rows = connections_of(permitted_payload)
        assert rows
        for row in rows:
            assert row["disposition"] == "permitted"
            assert row["assumptions"] == []
            assert row["semantic"]["evidence_basis"] == "permitted"

    def test_a_permitted_connection_is_never_labelled_validated(
        self, permitted_payload: dict
    ) -> None:
        for row in connections_of(permitted_payload):
            blob = json.dumps(row).lower()
            for word in ("validated", "verified", "reproduced"):
                assert word not in blob, (
                    f"a permitted connection must not be described as {word}"
                )

    def test_the_ganjave_cascade_is_permitted_conditionally(
        self, cascade_payload: dict
    ) -> None:
        """A forward cascade needs the upstream value to be glycerol in this
        medium. That premise is read from the model's own contract, not restated
        here, so it cannot drift away from what the model says."""
        row = only_connection(cascade_payload)
        assert row["disposition"] == "permitted_conditionally"
        assert row["assumptions"], "a conditional permission must state its condition"
        assumption = row["assumptions"][0]
        declared = next(
            r.assumption for r in INPUT_CONTRACT
            if r.port_id == "initial_glycerol_concentration"
        )
        assert declared in assumption, (
            "the assumption must be the model's own words, not a paraphrase"
        )

    def test_the_combined_graph_is_never_validated_by_a_clean_run(
        self, permitted_payload: dict, cascade_payload: dict
    ) -> None:
        for payload in (permitted_payload, cascade_payload):
            combined = rep_of(payload)["science"]["combined_graph"]
            assert combined["independently_validated"] is False
            assert combined["status"] == "not_established"
            assert combined["basis"].strip()
            assert combined["execution_is_not_validation"].strip()

    def test_a_model_without_a_validation_claim_is_reported_as_undocumented(
        self, permitted_payload: dict
    ) -> None:
        """Morris publishes no claim through this boundary. That is neither a
        validated model nor an unvalidated one, and 'undocumented' is the only
        honest label."""
        rows = rep_of(permitted_payload)["science"]["models"]
        assert rows
        for row in rows:
            assert row["reproduction_status"] == report.NOT_DOCUMENTED
            assert row["implementation_status"] == report.NOT_DOCUMENTED
            assert row["source"] == report.NOT_DOCUMENTED

    def test_a_model_that_does_publish_a_claim_is_quoted_not_summarised(
        self, cascade_payload: dict
    ) -> None:
        """Ganjave states its own standing. The report repeats it; it does not
        upgrade it, and it does not extend it to the composition."""
        rows = rep_of(cascade_payload)["science"]["models"]
        assert rows
        for row in rows:
            assert row["model_id"] == GANJAVE
            assert row["reproduction_status"] != report.NOT_DOCUMENTED
            assert "boundary" in row["source"]
        # Ganjave's own words say not_yet_validated; nothing here may improve
        # on that, least of all because the software tests pass.
        assert all(
            row["reproduction_status"] == "not_yet_validated" for row in rows
        )
        assert rep_of(cascade_payload)["science"]["combined_graph"][
            "independently_validated"
        ] is False

    def test_declared_model_limitations_are_carried(self, permitted_payload: dict) -> None:
        rows = rep_of(permitted_payload)["science"]["models"]
        assert any(row["limitations"]["source"] != report.NOT_DOCUMENTED for row in rows)
        for row in rows:
            assert "declared_unsupported_capabilities" in row["limitations"]
            assert "declared_missing_information" in row["limitations"]


# --------------------------------------------------------------------------- #
# Case 4 -- an unclassified pair is evidence-limited, not refuted
# --------------------------------------------------------------------------- #


def _ganjave_cascade_graph() -> dict:
    """One Ganjave culture feeding its glycerol concentration into a second.

    The second culture's other required inputs are declared as literals cloned
    from the first, exactly as an operator would have to: the model requires
    them and the adapter will not invent a default. Only ``initial_glycerol``
    arrives over a connection.
    """
    example = read_example("ganjave_fed_batch.json")
    source = json.loads(json.dumps(example["instances"][0]))
    second = json.loads(json.dumps(source))
    second["instance_id"] = "second_culture"
    second["label"] = "downstream culture on the first culture's spent medium"
    second["position"] = {"x": 560, "y": 120}

    literals: dict = {}
    for key, value in example["literal_inputs"].items():
        literals[key] = value
        literals[key.replace(source["instance_id"], "second_culture")] = \
            json.loads(json.dumps(value))

    return {
        "contract_version": "0.1.0",
        "graph_id": "ganjave-forward-cascade",
        "title": "Ganjave fed-batch forward cascade",
        "instances": [source, second],
        "connections": [{
            "connection_id": "glycerol-forward",
            "source": {"instance_id": source["instance_id"],
                       "port_id": "glycerol_concentration"},
            "target": {"instance_id": "second_culture",
                       "port_id": "initial_glycerol_concentration"},
        }],
        "literal_inputs": literals,
        "defaults": {},
    }


def _unclassified_verdict() -> "cross_model.Verdict":
    """What ``cross_model`` says about a pair no rule names.

    Built from the real rule table rather than hard-coded, so this test tracks
    the policy instead of restating it.
    """
    verdict = cross_model.check(
        source_model=GANJAVE, source_port_id="out:stream:x",
        source_quantity="quantity_no_rule_names",
        target_model=ZIELINSKI, target_port_id="in:stream:y",
        target_quantity="quantity_no_other_rule_names",
    )
    assert verdict is not None
    return verdict


class TestUnclassifiedQuantityPairs:
    def test_the_policy_still_fails_closed(self) -> None:
        verdict = _unclassified_verdict()
        assert verdict.permitted is False
        assert verdict.stance == "refused_unclassified"

    def test_the_verdict_says_its_basis_is_evidence(self) -> None:
        assert _unclassified_verdict().evidence_basis == "evidence_limited"

    def test_the_verdict_does_not_claim_physical_incompatibility(self) -> None:
        """The whole distinction. A refusal because nobody wrote anything down
        is not a finding that the two quantities cannot be connected."""
        reason = _unclassified_verdict().reason
        assert "not a documented finding" in reason
        assert "physically incompatible" in reason

    def test_an_unclassified_pair_reports_as_unresolved(self) -> None:
        """End of the mapping the Godot panel keys off: an evidence-limited
        refusal must present as `unresolved`, never as `scientifically_refused`.
        Presenting it as a refutation would be the exact conflation this report
        exists to prevent."""
        verdict = _unclassified_verdict()
        diagnostic = ModelDiagnostic(
            code=DiagnosticCode.CONNECTION_CROSS_MODEL_REFUSED,
            severity=Severity.ERROR,
            message="refused",
            where=("connection", "c1"),
        )
        assert report.disposition_for(diagnostic, verdict) == "unresolved"
        assert report.disposition_for(diagnostic, verdict) != "scientifically_refused"

    def test_a_documented_incompatibility_still_reports_as_refused(
        self, refused_payload: dict
    ) -> None:
        """The mapping has to discriminate, not blanket everything to
        `unresolved`."""
        row = only_connection(refused_payload)
        assert row["semantic"]["evidence_basis"] == "documented_incompatibility"
        assert row["disposition"] == "scientifically_refused"

    def test_the_two_bases_are_never_conflated(self) -> None:
        unclassified = _unclassified_verdict()
        documented = cross_model.check(
            source_model=GANJAVE, source_port_id="out:t:500:biomass_concentration",
            source_quantity="mass_concentration",
            target_model=ZIELINSKI,
            target_port_id="in:node:N01#wet_biomass_g_per_L_reported",
            target_quantity="mass_concentration",
        )
        assert documented is not None and documented.permitted is False
        assert unclassified.evidence_basis != documented.evidence_basis
        assert unclassified.reason != documented.reason

    def test_the_schema_names_the_three_evidence_bases(self) -> None:
        """A consumer has to be able to tell the bases apart without prose, so
        the declared set must be the set the policy actually emits -- derived,
        not restated."""
        emitted = {
            cross_model.check(
                source_model=boundary.source_model,
                source_port_id="out",
                source_quantity=boundary.rules[0][0] if boundary.rules else "q",
                target_model=boundary.target_model,
                target_port_id="in",
                target_quantity=boundary.rules[0][1] if boundary.rules else "q",
            ).evidence_basis
            for boundary in cross_model.BOUNDARIES
            if not boundary.enforced_by_engine
        }
        assert emitted <= set(report.EVIDENCE_BASES)
        assert emitted == {"documented_incompatibility", "evidence_limited", "permitted"}

    def test_every_registered_pair_is_classified_so_no_shipped_graph_is_unclassified(
        self,
    ) -> None:
        """A fact about the registry, not a wish: every quantity Ganjave can
        publish and Zielinski can accept is covered by a rule, so no example
        graph can currently exercise `refused_unclassified` end to end.

        Asserted so that when someone adds a port this fails loudly and the
        Case-4 example becomes buildable -- rather than the gap going unnoticed.
        """
        classified = {pair for b in cross_model.BOUNDARIES for pair in b.rules}
        shared = _shared_published_quantities()
        uncovered = {s for s in shared if s != "volume_flow"} - {
            s for s, _t in classified
        }
        assert not uncovered, (
            f"{sorted(uncovered)} is connectable but unclassified: ship a refusal "
            f"example for it, or delete this assertion on purpose"
        )

    def test_the_disposition_list_covers_the_documented_incompatibility(self) -> None:
        assert "scientifically_refused" in report.DISPOSITIONS
        assert "unresolved" in report.DISPOSITIONS


# --------------------------------------------------------------------------- #
# Case 5 -- previous results cannot be presented as current
# --------------------------------------------------------------------------- #


class TestStaleness:
    def test_a_fresh_report_is_not_marked_invalidated(self, permitted_payload: dict) -> None:
        assert rep_of(permitted_payload)["execution"]["results_invalidated"] is False

    def test_invalidation_is_recorded_when_the_runner_is_told_to(self) -> None:
        rep = report.build_report(
            {"graph_id": "g", "title": "t", "instances": [], "connections": []},
            {}, [], None, execution_attempted=False,
            previous_results_invalidated=True,
        )
        assert rep["execution"]["results_invalidated"] is True

    def test_a_stale_report_carries_no_results(self) -> None:
        """Marking staleness must not smuggle old numbers back in."""
        rep = report.build_report(
            {"graph_id": "g", "title": "t", "instances": [], "connections": []},
            {}, [], None, previous_results_invalidated=True,
        )
        assert rep["execution"]["results_produced"] is False
        assert rep["execution"]["result_count"] == 0
        assert rep["execution"]["attempted"] is False

    def test_the_report_has_no_results_field_to_go_stale(
        self, permitted_payload: dict
    ) -> None:
        """Staleness is about the execution block's own flags. If the report
        ever started embedding results, this would be the place it would go
        wrong, so the shape is pinned here."""
        assert "results" not in rep_of(permitted_payload)


# --------------------------------------------------------------------------- #
# Case 6 -- provenance is described, never re-invented
# --------------------------------------------------------------------------- #


class TestProvenanceIsNotDisturbed:
    def test_the_report_does_not_touch_the_provenance_index(
        self, permitted_payload: dict
    ) -> None:
        """The report is an addition, not a rewrite: the existing provenance
        reaches the document unchanged."""
        assert permitted_payload["provenance_index"], "the graph should have provenance"
        assert "provenance_index" not in rep_of(permitted_payload), (
            "the report describes provenance; it must not restate or replace it"
        )

    def test_source_transfer_and_receiving_instance_are_all_named(
        self, permitted_payload: dict
    ) -> None:
        """A carried value's chain names where it came from, that it was passed
        rather than recomputed, and which instance consumed it."""
        chain = permitted_payload["provenance_index"]["brass_alloying/out:A:w:Cu"]
        kinds = [record["kind"] for record in chain]
        assert kinds == ["source", "transfer", "source"], kinds

        upstream, transfer, downstream = chain
        assert upstream["where"] == "instance:brass_charge"
        assert upstream["connection_id"] is None

        assert transfer["kind"] == "transfer"
        assert transfer["connection_id"] == "c2"
        assert transfer["source_port"] == "out:D:w:Cu"
        assert transfer["target_port"] == "in:A:w:Cu"
        assert "no value was recomputed" in transfer["method"]

        assert downstream["where"] == "instance:brass_alloying"

    def test_a_computed_output_is_not_credited_to_the_upstream_instance(
        self, permitted_payload: dict
    ) -> None:
        """The alloying culture recomputed its copper fraction from its own
        inputs. Its record must name itself, not the charge it was fed.

        Crediting it upstream would assert that the balance closed, and only a
        residual can establish that -- the report must not imply it.
        """
        chain = permitted_payload["provenance_index"]["brass_alloying/out:A:w:Cu"]
        computed = [r for r in chain if r["where"] == "instance:brass_alloying"]
        assert len(computed) == 1
        record = computed[0]
        assert record["producer_model"] == MORRIS
        assert record["producer_version"] == "0.1.0"
        assert record["connection_id"] is None
        assert record["source_port"] is None
        assert record["target_port"] is None
        assert "solve_balance" in record["detail"]

    def test_a_transferred_value_is_never_marked_computed_by_the_report(
        self, permitted_payload: dict
    ) -> None:
        transfers = [
            record
            for chain in permitted_payload["provenance_index"].values()
            for record in chain
            if record["kind"] == "transfer"
        ]
        assert transfers, "the chain graph transfers values"
        for record in transfers:
            assert record["conversion"] is None, (
                "no conversion was performed, so none may be claimed"
            )

    def test_the_report_names_no_balance_it_did_not_evaluate(
        self, permitted_payload: dict
    ) -> None:
        """Residuals belong to the balance that computes them."""
        blob = json.dumps(rep_of(permitted_payload)).lower()
        for claim in ("balance closed", "conservation verified",
                      "mass balance holds", "balance holds"):
            assert claim not in blob


# --------------------------------------------------------------------------- #
# Case 7 -- the report is machine-readable
# --------------------------------------------------------------------------- #


class TestMachineReadable:
    def test_the_report_survives_a_json_round_trip(self, permitted_payload: dict) -> None:
        rep = rep_of(permitted_payload)
        assert json.loads(json.dumps(rep)) == rep

    def test_the_report_survives_the_runner_subprocess(
        self, tmp_path: Path
    ) -> None:
        """The Godot panel reads the file the runner writes, not an in-process
        object. Anything unserialisable is invisible to it."""
        import subprocess
        import sys as _sys

        out = tmp_path / "result.json"
        proc = subprocess.run(
            [_sys.executable, "-m", "composition.runner",
             "--graph", str(EXAMPLES / "brass_batch_chain.json"),
             "--result", str(out)],
            cwd=COMPOSITION_ROOT, capture_output=True, text=True,
            env={"PYTHONPATH": str(COMPOSITION_ROOT), "PATH": ""},
        )
        assert proc.returncode == 0, proc.stderr[-2000:]
        written = json.loads(out.read_text(encoding="utf-8"))
        assert written["composition_report"]["schema"] == report.REPORT_SCHEMA
        assert written["composition_report"]["connections"]

    def test_the_schema_is_declared_and_versioned(self, permitted_payload: dict) -> None:
        assert report.REPORT_SCHEMA.count("/") == 1
        assert rep_of(permitted_payload)["schema"] == report.REPORT_SCHEMA

    def test_every_connection_carries_the_declared_keys(
        self, permitted_payload: dict, refused_payload: dict
    ) -> None:
        expected = {
            "connection_id", "source", "destination", "dimensional", "semantic",
            "disposition", "disposition_explanation", "diagnostic", "evidence",
            "assumptions", "unresolved", "remediation", "other_diagnostics",
        }
        for payload in (permitted_payload, refused_payload):
            for row in connections_of(payload):
                assert expected <= set(row), f"missing: {expected - set(row)}"

    def test_the_unknown_sentinel_is_distinguishable_from_empty(
        self, permitted_payload: dict
    ) -> None:
        """`not_documented` means nobody said; `[]` means somebody said nothing.
        Collapsing them would let an empty list read as an absence of issues."""
        assert report.NOT_DOCUMENTED == "not_documented"
        row = rep_of(permitted_payload)["connections"][0]
        assert row["assumptions"] == []
        assert row["diagnostic"]["code"] == report.NOT_DOCUMENTED

    def test_every_disposition_used_is_declared(self) -> None:
        assert "compatible" not in report.DISPOSITIONS, (
            "a single boolean would be exactly the collapse this task forbids"
        )
        assert report.DISPOSITIONS[:3] == (
            "mechanically_invalid", "scientifically_refused", "permitted_conditionally"
        )

    def test_no_disposition_is_a_boolean(self, permitted_payload: dict) -> None:
        for row in connections_of(permitted_payload):
            assert isinstance(row["disposition"], str)
            assert "compatible" not in row


# --------------------------------------------------------------------------- #
# the report describes; it never decides
# --------------------------------------------------------------------------- #


class TestTheReportDecidesNothing:
    def test_there_is_no_second_rule_table_in_the_report(
        self, refused_payload: dict
    ) -> None:
        """Only the rule's own name appears -- never a model id list or a
        quantity pair list, either of which could drift from cross_model."""
        blob = json.dumps(rep_of(refused_payload))
        assert '"ganjave"' not in blob.replace('"model_id": "ganjave"', "")

    def test_the_execution_block_never_claims_a_scientific_outcome(
        self, permitted_payload: dict
    ) -> None:
        execution = rep_of(permitted_payload)["execution"]
        assert set(execution) >= {
            "attempted", "status", "results_produced", "result_count",
            "error_count", "warning_count", "results_invalidated",
        }
        for value in execution.values():
            if isinstance(value, str):
                assert "validated" not in value.lower()

    def test_the_reading_guide_states_the_four_way_distinction(
        self, permitted_payload: dict
    ) -> None:
        guide = rep_of(permitted_payload)["reading_guide"]
        assert set(guide["dispositions"]) == set(report.DISPOSITIONS)
        note = guide["note"].lower()
        for question in ("mechanical", "semantic", "execution", "scientific"):
            assert question in note
