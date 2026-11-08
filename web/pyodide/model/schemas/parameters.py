"""The versioned parameter set from Table 2.

Loaded from ``data/reference_parameters.json`` rather than written as literals,
so the JSON is the auditable artefact and the code is the loader. Every value
carries its symbol, unit, semantic quantity, provenance and printed location;
none of them is invented here.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Mapping

from .provenance import Parameter, ParameterError, Provenance, SourceRef
from .units import QuantityKind, symbols_for, unit

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PARAMETER_FILE = DATA_DIR / "reference_parameters.json"

PARAMETER_SET_ID = "ganjave2022.table2"
PARAMETER_SET_VERSION = "1.0.0"

#: Version of the *equations as implemented*. Bumped to 1.1.0 when the
#: oxygen-consumption factor in eq. (11)/(15) was corrected from the product
#: reading to the printed quotient (see `EQUATION_CHANGES` and TN-04): the
#: parameter values are unchanged, but a run recorded under 1.0.0 integrated a
#: different oxygen equation, so the two must not be comparable.
EQUATIONS_VERSION = "1.1.0"

EQUATION_CHANGES: dict[str, str] = {
    "1.0.0": (
        "Initial transcription of eq. (1)-(16)."
    ),
    "1.1.0": (
        "eq. (11) and eq. (15): the oxygen-consumption factor is the printed "
        "quotient (100/C*), not the product (100*C*) that the PDF text layer "
        "suggests. Verified against a rendering of printed page 4 and against "
        "the unit algebra in models.dimensions. No parameter value changed."
    ),
}

#: Every symbol the model reads. Listed so a missing one is a load error rather
#: than an ``AttributeError`` halfway through a simulation.
REQUIRED_SYMBOLS = (
    "mum1", "mum2",
    "K11", "K12", "K22", "Ko1", "Ko2",
    "Y11", "Y12", "Y22", "Yo1", "Yo2",
    "e_ratio1_0", "e_ratio2_0",
    "beta1", "beta2",
    "kLa", "C_star",
)

#: Symbols that are reported for context but are not read by eq. (1)-(16).
INFORMATIONAL_SYMBOLS = ("of_minimum",)


class ParameterSet:
    """An immutable, versioned collection of parameters.

    Construction validates every record: the unit must be registered for that
    parameter's :class:`QuantityKind`, and every required symbol must be present
    with a value. A parameter set that fails either check cannot be built, so no
    simulation can start from a half-populated one.
    """

    __slots__ = ("_parameters", "parameter_set_id", "version", "equations_version", "source")

    def __init__(self, parameters: Mapping[str, Parameter], *, parameter_set_id: str,
                 version: str, equations_version: str, source: Mapping[str, Any]) -> None:
        self._parameters = dict(parameters)
        self.parameter_set_id = parameter_set_id
        self.version = version
        self.equations_version = equations_version
        self.source = dict(source)

    def __contains__(self, symbol: str) -> bool:
        return symbol in self._parameters

    def __len__(self) -> int:
        return len(self._parameters)

    def __iter__(self) -> Iterator[str]:
        return iter(self._parameters)

    def parameter(self, symbol: str) -> Parameter:
        try:
            return self._parameters[symbol]
        except KeyError:
            raise ParameterError(
                f"{symbol!r} is not in parameter set {self.parameter_set_id}; "
                f"it holds {sorted(self._parameters)}"
            ) from None

    def value(self, symbol: str) -> float:
        parameter = self.parameter(symbol)
        if parameter.value is None:
            raise ParameterError(
                f"{symbol}: no value ({parameter.provenance.value}: "
                f"{parameter.missing_reason})"
            )
        return float(parameter.value)

    @property
    def parameters(self) -> Mapping[str, Parameter]:
        return dict(self._parameters)

    def with_overrides(
        self,
        overrides: Mapping[str, float],
        *,
        reason: str,
    ) -> "ParameterSet":
        """A copy with some values replaced by a caller's, marked ``assumed``.

        `reason` is mandatory: an override that cannot say why it exists is not
        a what-if run, it is an unattributed edit. The original fitted value is
        kept in the note so the change is auditable from the result alone.
        """
        if not reason.strip():
            raise ParameterError("an override must state why it is being made")
        unknown = [s for s in overrides if s not in self._parameters]
        if unknown:
            raise ParameterError(
                f"cannot override unknown parameters {sorted(unknown)}"
            )
        replaced: dict[str, Parameter] = dict(self._parameters)
        for symbol, value in overrides.items():
            original = self._parameters[symbol]
            number = float(value)
            if not _finite(number):
                raise ParameterError(
                    f"{symbol}: override {value!r} is not a finite number"
                )
            replaced[symbol] = Parameter(
                symbol=original.symbol,
                label=original.label,
                kind=original.kind,
                provenance=Provenance.ASSUMED,
                unit=original.unit,
                value=number,
                source=original.source,
                fitting=original.fitting,
                conversion=original.conversion,
                note=(
                    f"overridden by the caller; the parameter set {self.parameter_set_id} "
                    f"prints {original.value!r}. Reason: {reason}"
                ),
            )
        return ParameterSet(
            replaced,
            parameter_set_id=self.parameter_set_id,
            version=self.version,
            equations_version=self.equations_version,
            source=self.source,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter_set_id": self.parameter_set_id,
            "version": self.version,
            "equations_version": self.equations_version,
            "source": self.source,
            "parameters": {s: p.to_dict() for s, p in sorted(self._parameters.items())},
        }


def _finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))


def _parameter_from_dict(payload: Mapping[str, Any]) -> Parameter:
    source_payload = payload.get("source")
    source = None
    if source_payload:
        source = SourceRef(
            section=source_payload["section"],
            locator=source_payload["locator"],
            printed_page=source_payload.get("printed_page"),
            quote=source_payload.get("quote"),
        )
    return Parameter(
        symbol=payload["symbol"],
        label=payload["label"],
        kind=QuantityKind(payload["kind"]),
        provenance=Provenance(payload["provenance"]),
        unit=payload["unit"],
        value=payload.get("value"),
        source=source,
        note=payload.get("note", ""),
        conversion=payload.get("conversion", ""),
        fitting=payload.get("fitting", ""),
        missing_reason=payload.get("missing_reason", ""),
    )


def _validate(parameter: Parameter) -> None:
    """A unit must exist for this parameter's quantity, not merely exist."""
    registered = symbols_for(parameter.kind)
    if parameter.unit not in registered:
        raise ParameterError(
            f"{parameter.symbol}: unit {parameter.unit!r} is not registered for "
            f"{parameter.kind.value}; registered there: {list(registered)}"
        )
    unit(parameter.kind, parameter.unit)


@lru_cache(maxsize=1)
def table2_parameter_set() -> ParameterSet:
    """The Table 2 parameter set, loaded and validated."""
    with PARAMETER_FILE.open("r", encoding="utf-8") as fh:
        document = json.load(fh)

    parameters = {
        payload["symbol"]: _parameter_from_dict(payload)
        for payload in document["parameters"]
    }
    missing = [s for s in REQUIRED_SYMBOLS if s not in parameters]
    if missing:
        raise ParameterError(
            f"parameter set {document['parameter_set_id']} is missing required "
            f"symbols: {missing}"
        )
    for parameter in parameters.values():
        _validate(parameter)
        if parameter.symbol in REQUIRED_SYMBOLS and parameter.value is None:
            raise ParameterError(
                f"{parameter.symbol}: a required parameter must carry a value"
            )

    return ParameterSet(
        parameters,
        parameter_set_id=document["parameter_set_id"],
        version=document["version"],
        equations_version=document["equations_version"],
        source=document["source"],
    )