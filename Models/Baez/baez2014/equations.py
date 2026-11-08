"""The equations this package is allowed to run.

There is exactly one, and it is printed in the paper. Everything the process
would need in order to be *predictive* -- a growth law, a dissolved-oxygen
balance, an oxygen-transfer correlation, a product-expression model, a
fluorescence calibration, a digitised trajectory, a link to the other model
packages in this repository -- is declared in `MISSING_MODELS` and not
implemented. Declaring an absence is the point: it is what stops a caller from
mistaking a missing model for a zero.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from . import source
from .units import Dimension


class EquationError(ValueError):
    """Raised when an equation is asked for something it cannot do."""


@dataclass(frozen=True)
class EquationInput:
    key: str
    label: str
    unit: str
    dimension: Dimension
    origin: str
    """Either "reported_parameter" (the paper prints its value) or
    "required_run_input" (the paper does not print a value, so the caller must
    supply one for a particular run)."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "unit": self.unit,
            "dimension": self.dimension.value,
            "origin": self.origin,
        }


@dataclass(frozen=True)
class Equation:
    equation_id: str
    label: str
    statement: str
    printed_expression: str
    inputs: tuple[EquationInput, ...]
    output_key: str
    output_unit: str
    #: arithmetic; receives a mapping of input key -> value already in `unit`
    fn: Callable[[Mapping[str, float]], float]
    source_reference: str
    printed_page: int
    notes: str = ""

    def __post_init__(self) -> None:
        if not source.FIRST_PRINTED_PAGE <= self.printed_page <= source.PAGE_COUNT:
            raise EquationError(
                f"{self.equation_id}: printed page {self.printed_page} is outside "
                f"the article"
            )

    @property
    def required_run_inputs(self) -> tuple[str, ...]:
        return tuple(i.key for i in self.inputs if i.origin == "required_run_input")

    @property
    def reported_parameters(self) -> tuple[str, ...]:
        return tuple(i.key for i in self.inputs if i.origin == "reported_parameter")

    def evaluate(self, values: Mapping[str, float]) -> float:
        missing = [i.key for i in self.inputs if i.key not in values]
        if missing:
            raise EquationError(
                f"{self.equation_id} is missing required inputs: {missing}"
            )
        return float(self.fn(values))

    def to_dict(self) -> dict[str, Any]:
        return {
            "equation_id": self.equation_id,
            "label": self.label,
            "statement": self.statement,
            "printed_expression": self.printed_expression,
            "inputs": [i.to_dict() for i in self.inputs],
            "output_key": self.output_key,
            "output_unit": self.output_unit,
            "source_reference": self.source_reference,
            "printed_page": self.printed_page,
            "required_run_inputs": list(self.required_run_inputs),
            "reported_parameters": list(self.reported_parameters),
            "notes": self.notes,
        }


def _exponential_feed_rate(values: Mapping[str, float]) -> float:
    """F(t) = ((mu_set / Y_XS) + m) * (X_F * V_F / S_F) * exp(mu_set*(t - t_F)).

    Written in the order the paper prints it: the specific substrate uptake
    term, the biomass demand at fed-batch onset, then the exponential.
    """
    uptake = values["mu_set"] / values["Y_XS"] + values["m"]
    demand = values["X_F"] * values["V_F"] / values["S_F"]
    elapsed = values["t"] - values["t_F"]
    return uptake * demand * math.exp(values["mu_set"] * elapsed)


#: The printed fragment that the test suite looks for on the cited page.
PRINTED_FRAGMENT = "F(t) = feed rate (L/h)"

EQUATIONS: dict[str, Equation] = {}


def _register(equation: Equation) -> Equation:
    if equation.equation_id in EQUATIONS:
        raise EquationError(f"duplicate equation id {equation.equation_id!r}")
    EQUATIONS[equation.equation_id] = equation
    return equation


_register(
    Equation(
        equation_id="source_formula.exponential_feed_rate",
        label="Exponential fed-batch feed rate",
        statement="F(t) = (mu_set/Y_XS + m) * (X_F*V_F/S_F) * exp(mu_set*(t - t_F))",
        printed_expression=(
            "F(t) = ((mu_set / Y_XS) + m) * (X_F * V_F / S_F) * "
            "e^(mu_set*(t - t_F))"
        ),
        inputs=(
            EquationInput("mu_set", "specific growth rate set by the feed",
                          "1/h", Dimension.SPECIFIC_RATE, "reported_parameter"),
            EquationInput("Y_XS", "biomass yield on glucose", "g/g",
                          Dimension.MASS_RATIO, "reported_parameter"),
            EquationInput("m", "maintenance coefficient", "g/(g h)",
                          Dimension.SPECIFIC_RATE, "reported_parameter"),
            EquationInput("X_F", "biomass concentration at fed-batch onset", "g/L",
                          Dimension.MASS_CONCENTRATION, "required_run_input"),
            EquationInput("V_F", "volume at fed-batch onset", "L",
                          Dimension.VOLUME, "required_run_input"),
            EquationInput("S_F", "glucose concentration in the feed solution", "g/L",
                          Dimension.MASS_CONCENTRATION, "reported_parameter"),
            EquationInput("t_F", "fed-batch start time", "h",
                          Dimension.TIME, "required_run_input"),
            EquationInput("t", "evaluation time", "h",
                          Dimension.TIME, "required_run_input"),
        ),
        output_key="feed_rate",
        output_unit="L/h",
        fn=_exponential_feed_rate,
        source_reference=source.reference(6, section="Methods: fed-batch culture"),
        printed_page=6,
        notes=(
            "Reproduced as printed on p. 6. The pre-exponential factor "
            "(mu_set/Y_XS + m) * (X_F*V_F/S_F) has units of L/h: the uptake "
            "term is 1/h and the demand term is L, so the output is a volume "
            "rate in the printed unit with no conversion factor applied. "
            "X_F, V_F and t_F are required inputs because the paper prints no "
            "value for them; it defines them, and it prints 4 L as the initial "
            "*batch* volume, which is not the volume at fed-batch onset."
        ),
    )
)


@dataclass(frozen=True)
class MissingModel:
    """A model this process would need in order to predict, and does not have."""

    model_id: str
    label: str
    why_needed: str
    missing_inputs: tuple[str, ...]
    why_not_implemented: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "label": self.label,
            "why_needed": self.why_needed,
            "missing_inputs": list(self.missing_inputs),
            "why_not_implemented": self.why_not_implemented,
        }


MISSING_MODELS: dict[str, MissingModel] = {
    m.model_id: m
    for m in (
        MissingModel(
            model_id="kinetics.growth_law",
            label="Growth rate as a function of dissolved oxygen",
            why_needed=(
                "To predict growth at any dissolved oxygen other than the two "
                "the paper reports, or between them."
            ),
            missing_inputs=(
                "a functional form relating dO2 to growth",
                "more than two dissolved-oxygen levels with growth rates",
                "half-saturation or oxygen-limitation constant",
            ),
            why_not_implemented=(
                "The paper reports two batch points, 1.08/h at 30% and 1.00/h "
                "at 300% air saturation (p. 2), and states that the difference "
                "is not significant (p = 0.05). Two points do not define a "
                "function, and a Monod form is not printed. Both observations "
                "are stored as observations; nothing is fitted to them."
            ),
        ),
        MissingModel(
            model_id="kinetics.dissolved_oxygen_balance",
            label="Dissolved-oxygen differential equation",
            why_needed=(
                "To predict the dissolved-oxygen trajectory that a feed rate "
                "would have to satisfy."
            ),
            missing_inputs=(
                "gas-liquid interfacial area",
                "oxygen solubility",
                "gas composition",
                "inlet and outlet gas flow",
                "initial dissolved oxygen",
            ),
            why_not_implemented=(
                "The paper prints a feed equation, not a gas-balance. No "
                "dissolved-oxygen differential equation appears anywhere in it, "
                "so one would be invented rather than transcribed."
            ),
        ),
        MissingModel(
            model_id="transfer.oxygen_uptake",
            label="Oxygen-transfer / oxygen-uptake correlation",
            why_needed=(
                "To relate the dissolved-oxygen set point to an oxygen demand "
                "and to say whether the culture was oxygen limited."
            ),
            missing_inputs=("kLa", "OUR or OTR", "agitation or gas-flow regime as a function"),
            why_not_implemented=(
                "The paper prints the gas rate and agitation speed (0.075 vvm, "
                "100 rpm, p. 6) but no transfer coefficient and no uptake rate. "
                "A correlation fitted to two growth points would be a fitted "
                "model, not a sourced one."
            ),
        ),
        MissingModel(
            model_id="expression.gfp_kinetics",
            label="Kinetic model of GFP expression",
            why_needed=(
                "To predict GFP concentration or fluorescence at a time other "
                "than the reported endpoints."
            ),
            missing_inputs=(
                "transcription and translation rate constants",
                "mRNA and protein degradation rates",
                "induction delay",
            ),
            why_not_implemented=(
                "The paper reports endpoint readings and says the system is "
                "'dynamically responsive' (p. 4), with no rate constant printed."
            ),
        ),
        MissingModel(
            model_id="calibration.fluorescence_to_gfp_mass",
            label="Conversion between fluorescence and GFP mass",
            why_needed=(
                "To turn a fluorescence reading into a GFP concentration, or "
                "the reverse."
            ),
            missing_inputs=(
                "instrument and plate format",
                "dilution basis",
                "a specific activity valid for these cultures",
            ),
            why_not_implemented=(
                "The paper prints both readings side by side (109000 FU and "
                "494 mg/L on p. 3) and also prints specific activities for other "
                "experiments, but it states no conversion for this fed-batch "
                "endpoint. Both values are stored separately, in their own "
                "units, with no factor between them. FU has its own dimension "
                "in `units.py` and cannot be converted to a mass."
            ),
        ),
        MissingModel(
            model_id="data.digitised_trajectory",
            label="Digitised time series",
            why_needed=(
                "To evaluate the process over time rather than at the reported "
                "endpoints."
            ),
            missing_inputs=(
                "digitised coordinates",
                "the axes they were read from",
                "the read-off uncertainty",
            ),
            why_not_implemented=(
                "No dataset defining coordinates and digitisation provenance "
                "has been supplied. Figures 1B and 4A/4B are referenced by the "
                "paper but are not transcribed here, so there is nothing to "
                "digitise."
            ),
        ),
        MissingModel(
            model_id="coupling.other_models",
            label="Coupling to the Morris or Zielinski models",
            why_needed=(
                "To run this package inside the composition layer alongside the "
                "other models in this repository."
            ),
            missing_inputs=(
                "a model id and version agreed with the composition layer",
                "a shared component identity",
                "a declared port set",
            ),
            why_not_implemented=(
                "Coupling is out of scope for this package, and nothing in the "
                "paper supplies the bridge: there is no shared component "
                "vocabulary, and the register, feed and product quantities here "
                "have no counterpart in either model. No identifier is guessed "
                "and no adapter is registered."
            ),
        ),
    )
}


def equation(equation_id: str) -> Equation:
    try:
        return EQUATIONS[equation_id]
    except KeyError:
        raise KeyError(f"unknown equation {equation_id!r}") from None


def executable_equations() -> tuple[Equation, ...]:
    return tuple(EQUATIONS.values())