"""What this package declares about itself.

The manifest is bookkeeping. It records that this artefact exists, that it
declares one executable equation and a fixed set of reported observations, and
where each of those came from in the printed article. It does **not** claim
that the model is correct, independently supported, or predictive.

**On identifiers.** The `artefact_id` and `version` below are declared by this
package itself and match `pyproject.toml`. They are not registered anywhere
else in this repository: no adapter was added to `composition/composition/
adapters`, so `python -m composition.registry` does not list this package and
its output is unchanged. Registration would need a model id and version agreed
with the composition layer, which this package's specification does not
supply; none is guessed here.
"""

from __future__ import annotations

from typing import Any

from . import equations, feed_rate, observations, source, units

ARTEFACT_ID = "baez2014-oxygen-induced"
VERSION = "0.1.0"

SCOPE = (
    "The reported observations and the printed exponential fed-batch feed "
    "equation of Baez et al. (2014), Microbial Cell Factories 13:50."
)

DISCLAIMER = (
    "A passing test verifies that this implementation matches the supplied "
    "specification. It does not establish scientific validity, and the "
    "package contains no predictive capability beyond evaluating one printed "
    "equation at the caller's own inputs."
)

#: The specification's exclusions, restated as the package's own scope limit.
EXCLUSIONS = (
    "a Monod or any other growth equation",
    "a dissolved-oxygen differential equation",
    "an oxygen-transfer or oxygen-uptake model",
    "a kinetic model of GFP expression",
    "a conversion between fluorescence (FU) and GFP mass (mg/L)",
    "a digitised time series, absent a separately supplied dataset that "
    "defines the coordinates and the digitisation provenance",
    "any automatic coupling to the Morris or Zielinski models",
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
            "article_number": source.ARTICLE_NUMBER,
            "pages": source.PAGES,
            "doi": source.DOI,
            "citation": source.CITATION,
            "printed_pages": [source.FIRST_PRINTED_PAGE, source.PAGE_COUNT],
            "printed_page_equals_pdf_page": True,
            "page_numbering_evidence": (
                "pages 2-{n} carry the running footer '{footer}', each stating "
                "its own printed page number; page 1 carries the journal line "
                "and no page footer".format(
                    n=source.PAGE_COUNT,
                    footer=source.FOOTER_TEMPLATE % (2, source.PAGE_COUNT),
                )
            ),
        },
        "registration": {
            "registered_in_composition_registry": False,
            "reason": (
                "no adapter registration was added, so the composition "
                "registry neither lists nor validates this package; a model id "
                "and version agreed with the composition layer were not "
                "supplied and are not guessed"
            ),
        },
        "equations": [e.to_dict() for e in equations.executable_equations()],
        "reported_parameters": {
            name: q.to_dict() for name, q in feed_rate.REPORTED_PARAMETERS.items()
        },
        "required_run_inputs": [
            {
                "name": name,
                "unit": next(i.unit for i in equation.inputs if i.key == name),
                "definition_as_printed": feed_rate.UNVALUED_RUN_INPUTS[name],
                "defaulted": False,
            }
            for equation in equations.executable_equations()
            for name in equation.required_run_inputs
        ],
        "observations": [o.to_dict() for o in observations.all_observations()],
        "experimental_conditions": [
            c.to_dict() for c in observations.experimental_conditions()
        ],
        "missing_models": [m.to_dict() for m in equations.MISSING_MODELS.values()],
        "exclusions": list(EXCLUSIONS),
        "units": {
            symbol: {
                "dimension": unit.dimension.value,
                "to_base": unit.to_base,
                "note": unit.note,
            }
            for symbol, unit in sorted(units.UNITS.items())
        },
    }