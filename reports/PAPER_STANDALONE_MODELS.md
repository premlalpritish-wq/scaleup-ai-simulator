# Paper → standalone model: what was implemented, and how it is checked

Date: 2026-10-30. Project: `D:\Godot\Scaleup AI\pilot`.

Companion to `reports/PAPER_MODEL_COVERAGE_AUDIT.md`. That document recorded
*which papers have a model*; this one records *what the new standalone models
implement, how faithful each one is shown to be, and which papers remain
evidence-only and why.*

**Standalone is not composable.** Nothing in this step registered a model, added
an adapter, declared a port, or created a compatibility verdict. The three
composed models are still exactly the three they were.

---

## 1. The deliverable in one table

| Paper | Kind | Package | Runnable | Links to the insulin simulation |
|---|---|---|---|---|
| Zielinski et al. 2019 | registered model | `Models/Zielinski` | yes (composed) | **yes** — it *is* the simulation |
| Ganjave et al. 2022 | registered model | `Models/Ganjave` | yes (composed) | **yes** |
| Morris et al. 2011 | registered model | `Models/Morris` | yes (composed) | **yes** |
| Baez et al. 2014 | standalone equation model | `Models/Baez/baez2014` | yes (standalone) | no |
| **Lin et al. 2001** | standalone equation model | `Models/Lin/lin2000` | yes (standalone) | no |
| **Nanchen et al. 2006** | standalone equation model | `Models/nanchen/nanchen2006` | yes (standalone) | no |
| **Simensen et al. 2022** | standalone dataset model | `Models/Simensen/simensen2022` | yes (standalone) | no |
| Baez & Shiloach 2013 | evidence-only | — | no | no |
| Bhattacharya & Dubey 1997 | evidence-only | — | no | no |
| Farrell et al. 2015 | evidence-only | — | no | no |
| Krause et al. 2016 | evidence-only | — | no | no |
| Lemuth et al. 2008 | evidence-only | — | no | no |
| Marish et al. 2013 | evidence-only | — | no | no |
| Mikiewicz et al. 2017 | evidence-only | — | no | no |
| Siew & Zhang 2021 | evidence-only | — | no | no |

The three **bold** rows are new in this step.

## 2. Why the three are encodable, and the eight are not

The test applied to each paper was: *does it print an explicit quantitative
model, equation, or dataset whose values can be read and checked from its own
page?* Not "does it discuss numbers" — a paper can report readings in prose and
still print no model.

**Encodable.** Lin's Appendix prints a complete ODE model plus its parameter
table. Nanchen prints Pirt's chemostat relation plus the fitted parameters for its
own culture. Simensen prints a table of measured mass fractions.

**Not encodable, each for its own stated reason.**

* *Baez & Shiloach 2013* — a transcriptional mechanism study. Growth rates and
  mRNA fold-changes appear in prose and figures; no equation and no model is
  printed. Implementing a "SoxRS model" would mean inventing the kinetics.
* *Bhattacharya & Dubey 1997* — optima and readings are printed (2.67 and
  6.7 × 10² U mg⁻¹ p⁻¹ h⁻¹, OUR 0.135/0.095 mM L⁻¹ h⁻¹, kLa 61 and 84 h⁻¹,
  DO 0.22 mmol L⁻¹), but there is no equation, and the only series are in figures.
  Readings alone are not a dataset that can be encoded without digitising.
* *Farrell et al. 2015* — a DO-stat control strategy and a kLa-matched
  scale-down model, described in prose. No printed equation, no tabulated set.
* *Krause et al. 2016* — a review.
* *Lemuth et al. 2008* — a ¹³C flux and transcriptome study that *uses* models
  published elsewhere; the paper itself prints no rate model.
* *Marish et al. 2013* — a comparative strain characterisation; measurements in
  prose and figures, no equation.
* *Mikiewicz et al. 2017* — constructs and a downstream process; the one "model"
  it names is a program built on Sillero's published model, which is not printed
  in this paper.
* *Siew & Zhang 2021* — a review.

The rule that keeps this honest is the repository's own: **a digitised time
series is not encoded unless a dataset defining the coordinates and the
digitisation provenance is supplied.** A figure with an axis is not a dataset.


## 3. The models, and how each was validated

Each package follows the same pattern the repository already uses for Baez: a
citation with page-level provenance, an explicit unit whitelist, the paper's own
equations or table, a manifest, a `validate()` gate, its own test suite, and a
README/MODEL_REPORT stating what is absent.

### 3.1 Lin et al. (2001) — `lin2000`

**What it implements.** The Appendix's seven differential equations (p. 356):
`V̇ = F`, `Ẋ = (μ − F/V)X`, `Ṡ = −(F/V)(S − Sᵢ) − qS·X`,
`ḊOT = kLa(DOT* − DOT) − qO·X·H`, `Ȧ = −(F/V)A + (qAp − qAc)X`,
`ṙS = YES/X·μ − rS(qESd + μ)`, `ṙO = YEO/X·μ − rO(qEOd + μ)`; the initial values
`μmax = (qSmax − qm)·YX/S,ox`, `rS0`, `rO0`; the whole subsidiary chain including
**both** correction branches (pp. 356-357); Table I's two culture columns
(p. 348); and the pulse method, equation (1) (p. 351). Integration is RK4 over
the printed system, declared as such — the paper prints equations, not a solver.

**How it is validated** (`python -m lin2000 --validate`, 11 checks; 107 tests):

* every printed page carries its own number in the footer, so the
  `pdf_page = printed_page − 346` arithmetic is evidenced, not assumed;
* all 38 Table I numbers are looked up on printed p. 348, and the four abstract
  capacities on p. 347;
* every context quote is on its cited page;
* **a hand-worked evaluation of the printed chain**: W3110 with `cS = cO = 1` at
  the initial state gives `qScap = 1.86`, `qOcap = 0.607`, the oxygen-capacity
  clamp fires, and `μ = 0.45360 h⁻¹`;
* **both correction branches fire**: the clamp at the initial state, and the
  maintenance floor when `qOmax` is reduced, which sets `qmr = qSox = qSoxen`
  and `qSoxan = 0`;
* each printed derivative expression is reproduced term by term;
* a run is finite, biomass rises under feed, and a constant feed grows the
  volume by exactly `F·t`;
* equation (1) reproduces a hand-computed value.

**Declared absent:** a digitised trajectory (no coordinates supplied); values for
`cS`, `cO`, `kLa`, `DOT*` (defined, never valued) and `H` (printed in the
nomenclature only, still a required run input).

### 3.2 Nanchen, Schicker & Sauer (2006) — `nanchen2006`

**What it implements.** Pirt's chemostat relation, printed as equation (3)
(p. 1167), with the paper's own fitted parameters from Table 1 (p. 1167):
`mglc = 0.37 ± 0.09 mmol gdw⁻¹ h⁻¹`, `Yglc_max = 76 ± 3 gdw mol⁻¹`, MG1655 at
37 °C, "This study". The printed relation mixes a mol term with a mmol term, so
the model states `MOL_PER_MMOL = 1000` and applies it; at `μ = 0.4 h⁻¹` the
relation gives 5.633 mmol gdw⁻¹ h⁻¹.

**How it is validated** (`python -m nanchen2006 --validate`, 8 checks; 46 tests):
page numbering; the Table 1 row on p. 1167; every prose reading on its page;
every context quote on its page; `qglc(0) = mglc`; the slope is exactly
`1000/Yglc_max`; the relation round-trips through its inverse; and the observed
yield falls below `Yglc_max` as maintenance bites.

**Declared absent:** the ¹³C flux-ratio equations (1) and (2) — their mass-
distribution inputs are not tabulated — the eleven determined flux ratios
(Fig. 5 / Table S1), and an oxygen-transfer model. Table 1's **eight comparison
strains are deliberately not transcribed**: their column alignment is not
recoverable from the linearised page text, so encoding them would mean guessing.

### 3.3 Simensen et al. (2022) — `simensen2022`

**What it encodes.** Table 1 (p. 9): 42 rows × 3 printed columns of mass
fractions `g gCDW⁻¹`, with every printed SD, and with every printed non-numeric
marker preserved as a marker (`n.d.`, `-` for a value; `NA` for a standard
deviation). Derived: the top-level composition, the recomputed `Sum` row, and the
amino-acid subtotal.

**How it is validated** (`python -m simensen2022 --validate`, 8 checks; 51 tests):
page numbering (`N / 17` footers); every Table 1 cell with ≥ 3 printed digits
looked up on p. 9; the three `Sum` cells and the 91.6 % coverage on their pages;
no non-numeric cell silently becomes `0.0`; the recomputed macromolecule sum
reproduces the printed `0.835` for *This work* (0.8352) and `1.000` for
Neidhardt; and the amino-acid subtotal stays inside the protein pool for the one
column where a single sample produced both numbers.

**Declared absent:** the flux-variability comparison (Eq 1, Table 2) — it needs
iML1515a and its flux ranges, which are not part of the paper. The two printed
totals (0.835 and 91.6 %) are recorded as printed and left unreconciled, because
the paper leaves them so.



## 4. The checks that were added

Two gates, both runnable, both able to fail.

### 4.1 Coverage — `composition.evidence.papers --check`

The paper index now *links* every record instead of only classifying it. Each
entry carries `link_kind` (`composed_model`, `standalone_model`,
`evidence_only`), `link`, and, where applicable, `standalone_module`,
`standalone_artefact_id`, `standalone_kind` and `evidence_record`. The link is
derived from the record plus the standalone registry, so there is no second list
to keep in step.

New failure conditions (added to `PROBLEM_KEYS`, and therefore to the existing
parametrised test that every problem key exists):

| Key | Fails when |
|---|---|
| `papers_without_a_link` | a paper points nowhere |
| `unlinked_model_packages` | a package is neither registered nor a known standalone model |
| `conflicting_claims` | a paper is reported as both composable and standalone |
| `orphan_standalone_entries` | a standalone entry names a folder the index does not record |

It also reports an `execution` block — the three-way split — so "which papers are
executable standalone / evidence-only / composable" is always machine-readable.

### 4.2 Model fidelity — `composition.evidence.standalone --check --fidelity`

`composition/composition/evidence/standalone.py` registers the four standalone
packages (paper folder, package path, module, artefact id, kind, scope, and the
name of the module-level gate). Its checks:

* **structural** — package directory, module `__init__.py`, committed
  `manifest.json`, the manifest's `artefact_id` equal to the registry's, the
  manifest *not* claiming a composition registration, no duplicate paper folders
  or modules, and a known kind;
* **fidelity** — each package's own `validate()` is imported from its checkout
  and run, and its `ok` flag and check list are surfaced. Baez predates the gate
  and its own suite pins its exact module set, so it is checked through its public
  API instead: its manifest must still equal the committed snapshot, its one
  equation must evaluate, and it must still declare no registration;
* **separation** — every standalone package must be absent from
  `composition.adapters.REGISTRATIONS` and from `known_models()`.

`composition/tests/test_paper_model_fidelity.py` (19 tests) wraps both gates and
adds the negative controls: the split must be exactly 3 / 4 / 8, every entry must
link, every element of `PROBLEM_KEYS` must exist, and the fidelity gate must be
able to report a failure.

## 5. What was deliberately not done

* **No registration.** `composition/composition/adapters/__init__.py` is
  unchanged; `python -m composition.registry` still lists three models.
* **No port declarations, no adapters, no workers** for any new package.
* **No compatibility verdict.** `composition/cross_model.py` is unchanged, and no
  paper was given an engine position it does not have. Every unregistered paper
  still reports `not_evaluated` with a reason.
* **No parameter transfer.** Each package's context is recorded and states the
  mismatch with `zielinski2019.rhi_process`; none of those numbers was carried
  into the insulin process.
* **No invented data.** Where a paper's quantitative content is a figure with an
  axis, nothing was digitised; where an equation's inputs are not tabulated, the
  equation is declared absent with the reason.
* **No scientific verdict.** A passing test shows the transcription matches the
  printed page; it does not show the model is right.

## 6. Reproducing the result

```
# coverage: which papers are executable standalone / evidence-only / composable
cd composition
python -m composition.evidence.papers --check

# structural + fidelity gate over every standalone package
python -m composition.evidence.standalone --check --fidelity

# the composition-layer gates
python -m pytest tests/test_paper_coverage.py tests/test_paper_model_fidelity.py -q

# each standalone package's own suite
cd ../Models/Lin      && python -m pytest tests -q          # 107 tests
cd ../nanchen         && python -m pytest tests -q          #  46 tests
cd ../Simensen        && python -m pytest tests -q          #  51 tests

# the composed models are untouched
cd ../../composition && python -m composition.registry
```

Expected final line of the fidelity gate:

```
PASS -- every standalone model is present and matches its paper
```

