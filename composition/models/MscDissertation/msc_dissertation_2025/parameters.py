"""Empirically measured parameters from MSc Dissertation (2025)."""
from dataclasses import dataclass

@dataclass(frozen=True)
class DissertationParameters:
    yield_small_scale_neutralised: float = 0.26      # g/g dry biomass (26%)
    yield_scaled_up_15g: float = 0.3307              # g/g dry biomass (33%)
    mannuronic_guluronic_ratio: float = 2.491        # M/G ratio (Table 3)
    alginate_purity: float = 0.915                   # 91.5% uronic acids
    mw_extracted_kda: float = 251.0                  # kDa (GPC Table 4)
    mn_extracted_kda: float = 215.0                  # kDa (GPC Table 4)
    pdi_extracted: float = 1.17                      # PDI
    fibre_tensile_strength_mpa: float = 29.3         # MPa (Figure 8)
    fibre_citric_crosslinked_mpa: float = 43.1       # MPa (Figure 8)
    fibre_youngs_modulus_mpa: float = 0.10           # MPa (Table 6)
    fibre_elongation_at_break_pct: float = 29.31     # % (Table 6)
    k_extraction: float = 0.35                       # 1/h rate constant
    citric_acid_pct: float = 4.0                     # % w/v
    na2co3_pct: float = 2.0                          # % w/v
    extraction_temp_c: float = 20.0                  # degC
    target_ph: float = 7.0                           # neutralised pH

DEFAULT_PARAMETERS = DissertationParameters()
