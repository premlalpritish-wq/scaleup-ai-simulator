"""ScaleUp AI core: the registry of equations the engine is allowed to run.

Two kinds of object live here:

  * `Equation` - a transparent, executable identity. Each one names its inputs,
    its output unit, and the arithmetic in plain text. An equation is either
    executable or it is not; there is no partial evaluation.

  * `MissingModel` - a model the paper's process would need in order to be
    *predictive*. These are declared, never implemented. Registering them is
    what lets the engine fail closed with a precise reason instead of either
    inventing the model or returning a silent zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .provenance import Provenance


class UnresolvedPointValue(Exception):
    """Raised when an equation needs a point value but only a range exists."""

    def __init__(self, quantity_id: str, value_range: tuple[float, float]) -> None:
        super().__init__(
            f"{quantity_id} is reported as a range {value_range}; collapsing it to a "
            f"point value would be an undeclared assumption"
        )
        self.quantity_id = quantity_id
        self.value_range = value_range


class AmbiguousEquation(Exception):
    """Raised when an equation is requested that refuses to be evaluated."""


# --------------------------------------------------------------------------- #
# definitions
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class EquationInput:
    key: str
    label: str
    unit: str


@dataclass(frozen=True)
class Equation:
    equation_id: str
    label: str
    statement: str
    inputs: tuple[EquationInput, ...]
    output_key: str
    output_unit: str
    #: arithmetic; receives a mapping of input key -> value already in `unit`
    fn: Callable[[Mapping[str, float]], float] | None
    executable: bool
    ambiguity: str | None = None
    provenance: Provenance = Provenance.DERIVED
    #: may this equation be evaluated in PREDICTIVE mode from declared inputs?
    predictive_capable: bool = True
    #: true when the equation reproduces a formula printed verbatim in the paper
    from_source_formula: bool = False
    source_reference: str | None = None
    notes: str = ""
    #: optional first-order uncertainty propagation. Receives
    #: (value, half-width) per input key and returns the output half-width.
    #: When absent, a derived quantity carries no uncertainty and therefore
    #: supports no claim of statistical significance.
    uncertainty_fn: Callable[[Mapping[str, tuple[float, float]]], float] | None = None

    def __post_init__(self) -> None:
        if self.executable and self.fn is None:
            raise ValueError(f"{self.equation_id} is executable but has no fn")
        if not self.executable and self.fn is not None:
            raise ValueError(f"{self.equation_id} is not executable but supplies an fn")
        if not self.executable and not self.ambiguity:
            raise ValueError(f"{self.equation_id} must state why it is not executable")

    def evaluate(self, values: Mapping[str, float]) -> float:
        if not self.executable or self.fn is None:
            raise AmbiguousEquation(
                f"{self.equation_id} refuses to evaluate: {self.ambiguity}"
            )
        missing = [i.key for i in self.inputs if i.key not in values]
        if missing:
            raise KeyError(f"{self.equation_id} missing inputs: {missing}")
        return float(self.fn(values))

    def propagate(self, values: Mapping[str, float], halfwidths: Mapping[str, float]) -> float | None:
        """First-order uncertainty of the output, or None when not declared."""
        if self.uncertainty_fn is None:
            return None
        if any(self.inputs and i.key not in halfwidths for i in self.inputs):
            return None
        try:
            return float(self.uncertainty_fn({k: (v, halfwidths[k]) for k, v in values.items()}))
        except ZeroDivisionError:
            return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "equation_id": self.equation_id,
            "label": self.label,
            "statement": self.statement,
            "inputs": [
                {"key": i.key, "label": i.label, "unit": i.unit} for i in self.inputs
            ],
            "output_key": self.output_key,
            "output_unit": self.output_unit,
            "executable": self.executable,
            "ambiguity": self.ambiguity,
            "predictive_capable": self.predictive_capable,
            "from_source_formula": self.from_source_formula,
            "source_reference": self.source_reference,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class MissingModel:
    """A model that would be required for a prediction, and is not implemented."""

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


# --------------------------------------------------------------------------- #
# arithmetic
# --------------------------------------------------------------------------- #


def _mass_per_volume(values: Mapping[str, float]) -> float:
    return values["total_mass"] / values["volume"]


def _mass_fraction(values: Mapping[str, float]) -> float:
    return values["part_mass"] / values["total_mass"]


def _multiply(values: Mapping[str, float]) -> float:
    return values["a"] * values["b"]


def _sum(values: Mapping[str, float]) -> float:
    return values["a"] + values["b"]


def _diluted(values: Mapping[str, float]) -> float:
    return values["volume"] * values["factor"]


def _total_activity(values: Mapping[str, float]) -> float:
    return values["activity_per_volume"] * values["volume"]


def _volume_times_concentration(values: Mapping[str, float]) -> float:
    # AU = (AU/mL) * mL. Deliberately NOT convertible to mass, molarity or IU.
    return values["volume_ml"] * values["concentration_au_per_ml"]


def _zinc_chloride_from_volume(values: Mapping[str, float]) -> float:
    """Paper formula: 2 x V[cm3] / 100  ->  mL of 1 M ZnCl2."""
    return 2.0 * values["volume_ml"] / 100.0


def _aprotinin_from_trypsin(values: Mapping[str, float]) -> float:
    """Paper formula: V[trypsin] / 21  ->  uL of 1 mg/mL aprotinin."""
    return values["trypsin_volume_ul"] / 21.0


def _edta_from_deae_au(values: Mapping[str, float]) -> float:
    """Paper formula: total protein after DEAE / 190  ->  mL of 0.2 M EDTA."""
    return values["deae_total_au"] / 190.0


def _water_volume_from_deae_au(values: Mapping[str, float]) -> float:
    """Paper formula: total protein after DEAE / 7  ->  mL of water."""
    return values["deae_total_au"] / 7.0


def _cpb_from_au(values: Mapping[str, float]) -> float:
    """Paper formula: 10 uL per 150 AU  ->  uL of 2.5 mg/mL carboxypeptidase B."""
    return values["main_fraction_au"] * 10.0 / 150.0


def _stock_volume_for_target(values: Mapping[str, float]) -> float:
    """Ordinary dilution arithmetic C1V1 = C2V2, used only to cross-check the
    reported stock additions against reported volumes."""
    return values["target_concentration"] * values["final_volume"] / values["stock_concentration"]


def _mass_deviation(values: Mapping[str, float]) -> float:
    return values["measured_da"] - values["theoretical_da"]


def _relative_deviation_ppm(values: Mapping[str, float]) -> float:
    return (
        (values["measured_da"] - values["theoretical_da"])
        / values["theoretical_da"]
        * 1.0e6
    )


def _tris_molarity(values: Mapping[str, float]) -> float:
    """Resulting Tris concentration in mM after adding a stock volume."""
    return values["stock_volume_ml"] * values["stock_concentration"] / values["final_volume"]


def _implied_final_volume(values: Mapping[str, float]) -> float:
    """The total volume implied by a stated stock addition and target concentration."""
    return (
        values["stock_concentration"] * values["stock_volume"] / values["target_concentration"]
    )


def _percent_yield_from_au(values: Mapping[str, float]) -> float:
    """Percent yield computed from absorbance units.

    AU-based by construction: this is an absorbance ratio, not a mass or
    activity recovery.
    """
    return values["after_au"] / values["before_au"] * 100.0


# --- first-order uncertainty propagation -------------------------------------
#
# Each helper receives {key: (value, half-width)} and returns the output
# half-width using the standard linear combination rule. They are attached only
# to equations whose algebra supports the rule unambiguously, and only when
# every input actually carries an uncertainty.


def _unc_product(v: Mapping[str, tuple[float, float]]) -> float:
    """y = prod(x_i): relative half-widths add, then scale by |y|."""
    product = 1.0
    relative = 0.0
    for value, half in v.values():
        if value == 0:
            raise ZeroDivisionError("relative uncertainty of a zero-valued input")
        product *= value
        relative += half / abs(value)
    return abs(product) * relative


def _unc_quotient(num_key: str, den_key: str):
    """Build a propagator for y = x_num / x_den."""

    def propagate(v: Mapping[str, tuple[float, float]]) -> float:
        num, num_h = v[num_key]
        den, den_h = v[den_key]
        if den == 0:
            raise ZeroDivisionError("division by a zero-valued input")
        return abs(num_h / den) + abs(num * den_h / (den * den))

    return propagate


def _unc_difference(v: Mapping[str, tuple[float, float]]) -> float:
    """y = x1 - x2 (or x2 - x1): absolute half-widths add."""
    first, second = list(v.values())[:2]
    return abs(first[1]) + abs(second[1])


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #

EQUATIONS: dict[str, Equation] = {}


def _register(eq: Equation) -> Equation:
    if eq.equation_id in EQUATIONS:
        raise ValueError(f"duplicate equation id {eq.equation_id!r}")
    EQUATIONS[eq.equation_id] = eq
    return eq


# --- generic transparent accounting identities --------------------------------

_register(
    Equation(
        equation_id="accounting.mass_per_volume",
        label="Mass concentration from total mass and volume",
        statement="mass_per_volume = total_mass / volume",
        inputs=(
            EquationInput("total_mass", "total mass", "g"),
            EquationInput("volume", "volume", "L"),
        ),
        output_key="mass_per_volume",
        output_unit="g/L",
        fn=_mass_per_volume,
        executable=True,
        uncertainty_fn=_unc_quotient("total_mass", "volume"),
    )
)

_register(
    Equation(
        equation_id="absorbance.total_from_volume_and_concentration",
        label="Total absorbance units from volume and concentration",
        statement="total_AU = volume_mL * concentration_AU_per_mL",
        inputs=(
            EquationInput("volume_ml", "fraction volume", "mL"),
            EquationInput("concentration_au_per_ml", "A280 concentration", "AU/mL"),
        ),
        output_key="total_AU",
        output_unit="AU",
        fn=_volume_times_concentration,
        executable=True,
        uncertainty_fn=_unc_product,
        notes=(
            "Absorbance-based quantity only. The spectrophotometer was calibrated "
            "with water (no path length, no extinction coefficient), so AU cannot be "
            "converted to mass, molarity, activity or pure-insulin content."
        ),
    )
)

_register(
    Equation(
        equation_id="volume.diluted",
        label="Volume after a stated dilution factor",
        statement="V_diluted = V * factor",
        inputs=(
            EquationInput("volume", "starting volume", "mL"),
            EquationInput("factor", "dilution factor", "fold"),
        ),
        output_key="diluted_volume",
        output_unit="mL",
        fn=_diluted,
        executable=True,
    )
)

_register(
    Equation(
        equation_id="accounting.mass_fraction",
        label="Mass fraction of a part within a total",
        statement="fraction = part_mass / total_mass",
        inputs=(
            EquationInput("part_mass", "part mass", "g"),
            EquationInput("total_mass", "total mass", "g"),
        ),
        output_key="fraction",
        output_unit="1",
        fn=_mass_fraction,
        executable=True,
        uncertainty_fn=_unc_quotient("part_mass", "total_mass"),
        notes="Descriptive accounting ratio only; never a fitted model parameter.",
    )
)

_register(
    Equation(
        equation_id="volume.sum",
        label="Total volume of two reported additions",
        statement="V_total = V1 + V2",
        inputs=(
            EquationInput("a", "first volume", "mL"),
            EquationInput("b", "second volume", "mL"),
        ),
        output_key="total_volume",
        output_unit="mL",
        fn=_sum,
        executable=True,
    )
)

_register(
    Equation(
        equation_id="accounting.total_activity_from_per_volume",
        label="Batch activity from a reported per-litre average",
        statement="total_IU = IU_per_L * culture_volume_L",
        inputs=(
            EquationInput("activity_per_volume", "activity per litre of medium", "IU/L"),
            EquationInput("volume", "culture volume", "L"),
        ),
        output_key="total_activity",
        output_unit="IU",
        fn=_total_activity,
        executable=True,
        notes=(
            "Arithmetic restatement of a reported per-litre average over the reported "
            "culture volume. It assumes the published per-litre average applies to "
            "this 4 L batch and is not a validated scale-up prediction."
        ),
    )
)

# --- formulas printed verbatim in the paper ----------------------------------

_register(
    Equation(
        equation_id="source_formula.zinc_chloride_from_solution_volume",
        label="ZnCl2 amount from sample volume (sec. 2.12)",
        statement="V[ZnCl2 1 M] = 2 * V[solution, cm3] / 100",
        inputs=(EquationInput("volume_ml", "sample volume", "mL"),),
        output_key="zinc_chloride_volume",
        output_unit="mL",
        fn=_zinc_chloride_from_volume,
        executable=True,
        from_source_formula=True,
        source_reference="Zielinski et al. 2019, sec. 2.12, p.65",
        notes="cm3 and mL are the same volume; the printed formula is dimensionally sound.",
    )
)

_register(
    Equation(
        equation_id="source_formula.aprotinin_from_trypsin_volume",
        label="Aprotinin amount from trypsin volume (sec. 2.9)",
        statement="V[aprotinin] = V[trypsin] / 21",
        inputs=(EquationInput("trypsin_volume_ul", "1% trypsin volume", "uL"),),
        output_key="aprotinin_volume",
        output_unit="uL",
        fn=_aprotinin_from_trypsin,
        executable=True,
        from_source_formula=True,
        source_reference="Zielinski et al. 2019, sec. 2.9, p.65",
        notes=(
            "Dimensionally sound provided V[trypsin] is a volume in the same unit; "
            "the paper reports 70 uL of 1% trypsin for the reference batch."
        ),
    )
)

_register(
    Equation(
        equation_id="source_formula.edta_from_deae_protein",
        label="EDTA amount from post-DEAE protein (sec. 2.13)",
        statement="V[EDTA 0.2 M] = total_protein_after_DEAE / 190",
        inputs=(EquationInput("deae_total_au", "post-DEAE total protein", "AU"),),
        output_key="edta_volume",
        output_unit="mL",
        fn=_edta_from_deae_au,
        executable=True,
        from_source_formula=True,
        source_reference="Zielinski et al. 2019, sec. 2.13, p.65",
        notes="The divisor carries the AU-per-mL-equivalent scale; reproduced as printed.",
    )
)

_register(
    Equation(
        equation_id="source_formula.water_volume_from_deae_protein",
        label="Water volume from post-DEAE protein (sec. 2.13)",
        statement="V[water] = total_protein_after_DEAE / 7",
        inputs=(EquationInput("deae_total_au", "post-DEAE total protein", "AU"),),
        output_key="water_volume",
        output_unit="mL",
        fn=_water_volume_from_deae_au,
        executable=True,
        from_source_formula=True,
        source_reference="Zielinski et al. 2019, sec. 2.13, p.65",
        notes=(
            "Executable as printed, but the paper reports 285 mL of water in sec. 4.9 "
            "while this formula yields 306.07 mL from the reported DEAE AU. The "
            "engine computes both and reports the contradiction; it does not choose."
        ),
    )
)

_register(
    Equation(
        equation_id="source_formula.cpb_from_au",
        label="Carboxypeptidase B volume from main-fraction AU (sec. 2.15)",
        statement="V[CPB] = AU_main_fraction * 10 uL / 150 AU",
        inputs=(EquationInput("main_fraction_au", "main fraction total protein", "AU"),),
        output_key="cpb_volume",
        output_unit="uL",
        fn=_cpb_from_au,
        executable=True,
        from_source_formula=True,
        source_reference="Zielinski et al. 2019, sec. 2.15, p.65",
    )
)

_register(
    Equation(
        equation_id="accounting.stock_volume_for_target_concentration",
        label="Stock volume needed to reach a target concentration",
        statement="V1 = C2 * V2 / C1",
        inputs=(
            EquationInput("target_concentration", "target concentration", "mM"),
            EquationInput("stock_concentration", "stock concentration", "mM"),
            EquationInput("final_volume", "final volume", "mL"),
        ),
        output_key="stock_volume",
        output_unit="mL",
        fn=_stock_volume_for_target,
        executable=True,
        notes="Ordinary dilution arithmetic, used only to cross-check reported additions.",
    )
)

_register(
    Equation(
        equation_id="accounting.tris_molarity_after_dilution",
        label="Tris molarity after adding stock to a reported volume",
        statement="C_final = C_stock * V1 / V2",
        inputs=(
            EquationInput("stock_volume_ml", "stock volume added", "mL"),
            EquationInput("stock_concentration", "stock concentration", "mM"),
            EquationInput("final_volume", "final volume", "mL"),
        ),
        output_key="tris_concentration",
        output_unit="mM",
        fn=_tris_molarity,
        executable=True,
    )
)

# --- formulas the implementation refuses to run ------------------------------

_register(
    Equation(
        equation_id="source_formula.citraconylation_anhydride_amount",
        label="Citraconic anhydride amount (sec. 2.8)",
        statement="V[citraconic anhydride] = 0.2 * V[solution, dm3] * A280nm",
        inputs=(
            EquationInput("solution_volume_dm3", "solution volume", "dm3"),
            EquationInput("a280", "A280", "1"),
        ),
        output_key="citraconic_anhydride_volume",
        output_unit="mL",
        fn=None,
        executable=False,
        ambiguity=(
            "A280nm is a raw absorbance (dimensionless, instrument- and "
            "path-length dependent) while the rest of the paper reports AU "
            "(absorbance x volume). The paper gives neither the A280 value nor the "
            "path length (sec. 2.18: the spectrophotometer was calibrated with "
            "water). '0.2 * dm3 * absorbance' does not reduce to a volume, so the "
            "dimensional interpretation is unresolved."
        ),
        source_reference="Zielinski et al. 2019, sec. 2.8, p.64-65",
    )
)

_register(
    Equation(
        equation_id="source_formula.trypsin_amount",
        label="Trypsin amount (sec. 2.9)",
        statement="V[1% trypsin] = A280nm * V[solution, dm3] / 75",
        inputs=(
            EquationInput("a280", "A280", "1"),
            EquationInput("solution_volume_dm3", "solution volume", "dm3"),
        ),
        output_key="trypsin_volume",
        output_unit="uL",
        fn=None,
        executable=False,
        ambiguity=(
            "Same A280-vs-AU and path-length ambiguity as the citraconylation "
            "formula; the divisor 75 carries no stated unit. The paper separately "
            "reports an absolute 70 uL of 1% trypsin for the reference batch."
        ),
        source_reference="Zielinski et al. 2019, sec. 2.9, p.65",
    )
)

_register(
    Equation(
        equation_id="source_formula.ethanolamine_amount",
        label="Ethanolamine amount (sec. 2.8)",
        statement="V[2 M ethanolamine] = 3 * V[citraconic anhydride]",
        inputs=(
            EquationInput("citraconic_anhydride_volume", "anhydride volume", "mL"),
        ),
        output_key="ethanolamine_volume",
        output_unit="mL",
        fn=None,
        executable=False,
        ambiguity=(
            "Blocked upstream: V[citraconic anhydride] cannot be computed because "
            "source_formula.citraconylation_anhydride_amount is not executable. "
            "The paper separately reports an absolute 3 mL of 2 M ethanolamine."
        ),
        source_reference="Zielinski et al. 2019, sec. 2.8, p.65",
    )
)

# --- characterization ---------------------------------------------------------

_register(
    Equation(
        equation_id="accounting.implied_final_volume",
        label="Final volume implied by a stock addition and a target concentration",
        statement="V2 = C1 * V1 / C2",
        inputs=(
            EquationInput("stock_concentration", "stock concentration", "mM"),
            EquationInput("stock_volume", "stock volume added", "mL"),
            EquationInput("target_concentration", "stated target concentration", "mM"),
        ),
        output_key="implied_final_volume",
        output_unit="mL",
        fn=_implied_final_volume,
        executable=True,
        notes=(
            "Diagnostic inverse of a reported stock addition: it reveals which total "
            "volume the paper's own numbers are consistent with."
        ),
    )
)

_register(
    Equation(
        equation_id="accounting.percent_yield_from_au",
        label="Percent yield computed from absorbance units",
        statement="yield_pct = total_AU_after / total_AU_before * 100",
        inputs=(
            EquationInput("before_au", "AU before the step", "AU"),
            EquationInput("after_au", "AU after the step", "AU"),
        ),
        output_key="percent_yield",
        output_unit="%",
        fn=_percent_yield_from_au,
        executable=True,
        uncertainty_fn=_unc_quotient("after_au", "before_au"),
        notes=(
            "Absorbance-based ratio only. The 280 nm detector was blanked with water "
            "and the AU basis differs between stages, so this is not a mass yield "
            "and must not be quoted as a purification recovery."
        ),
    )
)


# --------------------------------------------------------------------------- #
# characterization
# --------------------------------------------------------------------------- #

_register(
    Equation(
        equation_id="characterization.mass_deviation",
        label="Absolute deviation of measured from theoretical mass",
        statement="delta = measured_da - theoretical_da",
        inputs=(
            EquationInput("measured_da", "measured mass", "Da"),
            EquationInput("theoretical_da", "theoretical mass", "Da"),
        ),
        output_key="mass_deviation",
        output_unit="Da",
        fn=_mass_deviation,
        executable=True,
        uncertainty_fn=_unc_difference,
    )
)

_register(
    Equation(
        equation_id="characterization.relative_mass_deviation_ppm",
        label="Relative deviation of measured from theoretical mass",
        statement="deviation_ppm = (measured_da - theoretical_da) / theoretical_da * 1e6",
        inputs=(
            EquationInput("measured_da", "measured mass", "Da"),
            EquationInput("theoretical_da", "theoretical mass", "Da"),
        ),
        output_key="relative_mass_deviation",
        output_unit="1",
        fn=_relative_deviation_ppm,
        executable=True,
        notes="Unit is parts-per-million by convention.",
    )
)


# --------------------------------------------------------------------------- #
# models that are deliberately absent
# --------------------------------------------------------------------------- #

MISSING_MODELS: dict[str, MissingModel] = {
    m.model_id: m
    for m in (
        MissingModel(
            model_id="kinetics.growth_ode",
            label="Biomass growth differential equation",
            why_needed="To predict OD600 or biomass from medium composition and feed rates.",
            missing_inputs=(
                "specific growth rate mu_max",
                "Monod saturation constant Ks",
                "maintenance coefficient",
                "oxygen limitation onset",
            ),
            why_not_implemented=(
                "The paper reports no kinetic parameters, no mu_max, no Ks and no "
                "oxygen-transfer data. Fitting a curve to the single Fig. 3 batch "
                "would be a fitted mechanistic model, not a sourced one."
            ),
        ),
        MissingModel(
            model_id="kinetics.monod_substrate",
            label="Monod substrate uptake",
            why_needed="To predict glucose consumption and feed volume from pH-stat control.",
            missing_inputs=("Ks", "Yx/s", "feed pump rate", "pH-stat dead-band response"),
            why_not_implemented=(
                "The paper gives only the controlled concentration ranges "
                "(70-120 and 30-50 mg/dL), never the feed rate or saturation "
                "constants needed to solve an uptake model."
            ),
        ),
        MissingModel(
            model_id="transfer.oxygen_kla",
            label="Oxygen transfer (kLa)",
            why_needed="To predict dissolved oxygen and whether growth is oxygen limited.",
            missing_inputs=("kLa", "air flow rate", "agitator speed", "vvm", "DO probe data"),
            why_not_implemented=(
                "No gas-flow, agitation or dissolved-oxygen data appear anywhere in "
                "the paper. CFD/mixing/heat-transfer simulation is out of scope."
            ),
        ),
        MissingModel(
            model_id="folding.renaturation_kinetics",
            label="Renaturation folding kinetics",
            why_needed="To predict refolding yield or time from temperature, pH or redox.",
            missing_inputs=(
                "rate constant",
                "redox potential",
                "folding equilibrium",
                "aggregate fraction",
            ),
            why_not_implemented=(
                "The paper explicitly reports that refolding 'was shown to depend on "
                "the redox potential and the pH value, but not on the temperature' "
                "(sec. 4.5), which contradicts reading temperature as the causal "
                "predictor. Two yields at two temperatures are not a yield function."
            ),
        ),
        MissingModel(
            model_id="calibration.au_to_mass",
            label="AU to protein mass calibration",
            why_needed="To convert any AU measurement into grams or mg of protein.",
            missing_inputs=(
                "extinction coefficient epsilon280",
                "cuvette path length",
                "protein-specific A280 factor",
            ),
            why_not_implemented=(
                "sec. 2.18 states the spectrophotometer was calibrated with water. "
                "Without a path length and an extinction coefficient the absorbance "
                "scale is undefined, so every AU value is instrument-relative."
            ),
        ),
        MissingModel(
            model_id="recovery.stage_yield",
            label="Per-stage purification recovery",
            why_needed="To predict downstream yield from upstream AU or mass.",
            missing_inputs=(
                "AU-to-mass calibration",
                "stage protein composition",
                "binding/elution selectivity",
                "volume accounting basis per stage",
            ),
            why_not_implemented=(
                "Inventing recovery efficiencies is explicitly out of scope, and the "
                "AU basis differs between stages (total protein at 280 nm vs. the "
                "insulin-containing fraction), so an AU ratio is not a recovery."
            ),
        ),
        MissingModel(
            model_id="activity.iu_from_au",
            label="Biological activity from absorbance",
            why_needed="To convert the final AU stream into IU/L.",
            missing_inputs=("AU-to-mass calibration", "specific activity", "assay calibration"),
            why_not_implemented=(
                "The paper reports activity only as a retrospective average of "
                "2700 IU per litre of culture medium; it gives no relation between "
                "that figure and any absorbance measurement."
            ),
        ),
        MissingModel(
            model_id="scaleup.effect_of_scale",
            label="Scale-up correlation",
            why_needed="To project the 4 L laboratory result onto larger fermenters.",
            missing_inputs=(
                "kLa at scale",
                "pH-stat response at scale",
                "feed profile",
                "shear history",
            ),
            why_not_implemented=(
                "Out of scope by instruction, and unsupportable: the paper reports a "
                "single laboratory scale with no scale-down/up correlation."
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
    return tuple(e for e in EQUATIONS.values() if e.executable)


def refuses_to_run() -> tuple[Equation, ...]:
    return tuple(e for e in EQUATIONS.values() if not e.executable)