"""Integration, the pulse method, units, the manifest, and isolation."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from lin2000 import manifest, model, parameters as params, units
from lin2000.validate import check_parameters, validate

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# integration of the printed system
# --------------------------------------------------------------------------- #


def test_constant_feed_grows_the_volume_by_exactly_F_times_t():
    p = check_parameters()
    feed = model.feed_constant(0.0532)
    result = model.simulate(p, feed, t_end=2.0, dt=0.001, record_every=100)
    assert result.final().state.V == pytest.approx(p.V0 + 0.0532 * 2.0, abs=1e-9)


def test_a_run_is_finite_and_biomass_increases_under_feed():
    p = check_parameters()
    result = model.simulate(p, model.feed_constant(0.0532), t_end=1.0, dt=0.005)
    xs = [s.state.X for s in result.samples]
    assert all(math_is_finite(v) for v in xs)
    assert xs[-1] > xs[0]


def test_the_exponential_feed_is_the_printed_protocol_shape():
    feed = model.feed_exponential(0.0057, 0.27)  # 5.7 mL/h = 0.0057 L/h
    assert feed(0.0) == pytest.approx(0.0057)
    assert feed(1.0) == pytest.approx(0.0057 * math.exp(0.27))


def test_a_non_positive_horizon_is_refused():
    p = check_parameters()
    with pytest.raises(model.ModelError):
        model.simulate(p, model.feed_constant(0.1), t_end=0.0)


# --------------------------------------------------------------------------- #
# the pulse method, equation (1)
# --------------------------------------------------------------------------- #


def test_the_pulse_equation_reproduces_a_hand_computed_value():
    q = model.qScap_from_pulse(
        delta_S_g=7.0, integral_F_Si_g=0.0, V_L=7.0, X_g_per_L=1.0,
        tP_h=0.0, tR_h=0.01,
    )
    assert q == pytest.approx(100.0)


def test_the_pulse_equation_adds_the_feed_contribution():
    q = model.qScap_from_pulse(
        delta_S_g=1.0, integral_F_Si_g=1.0, V_L=1.0, X_g_per_L=1.0,
        tP_h=0.0, tR_h=1.0,
    )
    assert q == pytest.approx(2.0)


def test_the_pulse_equation_refuses_a_non_positive_interval():
    with pytest.raises(model.ModelError):
        model.qScap_from_pulse(
            delta_S_g=1.0, integral_F_Si_g=0.0, V_L=1.0, X_g_per_L=1.0,
            tP_h=1.0, tR_h=1.0,
        )


# --------------------------------------------------------------------------- #
# units
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "src,dst,value,expected",
    [
        ("h", "min", 1.0, 60.0),
        ("mL", "L", 1000.0, 1.0),
        ("mL/h", "L/h", 1000.0, 1.0),
        ("mg/L", "g/L", 1000.0, 1.0),
    ],
)
def test_registered_conversions(src: str, dst: str, value: float, expected: float):
    assert units.convert(value, src, dst) == pytest.approx(expected)


@pytest.mark.parametrize(
    "src,dst",
    [("g/(g h)", "mmol/(g h)"), ("1/h", "g/(g h)"), ("g/L", "g/g")],
)
def test_unlike_dimensions_are_refused(src: str, dst: str):
    assert not units.is_convertible(src, dst)
    with pytest.raises(units.UnitError):
        units.convert(1.0, src, dst)


def test_an_unregistered_unit_is_refused():
    with pytest.raises(units.UnitError):
        units.dimension_of("mmol/L")


# --------------------------------------------------------------------------- #
# manifest, validation, and isolation from the composition layer
# --------------------------------------------------------------------------- #


def test_the_manifest_declares_the_source_and_the_absence_of_registration():
    m = manifest.build_manifest()
    assert m["artefact_id"] == manifest.ARTEFACT_ID
    assert m["source"]["source_id"] == "lin2000"
    assert m["registration"]["registered_in_composition_registry"] is False
    assert m["required_run_inputs"]
    assert all(not i["defaulted"] for i in m["required_run_inputs"])


def test_the_manifest_carries_the_experimental_context_it_preserves():
    keys = {c["key"] for c in manifest.build_manifest()["experimental_context"]}
    for required in ("strain.primary", "construct", "medium", "reactor", "scale"):
        assert required in keys


def test_the_committed_manifest_matches_what_the_package_declares():
    committed = PACKAGE_ROOT / "manifest.json"
    if not committed.is_file():
        pytest.skip("manifest.json has not been generated yet")
    expected = json.dumps(
        manifest.build_manifest(), indent=2, sort_keys=True, ensure_ascii=False
    ) + "\n"
    assert committed.read_text(encoding="utf-8") == expected


def test_validation_passes_on_this_repository():
    report = validate()
    assert report["ok"], report["failures"]


def test_the_package_does_not_import_the_composition_layer():
    """Standalone means standalone: no import of composition.*, anywhere."""
    for path in sorted((PACKAGE_ROOT / "lin2000").glob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            assert not stripped.startswith("import composition"), (
                f"{path.name} imports the composition layer"
            )
            assert not stripped.startswith("from composition"), (
                f"{path.name} imports the composition layer"
            )


def math_is_finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))
