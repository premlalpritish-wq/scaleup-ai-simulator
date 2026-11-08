"""Baez et al. (2014): reported observations and the printed feed equation.

    A. Baez, N. Majdalani, J. Shiloach, 'Production of recombinant protein by
    a novel oxygen-induced system in Escherichia coli', Microbial Cell
    Factories 2014, 13:50. doi:10.1186/1475-2859-13-50

What is here, and nothing more:

  * `observations` -- two reported batch growth rates (p. 2) and the four
    reported fed-batch endpoint readings (p. 3), stored as observations with
    their printed pages, units and verbatim text;
  * `feed_rate` -- the exponential fed-batch feed equation printed on p. 6,
    with `mu_set`, `Y_XS`, `m` and `S_F` as reported parameters and `X_F`,
    `V_F`, `t_F`, `t` as required per-run inputs;
  * `equations.MISSING_MODELS` -- the seven models this package deliberately
    does not implement, each with the reason.

What is not here: a growth law, a dissolved-oxygen balance, an oxygen-transfer
model, a GFP expression model, a fluorescence-to-mass conversion, a digitised
time series, or any coupling to the other model packages in this repository.

No third-party dependency. Standard library only.
"""

from __future__ import annotations

from . import equations, feed_rate, manifest, observations, source, units
from .feed_rate import (
    REPORTED_PARAMETERS,
    UNVALUED_RUN_INPUTS,
    FeedRateError,
    FeedRateResult,
    FeedTimeBeforeStart,
    MissingRunInput,
    feed_rate as feed_rate_at,
)
from .manifest import ARTEFACT_ID, VERSION, build_manifest
from .observations import (
    all_observations,
    experimental_conditions,
    fed_batch_endpoint,
    growth_rate_observations,
)

__all__ = [
    "ARTEFACT_ID",
    "REPORTED_PARAMETERS",
    "UNVALUED_RUN_INPUTS",
    "VERSION",
    "FeedRateError",
    "FeedRateResult",
    "FeedTimeBeforeStart",
    "MissingRunInput",
    "all_observations",
    "build_manifest",
    "equations",
    "experimental_conditions",
    "fed_batch_endpoint",
    "feed_rate_at",
    "growth_rate_observations",
    "manifest",
    "observations",
    "source",
    "units",
]