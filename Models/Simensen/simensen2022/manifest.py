"""What this package declares about itself.

Bookkeeping only: that the artefact exists, which printed table it encodes, which
context and units that table belongs to, and what it deliberately does not
implement. It claims no validity, transfers nothing, and registers nothing with
the composition layer.
"""

from __future__ import annotations

from typing import Any

from . import context, model, source, units

ARTEFACT_ID = "simensen2022-biomass-composition"
VERSION = "0.1.0"

SCOPE = (
    "Table 1 of Simensen et al. (2022), PLOS ONE 17(1):e0262450: the measured "
    "macromolecular biomass composition of E. coli K-12 MG1655 in "
    "glucose-minimal batch culture, in g gCDW-1, with the two published "
    "compositions the paper compares against."
)

DISCLAIMER = (
    "A passing test verifies that this implementation matches the printed table "
    "it was built from. It does not establish scientific validity, and it "
    "certifies no composition for any other strain, medium, scale or growth "
    "condition: the paper states that biomass composition is condition-dependent."
)


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
            "article_number": source.ARTICLE_NUMBER,
            "pages": source.PAGES,
            "doi": source.DOI,
            "citation": source.CITATION,
            "printed_pages": [source.FIRST_PRINTED_PAGE, source.LAST_PRINTED_PAGE],
            "printed_page_equals_pdf_page": True,
            "page_numbering_evidence": (
                "the article is paginated 1-17 and each page carries a footer of "
                "the form 'N / 17'"
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
        "table": {
            "printed_page": model.TABLE_I_PAGE,
            "unit_as_printed": "g gCDW-1",
            "columns": [
                {"key": c, "label": model.COLUMN_LABELS[c]} for c in model.COLUMNS
            ],
            "rows": [r.to_dict() for r in model.TABLE_1],
        },
        "printed_numeric_markers": {
            k: list(v) for k, v in sorted(model.stated_markers().items())
        },
        "derived": {
            "computed_macromolecule_sum": {
                c: model.computed_macromolecule_sum(c) for c in model.COLUMNS
            },
            "printed_sum": {c: model.printed_sum(c) for c in model.COLUMNS},
            "amino_acid_sum": {
                c: model.amino_acid_sum(c) for c in model.COLUMNS
            },
            "composition": {
                c: model.composition(c) for c in model.COLUMNS
            },
        },
        "reported_statements": [s.to_dict() for s in model.REPORTED_STATEMENTS],
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
