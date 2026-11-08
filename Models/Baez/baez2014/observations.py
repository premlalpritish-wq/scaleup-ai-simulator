"""What the paper reports, stored as reported.

Three groups of records, none of which is computed here:

  Component A  two batch specific growth rates, p. 2;
  Component C  the fed-batch endpoint, p. 3;
  setup        the cultivation and induction conditions they were obtained
               under, pp. 5-6.

Every quantity in this module is `Provenance.REPORTED` / `Basis.OBSERVED`.
There is no function here that predicts a growth rate, a biomass
concentration, a GFP concentration or a fluorescence reading, and there is no
function that converts one of these observations into another -- in particular
nothing relates 109000 FU to 494 mg/L. See `equations.MISSING_MODELS`.
"""

from __future__ import annotations

from typing import Any

from . import source
from .provenance import Condition, EvidenceRef, Quantity, ReportedObservation, reported

GROWTH_RATE_PAGE = 2
ENDPOINT_PAGE = 3
SETUP_PAGES = (5, 6)

#: Shared condition evidence.
_DO_30 = EvidenceRef(
    printed_page=GROWTH_RATE_PAGE,
    section="Results",
    quote="concentration of 30% air saturation",
)
_DO_300_BATCH = EvidenceRef(
    printed_page=GROWTH_RATE_PAGE,
    section="Results",
    quote="and 300% (1.00/h) of dO 2",
)
_DO_300_FEDBATCH = EvidenceRef(
    printed_page=ENDPOINT_PAGE,
    section="Results: production of GFP by oxygen-induced promoter in "
            "fed-batch growth",
    quote="After 3 hours at 300% air saturation",
)


def _batch_mode(page: int, quote: str) -> Condition:
    return Condition(
        label="culture mode",
        value="batch",
        evidence=EvidenceRef(printed_page=page, section="Results", quote=quote),
    )


# --------------------------------------------------------------------------- #
# Component A -- reported batch growth-rate observations
# --------------------------------------------------------------------------- #


def growth_rate_observations() -> tuple[ReportedObservation, ...]:
    """The two reported specific growth rates, at the two reported oxygen levels.

    p. 2: "No significant changes (p = 0.05) were observed in the specific
    growth rate of the culture at 30% (1.08/h) and 300% (1.00/h) of dO 2".

    These are two readings, not a function. Nothing in this package fits,
    interpolates or extrapolates them, and no Monod or other growth law is
    offered in their place; `equations.MISSING_MODELS` records that absence and
    why. Neither value is the feed's target rate of 0.35/h: that is a set
    point for the fed-batch feed, reported separately in `feed_rate`.
    """
    return (
        ReportedObservation(
            observation_id="batch.specific_growth_rate.do_30",
            quantity=reported(
                "observation.batch.specific_growth_rate.do_30",
                "specific growth rate at 30% dissolved oxygen",
                1.08,
                "1/h",
                _DO_30,
                original_unit="1/h",
                original_text=(
                    "the specific growth rate of the culture at 30% (1.08/h) "
                    "and 300% (1.00/h)"
                ),
                notes=(
                    "Reported observation, not a prediction. The paper states "
                    "that the difference from the 300% reading is not "
                    "significant (p = 0.05) and reads both values off Figure "
                    "1B."
                ),
            ),
            conditions=(
                Condition(
                    label="dissolved oxygen",
                    value="30% air saturation",
                    evidence=_DO_30,
                ),
                _batch_mode(GROWTH_RATE_PAGE, "was grown initially at a dissolved oxy-"),
            ),
        ),
        ReportedObservation(
            observation_id="batch.specific_growth_rate.do_300",
            quantity=reported(
                "observation.batch.specific_growth_rate.do_300",
                "specific growth rate at 300% dissolved oxygen",
                1.00,
                "1/h",
                _DO_300_BATCH,
                original_unit="1/h",
                original_text="(1.00/h)",
                notes=(
                    "Reported observation, not a prediction. Same sentence as "
                    "the 30% reading, and the paper reports no significant "
                    "difference between the two."
                ),
            ),
            conditions=(
                Condition(
                    label="dissolved oxygen",
                    value="300% air saturation",
                    evidence=_DO_300_BATCH,
                ),
                _batch_mode(GROWTH_RATE_PAGE, "was grown initially at a dissolved oxy-"),
            ),
        ),
    )


# --------------------------------------------------------------------------- #
# Component C -- the reported fed-batch endpoint
# --------------------------------------------------------------------------- #


def fed_batch_endpoint() -> tuple[ReportedObservation, ...]:
    """The four readings the paper reports at the end of the fed-batch run.

    p. 3: "After 3 hours at 300% air saturation, GFP fluorescence reached
    109000 FU (494 mg/L) representing 3.4% of the total protein and the cell
    concentration reached 29.1 g/L (DW) ... acetate accumulation reached
    7.1 g/L".

    Four separate readings in four separate units. The fluorescence and the
    GFP concentration are stored side by side and are never combined: the
    paper prints no conversion between them for this culture, so `FU` and
    `mg/L` stay in different dimensions. Each is an observation, and none is
    an output of the feed equation.
    """
    endpoint_conditions = (
        Condition(
            label="dissolved oxygen",
            value="300% air saturation",
            evidence=_DO_300_FEDBATCH,
        ),
        Condition(
            label="time at that dissolved oxygen",
            value="3 hours",
            evidence=_DO_300_FEDBATCH,
        ),
        Condition(
            label="culture mode",
            value="fed-batch, E. coli AB1157 bearing pAB49",
            evidence=EvidenceRef(
                printed_page=ENDPOINT_PAGE,
                section="Results: production of GFP by oxygen-induced promoter in "
                        "fed-batch growth",
                quote="high density fed-batch culture of E. coli AB1157 bearing pAB49",
            ),
        ),
    )

    return (
        ReportedObservation(
            observation_id="fedbatch.endpoint.biomass_concentration",
            quantity=reported(
                "observation.fedbatch.endpoint.biomass_concentration",
                "cell (biomass) concentration",
                29.1,
                "g/L",
                EvidenceRef(
                    printed_page=ENDPOINT_PAGE,
                    section="Results: production of GFP by oxygen-induced promoter "
                            "in fed-batch growth",
                    quote="the cell concentration reached 29.1 g/L (DW)",
                ),
                original_unit="g/L (DW)",
                original_text="the cell concentration reached 29.1 g/L (DW)",
                notes=(
                    "Dry-weight basis as printed. DW is a measurement basis, "
                    "not a unit, so it is kept in the printed text rather than "
                    "turned into a separate registered unit. Reported "
                    "observation, not a prediction of the fed-batch run."
                ),
            ),
            conditions=endpoint_conditions,
        ),
        ReportedObservation(
            observation_id="fedbatch.endpoint.gfp_concentration",
            quantity=reported(
                "observation.fedbatch.endpoint.gfp_concentration",
                "GFP concentration",
                494.0,
                "mg/L",
                EvidenceRef(
                    printed_page=ENDPOINT_PAGE,
                    section="Results: production of GFP by oxygen-induced promoter "
                            "in fed-batch growth",
                    quote="109000 FU (494 mg/L)",
                ),
                original_unit="mg/L",
                original_text="109000 FU (494 mg/L)",
                notes=(
                    "Reported observation. The paper prints it in the same "
                    "parenthesis as the fluorescence reading but states no "
                    "conversion between the two for this culture; see "
                    "equations.MISSING_MODELS['calibration.fluorescence_to_gfp_mass']."
                ),
            ),
            conditions=endpoint_conditions,
        ),
        ReportedObservation(
            observation_id="fedbatch.endpoint.fluorescence",
            quantity=reported(
                "observation.fedbatch.endpoint.fluorescence",
                "fluorescence",
                109000.0,
                "FU",
                EvidenceRef(
                    printed_page=ENDPOINT_PAGE,
                    section="Results: production of GFP by oxygen-induced promoter "
                            "in fed-batch growth",
                    quote="GFP fluorescence reached 109000 FU (494 mg/L)",
                ),
                original_unit="FU",
                original_text="GFP fluorescence reached 109000 FU (494 mg/L)",
                notes=(
                    "Instrument reading in fluorescence units. FU has its own "
                    "dimension in `units.py` and is not convertible to a mass."
                ),
            ),
            conditions=endpoint_conditions,
        ),
        ReportedObservation(
            observation_id="fedbatch.endpoint.acetate_concentration",
            quantity=reported(
                "observation.fedbatch.endpoint.acetate_concentration",
                "acetate concentration",
                7.1,
                "g/L",
                EvidenceRef(
                    printed_page=ENDPOINT_PAGE,
                    section="Results: production of GFP by oxygen-induced promoter "
                            "in fed-batch growth",
                    quote="acetate accumulation reached 7.1 g/L (Figure 4B)",
                ),
                original_unit="g/L",
                original_text="7.1 g/L (Figure 4B)",
                notes=(
                    "Reported observation. The paper notes that 'the cell growth "
                    "did not stop after induction' in the same passage; no "
                    "acetate uptake or overflow model is offered here."
                ),
            ),
            conditions=endpoint_conditions,
        ),
    )


# --------------------------------------------------------------------------- #
# setup and induction conditions (printed pages 5-6)
# --------------------------------------------------------------------------- #


def experimental_conditions() -> tuple[Condition, ...]:
    """The cultivation and induction conditions the paper prints.

    Recorded as quoted text with their printed page, so that a run supplied by
    a caller can be compared against what the authors actually did. None of
    these is a model parameter, and none of them is substituted for a run
    input: in particular the 4 L initial batch volume on p. 6 is *not* `V_F`,
    the volume at fed-batch onset, which the paper defines but does not
    value.
    """
    return (
        Condition(
            label="bioreactor (batch growth)",
            value="5 L B. Braun bioreactor",
            evidence=EvidenceRef(
                printed_page=5,
                section="Methods: bioreactor culture conditions",
                quote="Batch growth was performed in a 5 L B. Braun bioreac-",
            ),
        ),
        Condition(
            label="temperature",
            value="37 degrees C",
            evidence=EvidenceRef(
                printed_page=5,
                section="Methods: bioreactor culture conditions",
                quote="Temperature was kept at 37°C and pH was maintained at 7.0",
            ),
        ),
        Condition(
            label="pH",
            value="7.0",
            evidence=EvidenceRef(
                printed_page=5,
                section="Methods: bioreactor culture conditions",
                quote="Temperature was kept at 37°C and pH was maintained at 7.0",
            ),
        ),
        Condition(
            label="batch dissolved oxygen set point",
            value="30% air saturation",
            evidence=EvidenceRef(
                printed_page=5,
                section="Methods: bioreactor culture conditions",
                quote="controlled at 30% air saturation",
            ),
        ),
        Condition(
            label="inoculation density",
            value="OD600 of 0.2-0.3",
            evidence=EvidenceRef(
                printed_page=5,
                section="Methods: bioreactor culture conditions",
                quote="The bioreactor was inoculated at OD600 of 0.2-0.3",
            ),
        ),
        Condition(
            label="aeration and agitation",
            value="air at 0.075 vvm, agitation 100 rpm",
            evidence=EvidenceRef(
                printed_page=6,
                section="Methods: bioreactor culture conditions",
                quote="bubbling air at 0.075 vvm and agitation of 100 rpm",
            ),
        ),
        Condition(
            label="induction (soxS promoter)",
            value=(
                "increasing dO 2 to 300% air saturation, one hour after "
                "inoculation"
            ),
            evidence=EvidenceRef(
                printed_page=6,
                section="Methods: bioreactor culture conditions",
                quote=(
                    "by increasing the dO 2 to 300% air saturation to the culture "
                    "with the soxS promoter"
                ),
            ),
        ),
        Condition(
            label="fed-batch onset",
            value="exponential feeding after five hours of growth",
            evidence=EvidenceRef(
                printed_page=3,
                section="Results: production of GFP by oxygen-induced promoter in "
                        "fed-batch growth",
                quote=(
                    "After five hours growth, the exponential feeding was "
                    "initiated to maintain a specific growth rate of 0.35/h"
                ),
            ),
        ),
        Condition(
            label="fed-batch induction",
            value=(
                "dO 2 raised from 30% to 300% air saturation one hour after "
                "feeding started"
            ),
            evidence=EvidenceRef(
                printed_page=3,
                section="Results: production of GFP by oxygen-induced promoter in "
                        "fed-batch growth",
                quote=(
                    "GFP expression was induced by increasing the dO 2 "
                    "concentration from 30% to 300% air saturation"
                ),
            ),
        ),
        Condition(
            label="fed-batch initial volume",
            value="4 L (batch volume before feeding begins, not V_F)",
            evidence=EvidenceRef(
                printed_page=6,
                section="Methods: fed-batch culture",
                quote="the growth started at batch mode with initial volume of 4 L",
            ),
        ),
    )


def all_observations() -> tuple[ReportedObservation, ...]:
    """Every reported observation this package holds, in a fixed order."""
    return growth_rate_observations() + fed_batch_endpoint()


def observations_as_dict() -> dict[str, Any]:
    """Machine-readable form of every observation, for audit."""
    return {
        "source": {
            "source_id": source.SOURCE_ID,
            "citation": source.CITATION,
            "doi": source.DOI,
        },
        "observations": [o.to_dict() for o in all_observations()],
        "experimental_conditions": [c.to_dict() for c in experimental_conditions()],
    }


def quantity_for(observation_id: str) -> Quantity:
    """Look up one reported quantity by id, or raise."""
    for observation in all_observations():
        if observation.observation_id == observation_id:
            return observation.quantity
    raise KeyError(
        f"unknown observation {observation_id!r}; this package reports "
        f"{[o.observation_id for o in all_observations()]}"
    )