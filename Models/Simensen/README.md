# Simensen et al. (2022) — the measured biomass composition, standalone

An isolated package that encodes **only** what Simensen and co-authors print as a
quantitative dataset in *Experimental determination of Escherichia coli biomass
composition for constraint-based metabolic modeling*, PLOS ONE 17(1):e0262450,
2022 ([doi:10.1371/journal.pone.0262450](https://doi.org/10.1371/journal.pone.0262450)):

* **Table 1** (printed **p. 9**): the measured macromolecular composition of
  *E. coli* K-12 MG1655, in `g gCDW-1`, in all three printed columns
  (*This work*, Neidhardt, Beck et al.), with every printed standard deviation
  and every printed non-numeric marker (`n.d.`, `-`, `NA`) preserved;
* the **derived sums**: the table's own `Sum` row recomputed from the encoded
  rows (0.8352 for *This work*, 1.000 for Neidhardt);
* the **prose figures** beside the table: 91.6 % overall coverage (p. 1), the
  three `Sum` cells, and the 5.1 % ribose measured in addition to the listed
  carbohydrates (p. 12);
* the cultivation context the measurement belongs to (**pp. 1, 3**).

Nothing else. No other model in this repository is touched, imported or coupled
to.

**Location:** `Models/Simensen/`, beside `Models/Lin/` and `Models/nanchen/`.
Run its commands from that directory.

---

## ⚠️ Read this before quoting any number from here

**This package is a dataset with provenance, not a simulator.**

* It **does not predict** growth, flux or yield. The composition it holds was
  measured in one condition.
* It **does not implement** the flux-variability comparison (Eq 1, Table 2). That
  needs the genome-scale model iML1515a and its flux ranges, which are not part
  of this paper.
* It **coerces nothing.** A cell the paper prints as `n.d.` (not detected), `-`
  (not measured) or `NA` (no SD) keeps that marker; it is never read as 0.0.
* It **is not the insulin simulation's composition.** See "Process context".

## What is encoded

| Component | What it is | Where |
|---|---|---|
| Table 1, all rows and columns | mass fractions `g gCDW-1` with SDs and printed markers | `simensen2022.model.TABLE_1` |
| Top-level composition | protein, RNA, DNA, carbohydrate, lipid (and Others where printed) | `simensen2022.model.composition` |
| Recomputed sum | the arithmetic the table's `Sum` row implies | `simensen2022.model.computed_macromolecule_sum` |
| Amino-acid subtotal | the resolved part of the protein pool | `simensen2022.model.amino_acid_sum` |
| Prose figures | 91.6 % coverage, the three sums, 5.1 % ribose | `simensen2022.model.REPORTED_STATEMENTS` |
| Context | strain, no construct, M9 + 2 % glucose, 3 L BioFlo 115, 1 L, 37 °C | `simensen2022.context` |

### The `This work` column, as printed (printed p. 9)

| Component | g/gCDW | SD |
|---|---|---|
| Protein | 0.54 | 0.02 |
| RNA | 0.190 | 0.004 |
| DNA | 0.013 | 0.003 |
| Carbohydrate | 0.0312 | 0.0005 |
| Lipid | 0.061 | 0.002 |
| **Sum (recomputed)** | **0.8352** | — |
| **Sum (printed)** | **0.835** | — |

The 18 amino-acid rows are also encoded; they sum to 0.536 for *This work*, which
is the resolved part of the 0.54 protein pool. The package reports both and
reconciles neither.

### Two printed totals, not one

The table's `Sum` row prints **0.835** (This work), **1.000** (Neidhardt) and
**0.643** (Beck et al.). The abstract prints an overall coverage of **91.6 %**.
Both are recorded as printed and the package does not reconcile them, because the
paper does not: the table's sum covers the rows it lists, the abstract's coverage
is its own figure.

## Process context (and what this package does *not* connect to)

| | Simensen et al. (2022) | Zielinski et al. (2019), the composition layer's target |
|---|---|---|
| strain | *E. coli* K-12 MG1655 (ATCC 700926), non-recombinant | *E. coli* 20 IBA 1 (CSH50R derivative) |
| construct | none | pIBAINS |
| medium | modified minimal M9, 2 % (w/v) glucose | GMS |
| reactor | 3 L Eppendorf New Brunswick BioFlo 115 | 7.5 L Bioflo Celligen 310 |
| scale | 1 L | 4 L |
| mode | batch, balanced exponential growth | batch with pH-stat glucose feeding |
| temperature | 37 °C | 30 °C |

The paper states explicitly that biomass composition is condition-dependent, and
these are different conditions. No value is transferred, and this package adds no
adapter registration.

## Running it

```
cd Models/Simensen
python -m simensen2022 --validate                      # the fidelity checks
python -m simensen2022 --check manifest.json
python -m simensen2022 --composition this_work
python -m pytest tests                                 # 51 tests
```

## Known limitations

* **No flux analysis.** Eq 1 and Table 2 need iML1515a, which is not supplied.
* **One measurement condition.** The composition is the paper's own culture, not
  a general one, and the paper says composition depends on the condition.
* **Two printed totals are left unreconciled** (0.835 versus 91.6 %), as the
  paper leaves them.
* **A passing test does not establish scientific validity.** It establishes that
  this implementation matches the printed table.
