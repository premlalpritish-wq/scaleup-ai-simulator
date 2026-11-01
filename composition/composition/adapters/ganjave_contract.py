"""What Ganjave will and will not accept on its input ports.

This is *composition-side policy*, kept apart from both the adapter's mechanics
(``ganjave.py``) and the model's own declaration (``Models/Ganjave/models/
composition.py``).  The engine enforces quantity and unit compatibility
mechanically, but it cannot know that two matching ``mass_concentration`` ports
mean different substances.  That is what this module states.

The three rules, in order of how often they are got wrong:

**1. A quantity match is necessary, not sufficient.**  ``initial_glycerol_
concentration`` is a ``mass_concentration`` and any upstream ``mass_concentration``
is *connectable*; it is only meaningful if the upstream value is glycerol in
this medium.  :data:`INPUT_CONTRACT` records that as an assumption on the port,
and a connection to it is reported with the assumption attached.

**2. Some Ganjave inputs accept no upstream model at all.**  ``X0`` and
``DO0`` are refused outright, for reasons that have nothing to do with units --
see :data:`INPUT_CONTRACT`.

**3. Nothing converts across a quantity boundary.**  There is no
concentration-to-amount conversion (it needs a volume), no volumetric-to-mass
flow conversion (it needs a density), and no dissolved-oxygen-to-concentration
conversion that does not pass through the reported saturation concentration
``C*``.  Each is listed in :data:`REFUSED` with the reason and, where one
exists, what would be needed to make it legal.

What this module deliberately does **not** do: claim that Ganjave can connect to
Morris because both are "material balances", or to Zielinski because both are
"biology".  Morris computes non-reacting control-volume totals in kg; Ganjave
integrates a dynamic culture in g/L.  Zielinski's interface is a process graph of
its own quantities, not a dynamic protein-expression model, and this contract
does not pretend otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ..quantities import Quantity


@dataclass(frozen=True)
class InputRule:
    """The composition-side view of one Ganjave input port."""

    port_id: str
    quantity: Quantity
    unit: str
    required: bool
    #: Whether an upstream model may drive this port at all.
    upstream_supplyable: bool
    #: Why the port is or is not supplyable, in the author's words.
    reason: str
    #: The physical premise a supplyable connection rests on. An operator has to
    #: accept this; a matching quantity does not discharge it.
    assumption: str = ""
    #: A conversion the model performs on the way in. Only within-quantity and
    #: linear conversions are ever listed.
    inbound_conversion: str = ""
    required_when: tuple[str, ...] = ()
    #: Modes in which this port is read at all.
    modes: tuple[str, ...] = ("batch", "fed_batch")

    def to_dict(self) -> dict[str, object]:
        return {
            "port_id": self.port_id,
            "quantity": self.quantity.value,
            "unit": self.unit,
            "required": self.required,
            "required_when": list(self.required_when),
            "upstream_supplyable": self.upstream_supplyable,
            "reason": self.reason,
            "assumption": self.assumption,
            "inbound_conversion": self.inbound_conversion,
            "modes": list(self.modes),
        }


INPUT_CONTRACT: tuple[InputRule, ...] = (
    InputRule(
        port_id="initial_biomass_concentration",
        quantity=Quantity.MASS_CONCENTRATION,
        unit="g/L",
        required=True,
        upstream_supplyable=False,
        reason=(
            "No model in this repository publishes a culture biomass "
            "concentration. Morris publishes masses and mass fractions for "
            "non-reacting control volumes; a Morris total in kg is not a g/L "
            "concentration and is not made into one here. Declaring the input "
            "is the honest route: an operator or an upstream model must know "
            "what the number means."
        ),
    ),
    InputRule(
        port_id="initial_glycerol_concentration",
        quantity=Quantity.MASS_CONCENTRATION,
        unit="g/L",
        required=False,
        upstream_supplyable=True,
        reason="A glycerol concentration is a mass concentration.",
        assumption=(
            "The upstream value must be glycerol, in this medium. A mass "
            "concentration of another substance is not a substitute, even "
            "though the quantities match exactly."
        ),
    ),
    InputRule(
        port_id="initial_complex_substrate_concentration",
        quantity=Quantity.MASS_CONCENTRATION,
        unit="g/L",
        required=True,
        upstream_supplyable=True,
        reason="A complex-substrate concentration is a mass concentration.",
        assumption=(
            "The upstream value must be a nitrogen-rich complex substrate on "
            "this model's lumped basis, with a comparable fitted yield. A "
            "defined medium component (say a single amino acid) is not "
            "interchangeable with a lumped mixture the paper fitted as one "
            "number, and the model has no component identity to check it "
            "against."
        ),
    ),
    InputRule(
        port_id="initial_dissolved_oxygen",
        quantity=Quantity.DIMENSIONLESS,
        unit="%",
        required=True,
        upstream_supplyable=False,
        reason=(
            "This percent means 'of the saturation reading of this probe in "
            "this medium'. The contract's other percent is a mass fraction, and "
            "a dissolved-oxygen concentration is a third thing again: 100 % is "
            "C* = 0.0075 g/L. Connecting either would rescale the value by up "
            "to ~13333, so the port refuses every upstream quantity rather than "
            "trusting the reader to notice."
        ),
    ),
    InputRule(
        port_id="initial_culture_volume",
        quantity=Quantity.VOLUME,
        unit="L",
        required=False,
        upstream_supplyable=True,
        reason="A liquid working volume is a volume.",
        assumption=(
            "The upstream value must be a liquid working volume in this "
            "vessel, not a pipe or vessel void volume."
        ),
    ),
    InputRule(
        port_id="feed_glycerol_concentration",
        quantity=Quantity.MASS_CONCENTRATION,
        unit="g/L",
        required=False,
        required_when=("fed_batch",),
        modes=("fed_batch",),
        upstream_supplyable=True,
        reason="A feed concentration is a mass concentration.",
        assumption=(
            "The upstream stream must be the glycerol feed. A culture glycerol "
            "concentration shares the unit and the quantity but is a different "
            "physical stream."
        ),
    ),
    InputRule(
        port_id="feed_complex_substrate_concentration",
        quantity=Quantity.MASS_CONCENTRATION,
        unit="g/L",
        required=False,
        required_when=("fed_batch",),
        modes=("fed_batch",),
        upstream_supplyable=True,
        reason="A feed concentration is a mass concentration.",
        assumption=(
            "The upstream stream must be the nitrogen-rich feed on this "
            "model's lumped basis."
        ),
    ),
    InputRule(
        port_id="feed_flow_rate",
        quantity=Quantity.VOLUME_FLOW,
        unit="mL/h",
        required=False,
        required_when=("fed_batch",),
        modes=("fed_batch",),
        upstream_supplyable=True,
        reason=(
            "A volumetric flow is a volume_flow, and the within-quantity "
            "conversion to the model's L/h basis is linear."
        ),
        assumption=(
            "The upstream flow must be a liquid volumetric rate into this "
            "culture. A gas flow, or a per-minute rate, is a unit question "
            "rather than a meaning question and is converted; a *mass* flow is "
            "a different quantity and is refused."
        ),
        inbound_conversion="mL/h -> L/h, factor 1e-3, within volume_flow",
    ),
    InputRule(
        port_id="feed_start_time",
        quantity=Quantity.TIME,
        unit="h",
        required=False,
        required_when=("fed_batch",),
        modes=("fed_batch",),
        upstream_supplyable=True,
        reason="A process time is a time.",
        assumption="The same clock as this run's integration interval.",
    ),
)


#: Connections this contract refuses outright, each with the reason and what
#: would be needed to make one legitimate.
REFUSED: tuple[tuple[str, str, str, str], ...] = (
    (
        "initial_biomass_concentration",
        "mass",
        "X is a concentration in g/L. A total mass in kg needs the culture "
        "volume, which is an output of this model and not an assumption here.",
        "Multiply the concentration by the culture_volume output, stating the "
        "volume used. The composition layer does not do that silently.",
    ),
    (
        "initial_biomass_concentration",
        "mass_fraction",
        "A dry-cell-weight concentration is not a fraction of anything. A mass "
        "fraction carries no volume and so no concentration.",
        "Supply the culture volume alongside a total mass.",
    ),
    (
        "initial_glycerol_concentration",
        "mass_flow",
        "A concentration in g/L is not a flow in g/h; a flow needs a volume per "
        "time.",
        "Connect a genuine volumetric or mass flow, or supply a concentration.",
    ),
    (
        "initial_complex_substrate_concentration",
        "mass_flow",
        "A concentration in g/L is not a flow in g/h.",
        "Connect a genuine flow, or supply a concentration.",
    ),
    (
        "initial_dissolved_oxygen",
        "mass_fraction",
        "A dissolved-oxygen reading is a percentage of the probe's saturation, "
        "not a mass fraction. 100 % is C* = 0.0075 g/L, so the two differ by "
        "more than four orders of magnitude.",
        "Nothing: the concepts are unrelated. A conversion would need a "
        "saturation concentration and a decision about which basis is meant.",
    ),
    (
        "initial_dissolved_oxygen",
        "mass_concentration",
        "A concentration needs C* and an explicit, tested conversion, which is "
        "a modelling decision rather than a unit change.",
        "Declare C* (the model carries 0.0075 g/L) and convert explicitly "
        "through schemas.units.do_percentage_to_concentration.",
    ),
    (
        "initial_culture_volume",
        "mass",
        "A volume in litres is not a mass. Both being positive and both being "
        "declared on a vessel makes them easy to confuse and never "
        "interchangeable.",
        "Connect a volume, or convert using a stated density.",
    ),
    (
        "feed_flow_rate",
        "mass_flow",
        "The feed rate is volumetric. Turning mL/h into g/h needs the feed "
        "density, which the paper does not state.",
        "Supply a density for the feed. Until then the value is absent, not "
        "zero.",
    ),
    (
        "biomass_concentration",
        "mass",
        "X is a concentration in g/L. A total mass in kg needs the culture "
        "volume, which is published separately and is not assumed here.",
        "Use the culture_volume output and multiply, stating the volume you "
        "used. The composition layer does not do this silently.",
    ),
    (
        "glycerol_concentration",
        "mass_flow",
        "A concentration in g/L is not a flow in g/h; a flow needs a volume per "
        "time.",
        "Use the culture volume and the trajectory to integrate, or connect a "
        "genuine flow.",
    ),
    (
        "complex_substrate_concentration",
        "mass_fraction",
        "S2 is a lumped mixture of amino acids and peptides with a single fitted "
        "yield. It is not a nitrogen or protein mass fraction and has no "
        "component identity.",
        "A component-resolved substrate model would be a different model.",
    ),
    (
        "complex_substrate_concentration",
        "component_mass",
        "The value has no component identity, so it cannot enter a "
        "component-declared control volume.",
        "Supply component-resolved concentrations and a yield per component.",
    ),
)


class ConnectionRefused(ValueError):
    """A connection Ganjave's contract does not permit."""

    def __init__(self, port_id: str, proposed: str, reason: str, what_would_help: str = ""):
        message = (
            f"Ganjave refuses {port_id} <- a {proposed} value: {reason}"
        )
        if what_would_help:
            message += f" What would help: {what_would_help}"
        super().__init__(message)
        self.port_id = port_id
        self.proposed = proposed
        self.what_would_help = what_would_help


def rule_for(port_id: str) -> InputRule:
    for rule in INPUT_CONTRACT:
        if rule.port_id == port_id:
            return rule
    raise KeyError(
        f"{port_id!r} is not a Ganjave input port. Known: "
        f"{[r.port_id for r in INPUT_CONTRACT]}"
    )


def check_input_connection(
    port_id: str, proposed_quantity: str, via: str = "connection"
) -> InputRule:
    """Whether ``proposed_quantity`` may drive ``port_id``, or refuse.

    This is the *semantic* half of a connection check.  The engine has already
    established that the quantities are equal and the units convertible; this
    establishes whether the connection means anything, and returns the rule so
    the caller can surface the assumption.

    ``via`` is ``"connection"`` or ``"literal"``.  It changes exactly one thing:
    a port marked ``upstream_supplyable = False`` refuses a value that arrived
    from another model, but accepts one the operator declared on the graph.
    "No upstream model may supply this" is not "no value is obtainable", and
    conflating the two would make three required inputs impossible to fill.
    """
    rule = rule_for(port_id)

    # The specific table first. Every entry in REFUSED *is* a quantity
    # mismatch, so checking the generic mismatch ahead of it would swallow the
    # reason -- and the reason is the useful part: it says which physical
    # premise is missing (a volume, a density, C*).
    for refused_port, refused_quantity, reason, help_text in REFUSED:
        if refused_port == port_id and refused_quantity == proposed_quantity:
            raise ConnectionRefused(port_id, proposed_quantity, reason, help_text)

    if proposed_quantity != rule.quantity.value:
        raise ConnectionRefused(
            port_id,
            proposed_quantity,
            f"the port requires {rule.quantity.value} in {rule.unit}, not "
            f"{proposed_quantity}. These are different physical quantities; a "
            f"conversion between them would change what the number is.",
            "connect a value of the declared quantity, or leave the input "
            "unresolved",
        )
    if via == "connection" and not rule.upstream_supplyable:
        raise ConnectionRefused(port_id, proposed_quantity, rule.reason)
    return rule


def connection_contract() -> Mapping[str, object]:
    """The whole connection contract as plain data."""
    return {
        "model_id": "ganjave",
        "inputs": [rule.to_dict() for rule in INPUT_CONTRACT],
        "refused": [
            {
                "port_id": p,
                "refused_quantity": q,
                "reason": r,
                "what_would_help": h,
            }
            for p, q, r, h in REFUSED
        ],
        "cross_model_notes": [
            {
                "other_model": "morris2011.material_balance",
                "verdict": "no shared quantity",
                "note": (
                    "Morris computes non-reacting control-volume totals, mass "
                    "fractions and amounts in kg. Ganjave integrates a dynamic "
                    "culture in g/L. There is no port pair with equal "
                    "quantities, and inventing one would mean reinterpreting a "
                    "Morris total as a concentration. No connection is enabled "
                    "and none is implied."
                ),
            },
            {
                "other_model": "zielinski2019.rhi_process",
                "verdict": "quantity-compatible in places, meaningful only with the stated assumption",
                "note": (
                    "Zielinski publishes mass concentrations (g/L), volumes, "
                    "volumetric flows and times, so some pairs would pass the "
                    "engine's mechanical check. Whether any of them *means* "
                    "anything depends on the streams involved: its interface is "
                    "a process graph of its own declared quantities, not a "
                    "dynamic protein-expression model, and no composition "
                    "between it and this one has been validated. Such a "
                    "connection is therefore permitted only with its assumption "
                    "recorded, never silently."
                ),
            },
        ],
    }