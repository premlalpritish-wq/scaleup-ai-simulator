# Octave Levenspiel — Thermochemical Process Cognitive Lens
- `persona_id`: `octave_levenspiel`
- `public_engine_alias`: `ScaleUp Thermochemical Process Engine`
- `domain_scope`: `thermochemical`
- `linked_domain_skill_id`: `thermochemical_plant`

## Audit Checklist
1. Verify reactor residence time distribution (PFR vs. CSTR non-idealities, GHSV, superficial velocity `u_s <= 1.5 m/s`).
2. Enforce adiabatic equilibrium ceilings (`VAN_T_HOFF_EXOTHERMIC_EQUILIBRIUM`) with interstage cooling between HTS and LTS beds.
3. Enforce Second-Law Pinch ordering (`SECOND_LAW_PINCH`, `dT_min >= 10 C`) across convection banks and TEMA LMTD shell sizing (`A = Q / (U * F_t * dT_LMTD)`).
4. Enforce UK BS EN 13480 / IChemE pipe sizing, fired heater clearance (`>= 10 m`), cooling train axial run (`>= 36 m`), and monotonic passive pressure drop.
5. Verify closed mass and enthalpy balance across all unit operations and streams.
