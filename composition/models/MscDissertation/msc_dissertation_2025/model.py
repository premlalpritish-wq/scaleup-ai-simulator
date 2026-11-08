"""Bioprocess extraction kinetics model for MSc Dissertation (2025)."""
from __future__ import annotations

import math
from typing import Any, Mapping
from .parameters import DEFAULT_PARAMETERS, DissertationParameters

def extraction_fraction(t: float, k_ext: float = 0.35) -> float:
    """Fractional approach to extraction equilibrium: 1 - exp(-k_ext * t)."""
    if t <= 0:
        return 0.0
    return 1.0 - math.exp(-k_ext * t)

def simulate_extraction(
    t: float = 16.0,
    biomass: float = 15.0,
    feed_rate: float = 0.05,
    biomass_concentration: float = 20.0,
    params: DissertationParameters = DEFAULT_PARAMETERS,
) -> dict[str, float]:
    """Calculate extraction yield, remaining biomass, and rates at time t."""
    f = extraction_fraction(t, params.k_extraction)
    y_max = params.yield_scaled_up_15g
    product_yield = y_max * f
    extracted_mass = biomass * product_yield
    residual_biomass = max(0.0, biomass - extracted_mass)
    residual_conc = biomass_concentration * (1.0 - product_yield)
    rate = params.k_extraction * (y_max - product_yield) if y_max > product_yield else 0.0

    return {
        "product_yield": product_yield,
        "residual_biomass": residual_biomass,
        "extracted_mass": extracted_mass,
        "biomass_concentration": residual_conc,
        "feed_rate": feed_rate,
        "specific_rate": rate,
    }

def simulate_trajectory(
    duration_h: float = 40.0,
    n_points: int = 41,
    initial_biomass: float = 20.0,
    initial_volume: float = 5.0,
    params: DissertationParameters = DEFAULT_PARAMETERS,
) -> dict[str, list[float]]:
    """Produce time-series trajectory matching Godot 3D visualization format."""
    dt = duration_h / max(1, n_points - 1)
    times: list[float] = []
    biomass_arr: list[float] = []
    volume_arr: list[float] = []
    feed_arr: list[float] = []
    do_arr: list[float] = []
    glc_arr: list[float] = []
    mu_arr: list[float] = []
    yield_arr: list[float] = []

    y_max = params.yield_scaled_up_15g

    if duration_h <= 20.0:
        # 20-hour extraction test / batch mode
        for step in range(n_points):
            t = step * dt
            times.append(round(t, 2))
            f = extraction_fraction(t, params.k_extraction)
            y = y_max * f
            yield_arr.append(round(y, 4))
            b = initial_biomass * (1.0 - 0.45 * f)
            biomass_arr.append(round(b, 3))
            v = initial_volume + (0.05 * t)
            volume_arr.append(round(v, 3))
            feed = 0.05 if t < 16.0 else 0.0
            feed_arr.append(round(feed, 4))
            do_arr.append(round(95.0 - (5.0 * f), 1))
            glc_arr.append(round(max(0.0, 5.0 * (1.0 - f)), 2))
            mu_arr.append(round(params.k_extraction * math.exp(-params.k_extraction * t), 4))
    else:
        # 5-stage unit-operation train across 40 hours
        for step in range(n_points):
            t = step * dt
            times.append(round(t, 2))

            if t <= 16.0:
                # Stage 1: Acid Demineralisation (0 - 16 h)
                y = 0.0
                b = initial_biomass * (1.0 - 0.08 * (t / 16.0))
                v = initial_volume
                feed = 0.0
                rate = 0.0
            elif t <= 32.0:
                # Stage 2: Alkaline Solubilisation (16 - 32 h)
                t_ext = t - 16.0
                f = extraction_fraction(t_ext, params.k_extraction)
                y = y_max * f
                b = (initial_biomass * 0.92) * (1.0 - 0.45 * f)
                v = initial_volume + (0.05 * t_ext)
                feed = 0.05
                rate = params.k_extraction * (y_max - y)
            elif t <= 34.0:
                # Stage 3: Centrifugation & Neutralisation (32 - 34 h)
                y = y_max
                b = max(0.0, 0.5 * (1.0 - (t - 32.0) / 2.0))
                v = 5.2
                feed = 0.0
                rate = 0.0
            elif t <= 36.0:
                # Stage 4: Ethanol Precipitation (34 - 36 h)
                y = y_max
                b = 0.0
                v = 15.6
                feed = 0.0
                rate = 0.0
            else:
                # Stage 5: Wet Spinning (36 - 40 h)
                y = y_max
                b = 0.0
                v = 2.0
                feed = 0.0
                rate = 0.0

            yield_arr.append(round(y, 4))
            biomass_arr.append(round(b, 3))
            volume_arr.append(round(v, 3))
            feed_arr.append(round(feed, 4))
            do_arr.append(round(95.0, 1))
            glc_arr.append(round(max(0.0, 5.0 * (1.0 - (y / y_max if y_max > 0 else 0.0))), 2))
            mu_arr.append(round(rate, 4))

    return {
        "time_hours": times,
        "biomass_g_per_L": biomass_arr,
        "volume_L": volume_arr,
        "feed_rate_L_per_h": feed_arr,
        "dissolved_oxygen_pct": do_arr,
        "glucose_g_per_L": glc_arr,
        "specific_growth_rate_inv_h": mu_arr,
        "product_yield_g_per_g": yield_arr,
    }