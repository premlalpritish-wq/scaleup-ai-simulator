"""Provenance for the Ganjave et al. (2022) model.

Three rules, enforced structurally in ``__post_init__`` rather than by
convention:

1. **A number is either present or absent.** A quantity the paper does not
   state is an :class:`Unknown`, which carries an identity and a reason. It is
   never coerced to ``0.0`` and never given a fabricated default. This matters
   here more than in most models: the paper reports the *initial OD600*
   (0.05) but no OD600-to-DCW calibration, so the initial biomass in g/L is
   **not derivable** and must be supplied by the caller.

2. **A value is not dimensionless unless it says what it is.** Every record
   carries a :class:`QuantityKind` and a unit registered for that kind.

3. **Every value says how it came to exist.** :class:`Provenance` is
   ``reported``, ``derived``, ``fitted`` or ``assumed``, and the class
   dictates what must accompany it: a source location for ``reported``,
   a derivation for ``derived``, the fitting procedure for ``fitted``, and a
   stated purpose for ``assumed``. There is no fourth option that quietly
   means "it was convenient".

Note on ``fitted``: Table 2 is a *fitted* parameter set. The paper states the
parameters were estimated by fitting the model to six fed-batch experiments
with a hybrid genetic-algorithm/constrained-optimisation scheme (p. 5), and
then validated on two further runs (p. 5). The values are therefore recorded
as ``FITTED`` with the fitting procedure attached, and separately as
``REPORTED`` in the sense of "printed in Table 2". :class:`Provenance` keeps
those apart, because a value can be printed by the authors and still be a fit
rather than a measurement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .units import QuantityKind

# --------------------------------------------------------------------------- #
# the source
# --------------------------------------------------------------------------- #

SOURCE_ID = "ganjave2022"

AUTHORS = (
    "S. D. Ganjave",
    "V. A. J. E. S. Waghmare",
    "P. P. Wangikar",
)
TITLE = (
    "High cell density cultivation of E. coli in shake flasks for the "
    "production of recombinant proteins"
)
JOURNAL = "Biotechnology Reports"
YEAR = 2022
VOLUME = "33"
ARTICLE_NUMBER = "e00694"
PAGES = "1-10"
DOI = "10.1016/j.btre.2021.e00694"

CITATION = (
    "S. D. Ganjave, V. A. J. E. S. Waghmare, P. P. Wangikar, 'High cell density "
    "cultivation of E. coli in shake flasks for the production of recombinant "
    "proteins', Biotechnology Reports 33 (2022) e00694."
)


@dataclass(frozen=True)
class SourceRef:
    """Where in the paper a statement is printed."""

    section: str
    locator: str
    """An equation, table or figure locator, e.g. 'eq. (11)' or 'Table 2'."""
    printed_page: int | None = None
    quote: str | None = None

    def __post_init__(self) -> None:
        if not self.section or not self.locator:
            raise ValueError("a SourceRef needs a section and a locator")
        if self.printed_page is not None and not 1 <= self.printed_page <= 10:
            raise ValueError(
                f"printed page {self.printed_page} is outside the article (1-10)"
            )

    @property
    def citation(self) -> str:
        page = f", p. {self.printed_page}" if self.printed_page else ""
        return f"Ganjave et al. 2022, {self.section}, {self.locator}{page}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": SOURCE_ID,
            "section": self.section,
            "locator": self.locator,
            "printed_page": self.printed_page,
            "quote": self.quote,
            "citation": self.citation,
        }


# --------------------------------------------------------------------------- #
# provenance
# --------------------------------------------------------------------------- #


class Provenance(Enum):
    """How a value came to exist. Exactly one per record."""

    REPORTED = "reported"
    """Printed in the paper as a measurement or a stated condition."""

    FITTED = "fitted"
    """Estimated by the authors' own fitting procedure and printed (Table 2)."""

    DERIVED = "derived"
    """Computed by this model from other records by a stated calculation."""

    ASSUMED = "assumed"
    """Supplied by a caller or an implementer for a stated purpose."""

    UNKNOWN = "unknown"
    """Not available; carries a reason and never a value."""


class Basis(Enum):
    """Observed reference vs computed output -- the axis that keeps a fitted
    parameter from being read as a measurement, and a simulated state from being
    read as an observation."""

    OBSERVED = "observed_reference"
    COMPUTED = "computed"
    ASSUMED = "assumed_input"
    UNRESOLVED = "unresolved"


_BASIS_BY_PROVENANCE = {
    Provenance.REPORTED: Basis.OBSERVED,
    Provenance.FITTED: Basis.OBSERVED,
    Provenance.DERIVED: Basis.COMPUTED,
    Provenance.ASSUMED: Basis.ASSUMED,
    Provenance.UNKNOWN: Basis.UNRESOLVED,
}


class ValueState(Enum):
    """The six states a port value may be in, mirroring the composition layer.

    Kept separate from :class:`Provenance` because they answer different
    questions: *can this be a number* and *how did it come to exist*.
    """

    NUMBER = "number"
    ZERO = "zero"
    """A number the source states as zero; kept distinct from NUMBER."""
    RANGE = "range"
    NOT_REPORTED = "not_reported"
    UNRESOLVED = "unresolved"
    UNKNOWN = "unknown"

    @property
    def has_number(self) -> bool:
        return self in (ValueState.NUMBER, ValueState.ZERO)


class ParameterError(ValueError):
    """Raised when a parameter record violates an integrity rule."""


@dataclass(frozen=True)
class Parameter:
    """One versioned model parameter, with its provenance.

    Invariants checked in ``__post_init__``:

    * an ``unknown`` parameter carries no value and a reason;
    * ``reported``/``fitted``/``assumed`` carry a source reference or a stated
      purpose, so a number can never appear without saying where it came from;
    * a value carries a registered unit for its :class:`QuantityKind`;
    * ``fitted`` records carry the fitting procedure.
    """

    symbol: str
    label: str
    kind: QuantityKind
    provenance: Provenance
    unit: str
    value: float | None = None
    source: SourceRef | None = None
    note: str = ""
    conversion: str = ""
    """Any unit conversion applied to obtain `value`, stated in words."""
    fitting: str = ""
    """For FITTED parameters: how the authors obtained the number."""
    missing_reason: str = ""
    """For UNKNOWN parameters: why no value is available."""

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ParameterError("a parameter needs a symbol")
        if self.provenance is Provenance.UNKNOWN:
            if self.value is not None:
                raise ParameterError(
                    f"{self.symbol}: provenance is 'unknown' so value must be "
                    f"None; refusing to fabricate a default"
                )
            if not self.missing_reason:
                raise ParameterError(
                    f"{self.symbol}: an unknown parameter must say why it is unknown"
                )
            return
        if self.value is None:
            raise ParameterError(f"{self.symbol}: a known parameter needs a value")
        # A unit must exist *for this quantity*. `g/L` is registered for a
        # concentration and for the saturation constant, and `%` for two
        # different things; accepting a unit that merely exists somewhere would
        # let Ko,1 = 0.326 g/L through.
        from .units import UnitError, unit as lookup_unit

        try:
            lookup_unit(self.kind, self.unit)
        except UnitError as exc:
            raise ParameterError(
                f"{self.symbol}: unit {self.unit!r} is not registered for "
                f"{self.kind.value}: {exc}"
            ) from None
        if self.provenance in (
            Provenance.REPORTED, Provenance.FITTED, Provenance.ASSUMED
        ) and self.source is None:
            raise ParameterError(
                f"{self.symbol}: provenance is {self.provenance.value!r} so it "
                f"must cite where it came from"
            )
        if self.provenance is Provenance.FITTED and not self.fitting:
            raise ParameterError(
                f"{self.symbol}: a fitted parameter must record the fitting "
                f"procedure"
            )
        if self.provenance is Provenance.DERIVED and not self.conversion:
            raise ParameterError(
                f"{self.symbol}: a derived parameter must state its calculation"
            )

    @property
    def basis(self) -> Basis:
        return _BASIS_BY_PROVENANCE[self.provenance]

    @property
    def is_observed(self) -> bool:
        """True for values read out of the paper, fitted or measured.

        Both are *reported by the authors*; they are not computations this
        model performed. Which of the two it is stays visible on the record.
        """
        return self.basis is Basis.OBSERVED

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "label": self.label,
            "kind": self.kind.value,
            "provenance": self.provenance.value,
            "basis": self.basis.value,
            "unit": self.unit,
            "value": self.value,
            "source": self.source.to_dict() if self.source else None,
            "conversion": self.conversion,
            "fitting": self.fitting,
            "missing_reason": self.missing_reason,
            "note": self.note,
        }


@dataclass(frozen=True)
class Observation:
    """A reported experimental result, kept apart from model output.

    Used for the paper's measured outcomes (20.7 g DCW/L), its model
    predictions (19.44 g DCW/L) and the optimisation decision (17.5% / 24.5% /
    0.72 mL/h). None of these is ever returned by the simulator: they are
    reference records with their own provenance, so that a test cannot pass by
    returning a paper number as a computed result.
    """

    observation_id: str
    label: str
    kind: QuantityKind
    unit: str
    provenance: Provenance
    value: float | None
    value_range: tuple[float, float] | None = None
    source: SourceRef | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.value is None and self.value_range is None:
            raise ParameterError(f"{self.observation_id}: no value or range")
        if self.value is not None and self.value_range is not None:
            raise ParameterError(
                f"{self.observation_id}: holds either a value or a range, never both"
            )
        if self.source is None:
            raise ParameterError(
                f"{self.observation_id}: a reported observation must cite its source"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "label": self.label,
            "kind": self.kind.value,
            "unit": self.unit,
            "provenance": self.provenance.value,
            "basis": _BASIS_BY_PROVENANCE[self.provenance].value,
            "value": self.value,
            "value_range": list(self.value_range) if self.value_range else None,
            "source": self.source.to_dict(),
            "note": self.note,
        }


@dataclass(frozen=True)
class TranscriptionNote:
    """A point where the printed model needed a decision recorded.

    These exist because the paper's text is not a specification: where a symbol
    is mistyped, a denominator is ambiguous, or a unit is implied, the reading
    taken is written down here instead of being silently absorbed into code.
    """

    note_id: str
    statement: str
    decision: str
    affected_equations: tuple[str, ...]
    source: SourceRef
    unresolved: bool = False
    review_question: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "note_id": self.note_id,
            "statement": self.statement,
            "decision": self.decision,
            "affected_equations": list(self.affected_equations),
            "source": self.source.to_dict(),
            "unresolved": self.unresolved,
            "review_question": self.review_question,
        }


@dataclass(frozen=True)
class SimulationProvenance:
    """Everything needed to reproduce one run, recorded with its result.

    Holds the parameter set, the initial conditions, the solver configuration,
    the equations version, the feed program, and a digest over all of it. The
    digest is over the canonical JSON of the run inputs, so two runs that
    declare the same inputs have the same digest and cannot be confused.
    """

    model_id: str
    model_version: str
    equations_version: str
    source_id: str
    parameters: dict[str, Any]
    initial_conditions: dict[str, Any]
    feed: dict[str, Any]
    solver: dict[str, Any]
    initial_condition_provenance: Mapping[str, Any] = field(default_factory=dict)
    input_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "equations_version": self.equations_version,
            "source_id": self.source_id,
            "parameters": self.parameters,
            "initial_conditions": self.initial_conditions,
            "feed": self.feed,
            "solver": self.solver,
            "initial_condition_provenance": dict(self.initial_condition_provenance),
            "input_digest": self.input_digest,
        }