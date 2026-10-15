"""Tests for the ScaleUp AI material balance engine.

Organised by the property under test rather than by function:

  TestUnitRegistry / TestQuantityIntegrity / TestStreamIntegrity
        the data contract -- a number is present or absent, dimensioned, sourced
  TestProcessModeDiscipline
        only the equations the declared mode admits are ever generated
  TestEquationGeneration
        the three balance forms, composition sums, constraints, provenance
  TestSolvability / TestDeterminism
        unique, underdetermined, inconsistent and overconstrained systems
  TestResiduals
        closure checks computed independently of the solve
  TestDegreesOfFreedom
        the chapter's bookkeeping, and the rank check it does not replace
  TestWorkedExamples
        regression against the numbers printed in Chapter 4
"""

from __future__ import annotations

import math

import pytest
from dataclasses import FrozenInstanceError

from models.degrees_of_freedom import (
    DISTILLATION_OVERALL,
    DISTILLATION_PROCESS,
    DISTILLATION_STILL_I,
    DISTILLATION_STILL_II,
    SALTCAKE_PROCESS,
    SPENT_GAS_SPLITTER,
    DegreeOfFreedom,
    IndependentDegreesOfFreedom,
    compare_freedom,
    process_dof,
)
from models.material_balance import (
    generate_equations,
    solve_balance,
    solve_linear,
)
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
    Quantity,
    QuantityError,
    QuantityKind,
    QuantityKindError,
    Solvability,
    Stream,
    StreamError,
    assumed,
    base_unit,
    convert,
    derived,
    reported,
    stream_component_id,
    stream_fraction_id,
    stream_total_id,
    unit,
    unknown,
)

SEC = "Morris et al. 2011"


def copper_and_zinc() -> tuple[Component, Component]:
    return (
        Component("Cu", "copper", formula="Cu", molar_mass_kg_per_mol=0.063546),
        Component("Zn", "zinc", formula="Zn", molar_mass_kg_per_mol=0.065388),
    )


# --------------------------------------------------------------------------- #
# unit registry
# --------------------------------------------------------------------------- #


class TestUnitRegistry:
    def test_base_unit_per_kind(self):
        assert base_unit(QuantityKind.MASS) == "kg"
        assert base_unit(QuantityKind.MASS_FLOW) == "kg/h"
        assert base_unit(QuantityKind.MASS_FRACTION) == "1"
        assert base_unit(QuantityKind.AMOUNT) == "mol"
        assert base_unit(QuantityKind.AMOUNT_FLOW) == "mol/h"

    @pytest.mark.parametrize(
        ("value", "src", "dst", "expected"),
        [
            (1000.0, "g", "kg", 1.0),
            (1.0, "kg", "g", 1000.0),
            (50.0, "%", "1", 0.5),
            (1.0, "%", "1", 0.01),
            (1.0, "kmol", "mol", 1000.0),
            (120.0, "kg/min", "kg/h", 2.0),
            (1.0, "t", "kg", 1000.0),
        ],
    )
    def test_conversion_within_kind(self, value, src, dst, expected):
        assert convert(value, src, dst) == pytest.approx(expected)

    def test_conversion_refuses_to_cross_kinds(self):
        # mass -> amount needs a molar mass, which is a property of a Component
        with pytest.raises(QuantityKindError, match="declared molar mass"):
            convert(1.0, "kg", "mol")

    def test_conversion_refuses_to_cross_mass_and_flow(self):
        with pytest.raises(QuantityKindError):
            convert(1.0, "kg", "kg/h")

    def test_unknown_unit_raises_rather_than_guessing(self):
        with pytest.raises(QuantityKindError, match="unknown unit"):
            unit("furlong")

    def test_unit_kind_is_fixed(self):
        assert unit("kg").kind is QuantityKind.MASS
        assert unit("kg/h").kind is QuantityKind.MASS_FLOW


# --------------------------------------------------------------------------- #
# quantity integrity
# --------------------------------------------------------------------------- #


class TestQuantityIntegrity:
    def test_reported_requires_a_source(self):
        with pytest.raises(QuantityError, match="source_ref"):
            Quantity(
                quantity_id="q1",
                value=1.0,
                unit="kg",
                kind=QuantityKind.MASS,
                provenance=Provenance.REPORTED,
            )

    def test_derived_requires_a_method(self):
        with pytest.raises(QuantityError, match="derivation"):
            Quantity(
                quantity_id="q1",
                value=1.0,
                unit="kg",
                kind=QuantityKind.MASS,
                provenance=Provenance.DERIVED,
            )

    def test_assumed_requires_a_written_rationale(self):
        with pytest.raises(QuantityError, match="source_ref"):
            Quantity(
                quantity_id="q1",
                value=1.0,
                unit="kg",
                kind=QuantityKind.MASS,
                provenance=Provenance.ASSUMED,
            )

    def test_unit_must_belong_to_the_declared_kind(self):
        with pytest.raises(QuantityError, match="declares kind"):
            reported("q1", 1.0, "kg/h", source_ref="x").__class__(
                quantity_id="q2",
                value=1.0,
                unit="kg/h",
                kind=QuantityKind.MASS,
                provenance=Provenance.REPORTED,
                source_ref="x",
            )

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_values_are_refused(self, bad):
        with pytest.raises(QuantityError, match="finite"):
            reported("q1", bad, "kg", source_ref="x")

    def test_booleans_are_not_numbers(self):
        with pytest.raises(QuantityError, match="real number"):
            reported("q1", True, "kg", source_ref="x")

    def test_time_is_not_a_quantity_kind(self):
        # there is no TIME kind: a time basis is carried by the unit of a flow
        # ("kg/min"), not by a separately convertible number
        with pytest.raises(QuantityKindError, match="unknown unit"):
            unit("min")

    def test_unknown_cannot_hold_a_value(self):
        # an Unknown is a different type from a Quantity on purpose: there is no
        # way to write "unknown but zero", which is how a missing measurement
        # usually turns into a fabricated one
        with pytest.raises(FrozenInstanceError):
            unknown("v1", QuantityKind.MASS, unit="kg", reason="x").value = 0.0  # type: ignore[attr-defined]
        assert not hasattr(unknown("v1", QuantityKind.MASS), "value")

    def test_unknown_defaults_to_the_base_unit(self):
        assert unknown("v1", QuantityKind.MASS).effective_unit == "kg"

    def test_assumed_carries_its_assumption_in_the_source_ref(self):
        q = assumed("q1", 1.0, "kg", assumption_id="A-01", rationale="labelled pure")
        assert q.source_ref is not None and "A-01" in q.source_ref
        assert q.provenance is Provenance.ASSUMED

    def test_derived_carries_its_inputs(self):
        q = derived("q1", 2.0, "kg", derivation="a + b", source_ref="p.1")
        assert q.derivation == "a + b"


# --------------------------------------------------------------------------- #
# stream integrity
# --------------------------------------------------------------------------- #


class TestStreamIntegrity:
    def test_a_stream_needs_some_description(self):
        with pytest.raises(StreamError, match="must define"):
            Stream(stream_id="S", label="s", direction=Direction.INPUT)

    def test_cannot_mix_flow_with_composition_and_component_amounts(self):
        with pytest.raises(StreamError, match="not both"):
            Stream(
                stream_id="S",
                label="s",
                direction=Direction.INPUT,
                amount=reported("t", 1.0, "kg", source_ref="x"),
                mass_fractions={"Cu": reported("w", 1.0, "1", source_ref="x")},
                component_amounts={"Cu": reported("c", 1.0, "kg", source_ref="x")},
            )

    def test_component_amounts_already_fix_the_total(self):
        with pytest.raises(StreamError, match="already fixes the total"):
            Stream(
                stream_id="S",
                label="s",
                direction=Direction.INPUT,
                amount=reported("t", 1.0, "kg", source_ref="x"),
                component_amounts={"Cu": reported("c", 1.0, "kg", source_ref="x")},
            )

    def test_quantities_of_material_must_share_one_kind(self):
        with pytest.raises(StreamError, match="share one kind"):
            Stream(
                stream_id="S",
                label="s",
                direction=Direction.INPUT,
                component_amounts={
                    "Cu": reported("a", 1.0, "kg/h", source_ref="x"),
                    "Zn": reported("b", 1.0, "mol", source_ref="x"),
                },
            )

    def test_a_flow_plus_fractions_is_normal(self):
        # MASS_FLOW next to MASS_FRACTION is the ordinary way to state a stream
        stream = Stream(
            stream_id="S",
            label="s",
            direction=Direction.INPUT,
            amount=reported("t", 1000.0, "kg/h", source_ref="x"),
            mass_fractions={"Cu": reported("w", 0.5, "1", source_ref="x")},
        )
        assert stream.kind is QuantityKind.MASS_FLOW
        assert stream.is_flow

    def test_mass_fractions_must_be_fractions(self):
        with pytest.raises(StreamError, match="must be MASS_FRACTION"):
            Stream(
                stream_id="S",
                label="s",
                direction=Direction.INPUT,
                amount=reported("t", 1.0, "kg", source_ref="x"),
                mass_fractions={"Cu": reported("w", 1.0, "kg", source_ref="x")},
            )

    def test_partial_composition_must_declare_what_is_absent(self):
        # An omission here would act like a zero fraction once sum(w) = 1 is
        # generated, so it has to be stated rather than inferred.
        with pytest.raises(BalanceSystemError, match="absent_components"):
            BalanceSystem(
                system_id="sys",
                label="partial composition",
                process_mode=ProcessMode.STEADY_STATE,
                basis=BalanceBasis.MASS,
                components=copper_and_zinc(),
                streams=(
                    Stream(
                        stream_id="S1",
                        label="in",
                        direction=Direction.INPUT,
                        amount=reported("t", 100.0, "kg/h", source_ref="x"),
                        mass_fractions={"Cu": reported("w", 1.0, "1", source_ref="x")},
                    ),
                ),
            )

    def test_declaring_the_absent_component_is_accepted(self):
        system = BalanceSystem(
            system_id="sys",
            label="declared absence",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=copper_and_zinc(),
            streams=(
                Stream(
                    stream_id="S1",
                    label="in",
                    direction=Direction.INPUT,
                    amount=reported("t", 100.0, "kg/h", source_ref="x"),
                    mass_fractions={"Cu": reported("w", 1.0, "1", source_ref="x")},
                    absent_components=("Zn",),
                ),
            ),
        )
        assert system.stream("S1").absent_components == ("Zn",)

    def test_component_amounts_gap_is_reported_not_fatal(self):
        system = BalanceSystem(
            system_id="sys",
            label="component amounts with a gap",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=copper_and_zinc(),
            streams=(
                Stream(
                    stream_id="S1",
                    label="in",
                    direction=Direction.INPUT,
                    component_amounts={
                        "Cu": reported("c", 100.0, "kg/h", source_ref="x")
                    },
                ),
            ),
        )
        gaps = system.component_amounts_gap()
        assert len(gaps) == 1 and gaps[0][1] == {"Zn"}

    def test_time_basis_is_taken_from_the_unit_when_not_stated(self):
        stream = Stream(
            stream_id="S",
            label="s",
            direction=Direction.INPUT,
            amount=reported("t", 1.0, "kg/min", source_ref="x"),
            mass_fractions={"Cu": reported("w", 1.0, "1", source_ref="x")},
        )
        # normalised to the kg/h base, the basis is hours
        assert stream.effective_time_basis() == "h"

    def test_duplicate_variable_ids_are_refused(self):
        shared = stream_total_id("t")
        with pytest.raises(BalanceSystemError, match="declared twice"):
            BalanceSystem(
                system_id="sys",
                label="duplicate ids",
                process_mode=ProcessMode.STEADY_STATE,
                basis=BalanceBasis.MASS,
                components=copper_and_zinc(),
                streams=(
                    Stream(
                        stream_id="S1",
                        label="a",
                        direction=Direction.INPUT,
                        amount=unknown(shared, QuantityKind.MASS_FLOW),
                        mass_fractions={"Cu": reported("w", 1.0, "1", source_ref="x")},
                        absent_components=("Zn",),
                    ),
                    Stream(
                        stream_id="S2",
                        label="b",
                        direction=Direction.OUTPUT,
                        amount=unknown(shared, QuantityKind.MASS_FLOW),
                        mass_fractions={"Cu": reported("w", 1.0, "1", source_ref="x")},
                        absent_components=("Zn",),
                    ),
                ),
            )


# --------------------------------------------------------------------------- #
# process mode discipline
# --------------------------------------------------------------------------- #


class TestProcessModeDiscipline:
    def test_steady_state_rejects_a_batch_stream(self):
        with pytest.raises(ProcessModeError, match="does not admit"):
            BalanceSystem(
                system_id="sys",
                label="mode mismatch",
                process_mode=ProcessMode.STEADY_STATE,
                basis=BalanceBasis.MASS,
                components=copper_and_zinc(),
                streams=(
                    Stream(
                        stream_id="S1",
                        label="initial",
                        direction=Direction.INITIAL,
                        component_amounts={
                            "Cu": reported("c", 1.0, "kg", source_ref="x")
                        },
                    ),
                    Stream(
                        stream_id="S2",
                        label="final",
                        direction=Direction.FINAL,
                        component_amounts={
                            "Cu": reported("c", 2.0, "kg", source_ref="x")
                        },
                    ),
                ),
            )

    def test_batch_rejects_a_flow(self):
        with pytest.raises(BalanceSystemError, match="no material flows"):
            BalanceSystem(
                system_id="sys",
                label="batch with a flow",
                process_mode=ProcessMode.BATCH,
                basis=BalanceBasis.MASS,
                components=copper_and_zinc(),
                streams=(
                    Stream(
                        stream_id="S1",
                        label="initial",
                        direction=Direction.INITIAL,
                        component_amounts={
                            "Cu": reported("c", 1.0, "kg/h", source_ref="x")
                        },
                    ),
                    Stream(
                        stream_id="S2",
                        label="final",
                        direction=Direction.FINAL,
                        component_amounts={
                            "Cu": reported("c", 2.0, "kg", source_ref="x")
                        },
                    ),
                ),
            )

    def test_steady_state_rejects_an_inventory(self):
        with pytest.raises(BalanceSystemError, match="steady_state is a flow mode"):
            BalanceSystem(
                system_id="sys",
                label="steady state in kg",
                process_mode=ProcessMode.STEADY_STATE,
                basis=BalanceBasis.MASS,
                components=copper_and_zinc(),
                streams=(
                    Stream(
                        stream_id="S1",
                        label="in",
                        direction=Direction.INPUT,
                        component_amounts={
                            "Cu": reported("c", 1.0, "kg", source_ref="x")
                        },
                    ),
                    Stream(
                        stream_id="S2",
                        label="out",
                        direction=Direction.OUTPUT,
                        component_amounts={
                            "Cu": reported("c", 2.0, "kg", source_ref="x")
                        },
                    ),
                ),
            )

    def test_mode_requires_its_anchor_streams(self):
        with pytest.raises(ProcessModeError, match="at least one"):
            BalanceSystem(
                system_id="sys",
                label="accumulating with no accumulation",
                process_mode=ProcessMode.ACCUMULATING,
                basis=BalanceBasis.MASS,
                components=copper_and_zinc(),
                streams=(
                    Stream(
                        stream_id="S1",
                        label="in",
                        direction=Direction.INPUT,
                        component_amounts={
                            "Cu": reported("c", 1.0, "kg", source_ref="x")
                        },
                    ),
                    Stream(
                        stream_id="S2",
                        label="out",
                        direction=Direction.OUTPUT,
                        component_amounts={
                            "Cu": reported("c", 2.0, "kg", source_ref="x")
                        },
                    ),
                ),
            )

    def test_crossing_streams_must_be_commensurable(self):
        with pytest.raises(BalanceSystemError, match="in the same units"):
            BalanceSystem(
                system_id="sys",
                label="mixing a rate and an amount",
                process_mode=ProcessMode.ACCUMULATING,
                basis=BalanceBasis.MASS,
                components=copper_and_zinc(),
                streams=(
                    Stream(
                        stream_id="S1",
                        label="in",
                        direction=Direction.INPUT,
                        component_amounts={
                            "Cu": reported("c", 1.0, "kg/h", source_ref="x")
                        },
                    ),
                    Stream(
                        stream_id="S2",
                        label="out",
                        direction=Direction.OUTPUT,
                        component_amounts={
                            "Cu": reported("c", 2.0, "kg", source_ref="x")
                        },
                    ),
                    Stream(
                        stream_id="S3",
                        label="held",
                        direction=Direction.ACCUMULATED,
                        component_amounts={
                            "Cu": reported("c", 3.0, "kg", source_ref="x")
                        },
                    ),
                ),
            )

    def test_amount_basis_refuses_mass_quantities(self):
        with pytest.raises(BalanceSystemError, match="balance basis is"):
            BalanceSystem(
                system_id="sys",
                label="mass data on an amount basis",
                process_mode=ProcessMode.STEADY_STATE,
                basis=BalanceBasis.AMOUNT,
                components=copper_and_zinc(),
                streams=(
                    Stream(
                        stream_id="S1",
                        label="in",
                        direction=Direction.INPUT,
                        component_amounts={
                            "Cu": reported("c", 1.0, "kg/h", source_ref="x")
                        },
                    ),
                ),
            )


# --------------------------------------------------------------------------- #
# equation generation
# --------------------------------------------------------------------------- #


def _two_component_system(**overrides) -> BalanceSystem:
    cu, zn = copper_and_zinc()
    kwargs = dict(
        system_id="two-component",
        label="mixer",
        process_mode=ProcessMode.STEADY_STATE,
        basis=BalanceBasis.MASS,
        components=(cu, zn),
        streams=(
            Stream(
                stream_id="F",
                label="feed",
                direction=Direction.INPUT,
                amount=reported("F:total", 1000.0, "kg/h", source_ref="p.1"),
                mass_fractions={
                    "Cu": reported("F:w_Cu", 0.6, "1", source_ref="p.1"),
                    "Zn": reported("F:w_Zn", 0.4, "1", source_ref="p.1"),
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
    kwargs.update(overrides)
    return BalanceSystem(**kwargs)


class TestEquationGeneration:
    def test_one_balance_per_component_plus_one_composition_sum(self):
        equations = generate_equations(_two_component_system()).equations
        kinds = [e.kind for e in equations]
        assert kinds == [
            EquationKind.COMPONENT_BALANCE,
            EquationKind.COMPONENT_BALANCE,
            EquationKind.COMPOSITION_SUM,
        ]

    def test_steady_state_balance_puts_inputs_plus_and_outputs_minus(self):
        equations = generate_equations(_two_component_system()).equations
        copper = equations[0]
        assert copper.coefficients == {stream_component_id("P", "Cu"): -1.0}
        # 1000 * 0.6 = 600 kg/h of copper enters, as one retained constant
        assert copper.constant_sum == pytest.approx(600.0)

    def test_steady_state_balance_is_the_chapter_form(self):
        # the expression shows which reported numbers were multiplied, so the
        # constant can be traced back to the measurements that produced it
        expression = generate_equations(_two_component_system()).equations[0].expression
        assert expression == "1000 * 0.6 - Cu(P) = 0"

    def test_batch_balance_is_final_minus_initial_minus_added_plus_removed(self):
        cu, zn = copper_and_zinc()
        system = BalanceSystem(
            system_id="batch",
            label="charge and discharge",
            process_mode=ProcessMode.BATCH,
            basis=BalanceBasis.MASS,
            components=(cu, zn),
            balances=("Cu",),
            streams=(
                Stream(
                    stream_id="I",
                    label="initial",
                    direction=Direction.INITIAL,
                    component_amounts={"Cu": reported("I:Cu", 100.0, "kg", source_ref="p")},
                ),
                Stream(
                    stream_id="D",
                    label="added",
                    direction=Direction.ADDED,
                    component_amounts={"Cu": reported("D:Cu", 50.0, "kg", source_ref="p")},
                ),
                Stream(
                    stream_id="R",
                    label="removed",
                    direction=Direction.REMOVED,
                    component_amounts={"Cu": reported("R:Cu", 20.0, "kg", source_ref="p")},
                ),
                Stream(
                    stream_id="F",
                    label="final",
                    direction=Direction.FINAL,
                    component_amounts={
                        "Cu": unknown(stream_component_id("F", "Cu"), QuantityKind.MASS)
                    },
                ),
            ),
        )
        equation = generate_equations(system).equations[0]
        # final - initial - added + removed = 0  =>  F = 100 + 50 - 20 = 130
        assert equation.coefficients == {stream_component_id("F", "Cu"): 1.0}
        assert equation.constant_sum == pytest.approx(-130.0)
        assert solve_balance(system).variables[0].value == pytest.approx(130.0)

    def test_accumulating_balance_puts_accumulation_on_the_output_side(self):
        cu, zn = copper_and_zinc()
        system = BalanceSystem(
            system_id="accum",
            label="condensation",
            process_mode=ProcessMode.ACCUMULATING,
            basis=BalanceBasis.MASS,
            components=(cu, zn),
            balances=("Cu",),
            streams=(
                Stream(
                    stream_id="V",
                    label="vapour",
                    direction=Direction.INPUT,
                    component_amounts={"Cu": reported("V:Cu", 500.0, "kg", source_ref="p")},
                ),
                Stream(
                    stream_id="L",
                    label="liquid",
                    direction=Direction.OUTPUT,
                    component_amounts={"Cu": reported("L:Cu", 300.0, "kg", source_ref="p")},
                ),
                Stream(
                    stream_id="C",
                    label="condensate",
                    direction=Direction.ACCUMULATED,
                    component_amounts={
                        "Cu": unknown(stream_component_id("C", "Cu"), QuantityKind.MASS)
                    },
                ),
            ),
        )
        equation = generate_equations(system).equations[0]
        assert equation.coefficients == {stream_component_id("C", "Cu"): -1.0}
        assert solve_balance(system).variables[0].value == pytest.approx(200.0)

    def test_composition_sum_is_generated_only_for_fraction_streams(self):
        system = _two_component_system()
        result = solve_balance(system)
        composition = [
            e for e in result.equations if e.kind is EquationKind.COMPOSITION_SUM
        ]
        assert [e.stream_id for e in composition] == ["F"]

    def test_composition_sum_with_no_unknowns_still_checks_the_data(self):
        # all fractions known and summing to 1: a dependent equation, useful as
        # a check exactly as sec. 4.6.2 says, even though it adds no rank
        result = solve_balance(_two_component_system())
        composition = next(
            e for e in result.equations if e.kind is EquationKind.COMPOSITION_SUM
        )
        assert composition.coefficients == {}
        assert composition.constant_sum == pytest.approx(0.0)

    def test_a_non_closing_composition_is_reported_not_silently_fixed(self):
        system = _two_component_system()
        broken = BalanceSystem(
            system_id=system.system_id,
            label=system.label,
            process_mode=system.process_mode,
            basis=system.basis,
            components=system.components,
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    amount=reported("F:total", 1000.0, "kg/h", source_ref="p.1"),
                    mass_fractions={
                        "Cu": reported("F:w_Cu", 0.6, "1", source_ref="p.1"),
                        "Zn": reported("F:w_Zn", 0.5, "1", source_ref="p.1"),
                    },
                ),
                *system.streams[1:],
            ),
        )
        result = solve_balance(broken)
        assert result.solvability is Solvability.INCONSISTENT

    def test_bilinear_balance_is_skipped_with_a_named_diagnostic(self):
        cu, zn = copper_and_zinc()
        system = BalanceSystem(
            system_id="bilinear",
            label="total and composition both unknown",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=(cu, zn),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    amount=reported("F:total", 100.0, "kg/h", source_ref="p"),
                    mass_fractions={
                        "Cu": reported("F:w_Cu", 0.5, "1", source_ref="p"),
                        "Zn": reported("F:w_Zn", 0.5, "1", source_ref="p"),
                    },
                ),
                Stream(
                    stream_id="P",
                    label="product",
                    direction=Direction.OUTPUT,
                    amount=unknown(stream_total_id("P"), QuantityKind.MASS_FLOW),
                    mass_fractions={
                        "Cu": unknown(stream_fraction_id("P", "Cu"), QuantityKind.MASS_FRACTION),
                        "Zn": unknown(stream_fraction_id("P", "Zn"), QuantityKind.MASS_FRACTION),
                    },
                ),
            ),
        )
        equations = generate_equations(system)
        # the product stream makes both component balances bilinear, so neither
        # is generated; only the two composition sums survive
        assert [e.kind for e in equations.equations] == [
            EquationKind.COMPOSITION_SUM,
            EquationKind.COMPOSITION_SUM,
        ]
        skipped = [
            d for d in equations.diagnostics if d.code == "balance.non_linear_skipped"
        ]
        assert len(skipped) == 2
        assert "total(P) * w(P,Cu)" in skipped[0].message
        assert "total(P) * w(P,Zn)" in skipped[1].message

    def test_explicitly_requested_bilinear_balance_is_an_error(self):
        cu, zn = copper_and_zinc()
        system = BalanceSystem(
            system_id="bilinear",
            label="explicitly requested",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=(cu, zn),
            balances=("Cu",),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    amount=reported("F:total", 100.0, "kg/h", source_ref="p"),
                    mass_fractions={
                        "Cu": reported("F:w_Cu", 0.5, "1", source_ref="p"),
                        "Zn": reported("F:w_Zn", 0.5, "1", source_ref="p"),
                    },
                ),
                Stream(
                    stream_id="P",
                    label="product",
                    direction=Direction.OUTPUT,
                    amount=unknown(stream_total_id("P"), QuantityKind.MASS_FLOW),
                    mass_fractions={
                        "Cu": unknown(stream_fraction_id("P", "Cu"), QuantityKind.MASS_FRACTION),
                        "Zn": unknown(stream_fraction_id("P", "Zn"), QuantityKind.MASS_FRACTION),
                    },
                ),
            ),
        )
        equations = generate_equations(system)
        assert [e.kind for e in equations.equations] == [
            EquationKind.COMPOSITION_SUM,
            EquationKind.COMPOSITION_SUM,
        ]
        assert all(
            d.severity.value == "error"
            for d in equations.diagnostics
            if d.code == "balance.non_linear_skipped"
        )

    def test_internal_stream_cancels_and_is_reported(self):
        cu, zn = copper_and_zinc()
        system = BalanceSystem(
            system_id="with-internal",
            label="two devices around one control volume",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=(cu, zn),
            balances=("Cu",),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    component_amounts={"Cu": reported("F:Cu", 100.0, "kg/h", source_ref="p")},
                ),
                Stream(
                    stream_id="T",
                    label="transfer",
                    direction=Direction.INTERNAL,
                    component_amounts={
                        "Cu": unknown(stream_component_id("T", "Cu"), QuantityKind.MASS_FLOW)
                    },
                ),
                Stream(
                    stream_id="P",
                    label="product",
                    direction=Direction.OUTPUT,
                    component_amounts={"Cu": reported("P:Cu", 100.0, "kg/h", source_ref="p")},
                ),
            ),
        )
        equations = generate_equations(system)
        assert equations.equations[0].coefficients == {}
        assert equations.equations[0].constant_sum == pytest.approx(0.0)
        codes = {d.code for d in equations.diagnostics}
        assert "stream.internal_cancels" in codes
        result = solve_balance(system)
        assert "variable.internal_cancels" in {d.code for d in result.diagnostics}
        # the cancelling variable is reported, never silently dropped
        assert "stream:T:Cu" in {
            v.variable_id for v in result.unresolved
        } or result.n_unknowns == 0

    def test_user_constraints_join_the_system(self):
        # A split fraction: the chapter's subsidiary relation, written as a
        # constraint and given exactly the standing of a balance.
        constraint = BalanceEquation(
            equation_id="split:P1/P2 = 1/3",
            kind=EquationKind.USER_CONSTRAINT,
            label="a quarter of the copper goes to P1",
            expression="0.75 * Cu(P1) - 0.25 * Cu(P2) = 0",
            coefficients={
                stream_component_id("P1", "Cu"): 0.75,
                stream_component_id("P2", "Cu"): -0.25,
            },
            source_ref="split ratio supplied by the operator",
        )
        system = BalanceSystem(
            system_id="with-constraint",
            label="constrained splitter",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=copper_and_zinc(),
            balances=("Cu",),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    component_amounts={"Cu": reported("F:Cu", 1000.0, "kg/h", source_ref="p")},
                ),
                Stream(
                    stream_id="P1",
                    label="rich product",
                    direction=Direction.OUTPUT,
                    component_amounts={
                        "Cu": unknown(stream_component_id("P1", "Cu"), QuantityKind.MASS_FLOW)
                    },
                ),
                Stream(
                    stream_id="P2",
                    label="lean product",
                    direction=Direction.OUTPUT,
                    component_amounts={
                        "Cu": unknown(stream_component_id("P2", "Cu"), QuantityKind.MASS_FLOW)
                    },
                ),
            ),
            constraints=(constraint,),
        )
        result = solve_balance(system)
        assert "split:P1/P2 = 1/3" in {e.equation_id for e in result.equations}
        assert result.solvability is Solvability.UNIQUE
        # the constraint is load-bearing: without it the system is underdetermined
        assert solve_balance(
            BalanceSystem(
                system_id="unconstrained",
                label="no split ratio",
                process_mode=ProcessMode.STEADY_STATE,
                basis=BalanceBasis.MASS,
                components=copper_and_zinc(),
                balances=("Cu",),
                streams=system.streams,
            )
        ).solvability is Solvability.UNDERDETERMINED
        values = {v.variable_id: v.value for v in result.variables}
        assert values[stream_component_id("P1", "Cu")] == pytest.approx(250.0)
        assert values[stream_component_id("P2", "Cu")] == pytest.approx(750.0)

    def test_equation_constants_keep_their_provenance(self):
        result = solve_balance(_two_component_system())
        copper = result.equations[0]
        assert copper.constants
        constant = copper.constants[0]
        assert isinstance(constant, ConstantTerm)
        assert constant.derivation is not None
        assert "F:w_Cu" in constant.derivation

    def test_reported_constants_carry_their_source(self):
        cu, zn = copper_and_zinc()
        system = BalanceSystem(
            system_id="sources",
            label="sourced constants",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=(cu, zn),
            balances=("Cu",),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    component_amounts={"Cu": reported("F:Cu", 100.0, "kg/h", source_ref="p.1")},
                ),
                Stream(
                    stream_id="P",
                    label="product",
                    direction=Direction.OUTPUT,
                    component_amounts={
                        "Cu": unknown(stream_component_id("P", "Cu"), QuantityKind.MASS_FLOW)
                    },
                ),
            ),
        )
        constant = solve_balance(system).equations[0].constants[0]
        assert constant.provenance is Provenance.REPORTED
        assert constant.source_ref == "p.1"

    def test_an_assumed_quantity_is_labelled_as_such_in_the_equation(self):
        cu, zn = copper_and_zinc()
        system = BalanceSystem(
            system_id="assumed",
            label="assumed input",
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
                        "Cu": assumed(
                            "F:Cu",
                            100.0,
                            "kg/h",
                            assumption_id="A-01",
                            rationale="the meter is unreliable at low flow",
                        )
                    },
                ),
                Stream(
                    stream_id="P",
                    label="product",
                    direction=Direction.OUTPUT,
                    component_amounts={
                        "Cu": unknown(stream_component_id("P", "Cu"), QuantityKind.MASS_FLOW)
                    },
                ),
            ),
        )
        constant = solve_balance(system).equations[0].constants[0]
        assert constant.provenance is Provenance.ASSUMED
        assert "A-01" in (constant.source_ref or "")


# --------------------------------------------------------------------------- #
# solvability
# --------------------------------------------------------------------------- #


class TestSolvability:
    def test_a_well_posed_system_is_unique(self, cd_zn_result):
        assert cd_zn_result.solvability is Solvability.UNIQUE
        assert cd_zn_result.rank == cd_zn_result.n_unknowns
        assert cd_zn_result.balances_close

    def test_an_underdetermined_system_reports_its_free_variables(self):
        system = BalanceSystem(
            system_id="under",
            label="not enough data",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=copper_and_zinc(),
            balances=("Cu",),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    component_amounts={"Cu": reported("F:Cu", 100.0, "kg/h", source_ref="p")},
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
        assert result.n_unknowns == 2 and result.rank == 1
        assert [u.variable_id for u in result.unresolved] == [
            stream_component_id("P", "Zn")
        ]
        assert "under-determined" in result.unresolved[0].reason
        assert "system.underdetermined" in {d.code for d in result.diagnostics}

    def test_an_underdetermined_system_still_reports_what_it_can(self):
        # Section 4.7.2: an under-specified balance "may still be obtained"
        # useful information from, and the copper balance does pin one variable.
        system = BalanceSystem(
            system_id="under",
            label="partially determined",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=copper_and_zinc(),
            balances=("Cu",),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    component_amounts={"Cu": reported("F:Cu", 100.0, "kg/h", source_ref="p")},
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
        solved = {v.variable_id: v.value for v in result.variables}
        assert solved == {stream_component_id("P", "Cu"): pytest.approx(100.0)}

    def test_a_free_variable_is_never_reported_as_zero(self):
        # The representative solution sets free columns to 0.  Reporting that as
        # a solved value would be precisely the fabrication this engine exists to
        # prevent: an unknown silently becoming a measured zero.
        system = BalanceSystem(
            system_id="under",
            label="free variable must stay free",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=copper_and_zinc(),
            balances=("Cu",),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    component_amounts={"Cu": reported("F:Cu", 100.0, "kg/h", source_ref="p")},
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
        solved_ids = {v.variable_id for v in result.variables}
        free_ids = {u.variable_id for u in result.unresolved}
        assert solved_ids & free_ids == set()
        assert stream_component_id("P", "Zn") in free_ids
        assert stream_component_id("P", "Zn") not in solved_ids
        assert all(v.value != 0.0 for v in result.variables)

    def test_an_inconsistent_system_solves_nothing_and_reports_residuals(self):
        system = BalanceSystem(
            system_id="inconsistent",
            label="measurements that disagree",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=copper_and_zinc(),
            balances=("Cu",),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    component_amounts={
                        "Cu": reported("F:Cu", 100.0, "kg/h", source_ref="p.1")
                    },
                ),
                Stream(
                    stream_id="P",
                    label="product",
                    direction=Direction.OUTPUT,
                    component_amounts={
                        "Cu": reported("P:Cu", 90.0, "kg/h", source_ref="p.1"),
                        "Zn": unknown(stream_component_id("P", "Zn"), QuantityKind.MASS_FLOW),
                    },
                ),
            ),
        )
        result = solve_balance(system)
        assert result.solvability is Solvability.INCONSISTENT
        assert result.variables == ()
        assert len(result.unresolved) == 1
        assert "inconsistent" in result.unresolved[0].reason
        assert not result.balances_close
        residual = next(r for r in result.component_residuals if r.component_id == "Cu")
        assert residual.value == pytest.approx(10.0)
        assert residual.is_within_tolerance is False
        assert "system.inconsistent" in {d.code for d in result.diagnostics}

    def test_an_inconsistent_system_does_not_alter_the_measurements(self):
        before = {
            "F:Cu": reported("F:Cu", 100.0, "kg/h", source_ref="p.1"),
            "P:Cu": reported("P:Cu", 90.0, "kg/h", source_ref="p.1"),
        }
        system = BalanceSystem(
            system_id="inconsistent",
            label="measurements that disagree",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=copper_and_zinc(),
            balances=("Cu",),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    component_amounts={"Cu": before["F:Cu"]},
                ),
                Stream(
                    stream_id="P",
                    label="product",
                    direction=Direction.OUTPUT,
                    component_amounts={
                        "Cu": before["P:Cu"],
                        "Zn": unknown(stream_component_id("P", "Zn"), QuantityKind.MASS_FLOW),
                    },
                ),
            ),
        )
        solve_balance(system)
        assert before["F:Cu"].value == 100.0
        assert before["P:Cu"].value == 90.0

    def test_an_overconstrained_but_consistent_system_still_solves(self, dezinc_result):
        # Example 4.3 writes one more equation than it has unknowns: the
        # composition sum of the fully specified condensate is a pure check.
        assert dezinc_result.solvability is Solvability.OVERCONSTRAINED
        assert dezinc_result.n_equations > dezinc_result.rank
        assert dezinc_result.redundant_equation_ids
        assert dezinc_result.balances_close
        assert "system.overconstrained" in {d.code for d in dezinc_result.diagnostics}

    def test_a_fully_specified_system_is_a_verification(self):
        system = BalanceSystem(
            system_id="verify",
            label="all data stated",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=copper_and_zinc(),
            balances=("Cu",),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    component_amounts={"Cu": reported("F:Cu", 100.0, "kg/h", source_ref="p")},
                ),
                Stream(
                    stream_id="P",
                    label="product",
                    direction=Direction.OUTPUT,
                    component_amounts={"Cu": reported("P:Cu", 100.0, "kg/h", source_ref="p")},
                ),
            ),
        )
        result = solve_balance(system)
        assert result.solvability is Solvability.NO_UNKNOWNS
        assert result.n_unknowns == 0
        assert result.balances_close
        assert "system.verification_only" in {d.code for d in result.diagnostics}

    def test_an_empty_equation_set_leaves_everything_free(self):
        system = BalanceSystem(
            system_id="no-equations",
            label="nothing to balance",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=copper_and_zinc(),
            balances=(),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    component_amounts={
                        "Cu": unknown(stream_component_id("F", "Cu"), QuantityKind.MASS_FLOW)
                    },
                ),
                Stream(
                    stream_id="P",
                    label="product",
                    direction=Direction.OUTPUT,
                    component_amounts={
                        "Cu": unknown(stream_component_id("P", "Cu"), QuantityKind.MASS_FLOW)
                    },
                ),
            ),
        )
        result = solve_balance(system)
        assert result.n_equations == 0
        assert len(result.unresolved) == 2

    def test_a_constraint_naming_an_undeclared_variable_is_refused(self):
        constraint = BalanceEquation(
            equation_id="bogus",
            kind=EquationKind.USER_CONSTRAINT,
            label="nonsense",
            expression="x = 1",
            coefficients={"stream:ghost:total": 1.0},
        )
        with pytest.raises(BalanceSystemError, match="no stream declares"):
            BalanceSystem(
                system_id="bogus",
                label="undeclared variable",
                process_mode=ProcessMode.STEADY_STATE,
                basis=BalanceBasis.MASS,
                components=copper_and_zinc(),
                balances=("Cu",),
                streams=(
                    Stream(
                        stream_id="F",
                        label="feed",
                        direction=Direction.INPUT,
                        component_amounts={
                            "Cu": reported("F:Cu", 100.0, "kg/h", source_ref="p")
                        },
                    ),
                    Stream(
                        stream_id="P",
                        label="product",
                        direction=Direction.OUTPUT,
                        component_amounts={
                            "Cu": unknown(
                                stream_component_id("P", "Cu"), QuantityKind.MASS_FLOW
                            )
                        },
                    ),
                ),
                constraints=(constraint,),
            )

    def test_duplicate_equations_are_reported_as_dependent(self):
        # A second copy of the copper balance under a different id: the
        # equation count grows but the rank does not (sec. 4.6.2, "if you have
        # too many equations, one or more might be redundant").
        eq_set = generate_equations(_two_component_system())
        duplicate = BalanceEquation(
            equation_id="balance:duplicate:Cu",
            kind=EquationKind.COMPONENT_BALANCE,
            label="the copper balance, stated again",
            expression=eq_set.equations[0].expression,
            coefficients=dict(eq_set.equations[0].coefficients),
            constants=eq_set.equations[0].constants,
        )
        variables = sorted({v for e in eq_set.equations for v in e.coefficients})
        single = solve_linear(eq_set.equations, variables)
        doubled = solve_linear(eq_set.equations + [duplicate], variables)
        assert doubled.rank == single.rank
        assert doubled.n_equations == single.n_equations + 1
        assert "balance:duplicate:Cu" in doubled.redundant_equation_ids
        # a dependent equation is still a valid check, so the solve stands
        assert doubled.is_authoritative
        assert doubled.classification is Solvability.OVERCONSTRAINED
        assert all(abs(v) < 1e-9 for v in doubled.equation_residuals.values())


class TestDeterminism:
    def test_the_same_system_solves_identically_twice(self, brass_system):
        first = solve_balance(brass_system)
        second = solve_balance(brass_system)
        assert [v.variable_id for v in first.variables] == [
            v.variable_id for v in second.variables
        ]
        assert [v.value for v in first.variables] == [v.value for v in second.variables]
        assert first.to_dict() == second.to_dict()

    def test_equation_order_is_deterministic(self, cd_zn_system):
        first = [e.equation_id for e in generate_equations(cd_zn_system).equations]
        second = [e.equation_id for e in generate_equations(cd_zn_system).equations]
        assert first == second

    def test_solved_values_are_exact_for_clean_data(self, cd_zn_result):
        for variable in cd_zn_result.variables:
            assert math.isfinite(variable.value)


# --------------------------------------------------------------------------- #
# residuals
# --------------------------------------------------------------------------- #


class TestResiduals:
    def test_closing_system_has_zero_residuals(self, cd_zn_result):
        assert cd_zn_result.total_mass_residual is not None
        assert cd_zn_result.total_mass_residual.value == pytest.approx(0.0, abs=1e-9)
        for residual in cd_zn_result.component_residuals:
            assert residual.value == pytest.approx(0.0, abs=1e-9)
            assert residual.is_within_tolerance

    def test_residuals_name_the_streams_that_produced_them(self, cd_zn_result):
        residual = next(
            r for r in cd_zn_result.component_residuals if r.component_id == "Cd"
        )
        assert {c.stream_id for c in residual.contributions} == {"A", "B", "C"}

    def test_residuals_are_computed_even_for_unbalanced_components(self, dezinc_result):
        # Example 4.3 generates no lead balance -- the book says it "won't help"
        # -- yet the lead residual is still checked after the solve.
        lead = next(
            r for r in dezinc_result.component_residuals if r.component_id == "Pb"
        )
        assert lead.is_within_tolerance
        assert abs(lead.value) < 1e-6

    def test_total_residual_is_reported_in_the_basis_unit(self, brass_result):
        assert brass_result.basis_unit == "kg"
        assert brass_result.total_mass_residual.unit == "kg"

    def test_a_non_closing_balance_is_flagged(self):
        system = BalanceSystem(
            system_id="non-closing",
            label="streams that do not add up",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=copper_and_zinc(),
            balances=(),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    component_amounts={
                        "Cu": reported("F:Cu", 100.0, "kg/h", source_ref="p")
                    },
                ),
                Stream(
                    stream_id="P",
                    label="product",
                    direction=Direction.OUTPUT,
                    component_amounts={
                        "Cu": reported("P:Cu", 80.0, "kg/h", source_ref="p")
                    },
                ),
            ),
        )
        result = solve_balance(system)
        assert result.total_mass_residual.value == pytest.approx(20.0)
        assert not result.balances_close
        assert "residual.exceeds_tolerance" in {d.code for d in result.diagnostics}


# --------------------------------------------------------------------------- #
# degrees of freedom
# --------------------------------------------------------------------------- #


class TestDegreesOfFreedom:
    def test_salt_cake_bookkeeping_reproduces_the_chapter(self):
        # "The DOF for the salt cake process = 14 - 4 - 4 - 3 - 2 = +1"
        assert SALTCAKE_PROCESS.dof == 1
        assert SALTCAKE_PROCESS.classification == "under_specified"

    def test_spent_gas_splitter_is_correctly_specified(self):
        assert SPENT_GAS_SPLITTER.dof == 0

    def test_incomplete_bookkeeping_reports_no_dof(self):
        partial = DegreeOfFreedom(label="partial", sv=14, ib=4, ic=4, f=3)
        assert partial.dof is None
        assert partial.is_computable is False
        assert partial.missing_terms == ("sr",)
        assert partial.classification is None

    def test_an_incomplete_dof_is_never_read_as_zero(self):
        # the whole point: an unknown count must not collapse into DOF = 0
        complete = DegreeOfFreedom(label="complete", sv=14, ib=4, ic=4, f=3, sr=2)
        partial = DegreeOfFreedom(label="partial", sv=14, ib=4, ic=4, f=3)
        assert complete.dof == 1
        assert partial.dof is None
        assert partial.classification is None
        assert partial.missing_terms == ("sr",)

    def test_process_dof_does_not_double_count_connecting_streams(self):
        # Table 4.6: 8 + 8 - 3 = 13, not 16
        combined = process_dof(
            [DISTILLATION_STILL_I, DISTILLATION_STILL_II],
            connecting_stream_variables=3,
            connecting_stream_compositions=2,
        )
        assert combined.sv == DISTILLATION_PROCESS.sv
        assert combined.ib == DISTILLATION_PROCESS.ib
        assert combined.ic == DISTILLATION_PROCESS.ic
        assert combined.dof == DISTILLATION_PROCESS.dof

    def test_table_4_6_device_counts(self):
        assert (DISTILLATION_STILL_I.sv, DISTILLATION_STILL_I.dof) == (8, 0)
        assert (DISTILLATION_STILL_II.sv, DISTILLATION_STILL_II.dof) == (8, 1)
        assert (DISTILLATION_PROCESS.sv, DISTILLATION_PROCESS.dof) == (13, 0)
        assert (DISTILLATION_OVERALL.sv, DISTILLATION_OVERALL.dof) == (10, 2)

    def test_independent_dof_comes_from_the_matrix(self):
        independent = IndependentDegreesOfFreedom(n_unknowns=3, n_equations=3, rank=3)
        assert independent.dof == 0
        assert independent.redundant_equations == 0
        assert independent.classification == "correctly_specified"

    def test_independent_dof_rejects_an_impossible_rank(self):
        with pytest.raises(ValueError, match="out of range"):
            IndependentDegreesOfFreedom(n_unknowns=2, n_equations=2, rank=3)

    def test_agreeing_counts_are_reported_as_agreeing(self):
        comparison = compare_freedom(
            SALTCAKE_PROCESS,
            independent=IndependentDegreesOfFreedom(n_unknowns=3, n_equations=2, rank=2),
        )
        assert comparison.bookkeeping_dof == 1
        assert comparison.independent_dof == 1
        assert comparison.agrees is True
        assert not any(d.code == "dof.counts_disagree" for d in comparison.diagnostics)

    def test_disagreeing_counts_are_reported_not_reconciled(self):
        comparison = compare_freedom(
            SALTCAKE_PROCESS,
            independent=IndependentDegreesOfFreedom(n_unknowns=2, n_equations=2, rank=2),
        )
        assert comparison.bookkeeping_dof == 1
        assert comparison.independent_dof == 0
        assert comparison.agrees is False
        assert any(d.code == "dof.counts_disagree" for d in comparison.diagnostics)

    def test_the_matrix_is_authoritative_when_the_two_disagree(self):
        comparison = compare_freedom(
            SALTCAKE_PROCESS,
            independent=IndependentDegreesOfFreedom(n_unknowns=2, n_equations=2, rank=2),
        )
        assert comparison.authoritative_dof == 0
        assert comparison.bookkeeping_dof == 1

    def test_absence_of_a_rank_is_never_reported_as_agreement(self):
        comparison = compare_freedom(SALTCAKE_PROCESS)
        assert comparison.agrees is None
        assert comparison.authoritative_dof == 1
        assert any(d.code == "dof.no_matrix_rank" for d in comparison.diagnostics)

    def test_incomplete_bookkeeping_is_reported(self):
        comparison = compare_freedom(
            DegreeOfFreedom(label="partial", sv=14, ib=4),
            independent=IndependentDegreesOfFreedom(n_unknowns=4, n_equations=4, rank=4),
        )
        assert any(d.code == "dof.not_computable" for d in comparison.diagnostics)
        assert comparison.authoritative_dof == 0

    def test_redundant_equations_are_surfaced(self):
        comparison = compare_freedom(
            DegreeOfFreedom(label="redundant", sv=3, ib=1, ic=1, f=1, sr=0),
            independent=IndependentDegreesOfFreedom(n_unknowns=1, n_equations=3, rank=1),
        )
        assert any(d.code == "dof.redundant_equations" for d in comparison.diagnostics)

    def test_bookkeeping_attaches_to_a_result(self, cd_zn_system):
        result = solve_balance(cd_zn_system, dof=SALTCAKE_PROCESS)
        assert result.freedom is not None
        # the matrix says 3 unknowns of rank 3; the chapter's salt cake figure
        # describes a different system, so the two must not be conflated
        assert result.freedom.bookkeeping_dof == 1
        assert result.freedom.independent_dof == 0
        assert result.freedom.agrees is False
        assert any(d.code == "dof.counts_disagree" for d in result.diagnostics)


# --------------------------------------------------------------------------- #
# regression against the printed examples
# --------------------------------------------------------------------------- #


class TestWorkedExamples:
    """Every value here is printed in Chapter 4."""

    def test_example_4_1_matches_the_book(self, cd_zn_result):
        values = {v.variable_id: v.value for v in cd_zn_result.variables}
        assert values[stream_component_id("B", "Zn")] == pytest.approx(28.0)
        assert values[stream_component_id("C", "Cd")] == pytest.approx(46.0)
        assert values[stream_fraction_id("A", "Zn")] == pytest.approx(0.50)

    def test_example_4_1_ledger_matches_the_book(self, cd_zn_result):
        ledger = {
            (row.stream_id, row.component_id): row.value for row in cd_zn_result.ledger
        }
        # Stream A: 500 Cd, 500 Zn, 1000 total
        assert ledger[("A", "Cd")] == pytest.approx(500.0)
        assert ledger[("A", "Zn")] == pytest.approx(500.0)
        # Stream B (vapour): 28 Zn, 454 Cd, 482 total
        assert ledger[("B", "Zn")] == pytest.approx(28.0)
        assert ledger[("B", "Cd")] == pytest.approx(454.0)
        # Stream C (liquid): 472 Zn, 46 Cd, 518 total
        assert ledger[("C", "Zn")] == pytest.approx(472.0)
        assert ledger[("C", "Cd")] == pytest.approx(46.0)

    def test_example_4_1_compositions_match_the_book(self, cd_zn_result):
        ledger = {
            (row.stream_id, row.component_id): row
            for row in cd_zn_result.ledger
            if row.mass_fraction is not None
        }
        # "wBCd = 0.942" and "wcZn = 0.911"
        assert ledger[("B", "Cd")].mass_fraction == pytest.approx(0.942, abs=5e-4)
        assert ledger[("C", "Zn")].mass_fraction == pytest.approx(0.911, abs=5e-4)

    def test_example_4_1_total_mass_check_matches_the_book(self, cd_zn_result):
        # "1000 = 454 + 46 + 472 + 28 = 1000"
        assert cd_zn_result.total_mass_residual.value == pytest.approx(0.0, abs=1e-9)

    def test_example_4_2_matches_the_book(self, brass_result):
        values = {v.variable_id: v.value for v in brass_result.variables}
        assert values[stream_component_id("D", "Cu")] == pytest.approx(21215.0)
        assert values[stream_component_id("D", "Zn")] == pytest.approx(5385.0)
        assert values[stream_fraction_id("C", "Zn")] == pytest.approx(0.21)

    def test_example_4_2_total_matches_the_book(self, brass_result):
        ledger = {
            (row.stream_id, row.component_id): row.value for row in brass_result.ledger
        }
        assert ledger[("D", "Cu")] + ledger[("D", "Zn")] == pytest.approx(26600.0)

    def test_example_4_2_compositions_match_the_book_to_three_figures(self, brass_result):
        # "wDCu = 0.798" and "wDZn = 0.202"
        ledger = {
            (row.stream_id, row.component_id): row
            for row in brass_result.ledger
            if row.mass_fraction is not None and row.stream_id == "D"
        }
        assert ledger[("D", "Cu")].mass_fraction == pytest.approx(0.798, abs=5e-4)
        assert ledger[("D", "Zn")].mass_fraction == pytest.approx(0.202, abs=5e-4)

    def test_example_4_2_closes(self, brass_result):
        assert brass_result.balances_close
        assert brass_result.solvability is Solvability.UNIQUE

    def test_example_4_3_matches_the_book(self, dezinc_result):
        values = {v.variable_id: v.value for v in dezinc_result.variables}
        # "Bullion: mA = 408 240 kg" and "De-zinced lead: mB = 406 000 kg"
        assert values[stream_total_id("A")] == pytest.approx(408240.0)
        assert values[stream_total_id("B")] == pytest.approx(406000.0)

    def test_example_4_3_ledger_matches_the_book(self, dezinc_result):
        ledger = {
            (row.stream_id, row.component_id): row.value for row in dezinc_result.ledger
        }
        # the book's ledger, rounded to whole kilograms
        assert ledger[("A", "Zn")] == pytest.approx(2245.0, abs=0.5)
        assert ledger[("B", "Zn")] == pytest.approx(122.0, abs=0.5)
        assert ledger[("C", "Zn")] == pytest.approx(2124.0, abs=0.5)
        assert ledger[("A", "Pb")] == pytest.approx(405995.0, abs=0.5)
        assert ledger[("B", "Pb")] == pytest.approx(405878.0, abs=0.5)
        assert ledger[("C", "Pb")] == pytest.approx(116.0, abs=0.5)

    def test_example_4_3_every_balance_closes(self, dezinc_result):
        assert dezinc_result.balances_close
        assert {r.component_id for r in dezinc_result.component_residuals} == {"Zn", "Pb"}

    def test_salt_cake_analysis_based_balance_does_not_close(self):
        # Table 4.1, sec. 4.6.3: a fully sampled balance that nonetheless
        # violates conservation.  The engine must report the gap, not repair it.
        streams = (
            ("S1", "salt cake", Direction.INPUT, 415.0, {"NaCl": 0.644, "Slag": 0.325, "H2O": 0.031, "Air": 0.0}),
            ("S2", "leach soln", Direction.INPUT, 1260.0, {"NaCl": 0.104, "Slag": 0.0, "H2O": 0.896, "Air": 0.0}),
            ("S3", "amb air", Direction.INPUT, 335.0, {"NaCl": 0.0, "Slag": 0.0, "H2O": 0.0105, "Air": 0.9895}),
            ("S4", "wet air", Direction.OUTPUT, 348.0, {"NaCl": 0.0, "Slag": 0.0, "H2O": 0.0804, "Air": 0.9196}),
            ("S5", "salty soln", Direction.OUTPUT, 1435.0, {"NaCl": 0.257, "Slag": 0.0, "H2O": 0.743, "Air": 0.0}),
            ("S6", "slurry liquid", Direction.OUTPUT, 98.0, {"NaCl": 0.267, "Slag": 0.0, "H2O": 0.733, "Air": 0.0}),
            ("S7", "slurry slag", Direction.OUTPUT, 141.0, {"NaCl": 0.0, "Slag": 1.0, "H2O": 0.0, "Air": 0.0}),
        )
        components = (
            Component("NaCl", "sodium chloride", formula="NaCl"),
            Component("Slag", "slag"),
            Component("H2O", "water", formula="H2O"),
            Component("Air", "air"),
        )
        system = BalanceSystem(
            system_id="salt-cake-4.1",
            label="Salt cake leaching, analysis-based (Table 4.1)",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=components,
            streams=tuple(
                Stream(
                    stream_id=sid,
                    label=label,
                    direction=direction,
                    amount=reported(f"{sid}:total", flow, "kg/min", source_ref="Table 4.1"),
                    mass_fractions={
                        c: reported(f"{sid}:w_{c}", w, "1", source_ref="Table 4.1")
                        for c, w in composition.items()
                    },
                )
                for sid, label, direction, flow, composition in streams
            ),
            source_ref=f"{SEC}, Table 4.1, p.158",
        )
        result = solve_balance(system)
        assert result.n_unknowns == 0
        assert result.solvability is Solvability.INCONSISTENT
        assert result.variables == ()
        # inputs 415 + 1260 + 335 = 2010; outputs 348 + 1435 + 98 + 141 = 2022,
        # so the table as printed is 12 kg/min out of balance.  Residuals are
        # reported in the system's normalised basis unit, kg/h.
        assert result.basis_unit == "kg/h"
        assert result.total_mass_residual.value == pytest.approx(-0.2)
        assert convert(result.total_mass_residual.value, "kg/h", "kg/min") == pytest.approx(
            -12.0
        )
        assert not result.balances_close
        assert any(
            d.code == "system.inconsistent" and d.severity.value == "error"
            for d in result.diagnostics
        )


# --------------------------------------------------------------------------- #
# serialization
# --------------------------------------------------------------------------- #


class TestSerialization:
    def test_result_serializes_completely(self, cd_zn_result):
        payload = cd_zn_result.to_dict()
        assert payload["solvability"] == "unique"
        assert payload["process_mode"] == "steady_state"
        assert payload["rank"] == payload["n_unknowns"] == 3
        assert len(payload["equations"]) == 3
        assert len(payload["variables"]) == 3
        assert payload["unresolved"] == []
        assert payload["balances_close"] is True
        assert payload["ledger"]
        assert payload["total_mass_residual"]["is_within_tolerance"] is True

    def test_equations_serialize_their_constants(self, cd_zn_result):
        payload = cd_zn_result.to_dict()
        copper = next(e for e in payload["equations"] if e["component_id"] == "Cd")
        assert copper["kind"] == "component_balance"
        assert copper["constants"]
        assert copper["constants"][0]["provenance"] in ("reported", "derived", "assumed")

    def test_an_assumption_reaches_the_result_and_serializes(self):
        # An assumption is only auditable if it survives into the output, so a
        # result that quietly depends on one cannot be read as source-derived.
        cu, zn = copper_and_zinc()
        note = Assumption(
            assumption_id="A-01",
            statement="stream P is taken to be pure copper",
            rationale="no assay was available for the product stream",
            affects=(stream_component_id("P", "Zn"),),
        )
        system = BalanceSystem(
            system_id="assumed-purity",
            label="product assumed pure",
            process_mode=ProcessMode.STEADY_STATE,
            basis=BalanceBasis.MASS,
            components=(cu, zn),
            balances=("Cu",),
            streams=(
                Stream(
                    stream_id="F",
                    label="feed",
                    direction=Direction.INPUT,
                    component_amounts={"Cu": reported("F:Cu", 100.0, "kg/h", source_ref="p")},
                ),
                Stream(
                    stream_id="P",
                    label="product",
                    direction=Direction.OUTPUT,
                    component_amounts={
                        "Cu": assumed(
                            "P:Cu",
                            100.0,
                            "kg/h",
                            assumption_id="A-01",
                            rationale="no assay was available for the product stream",
                        )
                    },
                    absent_components=("Zn",),
                ),
            ),
            assumptions=(note,),
        )
        result = solve_balance(system)
        assert result.assumptions == (note,)
        payload = result.to_dict()
        assert payload["assumptions"][0]["assumption_id"] == "A-01"
        assert payload["assumptions"][0]["affects"] == [stream_component_id("P", "Zn")]
        assert result.balances_close

    def test_system_serializes(self, cd_zn_system):
        payload = cd_zn_system.to_dict()
        assert payload["basis"] == "mass"
        assert len(payload["streams"]) == 3
        assert payload["basis_unit"] == "kg/h"

    def test_freedom_serializes(self, cd_zn_system):
        result = solve_balance(cd_zn_system, dof=SALTCAKE_PROCESS)
        payload = result.to_dict()["freedom"]
        assert payload["bookkeeping"]["dof"] == 1
        assert payload["independent"]["rank"] == 3
        assert payload["agrees"] is False