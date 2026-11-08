"""Independent numerical fixtures for the feed-rate equation.

Run from this directory:

    python build_feed_rate_fixtures.py

It writes `feed_rate_fixtures.json` beside itself.

**Independence.** This script does not import `baez2014` and does not call the
implementation under test. It recomputes the printed expression from the
printed parameters with exact rational arithmetic (`fractions.Fraction`) for
everything except the exponential, and then evaluates the exponential with
`decimal.Decimal` at 60 significant digits. The implementation uses IEEE-754
doubles and `math.exp`, so agreement to ~1e-12 relative is what two different
numerical paths should give, and disagreement means one of them is wrong.

**The inputs are not paper values.** `X_F`, `V_F`, `t_F` and `t` are
illustrative numbers chosen to exercise the formula (t = t_F, one and three
hours past it, a unit conversion, a parameter override, a zero biomass). They
are fixtures, not observations, and nothing in this file should be read as a
measurement from Baez et al. (2014). The four printed parameters are the only
numbers here that come from the paper.

Each fixture stores the exact rational value of the pre-exponential factor and
of the exponent argument, so a reader can redo the arithmetic by hand without
running anything.
"""

from __future__ import annotations

import json
from decimal import Decimal, getcontext
from fractions import Fraction
from pathlib import Path

getcontext().prec = 60

# The parameters exactly as printed on p. 6, as exact rationals.
# Fraction(Decimal("0.35")) is 7/20 exactly: no binary rounding is involved.
MU_SET = Fraction(Decimal("0.35"))   # 0.35 1/h
Y_XS = Fraction(Decimal("1.28"))     # 1.28 g/g
M = Fraction(Decimal("0.12"))        # 0.12 g/g h
S_F = Fraction(141)                  # 141 g/L

CASES: list[dict] = [
    {
        "id": "feed_at_onset",
        "description": (
            "t = t_F, so the exponential factor is exactly 1 and the result "
            "is the pre-exponential factor alone."
        ),
        "inputs": {"X_F": "10.0", "V_F": "4.0", "t_F": "5.0", "t": "5.0"},
        "input_units": {"X_F": "g/L", "V_F": "L", "t_F": "h", "t": "h"},
        "parameters": None,
    },
    {
        "id": "one_hour_after_onset",
        "description": (
            "One hour of exponential feeding at the printed mu_set, so the "
            "exponent argument is exactly 0.35."
        ),
        "inputs": {"X_F": "10.0", "V_F": "4.0", "t_F": "5.0", "t": "6.0"},
        "input_units": {"X_F": "g/L", "V_F": "L", "t_F": "h", "t": "h"},
        "parameters": None,
    },
    {
        "id": "three_hours_after_onset",
        "description": (
            "Three hours after feeding starts, so the exponent argument is "
            "exactly 1.05."
        ),
        "inputs": {"X_F": "10.0", "V_F": "4.0", "t_F": "5.0", "t": "8.0"},
        "input_units": {"X_F": "g/L", "V_F": "L", "t_F": "h", "t": "h"},
        "parameters": None,
    },
    {
        "id": "same_point_in_other_units",
        "description": (
            "The same physical point as 'one_hour_after_onset', expressed in "
            "mg/L and mL. Exercises the unit conversion path; the expected "
            "value is unchanged."
        ),
        "inputs": {"X_F": "10000.0", "V_F": "4000.0", "t_F": "5.0", "t": "6.0"},
        "input_units": {"X_F": "mg/L", "V_F": "mL", "t_F": "h", "t": "h"},
        "parameters": None,
    },
    {
        "id": "overridden_parameters",
        "description": (
            "The printed parameters replaced by a caller's own values. "
            "Exercises the override path; the result must record that it is "
            "not the printed parameterisation."
        ),
        "inputs": {"X_F": "10.0", "V_F": "4.0", "t_F": "5.0", "t": "7.0"},
        "input_units": {"X_F": "g/L", "V_F": "L", "t_F": "h", "t": "h"},
        "parameters": {"mu_set": "0.5", "Y_XS": "1.0", "m": "0.1", "S_F": "141.0"},
    },
    {
        "id": "zero_biomass_at_onset",
        "description": (
            "Zero biomass at fed-batch onset. The pre-exponential factor is "
            "zero, so the feed rate is exactly zero: a boundary value, not an "
            "error."
        ),
        "inputs": {"X_F": "0.0", "V_F": "4.0", "t_F": "5.0", "t": "5.0"},
        "input_units": {"X_F": "g/L", "V_F": "L", "t_F": "h", "t": "h"},
        "parameters": None,
    },
]


def _frac(text: str) -> Fraction:
    return Fraction(Decimal(text))


def _in_printed_unit(value: Decimal, symbol: str) -> Fraction:
    """Convert a supplied value into the unit the paper prints.

    Only the two non-printed units the fixtures use appear here, so the
    conversion is stated rather than delegated to the implementation under
    test: a millilitre is a thousandth of a litre and a milligramme per litre
    is a thousandth of a gramme per litre.
    """
    per_printed = {
        "g/L": Fraction(1),
        "mg/L": Fraction(1, 1000),
        "L": Fraction(1),
        "mL": Fraction(1, 1000),
        "h": Fraction(1),
        "min": Fraction(1, 60),
    }
    if symbol not in per_printed:
        raise KeyError(f"fixture uses a unit with no stated conversion: {symbol!r}")
    return _frac(value) * per_printed[symbol]


def compute(case: dict) -> dict:
    mu_set = _frac(case["parameters"]["mu_set"]) if case["parameters"] else MU_SET
    y_xs = _frac(case["parameters"]["Y_XS"]) if case["parameters"] else Y_XS
    m = _frac(case["parameters"]["m"]) if case["parameters"] else M
    s_f = _frac(case["parameters"]["S_F"]) if case["parameters"] else S_F

    x_f = _in_printed_unit(Decimal(case["inputs"]["X_F"]), case["input_units"]["X_F"])
    v_f = _in_printed_unit(Decimal(case["inputs"]["V_F"]), case["input_units"]["V_F"])
    t_f = _in_printed_unit(Decimal(case["inputs"]["t_F"]), case["input_units"]["t_F"])
    t = _in_printed_unit(Decimal(case["inputs"]["t"]), case["input_units"]["t"])

    # exact rational part, straight from the printed expression
    pre_factor = (mu_set / y_xs + m) * (x_f * v_f / s_f)
    exponent_argument = mu_set * (t - t_f)

    # decimal evaluation of the same expression
    def dec(value) -> Decimal:
        if isinstance(value, Fraction):
            return Decimal(value.numerator) / Decimal(value.denominator)
        return value

    rate = dec(pre_factor) * dec(exponent_argument).exp()

    out = dict(case)
    out["exact_inputs_in_printed_units"] = {
        "X_F": f"{x_f.numerator}/{x_f.denominator} g/L",
        "V_F": f"{v_f.numerator}/{v_f.denominator} L",
        "t_F": f"{t_f.numerator}/{t_f.denominator} h",
        "t": f"{t.numerator}/{t.denominator} h",
    }
    out["exact_pre_factor_l_per_h"] = f"{pre_factor.numerator}/{pre_factor.denominator}"
    out["exact_exponent_argument"] = (
        f"{exponent_argument.numerator}/{exponent_argument.denominator}"
    )
    out["exact_exponential_factor"] = f"exp({dec(exponent_argument)})"
    out["expected_feed_rate_l_per_h"] = (
        "0.0" if rate == 0 else format(rate.quantize(Decimal("1.00000000000000e-15")), "e")
    )
    out["relative_tolerance"] = 1e-12
    return out


def build() -> dict:
    return {
        "equation": "F(t) = (mu_set/Y_XS + m) * (X_F*V_F/S_F) * exp(mu_set*(t - t_F))",
        "equation_source": "Baez et al. 2014, p. 6, printed",
        "output_unit": "L/h",
        "reported_parameters": {
            "mu_set": "0.35 1/h",
            "Y_XS": "1.28 g/g",
            "m": "0.12 g/(g h)",
            "S_F": "141 g/L",
        },
        "derivation": (
            "Computed by fixtures/build_feed_rate_fixtures.py with exact "
            "rational arithmetic for the non-exponential part and a 60-digit "
            "decimal exponential. The implementation uses IEEE-754 doubles and "
            "math.exp; the two paths share no code."
        ),
        "input_note": (
            "X_F, V_F, t_F and t are illustrative fixture values chosen to "
            "exercise the formula. They are not reported values from the paper "
            "and are not measurements."
        ),
        "cases": [compute(case) for case in CASES],
    }


def main() -> int:
    out = Path(__file__).parent / "feed_rate_fixtures.json"
    text = json.dumps(build(), indent=2, ensure_ascii=False) + "\n"
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {out}")
    for case in build()["cases"]:
        print(f"  {case['id']:<28} {case['expected_feed_rate_l_per_h']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())