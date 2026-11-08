"""XM-01 -- cross-model composition boundaries.

Every boundary between two registered models, tested from both ends: the one
that is permitted, and the ones that are refused. A refusal is only worth
anything if the reason survives into the diagnostic and can be read, so the
tests here assert the *content* of the refusal and not merely that a run failed.

Two questions this suite exists to keep honest:

1. **A matching unit is not a connection.** There are real pairs in this
   repository where the quantity matches, the unit converts, and the connection
   is still scientifically wrong. ``ganjave/biomass_concentration`` and
   ``zielinski/node:N01#wet_biomass_g_per_L_reported`` are both
   ``mass_concentration`` in ``g/L`` and both describe an *E. coli* culture. They
   are dry-cell weight and wet biomass in two different experiments. Connecting
   them is refused.
2. **A refusal must come before execution, not after.** These graphs validate
   mechanically. Before XM-01 the engine accepted them and ran them to a
   ``success_with_warnings``; a reader had no way to tell that the connection
   meant nothing.

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
EXAMPLES = COMPOSITION_ROOT / "examples"
sys.path.insert(0, str(COMPOSITION_ROOT))

from composition import cross_model                                    # noqa: E402
from composition.adapters import REGISTRATIONS                        # noqa: E402
from composition.adapters.ganjave_contract import INPUT_CONTRACT      # noqa: E402
from composition.diagnostics import DiagnosticCode, Severity          # noqa: E402
from composition.dimensions import (                                  # noqa: E402
    GANJAVE_KIND_TO_QUANTITY,
    MORRIS_KIND_TO_QUANTITY,
)
from composition.quantities import Quantity                            # noqa: E402
from composition.runner import run_graph                              # noqa: E402

MORRIS = "morris2011.material_balance"
ZIELINSKI = "zielinski2019.rhi_process"
GANJAVE = "ganjave"

CROSS_REFUSED = DiagnosticCode.CONNECTION_CROSS_MODEL_REFUSED.value


def read_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def execute(document: dict) -> tuple[dict, int]:
    payload, code = run_graph(copy.deepcopy(document), base=ROOT)
    return json.loads(json.dumps(payload, default=str)), code


def ganjave_instance() -> dict:
    return read_example("ganjave_fed_batch.json")["instances"][0]


def ganjave_literals() -> dict:
    return read_example("ganjave_fed_batch.json")["literal_inputs"]


def zielinski_instance() -> dict:
    return {
        "instance_id": "zielinski_rhi",
        "model_id": ZIELINSKI,
        "model_version": "1.0.0",
        "label": "Recombinant human insulin process",
        "role": "independent published process",
        "position": {"x": 560, "y": 120},
        "parameters": {"execution": {"mode": "evidence_replay"}},
    }


def two_model_graph(source: dict, source_port: str, target: dict, target_port: str):
    """One connection between two instances, with Ganjave's inputs declared."""
    document = {
        "contract_version": "0.1.0",
        "graph_id": "cross-model-probe",
        "title": "cross-model probe",
        "instances": [copy.deepcopy(source), copy.deepcopy(target)],
        "connections": [{
            "connection_id": "c1",
            "source": {"instance_id": source["instance_id"], "port_id": source_port},
            "target": {"instance_id": target["instance_id"], "port_id": target_port},
        }],
        "literal_inputs": ganjave_literals(),
        "defaults": {},
    }
    return document


def refusals(payload: dict) -> list[dict]:
    return [d for d in payload.get("diagnostics", []) if d.get("code") == CROSS_REFUSED]


def _published_quantities(model_id: str) -> tuple[set[str], set[str]]:
    """``(input quantities, output quantities)`` the model actually publishes."""
    from composition.runner import describe_model

    payload, code = describe_model(model_id)
    assert code == 0, f"{model_id} did not describe itself"
    inputs, outputs = set(), set()
    for port in payload["manifest"]["ports"]:
        (inputs if port["direction"] == "input" else outputs).add(port["quantity"])
    return inputs, outputs


def _shared_published_quantities() -> set[str]:
    """Quantities one model publishes as an output and the other accepts."""
    ganjave_out = _published_quantities(GANJAVE)[1]
    zielinski_in = _published_quantities(ZIELINSKI)[0]
    return ganjave_out & zielinski_in


def executed(payload: dict) -> list[str]:
    return [r["instance_id"] for r in payload.get("results", [])]


# --------------------------------------------------------------------------- #
# the permitted boundary
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def brass_chain() -> dict:
    """The one shipped graph that carries material between two instances."""
    payload, code = execute(read_example("brass_batch_chain.json"))
    assert code == 0, json.dumps(payload.get("diagnostics", []), indent=2)
    return payload


class TestThePermittedBoundary:
    """Morris -> Morris: conservation across non-reacting control volumes."""

    def test_it_runs_and_the_balance_closes(self, brass_chain):
        assert brass_chain["status"].startswith("success"), brass_chain["status"]
        instances = {r["instance_id"]: r for r in brass_chain["results"]}
        assert set(instances) == {"brass_charge", "brass_alloying", "zielinski_rhi"}
        assert all(r["status"].startswith("success") for r in brass_chain["results"])

    def test_exactly_two_boundaries_are_permitted(self):
        permitted = sorted(
            (b.source_model, b.target_model) for b in cross_model.BOUNDARIES
            if b.permitted
        )
        assert permitted == [(GANJAVE, GANJAVE), (MORRIS, MORRIS)], (
            "a new permitted boundary needs a source of its own and a test of "
            "its own; do not widen this list to make something pass"
        )

    def test_provenance_survives_the_hop(self, brass_chain):
        """A value forwarded through an instance still names where it came from.

        This is the half of CG-07 that had no test: the injected *input*
        carried a transfer record, but the *output* that re-publishes it named
        only the instance that re-published it. A propagated quantity whose
        chain stopped at the second instance is a propagated quantity with no
        evidence of where it was propagated from.
        """
        alloy = next(r for r in brass_chain["results"] if r["instance_id"] == "brass_alloying")
        outputs = {o["ref"]["port_id"]: o for o in alloy["outputs"]}

        forwarded = outputs["out:A:w:Cu"]
        kinds = [record["kind"] for record in forwarded["provenance_chain"]]
        assert kinds == ["source", "transfer", "source"], kinds
        assert forwarded["provenance_chain"][0]["where"] == "instance:brass_charge"
        assert forwarded["provenance_chain"][1]["connection_id"] == "c2"
        assert forwarded["provenance_chain"][1]["source_port"] == "out:D:w:Cu"
        assert forwarded["provenance_chain"][1]["target_port"] == "in:A:w:Cu"
        assert forwarded["provenance_chain"][2]["where"] == "instance:brass_alloying"

    def test_a_computed_total_is_not_credited_to_its_inputs(self, brass_chain):
        """The stream total is the sum the balance computed, not what it was fed.

        Crediting it to the upstream total would assert the balance closed --
        which is the thing a material balance exists to test. It must keep its
        own record alone.
        """
        alloy = next(r for r in brass_chain["results"] if r["instance_id"] == "brass_alloying")
        total = next(o for o in alloy["outputs"] if o["ref"]["port_id"] == "out:A:total")
        assert [r["kind"] for r in total["provenance_chain"]] == ["source"]

        solved = next(o for o in alloy["outputs"] if o["ref"]["port_id"] == "out:E:Cu")
        assert [r["kind"] for r in solved["provenance_chain"]] == ["source"]

    def test_propagation_does_not_change_any_value(self):
        """The provenance change moved records, not numbers."""
        payload, code = execute(read_example("brass_batch_chain.json"))
        assert code == 0
        upstream = next(r for r in payload["results"] if r["instance_id"] == "brass_charge")
        forwarded = next(o for o in upstream["outputs"]
                         if o["ref"]["port_id"] == "out:D:w:Cu")
        downstream, _ = execute(read_example("brass_batch_chain.json"))
        alloy = next(r for r in downstream["results"] if r["instance_id"] == "brass_alloying")
        mirror = next(o for o in alloy["outputs"] if o["ref"]["port_id"] == "out:A:w:Cu")
        assert forwarded["value"]["value"] == mirror["value"]["value"]

    def test_the_boundary_records_its_evidence(self):
        verdict = cross_model.check(
            MORRIS, "out:D:w:Cu", "mass_fraction", MORRIS, "in:A:w:Cu", "mass_fraction"
        )
        assert verdict is not None and verdict.permitted
        assert verdict.evidence, "a permitted boundary must say what supports it"
        assert any("Morris, Geiger & Fine (2011)" in e for e in verdict.evidence)


# --------------------------------------------------------------------------- #
# the refusals that need no new rule: the engine already owns them
# --------------------------------------------------------------------------- #


class TestBoundariesTheEngineAlreadyRefuses:
    """No duplicate diagnostic, and no weakening of the existing rules."""

    def test_morris_into_zielinski_is_refused_by_the_component_rules(self):
        document = two_model_graph(
            read_example("cycle_rejected.json")["instances"][0],
            "out:D:total",
            zielinski_instance(),
            "node:N01#wet_biomass_from_inputs",
        )
        payload, code = execute(document)
        assert code != 0
        codes = {d["code"] for d in payload["diagnostics"]}
        assert DiagnosticCode.CONNECTION_COMPONENT_MISMATCH.value in codes
        # The cross-model rule must not pile a second refusal on top.
        assert CROSS_REFUSED not in codes

    def test_zielinski_into_morris_is_refused_as_unattributed(self):
        document = two_model_graph(
            zielinski_instance(),
            "stream:S03_wet_biomass#wet_biomass_total",
            read_example("cycle_rejected.json")["instances"][0],
            "in:C:total",
        )
        payload, code = execute(document)
        assert code != 0
        codes = {d["code"] for d in payload["diagnostics"]}
        assert DiagnosticCode.CONNECTION_COMPONENT_UNATTRIBUTED.value in codes
        assert DiagnosticCode.CAPABILITY_REACTIVE_BALANCE_REFUSED.value in codes
        assert CROSS_REFUSED not in codes

    def test_morris_and_ganjave_share_no_quantity_at_all(self):
        """Not a refusal -- there is nothing to refuse."""
        morris = {q.value for q in MORRIS_KIND_TO_QUANTITY.values()}
        ganjave = {q.value for q in GANJAVE_KIND_TO_QUANTITY.values()}
        assert morris.isdisjoint(ganjave), morris & ganjave
        assert cross_model.boundary_for(MORRIS, GANJAVE).dimensional_note


# --------------------------------------------------------------------------- #
# the refusals XM-01 added: dimensionally legal, scientifically unsupported
# --------------------------------------------------------------------------- #


class TestDimensionallyLegalButUnsupported:
    """The acceptance case: real candidates that the mechanical rules let through."""

    #: (source port, target port, quantity pair, a phrase the reason must carry)
    CANDIDATES = [
        (
            GANJAVE, "biomass_concentration",
            ZIELINSKI, "node:N01#wet_biomass_g_per_L_reported",
            ("mass_concentration", "mass_concentration"),
            ("dry-cell weight", "wet biomass"),
        ),
        (
            GANJAVE, "glycerol_concentration",
            ZIELINSKI, "node:N01#glucose_target_initial",
            ("mass_concentration", "mass_concentration"),
            ("glycerol", "residual glycerol"),
        ),
        (
            GANJAVE, "culture_volume",
            ZIELINSKI, "node:N01#starting_medium_volume",
            ("volume", "volume"),
            ("working volume", "charges made at t = 0"),
        ),
        (
            GANJAVE, "dissolved_oxygen",
            ZIELINSKI, "node:N01#ph_stat_dead_band",
            ("dimensionless", "dimensionless"),
            ("dimensionless", "one dimensionless quantity"),
        ),
        (
            GANJAVE, "simulation_time",
            ZIELINSKI, "node:N01#growth_duration",
            ("time", "time"),
            ("horizon", "residence times"),
        ),
    ]

    @pytest.mark.parametrize("src,src_port,tgt,tgt_port,quantities,phrases", CANDIDATES)
    def test_it_is_refused_before_execution(
        self, src, src_port, tgt, tgt_port, quantities, phrases
    ):
        document = two_model_graph(
            ganjave_instance(), src_port, zielinski_instance(), tgt_port
        )
        payload, code = execute(document)
        assert code != 0, f"{src_port} -> {tgt_port} was accepted"
        assert payload["status"] == "invalid", payload["status"]
        assert executed(payload) == [], (
            "a refused connection must stop the run before any model executes; "
            f"these ran anyway: {executed(payload)}"
        )
        found = refusals(payload)
        assert len(found) == 1, [d["code"] for d in payload["diagnostics"]]
        assert found[0]["severity"] == Severity.ERROR.value

    @pytest.mark.parametrize("src,src_port,tgt,tgt_port,quantities,phrases", CANDIDATES)
    def test_the_refusal_says_why_in_its_own_words(
        self, src, src_port, tgt, tgt_port, quantities, phrases
    ):
        document = two_model_graph(
            ganjave_instance(), src_port, zielinski_instance(), tgt_port
        )
        payload, _code = execute(document)
        diagnostic = refusals(payload)[0]
        message = diagnostic["message"]
        assert "dimensionally legal and scientifically unsupported" in message
        for phrase in phrases:
            assert phrase in message, f"{phrase!r} missing from:\n{message}"

    @pytest.mark.parametrize("src,src_port,tgt,tgt_port,quantities,phrases", CANDIDATES)
    def test_the_refusal_carries_its_evidence_and_its_remediation(
        self, src, src_port, tgt, tgt_port, quantities, phrases
    ):
        document = two_model_graph(
            ganjave_instance(), src_port, zielinski_instance(), tgt_port
        )
        payload, _code = execute(document)
        diagnostic = refusals(payload)[0]
        assert diagnostic["remediation"], "a refusal must say what to do instead"
        evidence = diagnostic["detail"]["evidence"]
        assert len(evidence) >= 2
        joined = " ".join(evidence)
        assert "Ganjave et al. (2022)" in joined
        assert "Zielinski et al. (2019)" in joined
        assert diagnostic["detail"]["unresolved"], (
            "a refusal must record what is unresolved, not only what is wrong"
        )
        assert list(diagnostic["detail"]["quantity_pair"]) == list(quantities)

    def test_the_reverse_direction_is_refused_too(self):
        """The rule is not directional: a refusal must not depend on arrow order."""
        document = two_model_graph(
            zielinski_instance(),
            "stream:S09_deae_fraction#fraction_volume",
            ganjave_instance(),
            "initial_culture_volume",
        )
        payload, code = execute(document)
        assert code != 0
        found = refusals(payload)
        assert found, [d["code"] for d in payload["diagnostics"]]
        assert "eluate" in found[0]["message"] or "chromatograph" in found[0]["message"]

    def test_a_zielinski_percent_cannot_drive_a_dissolved_oxygen_reading(self):
        """Both are '%'. Neither is a dissolved-oxygen percentage."""
        document = two_model_graph(
            zielinski_instance(),
            "node:N05#implied_refolding_yield_pct",
            ganjave_instance(),
            "initial_dissolved_oxygen",
        )
        payload, code = execute(document)
        assert code != 0
        found = refusals(payload)
        assert found, [d["code"] for d in payload["diagnostics"]]
        assert "dimensionless" in found[0]["message"]

    def test_an_optical_density_cannot_drive_a_dissolved_oxygen_reading(self):
        """Already refused mechanically, and must stay that way."""
        document = two_model_graph(
            zielinski_instance(),
            "stream:S02_culture_broth#od600_plateau_max",
            ganjave_instance(),
            "initial_dissolved_oxygen",
        )
        payload, code = execute(document)
        assert code != 0
        codes = {d["code"] for d in payload["diagnostics"]}
        assert DiagnosticCode.CONNECTION_NON_CONVERTIBLE.value in codes

    def test_every_quantity_pair_the_rules_cover_is_a_real_candidate(self):
        """A rule that names a pair no manifest pair can produce is dead policy.

        The shared set is taken from the *published* ports, not from the kind
        tables: a kind may exist in a model and never reach a port, and a rule
        covering a pair of kinds that cannot occur would be policy written for
        a hypothetical.
        """
        covered = {pair for b in cross_model.BOUNDARIES for pair in b.rules}
        assert covered, "no quantity rules are declared"

        shared = _shared_published_quantities()
        assert shared, "the two cultures publish no shared quantity at all"
        for source_q, target_q in covered:
            assert source_q in shared, source_q
            assert target_q in shared, target_q
        assert {s for s, _t in covered} == {s for s in shared if s != "volume_flow"}


# --------------------------------------------------------------------------- #
# the shipped examples
# --------------------------------------------------------------------------- #


class TestTheShippedRefusals:
    """The refusals are inspectable from the Godot Load example menu."""

    @pytest.mark.parametrize("name,stance_fragment", [
        ("rejected_cross_model_dcw.json", "mass_concentration"),
        ("rejected_cross_model_fraction_volume.json", "volume"),
    ])
    def test_each_example_is_refused_with_its_reason(self, name, stance_fragment):
        payload, code = execute(read_example(name))
        assert code == 1, "a refused graph exits 1: the input was not runnable"
        assert payload["status"] == "invalid"
        assert executed(payload) == []
        found = refusals(payload)
        assert len(found) == 1
        assert stance_fragment in found[0]["detail"]["stance"]
        assert found[0]["remediation"]

    def test_each_example_states_what_it_demonstrates(self):
        for name in ("rejected_cross_model_dcw.json",
                     "rejected_cross_model_fraction_volume.json"):
            document = read_example(name)
            assert document["notes"]
            assert document["source_ref"]
            assert "Expected:" in document["notes"]


class TestSameModelOnBothSides:
    """Two self-pairs, two different answers, and each with its own reason.

    This pair of tests exists because the first draft of the policy refused
    both on "there is no iterative solve". That was wrong for Ganjave, and the
    project's own ``TestFailurePropagation`` suite -- which cascades residual
    glycerol from one culture into the next -- is what proved it wrong. A
    forward chain is ordered once and never iterates; only a cycle would need
    a solve it does not have.
    """

    def test_ganjave_cascades_into_a_second_culture(self):
        verdict = cross_model.check(
            GANJAVE, "glycerol_concentration", "mass_concentration",
            GANJAVE, "initial_glycerol_concentration", "mass_concentration",
        )
        assert verdict is not None and verdict.permitted
        assert verdict.stance == "permitted_forward_cascade"
        assert "forward cascade" in verdict.reason
        # It is permitted *under an assumption*, not as a validated coupling.
        assert verdict.unresolved, (
            "a permitted cascade must still record what is unresolved; the "
            "paper does not seed a second culture from the first"
        )
        assert "not" in verdict.unresolved[0] and "validat" in verdict.unresolved[0]

    def test_the_cascade_still_runs_and_is_not_refused(self):
        """The engine's own suite proves the cascade; this proves we allow it."""
        document = read_example("ganjave_fed_batch.json")
        second = copy.deepcopy(document["instances"][0])
        second["instance_id"] = "stage_b"
        second["parameters"]["simulation"]["mode"] = "batch"
        document["instances"].append(second)
        document["connections"] = [{
            "connection_id": "c1",
            "source": {"instance_id": "ganjave_fed_batch",
                       "port_id": "glycerol_concentration"},
            "target": {"instance_id": "stage_b",
                       "port_id": "initial_glycerol_concentration"},
        }]
        for name, spec in list(document["literal_inputs"].items()):
            document["literal_inputs"][f"stage_b/{name.split('/', 1)[1]}"] = copy.deepcopy(spec)
        document["literal_inputs"].pop("stage_b/initial_glycerol_concentration", None)

        payload, code = execute(document)
        assert CROSS_REFUSED not in {d["code"] for d in payload["diagnostics"]}
        assert code == 0, json.dumps(payload["diagnostics"][:3], indent=2)
        assert str(payload["status"]).startswith("success")

    def test_zielinski_declares_no_supplyable_port_at_all(self):
        verdict = cross_model.check(
            ZIELINSKI, "node:N02#wet_biomass_g_per_L", "mass_concentration",
            ZIELINSKI, "node:N01#wet_biomass_g_per_L_reported", "mass_concentration",
        )
        assert verdict is not None and not verdict.permitted
        assert verdict.stance == "refused_no_supplyable_port"
        assert "declares no port as supplyable" in verdict.reason


# --------------------------------------------------------------------------- #
# the declared position, as data
# --------------------------------------------------------------------------- #


class TestTheDeclaredPosition:
    """`--describe-connections` is the inspectable form of the whole judgement."""

    def test_the_runner_prints_it(self):
        completed = subprocess.run(
            [sys.executable, "-m", "composition.runner", "--describe-connections"],
            cwd=str(COMPOSITION_ROOT), capture_output=True, text=True,
            env={"PYTHONPATH": str(COMPOSITION_ROOT)}, timeout=120,
        )
        assert completed.returncode == 0, completed.stderr
        payload = json.loads(completed.stdout)
        assert payload["contract_version"] == "0.1.0"
        assert "matching unit is necessary and never sufficient" in payload["claim_scope"]
        assert "does not upgrade any model's reproduction_status" in (
            payload["validation_status"]
        )
        boundaries = {(b["source_model"], b["target_model"]) for b in payload["boundaries"]}
        # Every ordered pair of registered models, derived rather than listed,
        # so registering a model forces a position on it.
        registered = {r.model_id for r in REGISTRATIONS}
        assert boundaries == {(s, t) for s in registered for t in registered}

    def test_every_boundary_states_a_reason_and_cites_something(self):
        for boundary in cross_model.BOUNDARIES:
            assert boundary.reason.strip()
            assert boundary.evidence, boundary.stance
            if not boundary.permitted:
                assert boundary.remediation, boundary.stance

    def test_the_matrix_covers_every_ordered_pair_of_registered_models(self):
        registered = {r.model_id for r in REGISTRATIONS}
        declared = {(b.source_model, b.target_model) for b in cross_model.BOUNDARIES}
        for source in registered:
            for target in registered:
                assert (source, target) in declared, f"{source} -> {target} is undeclared"

    def test_a_boundary_the_engine_owns_is_not_reported_twice(self):
        """The engine consults this module only when nothing else has refused."""
        for boundary in cross_model.BOUNDARIES:
            if not boundary.enforced_by_engine:
                continue
            verdict = cross_model.check(
                boundary.source_model, "any", "mass",
                boundary.target_model, "any", "mass",
            )
            assert verdict is None, (
                f"{boundary.stance} is marked as the engine's to refuse, but this "
                "module would also emit a diagnostic for it"
            )

    def test_an_unclassified_pair_is_refused_rather_than_passed_through(self):
        """A gap in the rules must fail closed."""
        verdict = cross_model.check(
            GANJAVE, "biomass_concentration", "mass_concentration",
            ZIELINSKI, "node:N15#insulin_mass_from_au", "activity",
        )
        assert verdict is not None
        assert not verdict.permitted
        assert verdict.stance == "refused_unclassified"
        assert "No rule" in verdict.reason

    def test_the_policy_classifies_quantities_not_ports(self):
        """Rules are about meaning; a port list would go stale immediately.

        Checked on the declarative data rather than the module text: the prose
        is allowed -- and expected -- to *cite* a port as the example of a trap,
        but no rule may key on one.
        """
        rules = {
            "quantities": {pair for b in cross_model.BOUNDARIES for pair in b.rules},
            "reasons": [b.reason for b in cross_model.BOUNDARIES],
        }
        for fragment in ("node:N", "stream:S", "out:", "in:"):
            for reason in rules["reasons"]:
                assert fragment not in reason, (
                    f"a declared reason names the port-shaped fragment "
                    f"{fragment!r}; rules must classify quantities"
                )
        for source_q, target_q in rules["quantities"]:
            assert "#" not in source_q and ":" not in source_q
            assert "#" not in target_q and ":" not in target_q

    def test_no_boundary_claims_to_have_been_validated(self):
        """The policy may *disclaim* validation; it may never assert it.

        Scoped to affirmative claims. Saying a cascade is "not validated by
        the paper" is the required honesty and must not trip this check; saying
        it "is validated" is exactly the overclaim the task forbids.
        """
        forbidden = (
            " is validated", " has been validated", " was validated",
            " is reproduced", " has been reproduced",
            " is verified against", " has been verified against",
        )
        for boundary in cross_model.BOUNDARIES:
            text = " ".join((
                boundary.stance, boundary.reason, boundary.remediation,
                *boundary.evidence, *boundary.unresolved, boundary.dimensional_note,
            )).lower()
            for claim in forbidden:
                assert claim not in text, (
                    f"{boundary.stance} claims {claim.strip()!r}; these checks "
                    "say nothing about whether a model is scientifically correct"
                )

    def test_the_policy_states_that_it_validates_nothing(self):
        status = cross_model.describe()["validation_status"]
        assert "not a scientific validation" in status
        assert "does not upgrade" in status


# --------------------------------------------------------------------------- #
# the boundaries the models refuse for themselves
# --------------------------------------------------------------------------- #


class TestTheModelsOwnPositionsSurvive:
    """XM-01 adds a boundary; it does not displace the models' own contracts."""

    def test_ganjave_still_refuses_two_required_inputs_from_any_upstream_model(self):
        refused = {r.port_id for r in INPUT_CONTRACT if not r.upstream_supplyable}
        assert refused == {"initial_biomass_concentration", "initial_dissolved_oxygen"}

    def test_a_declared_literal_is_still_accepted_for_a_non_supplyable_port(self):
        """"No upstream model may supply this" is not "no value is obtainable"."""
        document = read_example("ganjave_fed_batch.json")
        document["literal_inputs"].pop("ganjave_fed_batch/initial_biomass_concentration")
        document["literal_inputs"]["ganjave_fed_batch/initial_biomass_concentration"] = {
            "state": "number", "quantity": "mass_concentration", "value": 0.05,
            "unit": "g/L", "method": "declared by the operator",
            "reason": "no OD600-to-DCW calibration is printed",
        }
        payload, code = execute(document)
        assert code == 0, json.dumps(payload.get("diagnostics", []), indent=2)
        assert CROSS_REFUSED not in {d["code"] for d in payload["diagnostics"]}

    def test_the_replay_scene_graph_is_unaffected(self):
        """The Zielinski evidence replay declares no connections and still runs."""
        replay = COMPOSITION_ROOT / "replay" / "zielinski_replay.json"
        payload, code = execute(json.loads(replay.read_text(encoding="utf-8")))
        assert code == 0
        assert payload["status"].startswith("success")
        assert len(payload["results"][0]["outputs"]) == 196

    def test_baez_is_not_registered_and_stays_out(self):
        """The assessment is not a route to registering it."""
        assert "baez" not in {r.model_id for r in REGISTRATIONS}
        assert cross_model.boundary_for("baez2014.oxygen_induced", MORRIS) is None

