"""Pirt's chemostat relation, equation (3), with this paper's fitted parameters.

The paper prints exactly one model equation for growth physiology -- Pirt's
chemostat model, printed as equation (3) on p. 1167:

    qglc = mu / Yglc_max + mglc                                            (3)

"where qglc is the specific rate of glucose consumption, mglc the maintenance
energy coefficient, and Yglc_max the maximum molar growth yield, i.e., the
biomass yield without maintenance-associated processes". The paper fits that
relation to its own mini-scale-chemostat data ("the maintenance coefficient ...
was determined by extrapolating the least-squares linear fit of the data to the
zero growth rate") and reports the fit in Table 1 (printed p. 1167): for
*E. coli* MG1655 at 37 degC, mglc = 0.37 +/- 0.09 mmol gdw-1 h-1 and
Yglc_max = 76 +/- 3 gdw mol-1.

This module implements that relation, in this paper's context, with this paper's
parameters. Two things are declared rather than hidden:

**The factor of 1000.** The printed equation adds a term in mol (mu/Yglc_max,
because Yglc_max is printed in gdw mol-1) to a term in mmol (mglc, printed in
mmol gdw-1 h-1). The model states `MOL_PER_MMOL = 1000` and applies it, so the
answer comes back in the unit the table prints. Nothing is fitted; a mol is
1000 mmol.

**The comparison rows are not transcribed.** Table 1 lists eight further
published strains alongside the paper's own row. Their column alignment is not
recoverable from the extracted text with confidence (blank yield cells and
"Unknown" temperatures collapse in the linearised text), so only the paper's own
row -- the row this model's parameters come from -- is encoded. See
`COMPARISON_TABLE_NOTE`.

**What is not here.** The 13C metabolic-flux-ratio machinery (the paper's
equations (1) and (2), pp. 1165-1166) needs GC-MS mass-distribution vectors that
are not tabulated in the paper, so it is declared in `MISSING_MODELS` and not
implemented. This module declares no ports and registers nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .provenance import EvidenceRef, Quantity, reported

#: Printed page carrying equation (3) and Table 1.
TABLE_I_PAGE = 1167
#: Printed page of the Results text quoted here.
RESULTS_PAGE = 1167
#: Printed page of the analytical-procedures section quoted here.
METHODS_PAGE = 1165
#: Printed pages carrying equations (1) and (2), the 13C flux-ratio algebra.
FLUX_RATIO_EQUATION_PAGES = (1165, 1166)

#: The mol/mmol reconciliation the printed equation leaves implicit.
MOL_PER_MMOL = 1000.0


class ModelError(ValueError):
    """Raised when the model is asked for something it cannot do."""


def q_glc(
    mu_per_h: float, Yglc_max_gdw_per_mol: float, mglc_mmol_per_gdw_h: float
) -> float:
    """Pirt's printed equation (3), answered in ``mmol gdw-1 h-1``.

    ``qglc = 1000 * mu / Yglc_max + mglc``. The 1000 is the mol-to-mmol factor
    the printed equation leaves implicit (see the module docstring).
    """
    if Yglc_max_gdw_per_mol <= 0:
        raise ModelError("Yglc_max must be positive")
    return MOL_PER_MMOL * mu_per_h / Yglc_max_gdw_per_mol + mglc_mmol_per_gdw_h


def mu_from_q_glc(
    q_mmol_per_gdw_h: float, Yglc_max_gdw_per_mol: float, mglc_mmol_per_gdw_h: float
) -> float:
    """The printed relation solved for ``mu``, in ``1/h``."""
    if Yglc_max_gdw_per_mol <= 0:
        raise ModelError("Yglc_max must be positive")
    return (q_mmol_per_gdw_h - mglc_mmol_per_gdw_h) * Yglc_max_gdw_per_mol / MOL_PER_MMOL


def biomass_yield(
    mu_per_h: float, Yglc_max_gdw_per_mol: float, mglc_mmol_per_gdw_h: float
) -> float:
    """Observed biomass yield at a growth rate, in ``gdw/mol`` (``mu / qglc``).

    It is below ``Yglc_max`` whenever maintenance is non-zero, which is the
    paper's own point about low growth rates.
    """
    q = q_glc(mu_per_h, Yglc_max_gdw_per_mol, mglc_mmol_per_gdw_h)
    if q <= 0:
        raise ModelError("the relation gives a non-positive glucose consumption rate")
    return mu_per_h / q * MOL_PER_MMOL


@dataclass(frozen=True)
class MaintenanceParameters:
    """The paper's own fitted parameters (Table 1, MG1655, "This study")."""

    strain: str
    mglc: float
    mglc_ci: float
    Yglc_max: float
    Yglc_max_ci: float
    temperature_C: float
    reference_as_printed: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "strain": self.strain,
            "mglc": self.mglc,
            "mglc_unit": "mmol/(gdw h)",
            "mglc_confidence_interval": self.mglc_ci,
            "Yglc_max": self.Yglc_max,
            "Yglc_max_unit": "gdw/mol",
            "Yglc_max_confidence_interval": self.Yglc_max_ci,
            "temperature_C": self.temperature_C,
            "reference_as_printed": self.reference_as_printed,
            "printed_page": TABLE_I_PAGE,
        }


#: The paper's own row of Table 1. The eight comparison rows are not encoded.
THIS_STUDY = MaintenanceParameters(
    strain="MG1655",
    mglc=0.37,
    mglc_ci=0.09,
    Yglc_max=76.0,
    Yglc_max_ci=3.0,
    temperature_C=37.0,
    reference_as_printed="This study",
)

COMPARISON_TABLE_NOTE = (
    "Table 1 also tabulates eight published strains (B/r, C(PC-1000), NTC9001, "
    "ML30, PS, TG1, W3110 and one unnamed) beside this paper's own row. They are "
    "not transcribed: the linearised page text loses the column alignment of "
    "their blank yield cells and 'Unknown' temperatures, so encoding them would "
    "mean guessing which printed number is which. Only the row this model's "
    "parameters come from is encoded."
)


@dataclass(frozen=True)
class ReportedReading:
    """A stated measurement from the paper, with its printed page."""

    reading_id: str
    label: str
    value: float
    unit: str
    evidence: EvidenceRef

    def to_dict(self) -> dict[str, Any]:
        return {
            "reading_id": self.reading_id,
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
            "evidence": self.evidence.to_dict(),
        }


#: Readings the paper states in the text: the fit's domain and its own limits.
REPORTED_READINGS: tuple[ReportedReading, ...] = (
    ReportedReading(
        "acetate.threshold", "dilution rate below which no acetate formed",
        0.4, "1/h",
        EvidenceRef(printed_page=RESULTS_PAGE, section="Results",
                    quote="Acetate formation did not occur at dilution rates below 0.4"),
    ),
    ReportedReading(
        "washout.threshold", "dilution rate above which washout occurred",
        0.7, "1/h",
        EvidenceRef(printed_page=RESULTS_PAGE, section="Results",
                    quote="Above a di- lution rate of 0.7"),
    ),
    ReportedReading(
        "od.dry_weight", "OD600 to dry-weight correlation factor",
        0.41, "g/OD",
        EvidenceRef(printed_page=METHODS_PAGE,
                    section="Analytical procedures and physiological parameters",
                    quote="0.41 g [dry weight]"),
    ),
)


def reported_quantities() -> dict[str, Quantity]:
    """The paper's own parameters as reported Quantities, keyed by name."""
    return {
        "mglc": reported(
            "table1.mglc", "maintenance coefficient", THIS_STUDY.mglc,
            "mmol/(gdw h)",
            EvidenceRef(printed_page=TABLE_I_PAGE, section="Table 1",
                        quote="0.37"),
            original_unit="mmol gdw-1 h-1",
            notes="MG1655, This study; the paper prints a 95% confidence "
                  "interval of +/- 0.09",
        ),
        "Yglc_max": reported(
            "table1.Yglc_max", "maximal molar growth yield", THIS_STUDY.Yglc_max,
            "gdw/mol",
            EvidenceRef(printed_page=TABLE_I_PAGE, section="Table 1",
                        quote="76"),
            original_unit="gdw mol-1",
            notes="MG1655, This study; the paper prints a 95% confidence "
                  "interval of +/- 3",
        ),
    }


#: The models this paper needs to be predictive and does not supply.
MISSING_MODELS: tuple[dict[str, str], ...] = (
    {
        "model_id": "flux_ratios.oaa_pep",
        "label": "The 13C metabolic-flux-ratio equations (1) and (2)",
        "why_not_implemented": (
            "These equations relate the mass distributions of proteinogenic "
            "amino-acid fragments (PEP, pyruvate, OAA, 2-oxoglutarate) to the "
            "fractions f1, f2 and the labelled-CO2 fraction. The paper does not "
            "tabulate those mass-distribution vectors, and states that it solved "
            "the system by an iterative process started from random values. With "
            "no tabulated input, an implementation would have to invent the data."
        ),
    },
    {
        "model_id": "dataset.metabolic_flux_ratios",
        "label": "The eleven determined flux ratios",
        "why_not_implemented": (
            "The ratios are plotted in Fig. 5 and tabulated in Table S1 of the "
            "supplement, neither of which has been supplied as a dataset, so "
            "there is nothing to encode."
        ),
    },
    {
        "model_id": "transfer.oxygen_transfer",
        "label": "An oxygen-transfer or kLa model",
        "why_not_implemented": (
            "The paper reports dissolved-oxygen concentrations above 70% and an "
            "aeration rate of 2 vvm; it prints no oxygen-transfer correlation and "
            "models no oxygen limitation. None is invented here."
        ),
    },
    {
        "model_id": "coupling.other_models",
        "label": "Coupling to the composition layer",
        "why_not_implemented": (
            "This is a standalone model of Nanchen et al.'s own chemostat. It "
            "declares no ports, transfers no parameter, adds no adapter "
            "registration and makes no compatibility claim."
        ),
    },
)

