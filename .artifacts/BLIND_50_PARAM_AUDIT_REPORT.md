# 50-Parameter Blind Extraction & Epistemic Quarantine Audit

## Executive Summary (Isolated `sqlite:///:memory:` Cold Run)

| Metric | Result | Target |
|---|---|---|
| Quarantine Precision | **100.0%** (40/40) | 100.0% |
| Extraction & Conversion Recall (Group A) | **100.0%** (40/40) | >= 95.0% |
| Range / ± Bound Accuracy | **100.0%** (15/15) | >= 95.0% |
| Operating Envelope Completeness | **100.0%** (40/40) | >= 95.0% |
| Adversarial Abstention / Quarantine Block Rate (Group B) | **100.0%** (10/10) | 100.0% |
| Cold-Miss Avg Latency | **2.91 ms** | — |
| Warm SQLite Read-Through Avg Latency | **0.61 ms** | — |

## All 50 Audit Cases

| ID | Group | Category | Entity | Expected | Extracted | Status |
|---|---|---|---|---|---|---|
| A01 | A_GROUNDED | Range+Env | `specific_growth_rate_mu_max` | 0.45 [0.38, 0.52] | 0.45 [0.38, 0.52] | PASS |
| A02 | A_GROUNDED | UnitConv+Env | `feed_glucose_concentration` | 450.0 | 449.99999999999994 | PASS |
| A03 | A_GROUNDED | PlusMinus+Env | `mass_transfer_kla` | 180.0 [165.0, 195.0] | 180.0 [165.0, 195.0] | PASS |
| A04 | A_GROUNDED | UnitConv+Env | `oxygen_saturation_c_star` | 0.0072 | 0.007199999999999999 | PASS |
| A05 | A_GROUNDED | UnitConv+Env | `dilution_rate` | 0.12 | 0.12 | PASS |
| A06 | A_GROUNDED | Range+Env | `methanol_uptake_rate` | 0.15 [0.12, 0.18] | 0.15 [0.12, 0.18] | PASS |
| A07 | A_GROUNDED | Scalar+Env | `protein_titer` | 4.8 | 4.799999999999999 | PASS |
| A08 | A_GROUNDED | PlusMinus+Env | `maintenance_coefficient` | 0.025 [0.02, 0.03] | 0.025 [0.02, 0.03] | PASS |
| A09 | A_GROUNDED | UnitConv+Env | `dynamic_viscosity` | 0.048 | 0.048 | PASS |
| A10 | A_GROUNDED | Range+Env | `alginate_yield` | 31.0 [28.0, 34.0] | 31.0 [28.0, 34.0] | PASS |
| A11 | A_GROUNDED | PlusMinus+Env | `tensile_strength` | 425.0 [400.0, 450.0] | 425.0 [400.0, 450.0] | PASS |
| A12 | A_GROUNDED | UnitConv+Env | `slurry_concentration` | 15.0 | 15.0 | PASS |
| A13 | A_GROUNDED | PlusMinus+Env | `chromatography_recovery` | 82.5 [78.0, 87.0] | 82.5 [78.0, 87.0] | PASS |
| A14 | A_GROUNDED | UnitConv+Env | `transmembrane_pressure` | 2.5 | 2.5 | PASS |
| A15 | A_GROUNDED | UnitConv+Env | `eluate_viscosity` | 0.00135 | 0.00135 | PASS |
| A16 | A_GROUNDED | Scalar+Env | `binding_capacity` | 55.0 | 55.0 | PASS |
| A17 | A_GROUNDED | Range+Env | `catalytic_turnover_rate` | 5400.0 [4320.0, 6480.0] | 5400.0 [4320.0, 6480.0] | PASS |
| A18 | A_GROUNDED | Scalar+Env | `substrate_affinity_km` | 12.5 | 12.499999999999998 | PASS |
| A19 | A_GROUNDED | Scalar+Env | `activation_energy` | 115000.0 | 115000.0 | PASS |
| A20 | A_GROUNDED | PlusMinus+Env | `glucose_conversion` | 76.0 [73.0, 79.0] | 76.0 [73.0, 79.0] | PASS |
| A21 | A_GROUNDED | Range+Env | `reformer_pressure` | 27.0 [24.0, 30.0] | 27.0 [24.0, 30.0] | PASS |
| A22 | A_GROUNDED | Scalar+Env | `reforming_enthalpy` | 206200.0 | 206200.0 | PASS |
| A23 | A_GROUNDED | UnitConv+Env | `compressor_discharge` | 400.0 | 400.0 | PASS |
| A24 | A_GROUNDED | Range+Env | `psa_hydrogen_recovery` | 88.0 [86.0, 90.0] | 88.0 [86.0, 90.0] | PASS |
| A25 | A_GROUNDED | Scalar+Env | `shift_enthalpy` | -41200.0 | -41200.0 | PASS |
| A26 | A_GROUNDED | UnitConv+Env | `syngas_heat_capacity` | 0.0345 | 0.0345 | PASS |
| A27 | A_GROUNDED | PlusMinus+Env | `co2_capture_efficiency` | 94.0 [92.5, 95.5] | 94.0 [92.5, 95.5] | PASS |
| A28 | A_GROUNDED | Scalar+Env | `catalyst_bulk_density` | 1150.0 | 1150.0000000000002 | PASS |
| A29 | A_GROUNDED | Range+Env | `synthesis_pressure` | 260.0 [240.0, 280.0] | 260.0 [240.0, 280.0] | PASS |
| A30 | A_GROUNDED | UnitConv+Env | `inlet_gas_pressure` | 260.0 | 260.0 | PASS |
| A31 | A_GROUNDED | Scalar+Env | `molar_entropy` | -0.0994 | -0.0994 | PASS |
| A32 | A_GROUNDED | Scalar+Env | `nitrogen_conversion` | 18.5 | 18.5 | PASS |
| A33 | A_GROUNDED | UnitConv+Env | `solar_irradiance` | 450.0 | 450.0 | PASS |
| A34 | A_GROUNDED | Range+Env | `biomass_productivity` | 0.12 [0.1, 0.14] | 0.11999999999999998 [0.09999999999999999, 0.13999999999999999] | PASS |
| A35 | A_GROUNDED | Scalar+Env | `electrolyzer_pressure` | 30.0 | 30.0 | PASS |
| A36 | A_GROUNDED | Scalar+Env | `faradaic_efficiency` | 98.5 | 98.5 | PASS |
| A37 | A_GROUNDED | UnitConv+Env | `broth_viscosity` | 0.012 | 0.012 | PASS |
| A38 | A_GROUNDED | PlusMinus+Env | `lipid_content` | 48.0 [44.5, 51.5] | 48.0 [44.5, 51.5] | PASS |
| A39 | A_GROUNDED | UnitConv+Env | `impeller_turnover` | 180.0 | 180.0 | PASS |
| A40 | A_GROUNDED | Scalar+Env | `biomass_titer` | 85.0 | 84.99999999999999 | PASS |
| B01 | B_ADVERSARIAL | MissingParam | `saturation_constant_ks` | ABSTAIN / REJECT | ParameterGap | PASS |
| B02 | B_ADVERSARIAL | MissingParam | `catalyst_pore_tortuosity` | ABSTAIN / REJECT | ParameterGap | PASS |
| B03 | B_ADVERSARIAL | MissingParam | `mannuronic_guluronic_ratio` | ABSTAIN / REJECT | ParameterGap | PASS |
| B04 | B_ADVERSARIAL | MissingParam | `inhibition_constant_ki` | ABSTAIN / REJECT | ParameterGap | PASS |
| B05 | B_ADVERSARIAL | DimMismatch | `specific_growth_rate` | ABSTAIN / REJECT | ParameterGap | PASS |
| B06 | B_ADVERSARIAL | DimMismatch | `activation_energy` | ABSTAIN / REJECT | ParameterGap | PASS |
| B07 | B_ADVERSARIAL | DimMismatch | `eluate_viscosity` | ABSTAIN / REJECT | ParameterGap | PASS |
| B08 | B_ADVERSARIAL | InvalidDOI | `specific_growth_rate` | ABSTAIN / REJECT | ParameterGap | PASS |
| B09 | B_ADVERSARIAL | ShortSnippet | `reformer_pressure` | ABSTAIN / REJECT | ParameterGap | PASS |
| B10 | B_ADVERSARIAL | InconsistentRange | `specific_growth_rate` | ABSTAIN / REJECT | ParameterGap | PASS |
