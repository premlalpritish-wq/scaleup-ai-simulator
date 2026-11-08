"""The reported observations: exact values, exact units, and what they are not.

Contract tests 5 (the four fed-batch endpoint readings) and 6 (reported growth
rates stay separate from model predictions).
"""

from __future__ import annotations

import inspect

import pytest

from baez2014 import observations
from baez2014.feed_rate import REPORTED_PARAMETERS
from baez2014.provenance import Basis, Provenance
from baez2014.units import UnitError, convert, dimension_of

#: The four readings, exactly as printed on p. 3.
EXPECTED_ENDPOINT = (
    ("fedbatch.endpoint.biomass_concentration", 29.1, "g/L"),
    ("fedbatch.endpoint.gfp_concentration", 494.0, "mg/L"),
    ("fedbatch.endpoint.fluorescence", 109000.0, "FU"),
    ("fedbatch.endpoint.acetate_concentration", 7.1, "g/L"),
)

#: The two readings, exactly as printed on p. 2.
EXPECTED_GROWTH_RATES = (
    ("batch.specific_growth_rate.do_30", 1.08, "30% air saturation"),
    ("batch.specific_growth_rate.do_300", 1.00, "300% air saturation"),
)


# --------------------------------------------------------------------------- #
# 5. the fed-batch endpoint
# --------------------------------------------------------------------------- #


def test_endpoint_has_exactly_the_four_reported_readings(endpoint: tuple) -> None:
    assert len(endpoint) == 4
    assert tuple(o.observation_id for o in endpoint) == tuple(
        e[0] for e in EXPECTED_ENDPOINT
    )


@pytest.mark.parametrize("observation_id,value,unit", EXPECTED_ENDPOINT)
def test_endpoint_values_and_units_are_exactly_as_reported(
    endpoint: tuple, observation_id: str, value: float, unit: str
) -> None:
    observation = next(o for o in endpoint if o.observation_id == observation_id)
    assert observation.quantity.value == value
    assert observation.quantity.unit == unit
    assert observation.quantity.value == type(value)(observation.quantity.value)


def test_endpoint_observations_are_reported_not_computed(endpoint: tuple) -> None:
    for observation in endpoint:
        quantity = observation.quantity
        assert quantity.provenance is Provenance.REPORTED
        assert quantity.basis is Basis.OBSERVED
        assert quantity.is_observed is True
        assert quantity.method is None
        assert quantity.printed_pages == (3,)


def test_endpoint_observations_carry_their_printed_text(endpoint: tuple) -> None:
    by_id = {o.observation_id: o for o in endpoint}
    biomass = by_id["fedbatch.endpoint.biomass_concentration"]
    assert biomass.quantity.original_text == "the cell concentration reached 29.1 g/L (DW)"
    assert biomass.quantity.original_unit == "g/L (DW)"
    assert "Dry-weight basis as printed" in biomass.quantity.notes
    fluorescence = by_id["fedbatch.endpoint.fluorescence"]
    assert fluorescence.quantity.original_unit == "FU"
    assert fluorescence.quantity.original_text == "GFP fluorescence reached 109000 FU (494 mg/L)"


def test_endpoint_observations_carry_their_conditions(endpoint: tuple) -> None:
    for observation in endpoint:
        conditions = {c.label: c.value for c in observation.conditions}
        assert conditions["dissolved oxygen"] == "300% air saturation"
        assert conditions["time at that dissolved oxygen"] == "3 hours"
        assert conditions["culture mode"].startswith("fed-batch")
        assert all(c.evidence.printed_page == 3 for c in observation.conditions)


def test_biomass_and_gfp_are_concentrations_but_fluorescence_is_not(endpoint: tuple) -> None:
    units = {o.observation_id: o.unit for o in endpoint}
    assert dimension_of(units["fedbatch.endpoint.biomass_concentration"]).value \
        == "mass_concentration"
    assert dimension_of(units["fedbatch.endpoint.gfp_concentration"]).value \
        == "mass_concentration"
    assert dimension_of(units["fedbatch.endpoint.fluorescence"]).value == "fluorescence"
    # the two mass concentrations share a dimension and convert; the
    # fluorescence reading does not convert to either of them
    assert convert(29.1, "g/L", "mg/L") == pytest.approx(29100.0)
    with pytest.raises(UnitError, match="dimension mismatch"):
        convert(109000.0, "FU", "mg/L")


# --------------------------------------------------------------------------- #
# 6. the reported growth rates, kept apart from any prediction
# --------------------------------------------------------------------------- #


def test_growth_rate_observations_are_exactly_as_reported(growth_rates: tuple) -> None:
    assert len(growth_rates) == 2
    for observation, (observation_id, value, do_level) in zip(growth_rates, EXPECTED_GROWTH_RATES):
        assert observation.observation_id == observation_id
        assert observation.quantity.value == value
        assert observation.quantity.unit == "1/h"
        conditions = {c.label: c.value for c in observation.conditions}
        assert conditions["dissolved oxygen"] == do_level
        assert conditions["culture mode"] == "batch"


def test_growth_rate_observations_are_observed_readings(growth_rates: tuple) -> None:
    for observation in growth_rates:
        assert observation.quantity.provenance is Provenance.REPORTED
        assert observation.quantity.basis is Basis.OBSERVED
        assert observation.quantity.printed_pages == (2,)
        assert observation.quantity.is_observed is True


def test_no_growth_rate_is_fitted_or_predicted(growth_rates: tuple) -> None:
    """The two readings are not a curve, and nothing here treats them as one."""
    values = [o.quantity.value for o in growth_rates]
    assert values == [1.08, 1.00]
    # no model quantity carries either reading as an input, so no output can
    # be traced to them
    for quantity in REPORTED_PARAMETERS.values():
        assert quantity.value not in values
    # the feed's target rate is a third, separate number
    assert REPORTED_PARAMETERS["mu_set"].value not in values
    assert REPORTED_PARAMETERS["mu_set"].printed_pages == (6,)


def test_observations_module_exposes_no_predictive_function() -> None:
    """Every public callable here reads or reports; none computes a reading."""
    public = {
        name
        for name, obj in vars(observations).items()
        if not name.startswith("_") and callable(obj) and getattr(obj, "__module__", "") == observations.__name__
    }
    assert public == {
        "growth_rate_observations",
        "fed_batch_endpoint",
        "experimental_conditions",
        "all_observations",
        "observations_as_dict",
        "quantity_for",
    }


def test_no_public_callable_takes_a_dissolved_oxygen_argument(growth_rates: tuple) -> None:
    """A growth rate cannot be asked for as a function of anything."""
    for name in ("growth_rate_observations", "fed_batch_endpoint", "quantity_for"):
        parameters = set(inspect.signature(getattr(observations, name)).parameters)
        assert not parameters & {"dO2", "do2", "oxygen", "t", "time", "mu", "rate"}


def test_observations_are_not_products_of_the_feed_equation(endpoint: tuple) -> None:
    """Endpoint readings are observations; the feed equation produces none of them."""
    from baez2014.equations import EQUATIONS

    assert len(EQUATIONS) == 1
    produced = {
        i.key
        for i in next(iter(EQUATIONS.values())).inputs
    }
    for observation in endpoint:
        assert observation.quantity.quantity_id not in produced


# --------------------------------------------------------------------------- #
# lookup and serialisation
# --------------------------------------------------------------------------- #


def test_quantity_lookup_by_id() -> None:
    quantity = observations.quantity_for("fedbatch.endpoint.fluorescence")
    assert quantity.value == 109000.0
    with pytest.raises(KeyError, match="unknown observation"):
        observations.quantity_for("fedbatch.endpoint.viability")


def test_all_observations_is_a_fixed_order_and_is_stable() -> None:
    first = [o.observation_id for o in observations.all_observations()]
    second = [o.observation_id for o in observations.all_observations()]
    assert first == second
    assert len(first) == 6


def test_observations_as_dict_is_json_shaped() -> None:
    import json

    document = observations.observations_as_dict()
    payload = json.loads(json.dumps(document))
    assert payload["source"]["doi"] == "10.1186/1475-2859-13-50"
    assert len(payload["observations"]) == 6
    assert len(payload["experimental_conditions"]) == 10
    for entry in payload["observations"]:
        assert entry["quantity"]["basis"] == "observed_reference"
        assert entry["quantity"]["evidence"][0]["printed_page"] in (2, 3)


def test_every_condition_cites_a_page_inside_the_article() -> None:
    for condition in observations.experimental_conditions():
        assert 1 <= condition.evidence.printed_page <= 7
        assert condition.value
        assert condition.evidence.quote