"""Shared fixtures.

The three worked examples are transcribed from Morris, Geiger & Fine (2011),
Chapter 4, and are used as regression tests: if a change to the engine makes any
of them stop reproducing the book's printed answer, the change is wrong.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from schemas.material_balance import (  # noqa: E402
    BalanceBasis,
    BalanceEquation,
    BalanceSystem,
    Component,
    Direction,
    EquationKind,
    ProcessMode,
    QuantityKind,
    Stream,
    reported,
    stream_component_id,
    stream_fraction_id,
    stream_total_id,
    unknown,
)
from models.material_balance import solve_balance  # noqa: E402

SEC = "Morris et al. 2011"


# --------------------------------------------------------------------------- #
# Example 4.1, sec. 4.5 -- distillation of a Cd-Zn alloy
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def cd_zn_system() -> BalanceSystem:
    """Example 4.1: 1000 kg/h alloy at wCd = 0.50, vapour carrying 454 kg/h Cd,
    liquid carrying 472 kg/h Zn.  The book solves mC_Cd = 46 and mB_Zn = 28 and
    checks 1000 = 454 + 46 + 472 + 28.
    """
    return BalanceSystem(
        system_id="example-4.1-cd-zn",
        label="Distillation of a Cd-Zn alloy",
        process_mode=ProcessMode.STEADY_STATE,
        basis=BalanceBasis.MASS,
        components=(
            Component("Cd", "cadmium", formula="Cd", molar_mass_kg_per_mol=0.112414),
            Component("Zn", "zinc", formula="Zn", molar_mass_kg_per_mol=0.065388),
        ),
        streams=(
            Stream(
                stream_id="A",
                label="original alloy",
                direction=Direction.INPUT,
                amount=reported("A:total", 1000.0, "kg/h", source_ref=f"{SEC} Example 4.1"),
                mass_fractions={
                    "Cd": reported(
                        "A:w_Cd", 0.50, "1", source_ref=f"{SEC} Example 4.1"
                    ),
                    "Zn": unknown(
                        stream_fraction_id("A", "Zn"),
                        QuantityKind.MASS_FRACTION,
                        reason="the book determines it from the Cd fraction",
                    ),
                },
            ),
            Stream(
                stream_id="B",
                label="vapour",
                direction=Direction.OUTPUT,
                component_amounts={
                    "Cd": reported(
                        stream_component_id("B", "Cd"),
                        454.0,
                        "kg/h",
                        source_ref=f"{SEC} Example 4.1",
                    ),
                    "Zn": unknown(
                        stream_component_id("B", "Zn"),
                        QuantityKind.MASS_FLOW,
                        reason="determined by the zinc balance",
                    ),
                },
                absent_components=(),
            ),
            Stream(
                stream_id="C",
                label="Zn-rich alloy",
                direction=Direction.OUTPUT,
                component_amounts={
                    "Zn": reported(
                        stream_component_id("C", "Zn"),
                        472.0,
                        "kg/h",
                        source_ref=f"{SEC} Example 4.1",
                    ),
                    "Cd": unknown(
                        stream_component_id("C", "Cd"),
                        QuantityKind.MASS_FLOW,
                        reason="determined by the cadmium balance",
                    ),
                },
            ),
        ),
        source_ref=f"{SEC}, sec. 4.5, Example 4.1, pp. 151-152",
    )


@pytest.fixture(scope="session")
def cd_zn_result(cd_zn_system):
    return solve_balance(cd_zn_system)


# --------------------------------------------------------------------------- #
# Example 4.2, sec. 4.5 -- batch charge for a brass melting furnace
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def brass_system() -> BalanceSystem:
    """Example 4.2: 3600 kg Zn, 14500 kg Cu and 8500 kg scrap brass at
    wCu = 0.79 are charged to a hopper.  The book gets 26600 kg of mixture at
    wCu = 0.798 and wZn = 0.202.
    """
    return BalanceSystem(
        system_id="example-4.2-brass-charge",
        label="Batch charge preparation for a brass melting furnace",
        process_mode=ProcessMode.BATCH,
        basis=BalanceBasis.MASS,
        components=(
            Component("Cu", "copper", formula="Cu", molar_mass_kg_per_mol=0.063546),
            Component("Zn", "zinc", formula="Zn", molar_mass_kg_per_mol=0.065388),
        ),
        streams=(
            Stream(
                stream_id="A",
                label="zinc charge",
                direction=Direction.INITIAL,
                component_amounts={
                    "Zn": reported(
                        stream_component_id("A", "Zn"),
                        3600.0,
                        "kg",
                        source_ref=f"{SEC} Example 4.2",
                    )
                },
            ),
            Stream(
                stream_id="B",
                label="copper charge",
                direction=Direction.INITIAL,
                component_amounts={
                    "Cu": reported(
                        stream_component_id("B", "Cu"),
                        14500.0,
                        "kg",
                        source_ref=f"{SEC} Figure 4.11 and the 26600 kg total",
                        note=(
                            "The prose says 14000 kg but the flowsheet and the book's "
                            "own 26600 kg total both require 14500 kg."
                        ),
                    )
                },
            ),
            Stream(
                stream_id="C",
                label="scrap brass",
                direction=Direction.INITIAL,
                amount=reported(
                    stream_total_id("C"), 8500.0, "kg", source_ref=f"{SEC} Example 4.2"
                ),
                mass_fractions={
                    "Cu": reported(
                        "C:w_Cu", 0.79, "1", source_ref=f"{SEC} Example 4.2"
                    ),
                    "Zn": unknown(
                        stream_fraction_id("C", "Zn"),
                        QuantityKind.MASS_FRACTION,
                        reason="follows by difference from wCu",
                    ),
                },
            ),
            Stream(
                stream_id="D",
                label="mixed scrap to furnace",
                direction=Direction.FINAL,
                component_amounts={
                    "Cu": unknown(
                        stream_component_id("D", "Cu"),
                        QuantityKind.MASS,
                        reason="determined by the copper balance",
                    ),
                    "Zn": unknown(
                        stream_component_id("D", "Zn"),
                        QuantityKind.MASS,
                        reason="determined by the zinc balance",
                    ),
                },
            ),
        ),
        source_ref=f"{SEC}, sec. 4.5, Example 4.2, pp. 152-153",
    )


@pytest.fixture(scope="session")
def brass_result(brass_system):
    return solve_balance(brass_system)


# --------------------------------------------------------------------------- #
# Example 4.3, sec. 4.5 -- vacuum de-zincing of lead (accumulating)
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def dezinc_system() -> BalanceSystem:
    """Example 4.3: bullion at wZn = 0.55 %, de-zinced lead at wZn = 0.03 %,
    and 2240 kg of condensate at wPb = 5.20 %.  The book gets 408240 kg of
    bullion and 406000 kg of de-zinced lead, and states that a lead balance adds
    nothing -- which is why only the zinc balance plus the total mass balance are
    generated here.

    The whole balance is stated as masses over one panel cycle rather than as
    rates.  The book's own equations are ``mA = mB + 2240`` and
    ``0.0055 mA = 0.0003 mB + 0.948 * 2240``: a rate would not be commensurable
    with a 2240 kg accumulation, so a per-cycle amount basis is the consistent
    reading.
    """
    return BalanceSystem(
        system_id="example-4.3-dezinc",
        label="Vacuum de-zincing of lead, per panel cycle",
        process_mode=ProcessMode.ACCUMULATING,
        basis=BalanceBasis.MASS,
        balances=("Zn",),
        total_balance=True,
        components=(
            Component("Zn", "zinc", formula="Zn", molar_mass_kg_per_mol=0.065388),
            Component("Pb", "lead", formula="Pb", molar_mass_kg_per_mol=0.2072),
        ),
        streams=(
            Stream(
                stream_id="A",
                label="bullion",
                direction=Direction.INPUT,
                amount=unknown(
                    stream_total_id("A"),
                    QuantityKind.MASS,
                    reason="the mass refined per panel cycle is what is being solved for",
                ),
                mass_fractions={
                    "Zn": reported(
                        "A:w_Zn", 0.0055, "1", source_ref=f"{SEC} Example 4.3"
                    ),
                    "Pb": unknown(
                        stream_fraction_id("A", "Pb"),
                        QuantityKind.MASS_FRACTION,
                        reason="follows by difference",
                    ),
                },
            ),
            Stream(
                stream_id="B",
                label="de-zinced lead",
                direction=Direction.OUTPUT,
                amount=unknown(
                    stream_total_id("B"),
                    QuantityKind.MASS,
                    reason="determined by the total mass balance",
                ),
                mass_fractions={
                    "Zn": reported(
                        "B:w_Zn", 0.0003, "1", source_ref=f"{SEC} Example 4.3"
                    ),
                    "Pb": unknown(
                        stream_fraction_id("B", "Pb"),
                        QuantityKind.MASS_FRACTION,
                        reason="follows by difference",
                    ),
                },
            ),
            Stream(
                stream_id="C",
                label="condensate on the panel",
                direction=Direction.ACCUMULATED,
                amount=reported(
                    stream_total_id("C"), 2240.0, "kg", source_ref=f"{SEC} Example 4.3"
                ),
                mass_fractions={
                    "Zn": reported(
                        "C:w_Zn", 0.948, "1", source_ref=f"{SEC} Example 4.3"
                    ),
                    "Pb": reported(
                        "C:w_Pb", 0.052, "1", source_ref=f"{SEC} Example 4.3"
                    ),
                },
            ),
        ),
        source_ref=f"{SEC}, sec. 4.5, Example 4.3, pp. 153-154",
    )


@pytest.fixture(scope="session")
def dezinc_result(dezinc_system):
    return solve_balance(dezinc_system)


# --------------------------------------------------------------------------- #
# MB-03: a synthetic splitter, used to pin steady-state component conservation
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def splitter_system() -> BalanceSystem:
    """A synthetic two-way splitter, not drawn from the chapter.

    A 160 kg/h feed of component X (100 kg/h) and Y (60 kg/h) divides between two
    products of identical composition, 40% to P1 and 60% to P2:

        P1: X = 40,  Y = 24,  total 64  kg/h
        P2: X = 60,  Y = 36,  total 96  kg/h

    The 40:60 division is supplied as a subsidiary relation in the chapter's
    sense (sec. 4.7.2: "each specified split fraction constitutes a SR"), so the
    system is solvable without any stream being measured twice.
    """
    split_ratio = BalanceEquation(
        equation_id="split:P2/P1 = 1.5",
        kind=EquationKind.USER_CONSTRAINT,
        label="the splitter sends 60% of the feed to P2",
        expression="total(P2) - 1.5 * total(P1) = 0",
        coefficients={stream_total_id("P2"): 1.0, stream_total_id("P1"): -1.5},
        source_ref="MB-03 split ratio, supplied as a subsidiary relation",
    )
    composition = {"X": 0.625, "Y": 0.375}

    def stream(sid, label, direction, amount):
        return Stream(
            stream_id=sid,
            label=label,
            direction=direction,
            amount=amount,
            mass_fractions={
                c: reported(f"{sid}:w_{c}", w, "1", source_ref="MB-03 synthetic splitter")
                for c, w in composition.items()
            },
        )

    return BalanceSystem(
        system_id="mb-03-splitter",
        label="Synthetic two-way splitter",
        process_mode=ProcessMode.STEADY_STATE,
        basis=BalanceBasis.MASS,
        components=(
            Component("X", "component X"),
            Component("Y", "component Y"),
        ),
        streams=(
            stream(
                "F",
                "feed",
                Direction.INPUT,
                reported(stream_total_id("F"), 160.0, "kg/h", source_ref="MB-03"),
            ),
            stream("P1", "product 1", Direction.OUTPUT, unknown(
                stream_total_id("P1"), QuantityKind.MASS_FLOW, reason="solved by the split ratio"
            )),
            stream("P2", "product 2", Direction.OUTPUT, unknown(
                stream_total_id("P2"), QuantityKind.MASS_FLOW, reason="solved by the split ratio"
            )),
        ),
        constraints=(split_ratio,),
        source_ref="MB-03 acceptance fixture",
    )


@pytest.fixture(scope="session")
def splitter_result(splitter_system):
    return solve_balance(splitter_system)
