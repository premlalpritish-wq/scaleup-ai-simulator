# MODEL_REPORT — Simensen et al. (2022)

What was encoded, how it was verified, and what is knowingly absent.

**A passing software test verifies that this implementation matches the printed
table it was given. It does not establish scientific validity, and it certifies no
composition for any other strain, medium, scale or growth condition.**

Source: V. Simensen, C. Schulz, E. Karlsen, S. Bråtelund, I. Burgos, L. B.
Thorfinnsdottir, L. García-Calvo, P. Bruheim, E. Almaas, *Experimental
determination of Escherichia coli biomass composition for constraint-based
metabolic modeling*, PLOS ONE 17(1):e0262450, 2022.
doi:10.1371/journal.pone.0262450.

---

## 1. Why this paper has a standalone implementation

Table 1 (printed p. 9) is a complete quantitative dataset: 42 components × 3
printed columns of mass fractions `g gCDW-1`, with standard deviations and
explicit markers for what was not measured. A printed table of values is
encodable in a way that a figure is not, and it is the paper's own measurement in
the paper's own condition. So it is a **dataset model**, not a simulator.

## 2. Contract → implementation

| Printed item | Page | Implemented in | Verified by |
|---|---|---|---|
| Table 1, all rows and columns | 9 | `model.TABLE_1` | `tests/test_simensen2022.py`, `validate` |
| Printed SDs and markers (`n.d.`, `-`, `NA`) | 9 | `model.Cell` (`note`, `sd_note`) | `validate`, `tests/test_simensen2022.py` |
| Table 1 `Sum` row | 9 | `model.printed_sum` | `validate` |
| Recomputed macromolecule sum | — | `model.computed_macromolecule_sum` | `validate` |
| Top-level composition (BOF fractions) | 9 | `model.composition` | `tests/test_simensen2022.py` |
| Amino-acid subtotal | — | `model.amino_acid_sum` | `validate` |
| Prose figures (91.6 %, sums, 5.1 % ribose) | 1, 9, 12 | `model.REPORTED_STATEMENTS` | `validate` |
| Cultivation context | 1, 3 | `context.EXPERIMENTAL_CONTEXT` | `validate` |

## 3. Fidelity: what is checked, and how

`python -m simensen2022 --validate` runs the same eight checks the composition
layer's `test_paper_model_fidelity.py` runs:

1. every printed page (1-17) has extracted text;
2. every page prints its own `N / 17` footer;
3. every Table 1 cell whose printed form has ≥ 3 significant digits is looked up
   verbatim on printed p. 9 (short decimals such as 0.1 occur elsewhere on the
   page, so checking them would be noise rather than evidence);
4. no cell with a printed non-numeric marker holds a number;
5. the three `Sum` cells and the 91.6 % coverage are on their cited pages;
6. every context quote is on its cited page;
7. the recomputed macromolecule sum reproduces the printed `Sum` row:
   `0.8352 ≈ 0.835` for *This work*, `1.000` for Neidhardt, `0.641 ≈ 0.643` for
   Beck et al.;
8. the amino-acid subtotal (0.536) stays inside the protein pool (0.54) for the
   one column where a single sample produced both numbers. It is deliberately not
   asserted for the comparison columns, whose `Protein` values and amino-acid
   lists come from different publications.

## 4. What is knowingly absent

1. **The flux-variability comparison (Eq 1, Table 2).** `xi` is a function of two
   constraint-based solutions of iML1515a; the model file and the flux ranges are
   not part of this paper. Implementing `xi` would mean inventing the flux
   distribution.
2. **Table 2's reaction flux shifts** — a selection computed from the model
   above, not a complete table.
3. **A single reconciled total.** The table prints `0.835` and the abstract prints
   `91.6 %`; both are recorded as printed and neither is derived from the other,
   because the paper does not reconcile them.
4. **Any other condition's composition.** The paper states that biomass
   composition depends on strain, medium and condition; this dataset is one
   measurement.
5. **No composition registration.** The process is not the composition layer's
   target; no adapter was added and no value was transferred.
6. **Tests cannot establish scientific validity.** They establish agreement with
   the printed table.
