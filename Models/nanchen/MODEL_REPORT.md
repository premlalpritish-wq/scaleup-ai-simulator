# MODEL_REPORT — Nanchen, Schicker & Sauer (2006)

What was implemented, how it was verified, and what is knowingly absent.

**A passing software test verifies that this implementation matches the printed
relation and the printed parameter row it was given. It does not independently
establish scientific validity.** The package reproduces no figure of the paper.

Source: A. Nanchen, A. Schicker, U. Sauer, *Nonlinear Dependency of Intracellular
Fluxes on Growth Rate in Miniaturized Continuous Cultures of Escherichia coli*,
Applied and Environmental Microbiology 72(2):1164-1172, 2006.
doi:10.1128/AEM.72.2.1164-1172.2006.

---

## 1. Why this paper has a model

The paper prints one growth-physiology relation — Pirt's chemostat model, its
equation (3) on p. 1167 — and fits it to its own mini-scale-chemostat data,
reporting the fitted maintenance coefficient and maximal molar yield for
*E. coli* MG1655 in Table 1 on the same page. A printed equation plus its own
fitted parameters in the paper's own context is exactly what a paper-faithful
standalone implementation needs.

## 2. Contract → implementation

| Printed item | Page | Implemented in | Verified by |
|---|---|---|---|
| Equation (3), `qglc = mu/Yglc_max + mglc` | 1167 | `model.q_glc` | `tests/test_nanchen2006.py`, `validate` |
| Equation (3) inverted | 1167 | `model.mu_from_q_glc` | `tests/test_nanchen2006.py` |
| Table 1, MG1655 "This study" row | 1167 | `model.THIS_STUDY` | `validate` |
| Reported thresholds and OD factor | 1165-1167 | `model.REPORTED_READINGS` | `validate` |
| Cultivation context | 1164-1165 | `context.EXPERIMENTAL_CONTEXT` | `validate` |
| Manifest | — | `manifest.build_manifest`, `manifest.json` | `tests/test_nanchen2006.py` |

## 3. Fidelity: what is checked, and how

`python -m nanchen2006 --validate` runs the same eight checks the composition
layer's `test_paper_model_fidelity.py` runs:

1. every printed page has extracted text;
2. every page prints its own number (`1164` … `1172`);
3. the Table 1 values `0.37`, `0.09`, `76`, `3` are on printed p. 1167;
4. every prose reading (0.4, 0.7, 0.41) is on its cited page;
5. every context quote is on its cited page;
6. every declared equation cites a populated page;
7. `qglc(0) = mglc`, the slope is exactly `1000/Yglc_max`, and the relation
   round-trips through its inverse;
8. the observed yield falls below `Yglc_max` and rises with growth rate.

## 4. What is knowingly absent

1. **The ¹³C metabolic-flux-ratio equations (1) and (2).** They relate
   proteinogenic amino-acid mass distributions to the OAA-origin fractions; the
   paper tabulates neither the distributions nor a solved set, and states it
   solved them iteratively from random starts. Implementing them would require
   inventing the input data.
2. **The eleven determined flux ratios** (Fig. 5 / Table S1) — not supplied as a
   dataset.
3. **Eight of Table 1's nine rows.** The comparison strains' column alignment is
   not recoverable from the linearised page text, so encoding them would mean
   guessing which printed number is which. The paper's own row is encoded.
4. **An oxygen-transfer or kLa model** — the paper prints none.
5. **No composition registration.** The process is not the composition layer's
   target; no adapter was added.
6. **Tests cannot establish scientific validity.** They establish agreement with
   the printed relation and the printed parameter row.
