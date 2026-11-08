"""What this package declares about itself.

Bookkeeping only: that the artefact exists, which printed equation it implements,
which context and parameters it belongs to, and what it deliberately does not
implement. It claims no validity and registers nothing with the composition
layer.
"""

from __future__ import annotations

from typing import Any

from . import context, model, source, units

ARTEFACT_ID = "nanchen2006-pirt-chemostat"
VERSION = "0.1.0"

SCOPE = (
    "Pirt's chemostat relation, printed as equation (3) of Nanchen, Schicker & "
    "Sauer (2006), Applied and Environmental Microbiology 72(2):1164-1172, "
    "together with the paper's own fitted maintenance parameters (Table 1)."
)

DISCLAIMER = (
    "A passing test verifies that this implementation matches the printed "
    "relation and the printed parameter row it was built from. It does not "
    "establish scientific validity. It reproduces no figure: the fit's data "
    "points are plotted in Fig. 4 and are not tabulated."
)

#: The printed equations this paper contains.
PRINTED_EQUATIONS: tuple[dict[str, Any], ...] = (
    {"id": "eq.3", "statement": "qglc = mu / Yglc_max + mglc",
     "printed_page": 1167, "implemented": True},
    {"id": "eq.1",
     "statement": ("OAA1-4 = f1 (PEP1-3 + CO2) + f2 (Pyr2-3 + 0.5 (OAA1-2 + "
                   "OAA3-4)) + (1 - f1 - f2) OGA2-5"),
     "printed_page": 1165, "implemented": False},
    {"id": "eq.2",
     "statement": "the expanded OAA1-4 mass-distribution equation solved for f1, f2",
     "printed_page": 1166, "implemented": False},
)

#: The one-dimensional quantity the model answers in, and its companion.
ANSWER_UNITS: dict[str, str] = {
    "qglc": "mmol/(gdw h)",
    "mu": "1/h",
    "biomass_yield": "gdw/mol",
}


def build_manifest() -> dict[str, Any]:
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
                f"the article is paginated {source.FIRST_PRINTED_PAGE}-"
                f"{source.LAST_PRINTED_PAGE} and each page prints its own number "
                "at the head or foot of the column, so pdf_page = printed_page - "
                f"{source.FIRST_PRINTED_PAGE - 1}"
            ),
        },
        "registration": {
            "registered_in_composition_registry": False,
            "reason": (
                "no adapter registration was added. This paper's process is not "
                "the composition layer's target process, no model id or version "
                "was agreed with that layer, and none is guessed"
            ),
        },
        "experimental_context": [c.to_dict() for c in context.EXPERIMENTAL_CONTEXT],
        "target_process_note": context.TARGET_PROCESS_NOTE,
        "printed_equations": [dict(e) for e in PRINTED_EQUATIONS],
        "answer_units": dict(ANSWER_UNITS),
        "mol_per_mmol": model.MOL_PER_MMOL,
        "fitted_parameters": model.THIS_STUDY.to_dict(),
        "comparison_table_note": model.COMPARISON_TABLE_NOTE,
        "reported_readings": [r.to_dict() for r in model.REPORTED_READINGS],
        "missing_models": [dict(m) for m in model.MISSING_MODELS],
        "units": {
            symbol: {
                "dimension": unit.dimension.value,
                "to_base": unit.to_base,
                "note": unit.note,
            }
            for symbol, unit in sorted(units.UNITS.items())
        },
    }
