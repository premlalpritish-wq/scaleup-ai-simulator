"""What this package declares about itself.

The manifest is bookkeeping. It records that this artefact exists, that it
implements the Appendix's printed equations, which experimental context those
equations belong to, and what it deliberately does not implement. It does **not**
claim that the model is correct, independently supported, or predictive, and it
does not register anything with the composition layer.

**On identifiers.** ``artefact_id`` and ``version`` are declared by this package
itself and match ``pyproject.toml``. No adapter was added to
``composition/composition/adapters``, so ``python -m composition.registry`` does
not list this package and its output is unchanged. Registration would need a
model id and version agreed with the composition layer, which this paper's
context does not supply -- it is a different process from the composition
layer's target -- and none is guessed here.
"""

from __future__ import annotations

from typing import Any

from . import context, model, parameters as params, source, units

ARTEFACT_ID = "lin2000-uptake-capacities"
VERSION = "0.1.0"

SCOPE = (
    "The complete simulation model printed in the Appendix of Lin et al. "
    "(2001), Biotechnology and Bioengineering 73(5):347-357, together with "
    "Table I's parameter set and the paper's reported uptake capacities."
)

DISCLAIMER = (
    "A passing test verifies that this implementation matches the printed "
    "equations and the printed parameter table it was built from. It does not "
    "establish scientific validity and it reproduces no figure of the paper: "
    "the paper prints no digitised trajectory, so a run evaluates the printed "
    "model at the caller's own inputs."
)

#: The printed equations this package implements, in the paper's own numbering.
PRINTED_EQUATIONS: tuple[dict[str, Any], ...] = (
    {"id": "ode.1", "statement": "V. = F", "printed_page": 356},
    {"id": "ode.2", "statement": "X. = (mu - F/V) X", "printed_page": 356},
    {"id": "ode.3", "statement": "S. = -(F/V)(S - Si) - qS X", "printed_page": 356},
    {"id": "ode.4",
     "statement": "DOT. = kLa(DOT* - DOT) - qO X H", "printed_page": 356},
    {"id": "ode.5",
     "statement": "A. = -(F/V) A + (qAp - qAc) X", "printed_page": 356},
    {"id": "ode.6",
     "statement": "rS. = YES/X mu - rS (qESd + mu)", "printed_page": 356},
    {"id": "ode.7",
     "statement": "rO. = YEO/X mu - rO (qEOd + mu)", "printed_page": 356},
    {"id": "initial.rS0",
     "statement": "rS0 = cS mu_max / (qESd + mu_max)", "printed_page": 356},
    {"id": "initial.rO0",
     "statement": "rO0 = cO mu_max / (qEOd + mu_max)", "printed_page": 356},
    {"id": "initial.mu_max",
     "statement": "mu_max = (qSmax - qm) YX/S,ox", "printed_page": 356},
    {"id": "subsidiary.qScap",
     "statement": "qScap = qSmax rS / rS0", "printed_page": 356},
    {"id": "subsidiary.qOcap",
     "statement": "qOcap = qOmax rO / rO0", "printed_page": 356},
    {"id": "subsidiary.qS",
     "statement": "qS = qScap S / (S + KS)", "printed_page": 356},
    {"id": "subsidiary.qSox", "statement": "qSox = qS", "printed_page": 356},
    {"id": "subsidiary.qmr",
     "statement": "qmr <= min{qm, qSox}", "printed_page": 356},
    {"id": "subsidiary.qSoxan",
     "statement": "qSoxan = (qSox - qmr) YX/S,ox CS", "printed_page": 356},
    {"id": "subsidiary.qSoxen",
     "statement": "qSoxen = qSox - qSoxan", "printed_page": 356},
    {"id": "subsidiary.qOs", "statement": "qOs = qSoxen YO/S", "printed_page": 356},
    {"id": "subsidiary.clamp_qos",
     "statement": ("if qOs > qOcap: qOs = qOcap; qSoxen = qOcap/YO/S; "
                   "qSox = (qmr CS YX/S,ox - qSoxen)/(CS YX/S,ox - 1); "
                   "qSoxan = qSox - qSoxen"),
     "printed_page": 357},
    {"id": "subsidiary.floor_qmr",
     "statement": "if qSox < qmr: qmr = qSox = qSoxen and qSoxan = 0",
     "printed_page": 357},
    {"id": "subsidiary.qSof",
     "statement": "qSof = qS - qSox", "printed_page": 357},
    {"id": "subsidiary.qAc",
     "statement": "qAc = qAc,max A / (A + KA)", "printed_page": 357},
    {"id": "subsidiary.qSofan",
     "statement": "qSofan = qSof YX/S,of CS", "printed_page": 357},
    {"id": "subsidiary.qSofen",
     "statement": "qSofen = qSof - qSofan", "printed_page": 357},
    {"id": "subsidiary.qAcan",
     "statement": "qAcan = qAc YX/A CA", "printed_page": 357},
    {"id": "subsidiary.qAcen",
     "statement": "qAcen = qAc - qAcan", "printed_page": 357},
    {"id": "subsidiary.clamp_qacen",
     "statement": ("if qAcen > qOcap - qOs/YO/A: qAcen = qOcap - qOs/YO/A; "
                   "qAc = qAcen/(1 - YX/A CA); qAcan = qAc - qAcen"),
     "printed_page": 357},
    {"id": "subsidiary.qAp", "statement": "qAp = qSofen YA/S", "printed_page": 357},
    {"id": "subsidiary.qO",
     "statement": "qO = qOs + qAcen YO/A", "printed_page": 357},
    {"id": "subsidiary.mu",
     "statement": "mu = (qSox - qm) YX/S,ox + qSof YX/S,of + qAc YX/A",
     "printed_page": 357},
    {"id": "method.pulse_qScap",
     "statement": "qScap = (dS + INT(F Si)) / (V X (tR - tP))",
     "printed_page": 351},
)


#: Models the paper would need in order to be predictive and does not print.
MISSING_MODELS: tuple[dict[str, str], ...] = (
    {
        "model_id": "data.digitised_trajectory",
        "label": "Digitised time series",
        "why_not_implemented": (
            "Figures 1-9 are referenced but no coordinate set with digitisation "
            "provenance has been supplied, so there is nothing to digitise. This "
            "package therefore reproduces no figure; it evaluates the printed "
            "model."
        ),
    },
    {
        "model_id": "constants.cS_cO",
        "label": "The initial-enzyme factors cS and cO",
        "why_not_implemented": (
            "The Appendix's initial-value equations multiply by cS and cO; no "
            "value for either is printed on any page, so both are required run "
            "inputs."
        ),
    },
    {
        "model_id": "transfer.oxygen_transfer",
        "label": "An oxygen-transfer correlation for kLa",
        "why_not_implemented": (
            "Equation (4) takes kLa as an input; the paper prints no correlation "
            "and no value of kLa for these cultivations, so it is a required run "
            "input."
        ),
    },
    {
        "model_id": "coupling.other_models",
        "label": "Coupling to the composition layer",
        "why_not_implemented": (
            "This is a standalone model of Lin et al.'s own experiment. It "
            "declares no ports, transfers no parameter, adds no adapter "
            "registration and makes no compatibility claim."
        ),
    },
)


def build_manifest() -> dict[str, Any]:
    """The declared manifest, as a deterministic plain-data structure."""
    return {
        "artefact_id": ARTEFACT_ID,
        "version": VERSION,
        "scope": SCOPE,
        "disclaimer": DISCLAIMER,
        "source": {
            "source_id": source.SOURCE_ID,
            "authors": list(source.AUTHORS),
            "title": source.TITLE,
            "journal": source.JOURNAL,
            "year": source.YEAR,
            "volume": source.VOLUME,
            "issue": source.ISSUE,
            "pages": source.PAGES,
            "doi": source.DOI,
            "citation": source.CITATION,
            "printed_pages": [source.FIRST_PRINTED_PAGE, source.LAST_PRINTED_PAGE],
            "page_numbering_evidence": (
                "the article is paginated "
                f"{source.FIRST_PRINTED_PAGE}-{source.LAST_PRINTED_PAGE} and each "
                "page carries a running footer whose leading integer is its own "
                "printed page number, so pdf_page = printed_page - "
                f"{source.FIRST_PRINTED_PAGE - 1}"
            ),
        },
        "registration": {
            "registered_in_composition_registry": False,
            "reason": (
                "no adapter registration was added. The paper's process is not "
                "the composition layer's target process, no model id or version "
                "was agreed with that layer, and none is guessed"
            ),
        },
        "experimental_context": [c.to_dict() for c in context.EXPERIMENTAL_CONTEXT],
        "target_process_note": context.TARGET_PROCESS_NOTE,
        "printed_equations": [dict(e) for e in PRINTED_EQUATIONS],
        "table_i": [p.to_dict() for p in params.TABLE_I],
        "table_i_page": params.TABLE_I_PAGE,
        "protocol_variants": [v.to_dict() for v in params.PROTOCOL_VARIANTS],
        "no_change_values": dict(params.NO_CHANGE_VALUES),
        "c_nomenclature_constants": {
            k: {"value": v, "unit": u}
            for k, (v, u) in params.NOMENCLATURE_CONSTANTS.items()
        },
        "required_run_inputs": [
            {
                "name": name,
                "definition_as_printed": params.UNVALUED_RUN_INPUTS[name],
                "defaulted": False,
            }
            for name in model.REQUIRED_RUN_INPUTS
        ],
        "reported_capacities": [q.to_dict() for q in params.REPORTED_CAPACITIES],
        "missing_models": [dict(m) for m in MISSING_MODELS],
        "units": {
            symbol: {
                "dimension": unit.dimension.value,
                "to_base": unit.to_base,
                "note": unit.note,
            }
            for symbol, unit in sorted(units.UNITS.items())
        },
    }
