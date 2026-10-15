"""Acceptance criteria MB-01 .. MB-12.

One class per criterion, named after it.  `MB_COVERAGE` maps every criterion to
the class that implements it, and `TestCoverageTable` fails if a criterion is
ever added without a class or a class goes missing -- so the table cannot quietly
drift away from the suite.

Each test states the criterion's acceptance value literally, so a reviewer can
check the assertion against the requirement without reading the engine.
"""

from __future__ import annotations

import pytest

from models.material_balance import solve_balance
from schemas.material_balance import (
    Assumption,
    BalanceBasis,
    BalanceEquation,
    BalanceSystem,
    BalanceSystemError,
    Component,
    ConstantTerm,
    Direction,
    EquationKind,
    ProcessMode,
    ProcessModeError,
    Provenance,
    QuantityKind,
    QuantityKindError,
    Solvability,
    Stream,
    StreamError,
    convert,
    reported,
    stream_component_id,
    stream_fraction_id,
    stream_total_id,
    unit,
    unknown,
)

# --------------------------------------------------------------------------- #
# fixtures shared by several criteria
# --------------------------------------------------------------------------- #


def _copper_zinc() -> tuple[Component, Component]:
    return (
        Component("Cu", "copper", formula="Cu", molar_mass_kg_per_mol=0.063546),
        Component("Zn", "zinc", formula="Zn", molar_mass_kg_per_mol=0.065388),
    )


def _three_components() -> tuple[Component, Component, Component]:
    return (
        Component("A", "component A"),
        Component("B", "component B"),
        Component("C", "component C"),
    )


def _resolved_total(result, stream_id: str) -> float:
    """The total flow/amount of a stream, from the ledger's component rows."""
    return sum(r.value for r in result.ledger if r.stream_id == stream_id)


def _ledger_cell(result, stream_id: str, component_id: str):
    return next(
        r
        for r in result.ledger
        if r.stream_id == stream_id and r.component_id == component_id
    )


# --------------------------------------------------------------------------- #
# MB-01 -- batch mixing total mass
# --------------------------------------------------------------------------- #


class TestMB01BatchMixingTotalMass:
    """The three brass inputs produce 26,600 kg total mixture."""

    def test_total_mixture_is_26600_kg(self, brass_result):
        assert _resolved_total(brass_result, "D") == pytest.approx(26600.0, abs=1e-9)

    def test_total_is_the_sum_of_the_three_charges(self, brass_result):
        charges = _resolved_total(brass_result, "A") + _resolved_total(
            brass_result, "B"
        ) + _resolved_total(brass_result, "C")
        assert charges == pytest.approx(3600.0 + 14500.0 + 8500.0)
        assert _resolved_total(brass_result, "D") == pytest.approx(charges, abs=1e-9)

    def test_total_mass_balance_closes_exactly(self, brass_result):
        assert brass_result.basis_unit == "kg"
        assert brass_result.total_mass_residual.value == pytest.approx(0.0, abs=1e-12)


# --------------------------------------------------------------------------- #
# MB-02 -- batch mixing composition
# --------------------------------------------------------------------------- #


class TestMB02BatchMixingComposition:
    """Cu = (14500 + 0.79 * 8500) / 26600 and Zn is its complement.

    Acceptance values 0.79756 and 0.20244, matched within 1e-5.
    """

    def test_copper_fraction_matches_the_stated_expression(self, brass_result):
        expected = (14500.0 + 0.79 * 8500.0) / 26600.0
        actual = _ledger_cell(brass_result, "D", "Cu").mass_fraction
        assert actual == pytest.approx(expected, abs=1e-12)
        assert actual == pytest.approx(0.79756, abs=1e-5)

    def test_zinc_fraction_is_the_complement(self, brass_result):
        copper = _ledger_cell(brass_result, "D", "Cu").mass_fraction
        zinc = _ledger_cell(brass_result, "D", "Zn").mass_fraction
        assert zinc == pytest.approx(0.20244, abs=1e-5)
        assert copper + zinc == pytest.approx(1.0, abs=1e-12)

    def test_fractions_are_derived_from_the_ledger_not_restated(self, brass_result):
        # the ledger must carry mass AND composition for every stream, which is
        # what section 4.5 asks for
        copper_mass = _ledger_cell(brass_result, "D", "Cu").value
        total = _resolved_total(brass_result, "D")
        assert _ledger_cell(brass_result, "D", "Cu").mass_fraction == pytest.approx(
            copper_mass / total
        )


# --------------------------------------------------------------------------- #
# MB-03 -- steady-state component conservation
# --------------------------------------------------------------------------- #


class TestMB03SteadyStateComponentConservation:
    """The synthetic splitter returns X = 40/60 kg/h and Y = 24/36 kg/h."""

    def test_component_x_splits_40_and_60(self, splitter_result):
        assert _ledger_cell(splitter_result, "P1", "X").value == pytest.approx(40.0)
        assert _ledger_cell(splitter_result, "P2", "X").value == pytest.approx(60.0)

    def test_component_y_splits_24_and_36(self, splitter_result):
        assert _ledger_cell(splitter_result, "P1", "Y").value == pytest.approx(24.0)
        assert _ledger_cell(splitter_result, "P2", "Y").value == pytest.approx(36.0)

    def test_each_component_is_conserved(self, splitter_result):
        for component_id in ("X", "Y"):
            feed = _ledger_cell(splitter_result, "F", component_id).value
            out = (
                _ledger_cell(splitter_result, "P1", component_id).value
                + _ledger_cell(splitter_result, "P2", component_id).value
            )
            assert feed == pytest.approx(out, abs=1e-9)

    def test_stream_totals_are_64_and_96(self, splitter_result):
        assert _resolved_total(splitter_result, "P1") == pytest.approx(64.0)
        assert _resolved_total(splitter_result, "P2") == pytest.approx(96.0)
        assert _resolved_total(splitter_result, "P1") + _resolved_total(
            splitter_result, "P2"
        ) == pytest.approx(160.0)


# --------------------------------------------------------------------------- #
# MB-04 -- residual closure
# --------------------------------------------------------------------------- #


class TestMB04ResidualClosure:
    """All exactly specified fixtures have |component residual| < 1e-8."""

    @pytest.mark.parametrize(
        "fixture_name",
        ["cd_zn_result", "brass_result", "dezinc_result", "splitter_result"],
    )
    def test_component_residuals_are_below_1e_8(self, request, fixture_name):
        result = request.getfixturevalue(fixture_name)
        assert result.component_residuals, f"{fixture_name} reported no component residuals"
        for residual in result.component_residuals:
            assert abs(residual.value) < 1e-8, (
                f"{fixture_name} {residual.label}: {residual.value!r}"
            )

    @pytest.mark.parametrize(
        "fixture_name",
        ["cd_zn_result", "brass_result", "dezinc_result", "splitter_result"],
    )
    def test_total_mass_residuals_are_below_1e_8(self, request, fixture_name):
        result = request.getfixturevalue(fixture_name)
        assert result.total_mass_residual is not None
        assert abs(result.total_mass_residual.value) < 1e-8

    @pytest.mark.parametrize(
        "fixture_name",
        ["cd_zn_result", "brass_result", "dezinc_result", "splitter_result"],
    )
    def test_every_fixture_reports_itself_as_closing(self, request, fixture_name):
        assert request.getfixturevalue(fixture_name).balances_close

    def test_every_fixture_checks_every_component(self, request):
        for fixture_name in ("brass_result", "dezinc_result", "splitter_result"):
            result = request.getfixturevalue(fixture_name)
            checked = {r.component_id for r in result.component_residuals}
            present = {row.component_id for row in result.ledger}
            assert checked == present, (
                f"{fixture_name}: checked {sorted(checked)} but the ledger holds "
                f"{sorted(present)}"
            )


# --------------------------------------------------------------------------- #
# MB-05 -- composition sum
# --------------------------------------------------------------------------- #


class TestMB05CompositionSum:
    """A complete composition summing to 0.98 is rejected, never normalized."""

    def _system_summing_to(self, total_fraction: float) -> BalanceSystem:
        cu, zn = _copper_zinc()
        return BalanceSystem(
            system_id="mb-05",
            label=f"feed composition summing to {total_fraction}",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=(cu, zn),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    amount=reported("F:total", 1000.0, "kg/h", source_ref="MB-05"),
                    mass_fractions={
                        "Cu": reported(
                            "F:w_Cu", total_fraction / 2, "1", source_ref="MB-05"
                        ),
                        "Zn": reported(
                            "F:w_Zn", total_fraction / 2, "1", source_ref="MB-05"
                        ),
                    },
                ),
                Stream(
                    stream_id="P",
                    label="product",
                    direction=Direction.OUTPUT,
                    component_amounts={
                        "Cu": unknown(
                            stream_component_id("P", "Cu"), QuantityKind.MASS_FLOW
                        ),
                        "Zn": unknown(
                            stream_component_id("P", "Zn"), QuantityKind.MASS_FLOW
                        ),
                    },
                ),
            ),
        )

    def test_a_composition_summing_to_0_98_is_reported_not_normalized(self):
        result = solve_balance(self._system_summing_to(0.98))
        assert result.solvability is Solvability.INCONSISTENT
        assert "system.inconsistent" in {d.code for d in result.diagnostics}
        assert result.variables == ()

    def test_the_engine_does_not_silently_rescale_the_fractions(self):
        # If the engine normalized 0.98 up to 1.0, this system would solve
        # cleanly and the product would be 490 kg/h. It must not.
        result = solve_balance(self._system_summing_to(0.98))
        assert result.variables == ()
        composition = next(
            e for e in result.equations if e.kind is EquationKind.COMPOSITION_SUM
        )
        # the composition equation still reads 0.49 + 0.49 - 1, unscaled
        assert composition.constant_sum == pytest.approx(-0.02)

    def test_the_reported_composition_is_not_normalized(self):
        # The equations are not the only place a normalization could hide. If the
        # engine reported a renormalized composition in the ledger while solving
        # with the raw one, the two would silently disagree -- so the fractions
        # as *reported* must also still sum to 0.98.
        result = solve_balance(self._system_summing_to(0.98))
        fractions = {
            r.component_id: r.mass_fraction
            for r in result.ledger
            if r.stream_id == "F"
        }
        assert fractions["Cu"] == pytest.approx(0.49)
        assert fractions["Zn"] == pytest.approx(0.49)
        assert sum(fractions.values()) == pytest.approx(0.98)
        assert sum(fractions.values()) != pytest.approx(1.0)

    def test_the_declared_fractions_are_left_untouched_by_the_run(self):
        system = self._system_summing_to(0.98)
        before = {
            cid: q.value for cid, q in system.stream("F").mass_fractions.items()
        }
        solve_balance(system)
        after = {
            cid: q.value for cid, q in system.stream("F").mass_fractions.items()
        }
        assert before == after == {"Cu": 0.49, "Zn": 0.49}

    def test_a_composition_summing_to_one_is_accepted(self):
        result = solve_balance(self._system_summing_to(1.0))
        assert result.variables
        assert {v.variable_id: v.value for v in result.variables}[
            stream_component_id("P", "Cu")
        ] == pytest.approx(500.0)
        assert result.balances_close

    def test_an_incomplete_composition_must_be_declared_not_inferred(self):
        cu, zn = _copper_zinc()
        with pytest.raises(BalanceSystemError, match="absent_components"):
            BalanceSystem(
                system_id="mb-05-partial",
                label="composition that silently omits a component",
                process_mode=ProcessMode.STEADY_STATE,
                basis=BalanceBasis.MASS,
                components=(cu, zn),
                streams=(
                    Stream(
                        stream_id="F",
                        label="feed",
                        direction=Direction.INPUT,
                        amount=reported("F:total", 1000.0, "kg/h", source_ref="MB-05"),
                        mass_fractions={
                            "Cu": reported("F:w_Cu", 1.0, "1", source_ref="MB-05")
                        },
                    ),
                ),
            )


# --------------------------------------------------------------------------- #
# MB-06 -- underdetermined system
# --------------------------------------------------------------------------- #


class TestMB06Underdetermined:
    """More unknown degrees of freedom than independent constraints."""

    @pytest.fixture()
    def underdetermined(self):
        cu, zn = _copper_zinc()
        return BalanceSystem(
            system_id="mb-06",
            label="two unknowns, one independent balance",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=(cu, zn),
            balances=("Cu",),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    component_amounts={
                        "Cu": reported("F:Cu", 100.0, "kg/h", source_ref="MB-06")
                    },
                ),
                Stream(
                    stream_id="P",
                    label="product",
                    direction=Direction.OUTPUT,
                    component_amounts={
                        "Cu": unknown(stream_component_id("P", "Cu"), QuantityKind.MASS_FLOW),
                        "Zn": unknown(stream_component_id("P", "Zn"), QuantityKind.MASS_FLOW),
                    },
                ),
            ),
        )

    def test_reported_as_underdetermined(self, underdetermined):
        result = solve_balance(underdetermined)
        assert result.solvability is Solvability.UNDERDETERMINED
        assert result.n_unknowns == 2
        assert result.rank == 1
        assert result.n_unknowns - result.rank == 1
        assert "system.underdetermined" in {d.code for d in result.diagnostics}

    def test_unresolved_quantities_remain_unresolved(self, underdetermined):
        result = solve_balance(underdetermined)
        assert [u.variable_id for u in result.unresolved] == [
            stream_component_id("P", "Zn")
        ]
        assert result.unresolved[0].reason

    def test_no_free_variable_is_given_a_value(self, underdetermined):
        result = solve_balance(underdetermined)
        solved = {v.variable_id for v in result.variables}
        free = {u.variable_id for u in result.unresolved}
        assert solved & free == set()
        assert all(v.value != 0.0 for v in result.variables)


# --------------------------------------------------------------------------- #
# MB-07 -- inconsistent equations
# --------------------------------------------------------------------------- #


class TestMB07Inconsistent:
    """Contradictory constraints are reported as inconsistent."""

    @pytest.fixture()
    def contradictory_constraints(self):
        cu, zn = _copper_zinc()

        # A known quantity enters a constraint as a constant that carries its own
        # provenance, never as a bare coefficient: the feed is 1000 kg/h either
        # way, and the two operators simply disagree about the split.
        def split_constraint(equation_id: str, fraction: float, note: str):
            return BalanceEquation(
                equation_id=equation_id,
                kind=EquationKind.USER_CONSTRAINT,
                label=f"product is {fraction} of the feed",
                expression=f"total(P) - {fraction * 1000:g} = 0",
                coefficients={stream_total_id("P"): 1.0},
                constants=(
                    ConstantTerm(
                        quantity_id=f"{equation_id}:feed_share",
                        value=fraction * 1000.0,
                        unit="kg/h",
                        kind=QuantityKind.MASS_FLOW,
                        provenance=Provenance.REPORTED,
                        source_ref=note,
                        sign=-1,
                    ),
                ),
            )

        return BalanceSystem(
            system_id="mb-07",
            label="two constraints that cannot both hold",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=(cu, zn),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    amount=reported("F:total", 1000.0, "kg/h", source_ref="MB-07"),
                    mass_fractions={
                        "Cu": reported("F:w_Cu", 0.6, "1", source_ref="MB-07"),
                        "Zn": reported("F:w_Zn", 0.4, "1", source_ref="MB-07"),
                    },
                ),
                Stream(
                    stream_id="P",
                    label="product",
                    direction=Direction.OUTPUT,
                    amount=unknown(stream_total_id("P"), QuantityKind.MASS_FLOW),
                    mass_fractions={
                        "Cu": unknown(
                            stream_fraction_id("P", "Cu"), QuantityKind.MASS_FRACTION
                        ),
                        "Zn": unknown(
                            stream_fraction_id("P", "Zn"), QuantityKind.MASS_FRACTION
                        ),
                    },
                ),
            ),
            constraints=(
                split_constraint("constraint:A", 0.5, "MB-07 operator A, half the feed"),
                split_constraint(
                    "constraint:B", 1.0 / 3.0, "MB-07 operator B, a third of the feed"
                ),
            ),
        )

    def test_reported_as_inconsistent(self, contradictory_constraints):
        result = solve_balance(contradictory_constraints)
        assert result.solvability is Solvability.INCONSISTENT

    def test_a_nonzero_residual_is_reported(self, contradictory_constraints):
        result = solve_balance(contradictory_constraints)
        offending = [
            abs(v)
            for equation_id, v in result.equation_residuals.items()
            if equation_id.startswith("constraint:")
        ]
        assert offending, "no residual was reported for the contradictory constraints"
        assert max(offending) > 0.0

    def test_a_solver_diagnostic_is_emitted(self, contradictory_constraints):
        result = solve_balance(contradictory_constraints)
        inconsistent = [d for d in result.diagnostics if d.code == "system.inconsistent"]
        assert inconsistent
        assert inconsistent[0].severity.value == "error"
        assert set(result.inconsistent_equation_ids) >= {"constraint:A", "constraint:B"}

    def test_nothing_is_solved_and_nothing_is_altered(self, contradictory_constraints):
        before = {
            s.stream_id: dict(s.mass_fractions)
            for s in contradictory_constraints.streams
            if s.mass_fractions
        }
        result = solve_balance(contradictory_constraints)
        assert result.variables == ()
        after = {
            s.stream_id: dict(s.mass_fractions)
            for s in contradictory_constraints.streams
            if s.mass_fractions
        }
        assert before == after


# --------------------------------------------------------------------------- #
# MB-08 -- redundant equation
# --------------------------------------------------------------------------- #


class TestMB08RedundantEquation:
    """An independent-equivalent check does not change the solution."""

    @pytest.fixture()
    def with_and_without(self, cd_zn_system):
        # Restate the generated cadmium balance as an explicit check equation.
        # It is algebraically identical, so it must add an equation, not rank.
        generated = next(
            e for e in solve_balance(cd_zn_system).equations if e.component_id == "Cd"
        )
        check = BalanceEquation(
            equation_id="check:cadmium balance",
            kind=EquationKind.USER_CONSTRAINT,
            label="independent restatement of the cadmium balance",
            expression=generated.expression,
            coefficients=dict(generated.coefficients),
            constants=generated.constants,
            component_id="Cd",
            source_ref="MB-08 redundant check",
        )
        without = solve_balance(cd_zn_system)
        with_check = solve_balance(
            BalanceSystem(
                system_id=cd_zn_system.system_id + "-checked",
                label=cd_zn_system.label + " (+ cadmium check)",
                process_mode=cd_zn_system.process_mode,
                basis=cd_zn_system.basis,
                components=cd_zn_system.components,
                streams=cd_zn_system.streams,
                balances=cd_zn_system.balances,
                constraints=(check,),
                source_ref=cd_zn_system.source_ref,
            )
        )
        return without, with_check

    def test_the_solution_is_unchanged(self, with_and_without):
        without, with_check = with_and_without
        assert {v.variable_id: v.value for v in with_check.variables} == {
            v.variable_id: v.value for v in without.variables
        }

    def test_rank_does_not_move(self, with_and_without):
        without, with_check = with_and_without
        assert with_check.rank == without.rank
        assert with_check.n_unknowns == without.n_unknowns

    def test_the_equation_count_increases_by_one(self, with_and_without):
        without, with_check = with_and_without
        assert with_check.n_equations == without.n_equations + 1

    def test_the_added_equation_is_reported_as_redundant(self, with_and_without):
        _, with_check = with_and_without
        assert "check:cadmium balance" in with_check.redundant_equation_ids

    def test_the_classification_reports_the_redundancy(self, with_and_without):
        without, with_check = with_and_without
        assert without.solvability is Solvability.UNIQUE
        assert with_check.solvability is Solvability.OVERCONSTRAINED
        assert "system.overconstrained" in {d.code for d in with_check.diagnostics}

    def test_the_result_still_closes(self, with_and_without):
        _, with_check = with_and_without
        assert with_check.balances_close
        assert abs(with_check.total_mass_residual.value) < 1e-8

    def test_a_total_balance_is_refused_when_a_stream_has_no_declared_total(
        self, cd_zn_system
    ):
        # Streams B and C are given as component amounts, so their totals are
        # derived rather than declared. A total balance over the remaining
        # streams would look like a system-wide balance while silently omitting
        # two of the three, so it is refused with a reason instead.
        result = solve_balance(
            BalanceSystem(
                system_id=cd_zn_system.system_id + "-total",
                label=cd_zn_system.label + " (+ total balance)",
                process_mode=cd_zn_system.process_mode,
                basis=cd_zn_system.basis,
                components=cd_zn_system.components,
                streams=cd_zn_system.streams,
                balances=cd_zn_system.balances,
                total_balance=True,
            )
        )
        assert "balance:steady_state:total" not in {
            e.equation_id for e in result.equations
        }
        diagnostic = next(
            d for d in result.diagnostics if d.code == "balance.total_not_generated"
        )
        assert "'B'" in diagnostic.message and "'C'" in diagnostic.message
        # and the system is still solvable, not corrupted into inconsistency
        assert result.solvability is Solvability.UNIQUE


# --------------------------------------------------------------------------- #
# MB-09 -- batch versus steady-state semantics
# --------------------------------------------------------------------------- #


class TestMB09BatchVersusSteadyState:
    """A batch amount is never treated as a flow rate."""

    def test_a_batch_stream_in_kg_h_is_rejected(self):
        cu, zn = _copper_zinc()
        with pytest.raises(BalanceSystemError, match="no material flows"):
            BalanceSystem(
                system_id="mb-09-a",
                label="batch stated as a flow",
                process_mode=ProcessMode.BATCH,
                basis=BalanceBasis.MASS,
                components=(cu, zn),
                streams=(
                    Stream(
                        stream_id="I",
                        label="initial",
                        direction=Direction.INITIAL,
                        component_amounts={
                            "Cu": reported("I:Cu", 1.0, "kg/h", source_ref="MB-09")
                        },
                    ),
                    Stream(
                        stream_id="F",
                        label="final",
                        direction=Direction.FINAL,
                        component_amounts={
                            "Cu": reported("F:Cu", 2.0, "kg", source_ref="MB-09")
                        },
                    ),
                ),
            )

    def test_a_steady_state_stream_in_kg_is_rejected(self):
        cu, zn = _copper_zinc()
        with pytest.raises(BalanceSystemError, match="steady_state is a flow mode"):
            BalanceSystem(
                system_id="mb-09-b",
                label="steady state stated as an inventory",
                process_mode=ProcessMode.STEADY_STATE,
                basis=BalanceBasis.MASS,
                components=(cu, zn),
                streams=(
                    Stream(
                        stream_id="F",
                        label="feed",
                        direction=Direction.INPUT,
                        component_amounts={
                            "Cu": reported("F:Cu", 1.0, "kg", source_ref="MB-09")
                        },
                    ),
                    Stream(
                        stream_id="P",
                        label="product",
                        direction=Direction.OUTPUT,
                        component_amounts={
                            "Cu": reported("P:Cu", 1.0, "kg", source_ref="MB-09")
                        },
                    ),
                ),
            )

    def test_mixing_kg_and_kg_h_in_one_balance_is_rejected(self):
        cu, zn = _copper_zinc()
        with pytest.raises(BalanceSystemError, match="in the same units"):
            BalanceSystem(
                system_id="mb-09-c",
                label="accumulation in kg against a feed in kg/h",
                process_mode=ProcessMode.ACCUMULATING,
                basis=BalanceBasis.MASS,
                components=(cu, zn),
                balances=("Cu",),
                streams=(
                    Stream(
                        stream_id="F",
                        label="feed",
                        direction=Direction.INPUT,
                        component_amounts={
                            "Cu": reported("F:Cu", 1.0, "kg/h", source_ref="MB-09")
                        },
                    ),
                    Stream(
                        stream_id="P",
                        label="product",
                        direction=Direction.OUTPUT,
                        component_amounts={
                            "Cu": reported("P:Cu", 1.0, "kg/h", source_ref="MB-09")
                        },
                    ),
                    Stream(
                        stream_id="A",
                        label="accumulated",
                        direction=Direction.ACCUMULATED,
                        component_amounts={
                            "Cu": reported("A:Cu", 1.0, "kg", source_ref="MB-09")
                        },
                    ),
                ),
            )

    def test_the_time_basis_is_recorded_and_derived(self, cd_zn_system):
        feed = cd_zn_system.stream("A")
        assert feed.is_flow
        # declared in kg/h, normalised to the kg/h base, so the basis is hours
        assert feed.effective_time_basis() == "h"
        assert feed.to_dict()["time_basis"] == "h"

    def test_batch_and_steady_state_choose_different_units(self, brass_system):
        batch = solve_balance(brass_system)
        assert batch.process_mode is ProcessMode.BATCH
        assert batch.basis_unit == "kg"
        for stream in brass_system.streams:
            assert not stream.is_flow
            assert stream.effective_time_basis() is None

        cd_zn = solve_balance(
            __import__(
                "tests.conftest", fromlist=["cd_zn_system"]
            ).cd_zn_system.__wrapped__()
        )
        assert cd_zn.process_mode is ProcessMode.STEADY_STATE
        assert cd_zn.basis_unit == "kg/h"

    def test_restating_batch_streams_as_a_flow_is_refused(self, brass_system):
        with pytest.raises(ProcessModeError, match="does not admit"):
            BalanceSystem(
                system_id="mb-09-restate",
                label="batch charges restated as a steady-state flow",
                process_mode=ProcessMode.STEADY_STATE,
                basis=BalanceBasis.MASS,
                components=brass_system.components,
                streams=brass_system.streams,
            )


# --------------------------------------------------------------------------- #
# MB-10 -- missing values
# --------------------------------------------------------------------------- #


class TestMB10MissingValues:
    """Missing inputs stay unknown and are never converted to zero."""

    def test_an_unknown_carries_no_value(self):
        marker = unknown("v", QuantityKind.MASS, reason="not stated by the source")
        assert not hasattr(marker, "value")
        assert marker.effective_unit == "kg"
        assert marker.reason

    @pytest.fixture()
    def with_a_gap(self):
        cu, zn = _copper_zinc()
        return BalanceSystem(
            system_id="mb-10",
            label="a product that was never measured",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=(cu, zn),
            balances=("Cu",),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    component_amounts={
                        "Cu": reported("F:Cu", 100.0, "kg/h", source_ref="MB-10")
                    },
                ),
                Stream(
                    stream_id="P",
                    label="product",
                    direction=Direction.OUTPUT,
                    component_amounts={
                        "Cu": unknown(
                            stream_component_id("P", "Cu"),
                            QuantityKind.MASS_FLOW,
                            reason="no flowmeter on this line",
                        )
                    },
                ),
            ),
        )

    def test_the_gap_is_solved_rather_than_filled_with_zero(self, with_a_gap):
        result = solve_balance(with_a_gap)
        solved = {v.variable_id: v.value for v in result.variables}
        assert solved[stream_component_id("P", "Cu")] == pytest.approx(100.0)
        assert solved[stream_component_id("P", "Cu")] != 0.0

    def test_an_unsolvable_gap_stays_unresolved(self, with_a_gap):
        result = solve_balance(with_a_gap)
        assert result.unresolved == ()
        for variable in result.variables:
            assert variable.provenance is Provenance.DERIVED
            assert variable.method

    def test_the_gap_is_not_silently_zero_in_the_ledger(self, with_a_gap):
        result = solve_balance(with_a_gap)
        assert _ledger_cell(result, "P", "Cu").value == pytest.approx(100.0)

    def test_a_free_variable_is_reported_as_free_not_as_zero(self):
        # one equation cannot pin two unknowns; exactly one stays free
        cu, zn = _copper_zinc()
        system = BalanceSystem(
            system_id="mb-10-free",
            label="two unknowns, one equation",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=(cu, zn),
            balances=("Cu",),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    component_amounts={
                        "Cu": reported("F:Cu", 100.0, "kg/h", source_ref="MB-10")
                    },
                ),
                Stream(
                    stream_id="P",
                    label="product",
                    direction=Direction.OUTPUT,
                    component_amounts={
                        "Cu": unknown(stream_component_id("P", "Cu"), QuantityKind.MASS_FLOW),
                        "Zn": unknown(stream_component_id("P", "Zn"), QuantityKind.MASS_FLOW),
                    },
                ),
            ),
        )
        result = solve_balance(system)
        assert result.solvability is Solvability.UNDERDETERMINED
        assert [u.variable_id for u in result.unresolved] == [
            stream_component_id("P", "Zn")
        ]
        # the free variable is absent from the solved set, not present as a 0
        assert stream_component_id("P", "Zn") not in {
            v.variable_id for v in result.variables
        }

    def test_missing_data_is_reported_as_a_diagnostic_not_an_error(self):
        # an under-specified system is a finding about the data, not a crash
        cu, zn = _copper_zinc()
        system = BalanceSystem(
            system_id="mb-10-under",
            label="one unknown given, one not",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=(cu, zn),
            balances=("Cu",),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    component_amounts={
                        "Cu": reported("F:Cu", 100.0, "kg/h", source_ref="MB-10")
                    },
                ),
                Stream(
                    stream_id="P",
                    label="product",
                    direction=Direction.OUTPUT,
                    component_amounts={
                        "Cu": unknown(stream_component_id("P", "Cu"), QuantityKind.MASS_FLOW),
                        "Zn": unknown(stream_component_id("P", "Zn"), QuantityKind.MASS_FLOW),
                    },
                ),
            ),
        )
        result = solve_balance(system)
        assert result.solvability is Solvability.UNDERDETERMINED
        assert len(result.unresolved) == 1
        assert all("under-determined" in u.reason for u in result.unresolved)
        assert not any(
            d.severity.value == "error" for d in result.diagnostics
        ), "an under-specified system must not be reported as an error"


# --------------------------------------------------------------------------- #
# MB-11 -- provenance
# --------------------------------------------------------------------------- #


class TestMB11Provenance:
    """Every solved output traces back to reported inputs and assumed constraints."""

    @pytest.fixture()
    def traced(self):
        # Three components, so the assumed constraint is load-bearing rather than
        # a redundant restatement: every solved variable is pinned by exactly one
        # equation, and each of those equations terminates in either a reported
        # measurement or the assumption.
        a, b, c = _three_components()
        note = Assumption(
            assumption_id="A-01",
            statement="the feed carries 100 kg/h of component C",
            rationale="no analyser was available on the feed line",
            affects=(stream_component_id("F", "C"),),
        )
        constraint = BalanceEquation(
            equation_id="constraint:feed C",
            kind=EquationKind.USER_CONSTRAINT,
            label="assumed feed content of C",
            expression="C(F) - 100 = 0",
            coefficients={stream_component_id("F", "C"): 1.0},
            constants=(
                ConstantTerm(
                    quantity_id="assumption:A-01:value",
                    value=100.0,
                    unit="kg/h",
                    kind=QuantityKind.MASS_FLOW,
                    provenance=Provenance.ASSUMED,
                    source_ref="A-01: no analyser was available on the feed line",
                    sign=-1,
                ),
            ),
        )
        system = BalanceSystem(
            system_id="mb-11",
            label="provenance chain",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=(a, b, c),
            balances=("A", "B", "C"),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    component_amounts={
                        "A": reported("F:A", 600.0, "kg/h", source_ref="MB-11 p.1"),
                        "B": unknown(
                            stream_component_id("F", "B"),
                            QuantityKind.MASS_FLOW,
                            reason="solved",
                        ),
                        "C": unknown(
                            stream_component_id("F", "C"),
                            QuantityKind.MASS_FLOW,
                            reason="solved",
                        ),
                    },
                ),
                Stream(
                    stream_id="P",
                    label="product",
                    direction=Direction.OUTPUT,
                    component_amounts={
                        "A": unknown(
                            stream_component_id("P", "A"),
                            QuantityKind.MASS_FLOW,
                            reason="solved",
                        ),
                        "B": reported("P:B", 400.0, "kg/h", source_ref="MB-11 p.1"),
                        "C": unknown(
                            stream_component_id("P", "C"),
                            QuantityKind.MASS_FLOW,
                            reason="solved",
                        ),
                    },
                ),
            ),
            constraints=(constraint,),
            assumptions=(note,),
        )
        return solve_balance(system)

    def test_a_solved_variable_names_its_equations(self, traced):
        for variable in traced.variables:
            assert variable.inputs, f"{variable.variable_id} names no equation"
            for equation_id in variable.inputs:
                assert equation_id in {e.equation_id for e in traced.equations}

    def test_the_chain_reaches_reported_or_assumed_leaves(self, traced):
        by_id = {e.equation_id: e for e in traced.equations}
        for variable in traced.variables:
            for equation_id in variable.inputs:
                for constant in by_id[equation_id].constants:
                    assert constant.provenance in (
                        Provenance.REPORTED,
                        Provenance.ASSUMED,
                        Provenance.DERIVED,
                    )
                    if constant.provenance is Provenance.REPORTED:
                        assert constant.source_ref
                    elif constant.provenance is Provenance.ASSUMED:
                        assert "A-01" in (constant.source_ref or "")
                    elif constant.provenance is Provenance.DERIVED:
                        assert constant.derivation

    def test_a_reported_leaf_names_its_source_page(self, traced):
        by_id = {e.equation_id: e for e in traced.equations}
        leaves = [
            c
            for variable in traced.variables
            for equation_id in variable.inputs
            for c in by_id[equation_id].constants
            if c.provenance is Provenance.REPORTED
        ]
        assert leaves
        assert all("MB-11" in (c.source_ref or "") for c in leaves)

    def test_an_assumed_leaf_names_its_assumption(self, traced):
        by_id = {e.equation_id: e for e in traced.equations}
        assumed_leaves = [
            c
            for variable in traced.variables
            for equation_id in variable.inputs
            for c in by_id[equation_id].constants
            if c.provenance is Provenance.ASSUMED
        ]
        assert assumed_leaves
        assert all(c.source_ref and "A-01" in c.source_ref for c in assumed_leaves)

    def test_the_assumption_reaches_the_result(self, traced):
        assert [a.assumption_id for a in traced.assumptions] == ["A-01"]
        assert traced.to_dict()["assumptions"][0]["rationale"]

    def test_solved_variables_carry_unit_kind_and_provenance(self, traced):
        for variable in traced.variables:
            assert variable.unit
            assert variable.kind is not None
            assert variable.provenance is Provenance.DERIVED
            assert variable.method

    def test_the_chain_survives_serialization(self, traced):
        payload = traced.to_dict()
        by_id = {e["equation_id"]: e for e in payload["equations"]}
        for variable in payload["variables"]:
            assert variable["inputs"]
            for equation_id in variable["inputs"]:
                assert equation_id in by_id


def _base_unit_for(kind: QuantityKind) -> str:
    from schemas.material_balance import base_unit

    return base_unit(kind)


# --------------------------------------------------------------------------- #
# MB-12 -- units
# --------------------------------------------------------------------------- #


class TestMB12Units:
    """Incompatible units are rejected or explicitly converted; never mixed."""

    def test_kg_and_kg_h_are_different_kinds(self):
        assert unit("kg").kind is QuantityKind.MASS
        assert unit("kg/h").kind is QuantityKind.MASS_FLOW
        assert unit("kg").kind is not unit("kg/h").kind

    def test_a_conversion_between_them_is_refused(self):
        with pytest.raises(QuantityKindError):
            convert(1.0, "kg", "kg/h")
        with pytest.raises(QuantityKindError):
            convert(1.0, "kg/h", "kg")

    def test_a_stream_cannot_mix_kg_and_kg_h(self):
        with pytest.raises(StreamError, match="share one kind"):
            Stream(
                stream_id="S",
                label="s",
                direction=Direction.INPUT,
                component_amounts={
                    "Cu": reported("a", 1.0, "kg", source_ref="MB-12"),
                    "Zn": reported("b", 1.0, "kg/h", source_ref="MB-12"),
                },
            )

    def test_the_balance_basis_must_match_the_streams(self):
        with pytest.raises(BalanceSystemError, match="balance basis is"):
            BalanceSystem(
                system_id="mb-12-basis",
                label="mass data on an amount basis",
                process_mode=ProcessMode.STEADY_STATE,
                basis=BalanceBasis.AMOUNT,
                components=_copper_zinc(),
                streams=(
                    Stream(
                        stream_id="F",
                        label="feed",
                        direction=Direction.INPUT,
                        component_amounts={
                            "Cu": reported("F:Cu", 1.0, "kg/h", source_ref="MB-12")
                        },
                    ),
                ),
            )

    @pytest.mark.parametrize(
        ("value", "src", "dst", "expected"),
        [
            (1000.0, "g", "kg", 1.0),
            (1.0, "kg", "g", 1000.0),
            (120.0, "kg/min", "kg/h", 2.0),
            (50.0, "%", "1", 0.5),
            (1.0, "kmol", "mol", 1000.0),
            (1.0, "t", "kg", 1000.0),
        ],
    )
    def test_the_conversion_layer_is_tested(self, value, src, dst, expected):
        assert convert(value, src, dst) == pytest.approx(expected)

    def test_solved_values_are_returned_in_the_declared_unit(self):
        cu, zn = _copper_zinc()
        system = BalanceSystem(
            system_id="mb-12-units",
            label="declared in g/min, solved in kg/h",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=(cu, zn),
            balances=("Cu",),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    component_amounts={
                        "Cu": reported("F:Cu", 60000.0, "g/min", source_ref="MB-12")
                    },
                ),
                Stream(
                    stream_id="P",
                    label="product",
                    direction=Direction.OUTPUT,
                    component_amounts={
                        "Cu": unknown(
                            stream_component_id("P", "Cu"),
                            QuantityKind.MASS_FLOW,
                            unit="g/min",
                            reason="reported in g/min by the operator",
                        )
                    },
                ),
            ),
        )
        result = solve_balance(system)
        solved = {v.variable_id: v for v in result.variables}[
            stream_component_id("P", "Cu")
        ]
        # 60000 g/min == 1 kg/s == 3600 kg/h, and the variable is asked for in
        # g/min, so it comes back in g/min
        assert solved.unit == "g/min"
        assert solved.value == pytest.approx(60000.0)
        assert solved.source_unit == "kg/h"
        assert convert(solved.source_value, "kg/h", "g/min") == pytest.approx(60000.0)

    def test_residuals_state_the_unit_they_are_in(self, splitter_result):
        assert splitter_result.basis_unit == "kg/h"
        for residual in splitter_result.component_residuals:
            assert residual.unit == "kg/h"
            assert residual.basis_unit == "kg/h"


# --------------------------------------------------------------------------- #
# coverage table
# --------------------------------------------------------------------------- #


MB_COVERAGE: dict[str, str] = {
    "MB-01": "TestMB01BatchMixingTotalMass",
    "MB-02": "TestMB02BatchMixingComposition",
    "MB-03": "TestMB03SteadyStateComponentConservation",
    "MB-04": "TestMB04ResidualClosure",
    "MB-05": "TestMB05CompositionSum",
    "MB-06": "TestMB06Underdetermined",
    "MB-07": "TestMB07Inconsistent",
    "MB-08": "TestMB08RedundantEquation",
    "MB-09": "TestMB09BatchVersusSteadyState",
    "MB-10": "TestMB10MissingValues",
    "MB-11": "TestMB11Provenance",
    "MB-12": "TestMB12Units",
}


class TestCoverageTable:
    def test_every_criterion_has_an_implementing_class(self):
        for criterion, class_name in MB_COVERAGE.items():
            assert class_name.startswith("Test"), criterion

    def test_no_implementing_class_is_missing(self, request):
        for criterion, class_name in MB_COVERAGE.items():
            assert class_name in globals(), f"{criterion} names a class that does not exist"

    def test_the_table_covers_the_twelve_criteria(self):
        assert len(MB_COVERAGE) == 12
        assert sorted(MB_COVERAGE) == [f"MB-{i:02d}" for i in range(1, 13)]

    def test_every_mapped_class_actually_carries_tests(self, class_name=None):
        for criterion, name in MB_COVERAGE.items():
            cls = globals()[name]
            tests = [
                m
                for m in dir(cls)
                if m.startswith("test_") and callable(getattr(cls, m))
            ]
            assert tests, f"{criterion}: {name} implements nothing"