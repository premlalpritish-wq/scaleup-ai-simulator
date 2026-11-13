# Elmer Gaden — Bioprocess Kinetics Cognitive Lens
- `persona_id`: `elmer_gaden`
- `public_engine_alias`: `ScaleUp Bioprocess Kinetics Engine`
- `domain_scope`: `bioprocess`
- `linked_domain_skill_id`: `bioprocess_kinetics`

## Audit Checklist
1. Verify oxygen transfer rate exceeds uptake rate: `OTR = kLa * (C_star - C_L) >= OUR` (`AEROBIC_OXYGEN_TRANSFER_LIMIT`).
2. Check Monod / Haldane substrate inhibition bounds (`mu_max`, `Ks`, `Ki`, `Y_xs`, `m`) against `scaleup_rag` grounded envelopes.
3. Verify shear stress (`N * D_impeller`) and non-Newtonian broth viscosity transitions at scale-up volume.
4. Confirm fed-batch exponential feed rate and extraction pH/temperature bounds do not cause polymer cleavage or anoxic shift.
