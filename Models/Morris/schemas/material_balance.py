"""Schemas for the ScaleUp AI material balance engine (v0.1).

Grounded in Morris, Geiger & Fine, *Introduction to Chemical Engineering:
Materials, Energy, and Balance*, 4th ed. (2011), Chapter 4,
"Fundamentals of Material Balances with Applications to Non-Reacting Systems".

Three integrity rules govern this module, and they are enforced structurally in
``__post_init__`` rather than by convention:

  1. **A number is either present or absent.**  A quantity that the source does
     not state is an `Unknown`, which carries a variable identity and a reason.
     It is never coerced to ``0.0`` and never given a fabricated default.  The
     chapter makes the same point in section 4.6.3: an analysis-based balance
     that cannot close is a *finding*, not something to be patched.

  2. **A value is dimensionless unless it says what it is.**  Every `Quantity`
     carries a `QuantityKind` (mass, mass flow, mass fraction, amount, amount
     flow) and a unit that must be registered *for that kind*.  Units are never
     interchanged across kinds, so a mass flow cannot silently be read as an
     amount flow.

  3. **Every value says how it came to exist.**  `Provenance` is `reported`,
     `derived` or `assumed`, and the class dictates what must accompany it: a
     source reference for `reported` and `assumed`, a derivation description
     for `derived`.  There is no fourth option that quietly means "it was
     convenient".

Non-goals, stated here because they bound every other file: this module does not
model reactions, infer stoichiometry, fit empirical correlations, or reconcile
inconsistent measurements by editing source data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

# --------------------------------------------------------------------------- #
# semantic type of a numerical quantity
# --------------------------------------------------------------------------- #


class QuantityKind(Enum):
    """What a number *is*, independent of the unit it is printed in.

    The chapter works almost exclusively in the first three (Morris et al. 2011,
    sec. 4.4 uses "mass" for batch processes and "kg/h" for continuous ones).
    Amount and amount flow are supported because the chapter's ledgers report
    both (sec. 4.5, Example 4.1) and because molar-mass conversion is only
    defensible when a molar mass is supplied.
    """

    MASS = "mass"
    MASS_FLOW = "mass_flow"
    MASS_FRACTION = "mass_fraction"
    AMOUNT = "amount"
    AMOUNT_FLOW = "amount_flow"


class QuantityKindError(ValueError):
    """Raised when a unit is unregistered, or registered under another kind."""


@dataclass(frozen=True)
class Unit:
    """A unit symbol bound to exactly one `QuantityKind`."""

    symbol: str
    kind: QuantityKind
    #: value_in_base = value * to_base
    to_base: float


#: Base unit per kind. Conversions are linear and stay inside a kind.
_BASE_UNITS: Mapping[QuantityKind, str] = {
    QuantityKind.MASS: "kg",
    QuantityKind.MASS_FLOW: "kg/h",
    QuantityKind.MASS_FRACTION: "1",
    QuantityKind.AMOUNT: "mol",
    QuantityKind.AMOUNT_FLOW: "mol/h",
}

_LB_KG = 0.45359237

_UNITS: tuple[Unit, ...] = (
    # mass -- base kg
    Unit("kg", QuantityKind.MASS, 1.0),
    Unit("g", QuantityKind.MASS, 1.0e-3),
    Unit("mg", QuantityKind.MASS, 1.0e-6),
    Unit("t", QuantityKind.MASS, 1.0e3),
    Unit("lb", QuantityKind.MASS, _LB_KG),
    # mass flow -- base kg/h
    Unit("kg/h", QuantityKind.MASS_FLOW, 1.0),
    Unit("kg/min", QuantityKind.MASS_FLOW, 1.0 / 60.0),
    Unit("kg/s", QuantityKind.MASS_FLOW, 1.0 / 3600.0),
    Unit("g/h", QuantityKind.MASS_FLOW, 1.0e-3),
    Unit("g/min", QuantityKind.MASS_FLOW, 1.0e-3 / 60.0),
    Unit("lb/h", QuantityKind.MASS_FLOW, _LB_KG),
    Unit("lb/min", QuantityKind.MASS_FLOW, _LB_KG / 60.0),
    # mass fraction -- base 1
    Unit("1", QuantityKind.MASS_FRACTION, 1.0),
    Unit("%", QuantityKind.MASS_FRACTION, 1.0e-2),
    # amount -- base mol
    Unit("mol", QuantityKind.AMOUNT, 1.0),
    Unit("kmol", QuantityKind.AMOUNT, 1.0e3),
    Unit("gmol", QuantityKind.AMOUNT, 1.0e-3),
    Unit("lbmol", QuantityKind.AMOUNT, 453.59237),
    # amount flow -- base mol/h
    Unit("mol/h", QuantityKind.AMOUNT_FLOW, 1.0),
    Unit("kmol/h", QuantityKind.AMOUNT_FLOW, 1.0e3),
    Unit("mol/min", QuantityKind.AMOUNT_FLOW, 1.0 / 60.0),
    Unit("kmol/min", QuantityKind.AMOUNT_FLOW, 1.0e3 / 60.0),
)

UNITS: dict[str, Unit] = {}
for _u in _UNITS:
    if _u.symbol in UNITS:  # pragma: no cover - registry is a module constant
        raise QuantityKindError(f"duplicate unit symbol {_u.symbol!r}")
    UNITS[_u.symbol] = _u


def unit(symbol: str) -> Unit:
    """Look up a registered unit, raising rather than guessing."""
    try:
        return UNITS[symbol]
    except KeyError:
        raise QuantityKindError(
            f"unknown unit {symbol!r}; registered units: {sorted(UNITS)}"
        ) from None


def base_unit(kind: QuantityKind) -> str:
    """The unit all conversions of `kind` pass through."""
    return _BASE_UNITS[kind]


def convert(value: float, src: str, dst: str) -> float:
    """Convert within a single `QuantityKind`.

    Refuses to cross kinds.  There is no mass-to-amount conversion here: that
    needs a molar mass, which is a property of a `Component`, not of a unit.
    """
    s, d = unit(src), unit(dst)
    if s.kind is not d.kind:
        raise QuantityKindError(
            f"cannot convert {src!r} ({s.kind.value}) to {dst!r} ({d.kind.value}): "
            f"a kind change needs a declared molar mass, not a unit conversion"
        )
    return (value * s.to_base) / d.to_base


# --------------------------------------------------------------------------- #
# provenance
# --------------------------------------------------------------------------- #


class Provenance(Enum):
    """How a value came to exist. Exactly one per `Quantity`."""

    REPORTED = "reported"
    """Stated by a source document, with a reference to that place."""

    DERIVED = "derived"
    """Computed by a transparent, named calculation from named inputs."""

    ASSUMED = "assumed"
    """Supplied by the implementer to close a gap, with a written rationale."""


class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# --------------------------------------------------------------------------- #
# values and unknowns
# --------------------------------------------------------------------------- #


class QuantityError(ValueError):
    """Raised when a `Quantity` violates a structural integrity rule."""


@dataclass(frozen=True)
class Quantity:
    """A single number with a unit, a semantic kind and a provenance.

    Invariants enforced in `__post_init__`:

      * the value is finite;
      * the unit is registered and belongs to `kind`;
      * `reported` and `assumed` values carry a source reference;
      * `derived` values carry a description of the calculation.

    A `Quantity` cannot be "unknown".  Unknowns are `Unknown` objects, which is
    a different type on purpose: the engine cannot accidentally treat a missing
    measurement as a measured zero.
    """

    quantity_id: str
    value: float
    unit: str
    kind: QuantityKind
    provenance: Provenance
    source_ref: str | None = None
    derivation: str | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.value, (int, float)) or isinstance(self.value, bool):
            raise QuantityError(
                f"{self.quantity_id}: value must be a real number, got "
                f"{self.value!r}"
            )
        if not math.isfinite(float(self.value)):
            raise QuantityError(
                f"{self.quantity_id}: value must be finite, got {self.value!r}"
            )
        u = unit(self.unit)
        if u.kind is not self.kind:
            raise QuantityError(
                f"{self.quantity_id}: unit {self.unit!r} is a {u.kind.value} but the "
                f"quantity declares kind {self.kind.value}"
            )
        if self.provenance is Provenance.DERIVED and not self.derivation:
            raise QuantityError(
                f"{self.quantity_id}: provenance 'derived' requires a `derivation` "
                f"describing the calculation; a number with no method is a guess"
            )
        if (
            self.provenance in (Provenance.REPORTED, Provenance.ASSUMED)
            and not self.source_ref
        ):
            raise QuantityError(
                f"{self.quantity_id}: provenance {self.provenance.value!r} requires "
                f"a `source_ref` (a citation for reported data, an assumption "
                f"statement for assumed data)"
            )

    @property
    def base_value(self) -> float:
        """The value expressed in this kind's base unit."""
        return self.value * unit(self.unit).to_base

    def convert_to(self, dst: str) -> float:
        """This value expressed in `dst`, which must share this value's kind."""
        return convert(self.value, self.unit, dst)

    def display(self) -> str:
        return f"{self.value:g} {self.unit}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "quantity_id": self.quantity_id,
            "value": self.value,
            "unit": self.unit,
            "kind": self.kind.value,
            "provenance": self.provenance.value,
            "source_ref": self.source_ref,
            "derivation": self.derivation,
            "note": self.note,
        }


@dataclass(frozen=True)
class Unknown:
    """A quantity the source does not supply, declared so it can be solved for.

    This object is the mechanism behind "unknowns must be explicit".  It names
    the variable the solver will produce, the kind of value that variable holds,
    and -- optionally -- why the source is silent.  It can never hold a value.
    """

    variable_id: str
    kind: QuantityKind
    unit: str | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.variable_id:
            raise QuantityError("an Unknown must name the variable it stands for")
        if self.unit is not None:
            u = unit(self.unit)
            if u.kind is not self.kind:
                raise QuantityError(
                    f"{self.variable_id}: unit {self.unit!r} is a {u.kind.value} but "
                    f"the unknown declares kind {self.kind.value}"
                )

    @property
    def effective_unit(self) -> str:
        return self.unit or base_unit(self.kind)

    def to_dict(self) -> dict[str, Any]:
        return {
            "variable_id": self.variable_id,
            "kind": self.kind.value,
            "unit": self.effective_unit,
            "reason": self.reason,
        }


def unknown(
    variable_id: str,
    kind: QuantityKind,
    *,
    unit: str | None = None,
    reason: str = "",
) -> Unknown:
    """Declare a quantity that is not known, so the solver can determine it.

    The `reason` is the gap the source leaves.  It is not decoration: it is what
    a reader needs in order to judge whether solving for this variable was the
    right question.
    """
    return Unknown(variable_id=variable_id, kind=kind, unit=unit, reason=reason)


def reported(
    quantity_id: str,
    value: float,
    unit: str,
    *,
    source_ref: str,
    note: str = "",
) -> Quantity:
    """A value stated by a source document."""
    return Quantity(
        quantity_id=quantity_id,
        value=value,
        unit=unit,
        kind=UNITS[unit].kind,
        provenance=Provenance.REPORTED,
        source_ref=source_ref,
        note=note,
    )


def derived(
    quantity_id: str,
    value: float,
    unit: str,
    *,
    derivation: str,
    source_ref: str | None = None,
    note: str = "",
) -> Quantity:
    """A value computed by a transparent, named calculation."""
    return Quantity(
        quantity_id=quantity_id,
        value=value,
        unit=unit,
        kind=UNITS[unit].kind,
        provenance=Provenance.DERIVED,
        source_ref=source_ref,
        derivation=derivation,
        note=note,
    )


def assumed(
    quantity_id: str,
    value: float,
    unit: str,
    *,
    assumption_id: str,
    rationale: str,
    note: str = "",
) -> Quantity:
    """A value supplied by the implementer to close a documented gap."""
    return Quantity(
        quantity_id=quantity_id,
        value=value,
        unit=unit,
        kind=UNITS[unit].kind,
        provenance=Provenance.ASSUMED,
        source_ref=f"{assumption_id}: {rationale}",
        note=note,
    )


# --------------------------------------------------------------------------- #
# components, streams, directions
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Component:
    """A conserved entity that can carry an independent balance.

    Section 4.7.1 is careful about this term: in a non-reacting system a
    component is *usually* a chemical species, but it may equally be a group of
    species of known composition, or a phase of constant composition such as a
    solid assemblage that passes through a device unchanged.  `molar_mass` is
    optional and is only ever used to move between a mass basis and an amount
    basis -- never guessed.
    """

    component_id: str
    label: str
    formula: str | None = None
    molar_mass_kg_per_mol: float | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if not self.component_id:
            raise QuantityError("a Component must have a component_id")
        if (
            self.molar_mass_kg_per_mol is not None
            and self.molar_mass_kg_per_mol <= 0.0
        ):
            raise QuantityError(
                f"{self.component_id}: molar_mass_kg_per_mol must be positive, got "
                f"{self.molar_mass_kg_per_mol!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "label": self.label,
            "formula": self.formula,
            "molar_mass_kg_per_mol": self.molar_mass_kg_per_mol,
            "note": self.note,
        }


class Direction(Enum):
    """Which side of the control volume a stream sits on.

    The legal set is restricted per `ProcessMode`; `BalanceSystem` rejects any
    stream whose direction the declared mode does not admit.  This is what stops
    the engine from quietly running a steady-state balance on a batch.
    """

    # continuous
    INPUT = "input"
    OUTPUT = "output"
    ACCUMULATED = "accumulated"
    # batch
    INITIAL = "initial"
    ADDED = "added"
    REMOVED = "removed"
    FINAL = "final"
    # any mode
    INTERNAL = "internal"


class ProcessMode(Enum):
    """The declared operating mode of the control volume.

    Each mode generates only the equations the chapter gives for it, and
    `BalanceSystem` rejects a system whose streams do not match its mode.
    """

    STEADY_STATE = "steady_state"
    """No accumulation (Morris et al. 2011, sec. 4.4/4.5): input - output = 0."""

    ACCUMULATING = "accumulating"
    """Continuous flow with material retained (sec. 4.4, Example 4.3):
    input - output - accumulation = 0."""

    BATCH = "batch"
    """No material crosses during operation (sec. 4.18): final - initial -
    added + removed = 0."""


#: Directions each mode admits.
LEGAL_DIRECTIONS: Mapping[ProcessMode, frozenset[Direction]] = {
    ProcessMode.STEADY_STATE: frozenset(
        {Direction.INPUT, Direction.OUTPUT, Direction.INTERNAL}
    ),
    ProcessMode.ACCUMULATING: frozenset(
        {
            Direction.INPUT,
            Direction.OUTPUT,
            Direction.ACCUMULATED,
            Direction.INTERNAL,
        }
    ),
    ProcessMode.BATCH: frozenset(
        {
            Direction.INITIAL,
            Direction.ADDED,
            Direction.REMOVED,
            Direction.FINAL,
            Direction.INTERNAL,
        }
    ),
}

#: Directions each mode *requires* at least one of.
REQUIRED_DIRECTIONS: Mapping[ProcessMode, tuple[Direction, ...]] = {
    ProcessMode.STEADY_STATE: (Direction.INPUT,),
    ProcessMode.ACCUMULATING: (Direction.INPUT, Direction.ACCUMULATED),
    ProcessMode.BATCH: (Direction.INITIAL, Direction.FINAL),
}


class ProcessModeError(ValueError):
    """Raised when a system's streams do not fit its declared process mode."""


class StreamError(ValueError):
    """Raised when a `Stream` is internally inconsistent or under-specified."""


def stream_total_id(stream_id: str) -> str:
    """Variable id for a stream's total flow or amount."""
    return f"stream:{stream_id}:total"


def stream_component_id(stream_id: str, component_id: str) -> str:
    """Variable id for a stream's total flow/amount of one component."""
    return f"stream:{stream_id}:{component_id}"


def stream_fraction_id(stream_id: str, component_id: str) -> str:
    """Variable id for a stream's mass fraction of one component."""
    return f"stream:{stream_id}:w:{component_id}"


@dataclass(frozen=True)
class Stream:
    """Material entering, leaving, retained by, or contained in the control volume.

    Exactly one of two ways of describing the contents is required, mirroring the
    chapter's definition of a completely specified stream (sec. 4.18: the stream
    is fully specified either when flow *and* composition are given, or when the
    flow of each constituent is given):

      * `amount` + `mass_fractions` -- total flow/amount, and a composition;
      * `component_amounts` -- the flow/amount of each component directly.

    A stream may not mix the two.  Within a stream, every quantity must share one
    `QuantityKind`, so a mass flow is never silently read as an amount flow.

    Composition completeness matters.  When `mass_fractions` is used the
    generated constraint ``sum(w) = 1`` runs over exactly the components present,
    so any system component the stream omits must be declared in
    `absent_components`; `BalanceSystem` raises rather than let an omission look
    like a zero fraction.  Components omitted from `component_amounts` contribute
    no term to any balance, so their absence is reported as a warning instead.
    """

    stream_id: str
    label: str
    direction: Direction
    amount: Quantity | Unknown | None = None
    mass_fractions: Mapping[str, Quantity | Unknown] = field(default_factory=dict)
    component_amounts: Mapping[str, Quantity | Unknown] = field(default_factory=dict)
    absent_components: tuple[str, ...] = ()
    time_basis: str | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if not self.stream_id:
            raise StreamError("a Stream must have a stream_id")
        if self.mass_fractions and self.component_amounts:
            raise StreamError(
                f"{self.stream_id}: declare either (amount + mass_fractions) or "
                f"component_amounts, not both; the chapter treats these as two "
                f"alternative ways of specifying a stream (sec. 4.18)"
            )
        if self.component_amounts and self.amount is not None:
            raise StreamError(
                f"{self.stream_id}: component_amounts already fixes the total, so "
                f"`amount` must be None or an Unknown"
            )
        if not self.mass_fractions and not self.component_amounts:
            raise StreamError(
                f"{self.stream_id}: a stream must define either (amount + "
                f"mass_fractions) or component_amounts; an empty stream has no "
                f"meaning in a balance"
            )
        for cid, frac in self.mass_fractions.items():
            if isinstance(frac, Quantity) and frac.kind is not QuantityKind.MASS_FRACTION:
                raise StreamError(
                    f"{self.stream_id}.w_{cid}: mass fractions must be "
                    f"MASS_FRACTION, got {frac.kind.value}"
                )
            if isinstance(frac, Unknown) and frac.kind is not QuantityKind.MASS_FRACTION:
                raise StreamError(
                    f"{self.stream_id}.w_{cid}: unknown mass fractions must declare "
                    f"kind MASS_FRACTION, got {frac.kind.value}"
                )
        self._check_single_kind()

    # ---- kind consistency ----------------------------------------------------
    def _kinds(self) -> list[QuantityKind]:
        """The kinds of the stream's *quantities of material*.

        Mass fractions are deliberately excluded: a stream described by a total
        flow and a composition necessarily pairs a MASS_FLOW with a
        MASS_FRACTION, and that is the ordinary way to state a stream.  What has
        to agree is the kind of the flow or amount itself, so that a mass flow
        can never be read as an amount flow.
        """
        kinds: list[QuantityKind] = []
        if self.amount is not None:
            kinds.append(self.amount.kind)
        for comp in self.component_amounts.values():
            kinds.append(comp.kind)
        return kinds

    def _check_single_kind(self) -> None:
        kinds = set(self._kinds())
        if len(kinds) > 1:
            raise StreamError(
                f"{self.stream_id}: the quantities of material in a stream must "
                f"share one kind, found {sorted(k.value for k in kinds)}"
            )
        if not kinds:
            raise StreamError(
                f"{self.stream_id}: a stream described only by mass fractions has no "
                f"flow or amount; add `amount`, or give component amounts instead"
            )

    @property
    def kind(self) -> QuantityKind:
        """The single semantic kind shared by this stream's quantities."""
        kinds = set(self._kinds())
        assert len(kinds) == 1, "checked in __post_init__"
        return next(iter(kinds))

    @property
    def is_flow(self) -> bool:
        return self.kind in (QuantityKind.MASS_FLOW, QuantityKind.AMOUNT_FLOW)

    @property
    def components_declared(self) -> tuple[str, ...]:
        if self.mass_fractions:
            return tuple(self.mass_fractions)
        return tuple(self.component_amounts)

    def effective_time_basis(self) -> str | None:
        """The time basis of a flow stream, taken from its unit when not stated.

        Returns None for non-flow kinds, which have no time basis.
        """
        if not self.is_flow:
            return None
        if self.time_basis:
            return self.time_basis
        base = base_unit(self.kind)
        return base.rsplit("/", 1)[-1] if "/" in base else base

    def unknown_variable_ids(self) -> tuple[str, ...]:
        """Variable ids this stream contributes to the linear system."""
        out: list[str] = []
        if isinstance(self.amount, Unknown):
            out.append(self.amount.variable_id)
        for cid, val in self.mass_fractions.items():
            if isinstance(val, Unknown):
                out.append(val.variable_id)
        for cid, val in self.component_amounts.items():
            if isinstance(val, Unknown):
                out.append(val.variable_id)
        return tuple(out)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stream_id": self.stream_id,
            "label": self.label,
            "direction": self.direction.value,
            "kind": self.kind.value,
            "amount": self.amount.to_dict() if self.amount is not None else None,
            "mass_fractions": {
                k: v.to_dict() for k, v in self.mass_fractions.items()
            },
            "component_amounts": {
                k: v.to_dict() for k, v in self.component_amounts.items()
            },
            "absent_components": list(self.absent_components),
            "time_basis": self.effective_time_basis(),
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# equations
# --------------------------------------------------------------------------- #


class EquationKind(Enum):
    COMPONENT_BALANCE = "component_balance"
    """Sum(component i input) - sum(component i output) = 0 (sec. 4.5)."""

    COMPOSITION_SUM = "composition_sum"
    """sum(component mass fractions) = 1 for a complete composition."""

    USER_CONSTRAINT = "user_constraint"
    """A caller-supplied relation, treated with exactly the status of a balance."""


@dataclass(frozen=True)
class ConstantTerm:
    """A known number folded into an equation, kept with its provenance.

    Residuals are only auditable if the measurement that caused them is still
    identifiable, so constants are never flattened into an anonymous float.
    """

    quantity_id: str
    value: float
    unit: str
    kind: QuantityKind
    provenance: Provenance
    source_ref: str | None
    #: sign as it appears in the equation's constant sum
    sign: int = 1
    #: for a constant that is itself computed, the inputs it was computed from
    derivation: str | None = None

    def signed_base_value(self) -> float:
        return self.sign * self.value * unit(self.unit).to_base

    def to_dict(self) -> dict[str, Any]:
        return {
            "quantity_id": self.quantity_id,
            "value": self.value,
            "unit": self.unit,
            "kind": self.kind.value,
            "provenance": self.provenance.value,
            "source_ref": self.source_ref,
            "sign": self.sign,
            "derivation": self.derivation,
        }


@dataclass(frozen=True)
class BalanceEquation:
    """One generated or supplied equation, in ``sum(c_j x_j) + sum(k_i) = 0``.

    Coefficients are expressed in the base unit of the system's balance basis so
    that rows can be compared and ranked without unit bookkeeping.  `constants`
    retains every known term with its provenance, which is what makes a residual
    traceable back to a specific measurement.
    """

    equation_id: str
    kind: EquationKind
    label: str
    expression: str
    coefficients: Mapping[str, float]
    constants: tuple[ConstantTerm, ...] = ()
    component_id: str | None = None
    stream_id: str | None = None
    inputs: tuple[str, ...] = ()
    process_mode: ProcessMode = ProcessMode.STEADY_STATE
    source_ref: str | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if not self.equation_id:
            raise QuantityError("a BalanceEquation must have an equation_id")
        if not self.coefficients and not self.constants:
            raise QuantityError(
                f"{self.equation_id}: an equation with no variables and no "
                f"constants constrains nothing"
            )

    @property
    def constant_sum(self) -> float:
        return sum(c.signed_base_value() for c in self.constants)

    def terms(self) -> tuple[str, ...]:
        ids = list(self.inputs)
        ids.extend(c.quantity_id for c in self.constants)
        return tuple(ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "equation_id": self.equation_id,
            "kind": self.kind.value,
            "label": self.label,
            "expression": self.expression,
            "coefficients": dict(self.coefficients),
            "constants": [c.to_dict() for c in self.constants],
            "constant_sum": self.constant_sum,
            "component_id": self.component_id,
            "stream_id": self.stream_id,
            "inputs": list(self.inputs),
            "process_mode": self.process_mode.value,
            "source_ref": self.source_ref,
            "note": self.note,
        }


# --------------------------------------------------------------------------- #
# results
# --------------------------------------------------------------------------- #


class Solvability(Enum):
    """How the assembled linear system came out.

    These four cases are the ones the chapter distinguishes in section 4.7:
    a balanced system (DOF = 0), an under-specified one (DOF > 0), an
    over-specified one (DOF < 0), and -- the case the chapter warns about at
    length -- over-specified data that disagree with each other.
    """

    UNIQUE = "unique"
    """Every unknown determined; no redundant information."""

    UNDERDETERMINED = "underdetermined"
    """Fewer independent equations than unknowns; some variables stay free."""

    INCONSISTENT = "inconsistent"
    """The measurements contradict each other. Nothing is discarded."""

    OVERCONSTRAINED = "overconstrained"
    """More equations than unknowns, but the surplus is mutually consistent."""

    NO_UNKNOWNS = "no_unknowns"
    """Nothing to solve: a pure verification of fully stated data."""


class BalanceSystemError(ValueError):
    """Raised when a `BalanceSystem` is not internally consistent."""


@dataclass(frozen=True)
class Assumption:
    """An implementer-supplied bridge across a gap the sources leave open.

    Assumptions exist to be audited.  Each names what was assumed, why, and
    which quantities become conditional on it.
    """

    assumption_id: str
    statement: str
    rationale: str
    affects: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "assumption_id": self.assumption_id,
            "statement": self.statement,
            "rationale": self.rationale,
            "affects": list(self.affects),
        }


@dataclass(frozen=True)
class BalanceDiagnostic:
    """A message attached to a result: why it is solvable, or why it is not."""

    code: str
    severity: Severity
    message: str
    where: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "where": list(self.where),
        }


@dataclass(frozen=True)
class SolvedVariable:
    """A variable the linear system determined, with how it was determined."""

    variable_id: str
    value: float
    unit: str
    kind: QuantityKind
    method: str
    inputs: tuple[str, ...]
    provenance: Provenance = Provenance.DERIVED
    #: the same variable id when the same quantity is reported in the source unit
    source_unit: str | None = None
    source_value: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "variable_id": self.variable_id,
            "value": self.value,
            "unit": self.unit,
            "kind": self.kind.value,
            "provenance": self.provenance.value,
            "method": self.method,
            "inputs": list(self.inputs),
            "source_unit": self.source_unit,
            "source_value": self.source_value,
        }


@dataclass(frozen=True)
class UnresolvedVariable:
    """A variable the system could not determine, and the reason it could not."""

    variable_id: str
    unit: str
    kind: QuantityKind
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "variable_id": self.variable_id,
            "unit": self.unit,
            "kind": self.kind.value,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ResidualContribution:
    """One stream's signed contribution to a balance residual."""

    stream_id: str
    label: str
    value: float
    unit: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "stream_id": self.stream_id,
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class BalanceResidual:
    """How far a balance fails to close, and which streams account for it.

    The chapter's step 3 of section 4.6.2 -- check the answer against a
    dependent equation -- made mechanical here.
    """

    label: str
    value: float
    unit: str
    basis_unit: str
    tolerance: float
    contributions: tuple[ResidualContribution, ...] = ()
    component_id: str | None = None

    @property
    def is_within_tolerance(self) -> bool:
        return abs(self.value) <= self.tolerance

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "component_id": self.component_id,
            "value": self.value,
            "unit": self.unit,
            "basis_unit": self.basis_unit,
            "tolerance": self.tolerance,
            "is_within_tolerance": self.is_within_tolerance,
            "contributions": [c.to_dict() for c in self.contributions],
        }


@dataclass(frozen=True)
class LedgerRow:
    """One resolved stream/component cell of the chapter's ledger (sec. 4.5)."""

    stream_id: str
    label: str
    direction: Direction
    component_id: str
    component_label: str
    value: float
    unit: str
    kind: QuantityKind
    provenance: Provenance
    mass_fraction: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "stream_id": self.stream_id,
            "label": self.label,
            "direction": self.direction.value,
            "component_id": self.component_id,
            "component_label": self.component_label,
            "value": self.value,
            "unit": self.unit,
            "kind": self.kind.value,
            "provenance": self.provenance.value,
            "mass_fraction": self.mass_fraction,
        }


@dataclass(frozen=True)
class BalanceResult:
    """Everything one balance run produced.

    The result is deliberately explicit about what is *not* in it: no field
    holds a best-guess value for a variable that could not be determined, and
    no measurement is adjusted to make a balance close.
    """

    system_id: str
    label: str
    process_mode: ProcessMode
    basis: str
    basis_unit: str
    solvability: Solvability
    n_unknowns: int
    n_equations: int
    rank: int
    equations: tuple[BalanceEquation, ...]
    variables: tuple[SolvedVariable, ...]
    unresolved: tuple[UnresolvedVariable, ...]
    component_residuals: tuple[BalanceResidual, ...]
    total_mass_residual: BalanceResidual | None
    ledger: tuple[LedgerRow, ...] = ()
    #: per-equation residual after the solve, keyed by equation_id
    equation_residuals: Mapping[str, float] = field(default_factory=dict)
    independent_equation_ids: tuple[str, ...] = ()
    redundant_equation_ids: tuple[str, ...] = ()
    inconsistent_equation_ids: tuple[str, ...] = ()
    freedom: Any | None = None
    """`models.degrees_of_freedom.FreedomComparison`, or None when not supplied.

    Typed as Any to keep `schemas` free of any dependency on the engine layer.
    """
    diagnostics: tuple[BalanceDiagnostic, ...] = ()
    assumptions: tuple[Assumption, ...] = ()
    source_ref: str | None = None
    notes: str = ""

    @property
    def is_consistent(self) -> bool:
        return self.solvability is not Solvability.INCONSISTENT

    @property
    def balances_close(self) -> bool:
        """True when every reported residual is within its tolerance."""
        checks = list(self.component_residuals)
        if self.total_mass_residual is not None:
            checks.append(self.total_mass_residual)
        return all(r.is_within_tolerance for r in checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "system_id": self.system_id,
            "label": self.label,
            "process_mode": self.process_mode.value,
            "basis": self.basis,
            "basis_unit": self.basis_unit,
            "solvability": self.solvability.value,
            "is_consistent": self.is_consistent,
            "balances_close": self.balances_close,
            "n_unknowns": self.n_unknowns,
            "n_equations": self.n_equations,
            "rank": self.rank,
            "equations": [e.to_dict() for e in self.equations],
            "variables": [v.to_dict() for v in self.variables],
            "unresolved": [u.to_dict() for u in self.unresolved],
            "component_residuals": [r.to_dict() for r in self.component_residuals],
            "total_mass_residual": (
                self.total_mass_residual.to_dict() if self.total_mass_residual else None
            ),
            "residuals": [
                r.to_dict()
                for r in (*self.component_residuals, *(
                    (self.total_mass_residual,) if self.total_mass_residual else ()
                ))
            ],
            "equation_residuals": dict(self.equation_residuals),
            "ledger": [r.to_dict() for r in self.ledger],
            "independent_equation_ids": list(self.independent_equation_ids),
            "redundant_equation_ids": list(self.redundant_equation_ids),
            "inconsistent_equation_ids": list(self.inconsistent_equation_ids),
            "freedom": self.freedom.to_dict() if self.freedom is not None else None,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "assumptions": [a.to_dict() for a in self.assumptions],
            "source_ref": self.source_ref,
            "notes": self.notes,
        }


# --------------------------------------------------------------------------- #
# system
# --------------------------------------------------------------------------- #


class BalanceBasis(Enum):
    """The dimensional basis the balance equations are written in."""

    MASS = "mass"
    AMOUNT = "amount"


_BASIS_KINDS: Mapping[BalanceBasis, tuple[QuantityKind, QuantityKind]] = {
    BalanceBasis.MASS: (QuantityKind.MASS, QuantityKind.MASS_FLOW),
    BalanceBasis.AMOUNT: (QuantityKind.AMOUNT, QuantityKind.AMOUNT_FLOW),
}


@dataclass(frozen=True)
class BalanceSystem:
    """A control volume, its components, its streams and its declared mode.

    Construction validates the declaration, not the arithmetic: it checks that
    the mode is consistent with the stream directions, that stream kinds match
    the balance basis, that variable ids are unique, and that any component a
    stream leaves out is declared.  The balance equations themselves are
    generated later, by `models.material_balance`.

    `constraints` are caller-supplied relations.  They are treated with exactly
    the same standing as generated balances: they appear in the rank count, they
    can make a system overconstrained, and their residuals are reported.
    """

    system_id: str
    label: str
    process_mode: ProcessMode
    basis: BalanceBasis
    components: tuple[Component, ...]
    streams: tuple[Stream, ...]
    constraints: tuple[BalanceEquation, ...] = ()
    assumptions: tuple[Assumption, ...] = ()
    balances: tuple[str, ...] | None = None
    """Which components get an independent balance; None means every component.

    The chapter allows fewer balances than components in two circumstances:
    section 4.7.2 ("an independent balance can be written for each component, or
    for the total mass plus the number of components - 1") and Example 4.3,
    where a lead balance "won't help because it provides no useful information".
    Naming the components here makes that choice explicit instead of implicit.
    """
    total_balance: bool = False
    """Generate the total-mass equation in addition to the component balances.

    Redundant when every component already has a balance, since the total mass
    balance is exactly their sum.  Needed when `balances` names fewer than all
    components, to keep the count at one independent equation per component.
    """
    residual_tolerance: float = 1.0e-6
    rank_tolerance: float = 1.0e-10
    source_ref: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.system_id:
            raise BalanceSystemError("a BalanceSystem must have a system_id")
        if not self.components:
            raise BalanceSystemError(
                f"{self.system_id}: a system with no components has no balances"
            )
        if not self.streams:
            raise BalanceSystemError(f"{self.system_id}: a system has no streams")
        if self.residual_tolerance < 0.0 or self.rank_tolerance <= 0.0:
            raise BalanceSystemError(
                f"{self.system_id}: tolerances must be non-negative, with a strictly "
                f"positive rank tolerance"
            )
        seen_components: set[str] = set()
        for comp in self.components:
            if comp.component_id in seen_components:
                raise BalanceSystemError(
                    f"{self.system_id}: duplicate component id {comp.component_id!r}"
                )
            seen_components.add(comp.component_id)
        if self.balances is not None:
            unknown_balances = set(self.balances) - seen_components
            if unknown_balances:
                raise BalanceSystemError(
                    f"{self.system_id}: `balances` names component(s) "
                    f"{sorted(unknown_balances)} that the system does not define"
                )
        self._check_directions()
        self._check_stream_kinds()
        self._check_composition_completeness()
        self._check_unique_variable_ids()

    # ---- validation ----------------------------------------------------------
    def _check_directions(self) -> None:
        legal = LEGAL_DIRECTIONS[self.process_mode]
        for stream in self.streams:
            if stream.direction not in legal:
                raise ProcessModeError(
                    f"{self.system_id}: stream {stream.stream_id!r} has direction "
                    f"{stream.direction.value!r}, which {self.process_mode.value} does "
                    f"not admit. Legal directions: "
                    f"{sorted(d.value for d in legal)}. Declare the mode that matches "
                    f"the process rather than inferring one."
                )
        present = {s.direction for s in self.streams}
        for required in REQUIRED_DIRECTIONS[self.process_mode]:
            if required not in present:
                raise ProcessModeError(
                    f"{self.system_id}: {self.process_mode.value} requires at least "
                    f"one {required.value!r} stream, and there is none"
                )

    def _expected_kinds(self) -> tuple[QuantityKind, QuantityKind]:
        return _BASIS_KINDS[self.basis]

    def _check_stream_kinds(self) -> None:
        instance_kind, flow_kind = self._expected_kinds()
        crossing = self.crossing_streams()
        for stream in self.streams:
            if stream.kind not in (instance_kind, flow_kind):
                raise BalanceSystemError(
                    f"{self.system_id}: stream {stream.stream_id!r} carries "
                    f"{stream.kind.value} quantities but the balance basis is "
                    f"{self.basis.value!r}, which needs {instance_kind.value} or "
                    f"{flow_kind.value}. Convert explicitly or change the basis."
                )
        if self.process_mode is ProcessMode.STEADY_STATE:
            # "No accumulation" is a statement about rates; an inventory cannot
            # have one.
            for stream in crossing:
                if not stream.is_flow:
                    raise BalanceSystemError(
                        f"{self.system_id}: stream {stream.stream_id!r} is a "
                        f"{stream.kind.value} stream, but steady_state is a flow "
                        f"mode and requires {flow_kind.value} quantities. Restate "
                        f"the balance on a rate basis, or declare the operating "
                        f"time interval and use accumulating with {instance_kind} "
                        f"quantities."
                    )
        if self.process_mode is ProcessMode.BATCH:
            for stream in crossing:
                if stream.is_flow:
                    raise BalanceSystemError(
                        f"{self.system_id}: stream {stream.stream_id!r} is a "
                        f"{stream.kind.value} stream, but batch is an inventory "
                        f"mode: section 4.18 defines a batch process as one in "
                        f"which no material flows in or out during operation."
                    )
        # Input, output and accumulation must be commensurable, so all crossing
        # streams share one kind.  Example 4.3 states bullion and lead as
        # amounts per panel cycle, not rates, and that is the consistent choice.
        kinds = {s.kind for s in crossing}
        if len(kinds) > 1:
            raise BalanceSystemError(
                f"{self.system_id}: the streams crossing the control volume mix "
                f"{sorted(k.value for k in kinds)}. Input, output and accumulation "
                f"have to be in the same units before they can be subtracted."
            )

    def _check_composition_completeness(self) -> None:
        system_components = {c.component_id for c in self.components}
        for stream in self.streams:
            declared = set(stream.components_declared)
            unknown_ids = set(declared) | set(stream.absent_components)
            stray = unknown_ids - system_components
            if stray:
                raise BalanceSystemError(
                    f"{self.system_id}: stream {stream.stream_id!r} references "
                    f"component(s) {sorted(stray)} that the system does not define"
                )
            if stream.mass_fractions:
                missing = system_components - declared - set(stream.absent_components)
                if missing:
                    raise BalanceSystemError(
                        f"{self.system_id}: stream {stream.stream_id!r} gives mass "
                        f"fractions for {sorted(declared)} but does not mention "
                        f"{sorted(missing)}. Because the engine will write "
                        f"sum(w) = 1 over the declared components, an omission would "
                        f"silently read as a zero fraction. List them in "
                        f"`absent_components` if they are genuinely absent."
                    )

    def _check_unique_variable_ids(self) -> None:
        stream_ids: dict[str, str] = {}
        for stream in self.streams:
            for vid in stream.unknown_variable_ids():
                if vid in stream_ids:
                    raise BalanceSystemError(
                        f"{self.system_id}: variable id {vid!r} is declared twice "
                        f"(streams {stream_ids[vid]!r} and {stream.stream_id!r})"
                    )
                stream_ids[vid] = stream.stream_id
        # Constraints are *meant* to reference stream variables -- that is how a
        # split fraction or a flow ratio is written.  What they must not do is
        # invent one: an unknown the streams never declare would sit in the
        # matrix with no provenance behind it.
        for constraint in self.constraints:
            stray = sorted(set(constraint.coefficients) - set(stream_ids))
            if stray:
                raise BalanceSystemError(
                    f"{self.system_id}: constraint {constraint.equation_id!r} "
                    f"references unknown variable(s) {stray}, which no stream "
                    f"declares. A constraint may relate stream variables, not "
                    f"introduce new ones."
                )

    # ---- accessors -----------------------------------------------------------
    @property
    def component_ids(self) -> tuple[str, ...]:
        return tuple(c.component_id for c in self.components)

    @property
    def quantity_kind(self) -> QuantityKind:
        """The single kind of material flowing through this control volume.

        All crossing streams are validated to share it, so the balance's unit
        follows from the data rather than from a separate declaration that could
        drift away from it.
        """
        crossing = self.crossing_streams()
        if not crossing:
            return _BASIS_KINDS[self.basis][0]
        return crossing[0].kind

    @property
    def basis_unit(self) -> str:
        """The unit all balance arithmetic is performed in.

        For a flow mode this is the rate base unit (`kg/h`); for an inventory
        mode it is the plain base unit (`kg`).  It is derived from the streams
        themselves, so it cannot disagree with the numbers in the system.
        """
        return base_unit(self.quantity_kind)

    def component(self, component_id: str) -> Component:
        for comp in self.components:
            if comp.component_id == component_id:
                return comp
        raise KeyError(
            f"{self.system_id}: no component {component_id!r}; known: "
            f"{self.component_ids}"
        )

    def stream(self, stream_id: str) -> Stream:
        for stream in self.streams:
            if stream.stream_id == stream_id:
                return stream
        raise KeyError(
            f"{self.system_id}: no stream {stream_id!r}; known: "
            f"{tuple(s.stream_id for s in self.streams)}"
        )

    def crossing_streams(self) -> tuple[Stream, ...]:
        """Streams that actually cross the control volume boundary.

        Internal streams enter and leave and so cancel from every balance; they
        are excluded here and reported separately by the engine.
        """
        return tuple(s for s in self.streams if s.direction is not Direction.INTERNAL)

    def internal_streams(self) -> tuple[Stream, ...]:
        return tuple(s for s in self.streams if s.direction is Direction.INTERNAL)

    def component_amounts_gap(self) -> list[tuple[Stream, set[str]]]:
        """Streams that give component amounts but omit other components.

        An incomplete *mass-fraction* composition has to be declared, because the
        generated ``sum(w) = 1`` runs over exactly the declared components, so an
        omission would silently act like a zero fraction.  A stream given as
        component amounts is different: a component it does not mention simply
        contributes no term to any balance.  That is still worth surfacing, but
        as a warning rather than as a hard error.
        """
        system_components = {c.component_id for c in self.components}
        gaps: list[tuple[Stream, set[str]]] = []
        for stream in self.streams:
            if not stream.component_amounts:
                continue
            missing = system_components - set(stream.component_amounts) - set(
                stream.absent_components
            )
            if missing:
                gaps.append((stream, missing))
        return gaps

    def to_dict(self) -> dict[str, Any]:
        return {
            "system_id": self.system_id,
            "label": self.label,
            "process_mode": self.process_mode.value,
            "basis": self.basis.value,
            "basis_unit": self.basis_unit,
            "residual_tolerance": self.residual_tolerance,
            "rank_tolerance": self.rank_tolerance,
            "components": [c.to_dict() for c in self.components],
            "balances": list(self.balances) if self.balances is not None else None,
            "total_balance": self.total_balance,
            "streams": [s.to_dict() for s in self.streams],
            "constraints": [c.to_dict() for c in self.constraints],
            "assumptions": [a.to_dict() for a in self.assumptions],
            "source_ref": self.source_ref,
            "notes": self.notes,
        }


__all__ = [
    "LEGAL_DIRECTIONS",
    "REQUIRED_DIRECTIONS",
    "UNITS",
    "Assumption",
    "BalanceBasis",
    "BalanceDiagnostic",
    "BalanceEquation",
    "BalanceResidual",
    "BalanceResult",
    "BalanceSystem",
    "BalanceSystemError",
    "Component",
    "ConstantTerm",
    "Direction",
    "EquationKind",
    "LedgerRow",
    "ProcessMode",
    "ProcessModeError",
    "Provenance",
    "Quantity",
    "QuantityError",
    "QuantityKind",
    "QuantityKindError",
    "ResidualContribution",
    "Severity",
    "SolvedVariable",
    "Solvability",
    "Stream",
    "StreamError",
    "UnresolvedVariable",
    "Unknown",
    "assumed",
    "base_unit",
    "convert",
    "derived",
    "reported",
    "stream_component_id",
    "stream_fraction_id",
    "stream_total_id",
    "unit",
    "unknown",
]
