"""Composition contract: what this model exposes, and what it refuses.

This module is the **single declaration** of Ganjave's composition surface.
The composition layer's worker derives its manifest from here, and
:func:`composition_contract` emits the whole thing as plain data so it can be
frozen, diffed and audited. Nothing about the interface is duplicated in the
adapter.

Three ideas run through it.

**A unit symbol is not a quantity.** ``g/L`` is a culture concentration, a
half-saturation constant and the oxygen saturation concentration; ``%`` is a
half-saturation constant and the dissolved-oxygen reading. Ports are keyed by
:class:`~schemas.units.QuantityKind` and carry an explicit contract
``quantity`` string, so no connection can be made on the strength of a symbol.

**Absent is not zero.** Three initial conditions are not stated in the paper
(``X0``, ``S2_0``, ``DO0``) and are therefore ``required`` inputs. The four that
the paper *does* state carry ``default_value`` together with the provenance of
that default, so a graph may omit them without anyone inventing a number.

**A connection needs physics, not a matching symbol.** Every input declares
whether an upstream model may supply it and, if so, under what assumption.
Dissolved oxygen is a percentage of the probe's saturation reading and is
refused as a mass fraction; a volumetric feed rate is refused as a mass flow;
a concentration is refused as a total mass. Each refusal carries the reason.

Scientific validation status is declared here and travels with every result:
``implemented``, reproduction ``not_yet_validated``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from schemas.units import QuantityKind

#: The composition contracts version this interface was written against.
#: Read from the repository's composition package when it is importable; a
#: standalone copy of this model must not silently claim compatibility with a
#: contract it has never seen.
CONTRACT_VERSION_COMPATIBLE = "0.1.0"

#: The model's own identifier inside this package.
MODEL_ID = "ganjave2022.cybernetic-growth"
MODEL_VERSION = "0.1.0"

# --------------------------------------------------------------------------- #
# scientific validation status
# --------------------------------------------------------------------------- #

#: The software works: every equation is transcribed, dimensioned, tested and
#: executable, and the model composes. That is a separate claim from whether the
#: paper has been reproduced, and the two must not be merged.
IMPLEMENTATION_STATUS = "implemented"

#: Quantitative reproduction of Ganjave et al. (2022) has **not** been
#: demonstrated. The time courses are figures rather than numerical data, three
#: initial conditions are not stated by the source, and one transcription item
#: (TN-02) is still open. Nothing computed here may be presented as a validated
#: reproduction of the paper.
REPRODUCTION_STATUS = "not_yet_validated"

VALIDATION_CLAIM = {
    "implementation_status": IMPLEMENTATION_STATUS,
    "reproduction_status": REPRODUCTION_STATUS,
    "what_is_validated": [
        "every implemented equation against an independent hand calculation",
        "the dissolved-oxygen balance against the printed page and unit algebra",
        "the solver against a closed-form volume balance",
        "numerical convergence of the fed-batch volume",
    ],
    "what_is_not_validated": [
        "quantitative agreement with the paper's reported biomass",
        "agreement with the paper's reported dissolved-oxygen trajectory",
        "agreement with any figure in the paper: no figure was digitised",
    ],
    "unresolved_items": [
        {
            "item_id": "TN-02",
            "summary": (
                "Table 2 prints the initial enzyme ratio for combination 2 as "
                "'e20/em1'; the denominator of combination 2 must be e_m2. Read "
                "as e2(0)/e_m2 = 0.874."
            ),
            "status": "unresolved",
            "needs": "confirmation from the paper's authors",
        },
        {
            "item_id": "INITIAL_CONDITIONS",
            "summary": (
                "X0, S2_0 and DO0 are not stated in the paper and are supplied by "
                "the caller. S2_0 in particular decides whether the culture becomes "
                "oxygen-limited."
            ),
            "status": "caller_supplied",
            "needs": "a reported initial condition, or an operator's value",
        },
        {
            "item_id": "PAPER_REPRODUCTION",
            "summary": (
                "The published time courses are figures. No numerical observations "
                "were recoverable, so no trajectory here has been compared against a "
                "measured point."
            ),
            "status": "not_yet_validated",
            "needs": "the underlying time-course data, or the figures digitised",
        },
    ],
    "source": (
        "Ganjave et al. 2022, Biotechnology Reports 33:e00694, "
        "doi:10.1016/j.btre.2021.e00694"
    ),
    "report": "Models/Ganjave/OXYGEN_BALANCE_REPORT.md",
}

#: Composition-layer quantity names, restated so this package does not have to
#: import the composition layer to know what it means. These must match
#: `composition.composition.quantities.Quantity` values.
COMPOSITION_QUANTITY = {
    QuantityKind.TIME: "time",
    QuantityKind.VOLUME: "volume",
    QuantityKind.VOLUME_FLOW: "volume_flow",
    QuantityKind.MASS_CONCENTRATION: "mass_concentration",
    QuantityKind.SPECIFIC_GROWTH_RATE: "dimensionless",
    QuantityKind.HALF_SATURATION_CONCENTRATION: "mass_concentration",
    QuantityKind.HALF_SATURATION_DO: "dimensionless",
    QuantityKind.YIELD: "dimensionless",
    QuantityKind.ENZYME_RATIO: "dimensionless",
    QuantityKind.OXYGEN_TRANSFER_COEFFICIENT: "dimensionless",
    QuantityKind.OXYGEN_SATURATION_CONCENTRATION: "mass_concentration",
    QuantityKind.DISSOLVED_OXYGEN_PERCENT: "dimensionless",
    QuantityKind.FEED_PERCENT_WV: "dimensionless",
    QuantityKind.OPTICAL_DENSITY: "dimensionless",
    QuantityKind.FOLD: "dimensionless",
}

#: Quantity pairs this model refuses to be connected across, with the reason.
#: Each entry has been a plausible-looking conversion at some point.
REFUSED_MAPPINGS: tuple[tuple[str, str, str], ...] = (
    (
        "dissolved_oxygen",
        "mass_fraction",
        "A dissolved-oxygen reading is a percentage of the probe's saturation, "
        "not a mass fraction. C* = 0.0075 g/L, so 100 % is 0.0075 g/L: the two "
        "differ by orders of magnitude and connecting them would silently "
        "rescale every oxygen quantity by a factor of ~13333.",
    ),
    (
        "dissolved_oxygen",
        "mass_concentration",
        "The DO reading is a percentage; a concentration needs C* and an "
        "explicit conversion (schemas.units.do_percentage_to_concentration).",
    ),
    (
        "complex_substrate_concentration",
        "mass_fraction",
        "S2 is a lumped mixture (amino acids and peptides, represented by "
        "yeast extract) with one fitted yield. It is not a nitrogen or protein "
        "mass fraction and has no component identity.",
    ),
    (
        "glycerol_concentration",
        "mass_flow",
        "A concentration in g/L is not a flow in g/h. Converting needs the "
        "culture volume, which is an output of this model and not something the "
        "engine may assume.",
    ),
    (
        "biomass_concentration",
        "mass",
        "X is g/L. A total mass needs the volume; the two are not "
        "interchangeable.",
    ),
    (
        "complex_substrate_concentration",
        "component_mass",
        "S2 has no component identity, so it cannot enter a component-declared "
        "control volume (the composition layer's attribution rule).",
    ),
    (
        "culture_volume",
        "mass",
        "V is a volume in litres. Connecting it to a mass because both are "
        "positive would be meaningless.",
    ),
)


class PortDirection(Enum):
    INPUT = "input"
    OUTPUT = "output"


class TemporalBasis(Enum):
    INSTANT = "instant"
    """A value held at one instant, such as an initial condition."""
    RATE = "rate"
    """A flow; the per-hour basis is in the unit."""
    TRAJECTORY = "trajectory_point"
    """A value read off a time series."""
    INVENTORY = "inventory"
    """A total held at an instant, such as a culture volume."""
    DURATION = "duration"
    """An elapsed or elapsed-to time."""


@dataclass(frozen=True)
class Port:
    """One typed value this model consumes or produces."""

    port_id: str
    direction: PortDirection
    kind: QuantityKind
    unit: str
    label: str
    quantity: str
    """The composition-layer quantity name."""
    temporal_basis: TemporalBasis
    state_key: str | None = None
    """Which state variable this port carries, when it carries one."""
    required: bool = False
    attribution_required: bool = False
    description: str = ""
    #: The value the model itself supplies when nothing is connected. Declared
    #: only where the paper states it, and always with its provenance: an
    #: unreported quantity gets no default at all.
    default_value: float | None = None
    default_provenance: str = ""
    default_source: str = ""
    #: Conditions under which this input becomes required, e.g. a fed-batch
    #: feed. The contract has no conditional-required flag, so the adapter
    #: enforces these with a structured diagnostic.
    required_when: tuple[str, ...] = ()
    #: Whether an upstream model may supply this port, and under what
    #: assumption. Absent from `upstream` means no.
    upstream: "UpstreamRule | None" = None
    #: A conversion the model performs on the way in, stated in words. Only
    #: within-quantity, linear conversions are ever permitted.
    inbound_conversion: str = ""
    #: The model's own symbol, for the inspector.
    model_symbol: str = ""
    #: The state vector's position, so a reader can find it in the source.
    source_equation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "port_id": self.port_id,
            "direction": self.direction.value,
            "quantity": self.quantity,
            "kind": self.kind.value,
            "unit": self.unit,
            "label": self.label,
            "temporal_basis": self.temporal_basis.value,
            "required": self.required,
            "required_when": list(self.required_when),
            "attribution_required": self.attribution_required,
            "has_component_identity": False,
            "default_value": self.default_value,
            "default_provenance": self.default_provenance,
            "default_source": self.default_source,
            "inbound_conversion": self.inbound_conversion,
            "model_symbol": self.model_symbol,
            "source_equation": self.source_equation,
            "upstream": self.upstream.to_dict() if self.upstream else None,
            "description": self.description,
        }


@dataclass(frozen=True)
class UpstreamRule:
    """Whether an upstream model may drive this port, and on what assumption.

    ``supplyable`` is the compatibility answer. ``assumption`` is what a human
    has to accept for the connection to mean anything: a quantity match is
    necessary but not sufficient, because two models can both publish a mass
    concentration while meaning different substances.
    """

    supplyable: bool
    reason: str
    assumption: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "supplyable": self.supplyable,
            "reason": self.reason,
            "assumption": self.assumption,
        }


# --------------------------------------------------------------------------- #
# inputs
# --------------------------------------------------------------------------- #

_REPORTED_GLYCEROL = (
    "Ganjave et al. 2022, 2.2 Batch fermentation, printed p. 2: "
    "'The initial production medium was supplemented with 2.76 g/L glycerol'"
)
_REPORTED_VOLUME = (
    "Ganjave et al. 2022, 2.3 Fed-batch fermentation in shake flask, printed "
    "p. 2: 'These flasks were filled with 100 mL medium'"
)

INPUT_PORTS: tuple[Port, ...] = (
    Port(
        port_id="initial_biomass_concentration",
        direction=PortDirection.INPUT,
        kind=QuantityKind.MASS_CONCENTRATION,
        unit="g/L",
        label="initial biomass concentration (X0)",
        quantity="mass_concentration",
        temporal_basis=TemporalBasis.INSTANT,
        required=True,
        model_symbol="X",
        source_equation="state initial condition; used by eq. (8)-(15)",
        description=(
            "Required, with no default. The paper reports an initial OD600 of "
            "0.05 but no OD600-to-dry-cell-weight calibration, so X0 is not "
            "derivable from it and is not guessed."
        ),
        upstream=UpstreamRule(
            supplyable=False,
            reason=(
                "No other model in this repository publishes a biomass "
                "concentration. Morris publishes masses and mass fractions for "
                "non-reacting control volumes; Zielinski publishes a process "
                "graph whose media quantities are not a culture biomass."
            ),
        ),
    ),
    Port(
        port_id="initial_glycerol_concentration",
        direction=PortDirection.INPUT,
        kind=QuantityKind.MASS_CONCENTRATION,
        unit="g/L",
        label="initial glycerol concentration (S1_0)",
        quantity="mass_concentration",
        temporal_basis=TemporalBasis.INSTANT,
        model_symbol="S1",
        default_value=2.76,
        default_provenance="reported",
        default_source=_REPORTED_GLYCEROL,
        source_equation="state initial condition; used by eq. (9), (13)",
        description=(
            "Optional. The paper states 2.76 g/L for the production medium, so "
            "the default is reported rather than invented."
        ),
        upstream=UpstreamRule(
            supplyable=True,
            reason=(
                "A glycerol concentration is a mass concentration, which the "
                "contract can carry."
            ),
            assumption=(
                "The upstream value must be glycerol in the same medium. A "
                "mass concentration of some other substance is not a legal "
                "substitute even though the quantities match."
            ),
        ),
    ),
    Port(
        port_id="initial_complex_substrate_concentration",
        direction=PortDirection.INPUT,
        kind=QuantityKind.MASS_CONCENTRATION,
        unit="g/L",
        label="initial complex nitrogen-rich substrate concentration (S2_0)",
        quantity="mass_concentration",
        temporal_basis=TemporalBasis.INSTANT,
        required=True,
        attribution_required=True,
        model_symbol="S2",
        source_equation="state initial condition; used by eq. (10), (14)",
        description=(
            "Required, with no default. S2 is a lumped mixture of amino acids "
            "and peptides represented experimentally by yeast extract. The SOB "
            "recipe's 5 g/L is a reported medium composition, not a stated "
            "model initial condition, so it is not used as a default. This "
            "value materially changes the trajectory: it decides whether the "
            "culture becomes oxygen-limited or substrate-limited."
        ),
        upstream=UpstreamRule(
            supplyable=True,
            reason=(
                "A complex-substrate concentration is a mass concentration, "
                "which the contract can carry."
            ),
            assumption=(
                "The upstream value must be a nitrogen-rich complex substrate "
                "on this model's own lumped basis, with a comparable yield "
                "coefficient. A defined medium component is not interchangeable "
                "with a lumped mixture that the paper fitted as one number."
            ),
        ),
    ),
    Port(
        port_id="initial_dissolved_oxygen",
        direction=PortDirection.INPUT,
        kind=QuantityKind.DISSOLVED_OXYGEN_PERCENT,
        unit="%",
        label="initial dissolved oxygen (DO0)",
        quantity="dimensionless",
        temporal_basis=TemporalBasis.INSTANT,
        required=True,
        model_symbol="DO",
        source_equation="state initial condition; used by eq. (3), (4), (11), (15)",
        description=(
            "Required, with no default. The paper does not state an initial "
            "dissolved oxygen in the main text. The unit is a percentage of the "
            "probe's saturation reading, NOT a mass fraction and NOT a "
            "concentration."
        ),
        upstream=UpstreamRule(
            supplyable=False,
            reason=(
                "A percentage that means 'of the saturation reading of a "
                "particular probe in a particular medium' is not the same "
                "physical quantity as a generic percent, a mass fraction or a "
                "dissolved-oxygen concentration. Connecting any of those would "
                "rescale the value by up to ~13333 (100 % is C* = 0.0075 g/L)."
            ),
        ),
    ),
    Port(
        port_id="initial_culture_volume",
        direction=PortDirection.INPUT,
        kind=QuantityKind.VOLUME,
        unit="L",
        label="initial culture volume (V0)",
        quantity="volume",
        temporal_basis=TemporalBasis.INSTANT,
        model_symbol="V",
        default_value=0.1,
        default_provenance="reported",
        default_source=_REPORTED_VOLUME,
        source_equation="state initial condition; the F/V dilution factor in eq. (12)-(16)",
        description=(
            "Optional. The paper states 100 mL in the 500 mL baffled flask, "
            "which is 0.1 L."
        ),
        upstream=UpstreamRule(
            supplyable=True,
            reason="A vessel volume is a volume, which the contract can carry.",
            assumption=(
                "The upstream value must be a liquid working volume in the same "
                "vessel. A pipe or vessel void volume is not a culture volume."
            ),
        ),
    ),
)

#: Fed-batch inputs. Not unconditionally required, because a batch graph must
#: not be blocked by ports the batch balances never read; the adapter enforces
#: them whenever the mode is `fed_batch`.
FED_BATCH_INPUT_PORTS: tuple[Port, ...] = (
    Port(
        port_id="feed_glycerol_concentration",
        direction=PortDirection.INPUT,
        kind=QuantityKind.MASS_CONCENTRATION,
        unit="g/L",
        label="feed glycerol concentration (S10)",
        quantity="mass_concentration",
        temporal_basis=TemporalBasis.INSTANT,
        required_when=("fed_batch",),
        model_symbol="S10",
        source_equation="eq. (13)",
        description=(
            "Required in fed-batch mode. The paper prints feed recipes in "
            "percent weight/volume (1 % w/v = 10 g/L); this port is the "
            "concentration eq. (13) requires, in g/L."
        ),
        upstream=UpstreamRule(
            supplyable=True,
            reason="A feed concentration is a mass concentration.",
            assumption=(
                "The upstream stream must be the glycerol feed itself. A "
                "culture glycerol concentration is a different quantity in "
                "meaning even though the units agree."
            ),
        ),
    ),
    Port(
        port_id="feed_complex_substrate_concentration",
        direction=PortDirection.INPUT,
        kind=QuantityKind.MASS_CONCENTRATION,
        unit="g/L",
        label="feed complex substrate concentration (S20)",
        quantity="mass_concentration",
        temporal_basis=TemporalBasis.INSTANT,
        required_when=("fed_batch",),
        attribution_required=True,
        model_symbol="S20",
        source_equation="eq. (14)",
        description=(
            "Required in fed-batch mode, in g/L. As with S2, this is the "
            "lumped nitrogen-rich substrate, not a defined medium component."
        ),
        upstream=UpstreamRule(
            supplyable=True,
            reason="A feed concentration is a mass concentration.",
            assumption=(
                "The upstream stream must be the nitrogen-rich feed on this "
                "model's lumped basis."
            ),
        ),
    ),
    Port(
        port_id="feed_flow_rate",
        direction=PortDirection.INPUT,
        kind=QuantityKind.VOLUME_FLOW,
        unit="mL/h",
        label="volumetric feed flow rate (F)",
        quantity="volume_flow",
        temporal_basis=TemporalBasis.RATE,
        required_when=("fed_batch",),
        model_symbol="F",
        inbound_conversion=(
            "mL/h -> L/h, factor 1e-3, within volume_flow. The model integrates "
            "in L and L/h so that F/V is a rate; the contract registers mL/h, "
            "which is the unit the paper's Table 1 prints."
        ),
        source_equation="eq. (12)-(16)",
        description=(
            "Required in fed-batch mode. Volumetric, not a mass flow: turning "
            "it into g/h would need the feed density, which the paper does not "
            "state."
        ),
        upstream=UpstreamRule(
            supplyable=True,
            reason=(
                "A volumetric flow is a volume_flow, which the contract can "
                "carry, and the within-quantity conversion to L/h is linear."
            ),
            assumption=(
                "The upstream flow must be a liquid volumetric rate into this "
                "culture. A gas flow, or a feed in different units of time, is "
                "not equivalent even where the quantity matches."
            ),
        ),
    ),
    Port(
        port_id="feed_start_time",
        direction=PortDirection.INPUT,
        kind=QuantityKind.TIME,
        unit="h",
        label="feed start time",
        quantity="time",
        temporal_basis=TemporalBasis.DURATION,
        default_value=0.0,
        default_provenance="reported",
        default_source=(
            "Ganjave et al. 2022, 3.1, printed p. 3: feeding begins at 6 h, at "
            "the dissolved-oxygen landmark"
        ),
        source_equation="the pump schedule of eq. (13)-(16)",
        description=(
            "Optional. Defaults to 0 h, meaning the pump runs from the start. "
            "The paper's own process starts at 6 h."
        ),
        upstream=UpstreamRule(
            supplyable=True,
            reason="A process time is a time, which the contract can carry.",
            assumption=(
                "The upstream time must be measured on the same clock as this "
                "run's integration interval."
            ),
        ),
    ),
)

# --------------------------------------------------------------------------- #
# outputs
# --------------------------------------------------------------------------- #

OUTPUT_PORTS: tuple[Port, ...] = (
    Port(
        port_id="biomass_concentration",
        direction=PortDirection.OUTPUT,
        kind=QuantityKind.MASS_CONCENTRATION,
        unit="g/L",
        label="biomass concentration",
        quantity="mass_concentration",
        temporal_basis=TemporalBasis.TRAJECTORY,
        state_key="X",
        model_symbol="X",
        source_equation="eq. (8) batch, eq. (12) fed-batch",
        description=(
            "X, dry cell weight per litre, computed. Not a total mass: a mass "
            "needs the culture volume, which is published separately. Not a "
            "measurement: this is a simulation output."
        ),
    ),
    Port(
        port_id="glycerol_concentration",
        direction=PortDirection.OUTPUT,
        kind=QuantityKind.MASS_CONCENTRATION,
        unit="g/L",
        label="glycerol concentration",
        quantity="mass_concentration",
        temporal_basis=TemporalBasis.TRAJECTORY,
        state_key="S1",
        model_symbol="S1",
        source_equation="eq. (9) batch, eq. (13) fed-batch",
        description="S1, residual glycerol, computed. A concentration, not a flow.",
    ),
    Port(
        port_id="complex_substrate_concentration",
        direction=PortDirection.OUTPUT,
        kind=QuantityKind.MASS_CONCENTRATION,
        unit="g/L",
        label="complex nitrogen-rich substrate concentration",
        quantity="mass_concentration",
        temporal_basis=TemporalBasis.TRAJECTORY,
        state_key="S2",
        attribution_required=True,
        model_symbol="S2",
        source_equation="eq. (10) batch, eq. (14) fed-batch",
        description=(
            "S2, a lumped mixture of amino acids and peptides (yeast extract). "
            "No component identity; cannot enter a component-declared control "
            "volume, and cannot be connected as a mass fraction."
        ),
    ),
    Port(
        port_id="dissolved_oxygen",
        direction=PortDirection.OUTPUT,
        kind=QuantityKind.DISSOLVED_OXYGEN_PERCENT,
        unit="%",
        label="dissolved oxygen",
        quantity="dimensionless",
        temporal_basis=TemporalBasis.TRAJECTORY,
        state_key="DO",
        model_symbol="DO",
        source_equation="eq. (11) batch, eq. (15) fed-batch",
        description=(
            "Percentage of the probe's saturation reading. NOT a mass fraction: "
            "100 % corresponds to C* = 0.0075 g/L. NOT a concentration: that "
            "needs C* and an explicit conversion."
        ),
    ),
    Port(
        port_id="culture_volume",
        direction=PortDirection.OUTPUT,
        kind=QuantityKind.VOLUME,
        unit="L",
        label="culture volume",
        quantity="volume",
        temporal_basis=TemporalBasis.INVENTORY,
        state_key="V",
        model_symbol="V",
        source_equation="eq. (16); constant in batch mode",
        description=(
            "V. Constant in batch mode; dV/dt = F in fed-batch. Published so a "
            "consumer can turn a concentration into a total, if it chooses to "
            "and states it."
        ),
    ),
    Port(
        port_id="simulation_time",
        direction=PortDirection.OUTPUT,
        kind=QuantityKind.TIME,
        unit="h",
        label="final simulation time",
        quantity="time",
        temporal_basis=TemporalBasis.DURATION,
        description=(
            "The end of the integration interval, in hours. Published so a "
            "consumer knows the horizon the trajectory covers; the trajectory "
            "itself carries the full time axis."
        ),
    ),
)

ALL_PORTS: tuple[Port, ...] = (
    INPUT_PORTS + FED_BATCH_INPUT_PORTS + OUTPUT_PORTS
)

#: The two ODE states that are deliberately **not** published. Both are computed,
#: and both are withheld on purpose.
WITHHELD_STATES: tuple[Mapping[str, str], ...] = (
    {
        "state_key": "e1",
        "model_symbol": "e1/e_m1",
        "reason": (
            "A normalised key-enzyme fraction. The contract has no quantity that "
            "means this, and publishing it as a dimensionless '1' would make it "
            "connectable to every other dimensionless value in the repository, "
            "which is precisely the kind of connection that looks legal and means "
            "nothing. It is an internal state of eq. (7), not a process "
            "quantity."
        ),
    },
    {
        "state_key": "e2",
        "model_symbol": "e2/e_m2",
        "reason": (
            "As e1. Also the state carrying the unresolved TN-02 reading, so "
            "publishing it would present an open question as a settled value."
        ),
    },
)


def port_by_id(port_id: str) -> Port:
    for port in ALL_PORTS:
        if port.port_id == port_id:
            return port
    raise KeyError(
        f"unknown port {port_id!r}; this model declares "
        f"{[p.port_id for p in ALL_PORTS]}"
    )


def required_input_ports(mode: str = "batch") -> tuple[Port, ...]:
    """The inputs a run in `mode` cannot proceed without."""
    out: list[Port] = []
    for port in INPUT_PORTS:
        if port.required:
            out.append(port)
    if mode == "fed_batch":
        out.extend(
            port for port in FED_BATCH_INPUT_PORTS
            if "fed_batch" in port.required_when
        )
    return tuple(out)


def composition_contract() -> dict[str, Any]:
    """The whole contract as plain data: frozen, diffable, auditable."""
    return {
        "contract_id": "ganjave2022.composition",
        "version": "1.0.0",
        "composition_contract_version": CONTRACT_VERSION_COMPATIBLE,
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "registered_in_composition_layer": True,
        "registered_model_id": "ganjave",
        "registration_note": (
            "Reachable from the composition layer through "
            "composition.adapters.ganjave.GanjaveAdapter and "
            "composition._workers.ganjave_worker. This package still does not "
            "import the composition layer, so the dependency arrow points one "
            "way: model -> JSON boundary -> composition."
        ),
        "source": {
            "source_id": "ganjave2022",
            "citation": (
                "S. D. Ganjave, V. A. J. E. S. Waghmare, P. P. Wangikar, 'High "
                "cell density cultivation of E. coli in shake flasks for the "
                "production of recombinant proteins', Biotechnology Reports 33 "
                "(2022) e00694."
            ),
            "doi": "10.1016/j.btre.2021.e00694",
        },
        "modes": {
            "batch": {
                "equations": "(8)-(11)",
                "feed_ports_used": [],
                "volume_changes": False,
            },
            "fed_batch": {
                "equations": "(12)-(16)",
                "feed_ports_used": [
                    p.port_id for p in FED_BATCH_INPUT_PORTS
                ],
                "volume_changes": True,
            },
        },
        "parameter_set": {
            "id": "ganjave2022.table2",
            "version": "1.0.0",
            "equations_version": "1.1.0",
            "provenance": (
                "fitted by the authors against six fed-batch experiments; kLa "
                "and C* are reported measurements"
            ),
            "overridable": False,
            "override_note": (
                "The model accepts an explicit override with a stated reason, and "
                "records it as assumed. It does not refit."
            ),
        },
        "solver": {
            "name": "runge-kutta-4(3) step-doubling",
            "version": "1.0.0",
            "rtol": 1.0e-6,
            "atol": 1.0e-9,
            "h_max_h": 1.0e-2,
            "h_max_reason": (
                "chosen from the reported kLa = 133 h^-1: the dissolved-oxygen "
                "state relaxes in 7.5 ms while biomass runs at mu ~ 0.6-1.5 h^-1, "
                "so h_max*kLa = 1.33 stays inside the explicit RK4 stability limit"
            ),
        },
        "validation_claim": dict(VALIDATION_CLAIM),
        "ports": [p.to_dict() for p in ALL_PORTS],
        "withheld_states": [dict(w) for w in WITHHELD_STATES],
        "quantity_map": {k.value: v for k, v in COMPOSITION_QUANTITY.items()},
        "refused_mappings": [
            {"subject": s, "refused_as": r, "reason": why}
            for s, r, why in REFUSED_MAPPINGS
        ],
        "capabilities": [
            "batch simulation over eq. (8)-(11)",
            "fed-batch simulation over eq. (12)-(16)",
            "full state trajectories with solver report and run provenance",
            "structured diagnostics on every failure, with no result returned",
        ],
        "non_capabilities": [
            "no parameter estimation (the paper's genetic-algorithm fit is not "
            "reimplemented; Table 2 is loaded as a fitted set)",
            "no multi-objective optimisation or Pareto front (eq. (19)-(24) are "
            "out of scope, and the constraints of Table S3 are not in the main "
            "paper)",
            "no protein expression, inclusion-body or purification model",
            "no automatic scale-up from shake flask to 3 L bioreactor",
            "no kLa prediction for other geometries",
            "no figure digitisation, and therefore no claim of reproducing the "
            "paper's time courses",
        ],
    }


def manifest() -> dict[str, Any]:
    """The model's declared interface, as plain data.

    Kept as a function rather than a stored file so that it cannot drift from
    the code that implements it; the composition worker reads this directly.
    """
    document = composition_contract()
    document["adapter"] = "composition.adapters.ganjave.GanjaveAdapter"
    return document


class CompositionMismatch(ValueError):
    """A connection this model refuses."""


def check_connection(port_id: str, proposed_quantity: str) -> str:
    """Return the compatible composition quantity, or refuse.

    Used by a caller (or the adapter) to ask whether a value of
    ``proposed_quantity`` may enter ``port_id``. Refusals name the reason, so a
    rejected connection explains itself rather than just failing.
    """
    port = port_by_id(port_id)
    if proposed_quantity == port.quantity:
        return port.quantity
    for subject, refused, reason in REFUSED_MAPPINGS:
        if subject == port_id and refused == proposed_quantity:
            raise CompositionMismatch(
                f"{port_id} cannot be connected to a {proposed_quantity!r}: {reason}"
            )
    raise CompositionMismatch(
        f"{port_id} carries {port.quantity!r} (a {port.kind.value} in "
        f"{port.unit}); {proposed_quantity!r} is a different physical quantity"
    )


def assert_contract_compatibility(contract_version: str) -> None:
    """Refuse to claim compatibility with an unseen contract version."""
    if contract_version != CONTRACT_VERSION_COMPATIBLE:
        raise CompositionMismatch(
            f"this model declares composition contract "
            f"{CONTRACT_VERSION_COMPATIBLE} but was offered {contract_version!r}. "
            f"Re-check models/composition.py against the composition contracts "
            f"before connecting them."
        )


def quantity_summary() -> Mapping[str, str]:
    """Which composition quantity each of this model's quantities maps to."""
    return dict(COMPOSITION_QUANTITY)