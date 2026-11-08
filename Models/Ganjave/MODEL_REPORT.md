# MODEL_REPORT — Ganjave et al. (2022) cybernetic growth model

What was implemented, how it was checked, and what remains unresolved.

**A passing test establishes that this implementation matches the printed
equations and the supplied specification. It does not establish that the model
reproduces the paper**, and it does not — see §7.

Source: S. D. Ganjave, V. A. J. E. S. Waghmare, P. P. Wangikar, *High cell
density cultivation of E. coli in shake flasks for the production of
recombinant proteins*, Biotechnology Reports 33 (2022) e00694.
doi:10.1016/j.btre.2021.e00694. All equations were transcribed from printed
pages 3–4 and checked against the extracted text of the article PDF.

---

## 1. Equations implemented

All sixteen printed equations, one function or residual each. See `README.md`
for the full table. Four transcription decisions were required; they are in
`models/kinetics.py::TRANSCRIPTION_NOTES`, attached to every run as
diagnostics, and covered by tests.

| Note | What the paper prints | What was done |
|---|---|---|
| TN-01 | eq. (1)/(2) written `= 0`, which reads like a balance | implemented as checkable residuals; **not** integrated. They define the yields |
| TN-02 | Table 2 prints `e20/em1` for the second initial enzyme ratio | read as `e2(0)/e_m2 = 0.874`; printed string preserved in the quote. **Unresolved** |
| TN-03 | DO is a percentage throughout | kept as a percentage; conversion to g/L requires `C*` and is explicit |
| TN-04 | eq. (11)/(15) print the oxygen factor as the **quotient** `100/C*` | this package had transcribed it as the product `100*C*`, because the PDF text layer drops the fraction bar. **Corrected**, with the evidence in `OXYGEN_BALANCE_REPORT.md` and `tests/test_oxygen_balance.py` |
| TN-05 | recipes in % w/v, eq. (13)/(14) need g/L | 1 % w/v = 10 g/L, applied explicitly at the boundary |

The oxygen correction is the substantive change since the first release of this
package. `EQUATIONS_VERSION` moved from `1.0.0` to `1.1.0` so that a run
recorded under the transposed reading cannot be mistaken for a run under the
corrected one; the input digest changed accordingly. **No parameter value was
altered** — `kLa`, `C*`, `Yo1`, `Yo2` and the rest are as Table 2 prints them.

### The enzyme state

`e_k/e_mk`, a **normalised fraction**. Eq. (5) multiplies `mum_k` by the ratio
and eq. (7) differentiates it directly, so `e_mk` is never a state and needs
no value. The two initial fractions come from the Table 2 parameters.

### Batch and fed-batch are separate

`models/batch.py` and `models/fed_batch.py` expose different right-hand sides.
Batch has no dilution and no volume term; feeding a batch run raises rather
than being ignored. The tests assert that the two differ in every balance
except the two enzyme terms.

## 2. Parameters and their provenance

`data/reference_parameters.json`, loaded and validated by
`schemas/parameters.py`. Every record carries symbol, unit, semantic quantity,
provenance, printed location, and any conversion.

| Class | Parameters |
|---|---|
| `fitted` (Table 2) | `mum1`, `mum2`, `K11`, `K12`, `K22`, `Ko1`, `Ko2`, `Y11`, `Y12`, `Y22`, `Yo1`, `Yo2`, `e_ratio1_0`, `e_ratio2_0`, `beta1`, `beta2` |
| `reported` | `kLa` (measured, p. 3), `C_star` (p. 2), `of_minimum` (informational, not read by the equations) |

Table 2 is a **fitted** set — the paper estimates it against six fed-batch
experiments with a hybrid genetic-algorithm/`fmincon` scheme (p. 5) and
validates on two more. The values are printed, but they are a fit, and the
package records them as `Provenance.FITTED` with the procedure attached rather
than as measurements.

`Parameter.__post_init__` refuses a record that has no value with a known
provenance, a known provenance with no source, a fitted record with no
procedure, or a unit that is not registered **for that quantity** — the last
check matters because `g/L` is registered for three different quantities in
this paper and `%` for two.

## 3. Initial conditions

`models/initial.py` encodes which of the seven the paper states:

| State | Value | Provenance |
|---|---|---|
| `S1` | 2.76 g/L (p. 2) | `reported` |
| `V` | 0.1 L = 100 mL (p. 2) | `reported` |
| `e1`, `e2` | 0.082, 0.874 (Table 2) | `reported` |
| `X`, `S2`, `DO` | — | `assumed`, **required from the caller** |

`X₀` is not derivable from the reported initial OD600 of 0.05 because the
paper prints no OD600-to-dry-cell-weight calibration. `models/initial.py`
raises `MissingInitialCondition` rather than defaulting, and
`InitialConditions.__post_init__` raises `UnresolvedInitialCondition` for an
incomplete set, so a half-populated culture cannot reach the solver.

## 4. Numerical method

Classical RK4 with step-doubling error control (`models/solver.py`). Standard
library only; no third-party runtime dependency, consistent with the
repository.

Two findings from building it, both recorded in the module docstring:

* **The model is mildly stiff.** `kLa = 133 h⁻¹` relaxes the dissolved-oxygen
  state with a time constant of 7.5 ms against biomass dynamics at
  `mu ≈ 0.6–1.5 h⁻¹`. The first attempt used `h_max = 0.1 h`, thirteen
  relaxation times and far outside RK4's stability region, and produced
  dissolved oxygen above 100 %. The default is now `h_max = 0.01 h`
  (`h·kLa = 1.33`), and a test asserts `h_max·kLa < 2.8`.
* **A trial step must not be committed.** A rejected step initially left `t`
  and `y` advanced to the rejected values, which corrupted the trajectory. The
  loop now commits only after acceptance.

An out-of-range candidate is a **rejected step**, retried with a halved step
up to a bounded number of times; nothing is clipped. A non-finite value, or a
right-hand side evaluated outside the model's domain, is handled by shortening
the step; exhausting the retry budget is a structured failure with **no
trajectory returned**.

## 5. Acceptance tests

`cd Models/Ganjave && python -m pytest tests` → **292 passed, 0 skipped**.

| ID | Requirement | Where | Tests |
|---|---|---|---:|
| GJ-01 | every Table 2 parameter against value, unit, provenance | `test_provenance.py::TestParameterFidelity` | 56 |
| GJ-02 | response bounds and monotonicity | `test_kinetics.py::TestResponseBounds` | 10 |
| GJ-03 | zero limiting substrate → zero, no NaN | `test_kinetics.py::TestZeroSubstrate` | 5 |
| GJ-04 | `mu = mu1 + mu2` | `test_kinetics.py::TestGrowthAggregation` | 4 |
| GJ-05 | enzyme derivatives vs hand calculation | `test_kinetics.py::TestEnzymeDynamics` | 5 |
| GJ-06 | `dX/dt = mu·X` | `test_batch.py::TestBiomassBalance` | 3 |
| GJ-07 | substrate balances, both consumption routes | `test_batch.py::TestSubstrateBalances` | 6 |
| GJ-08 | oxygen transfer and consumption separately | `test_batch.py::TestOxygenBalance` | 9 |
| GJ-09 | feed dilution is negative | `test_fed_batch.py::TestDilution` | 5 |
| GJ-10 | substrate input from feed concentration and `F/V` | `test_fed_batch.py::TestSubstrateInput` | 5 |
| GJ-11 | `dV/dt = F`, constant feed → expected volume | `test_fed_batch.py::TestOxygenAndVolume` | 6 |
| GJ-12 | batch and fed-batch differ | `test_fed_batch.py::TestBatchVersusFedBatch` | 5 |
| GJ-13 | finite, reproducible, in-domain integration | `test_acceptance.py::TestIntegration` | 9 |
| GJ-14 | missing initial conditions stay unresolved | `test_acceptance.py::TestMissingInitialConditions` | 4 |
| GJ-15 | distinct provenance classes | `test_provenance.py::TestParameterIntegrity`, `::TestInitialConditionProvenance`, `::TestSimulationProvenance` | 15 |
| GJ-16 | reference results stored as records | `test_provenance.py::TestReferenceRecords` | 11 |
| GJ-17 | structured diagnostics, no plausible success | `test_acceptance.py::TestStructuredFailures` | 11 |
| GJ-18 | quantity keys, units, value states, refusals | `test_acceptance.py::TestCompositionCompatibility` | 18 |
| GJ-O2-01…08 | the oxygen-balance investigation | `test_oxygen_balance.py` | 66 |

Module totals (measured with `--collect-only`): `test_provenance.py` 87,
`test_oxygen_balance.py` 66, `test_acceptance.py` 52, `test_kinetics.py` 31,
`test_fed_batch.py` 28, `test_batch.py` 23 — **287**.

The five PDF-backed tests inside `test_oxygen_balance.py` re-measure the
article's glyph geometry; they ran here (PyMuPDF and the PDF are both present)
rather than skipping.

Every expected derivative in the equation tests is written out as arithmetic on
the printed Table 2 numbers rather than produced by the implementation, so a
passing test means the code agrees with the paper.

**Mutation check.** Reverting the oxygen factor to the transposed product
reading in a scratch copy makes 11 of the new tests fail, spanning GJ-O2-01,
-04, -05, -07 and -08 — so the suite is sensitive to the defect it was written
for.

## 6. Worked example

```bash
cd Models/Ganjave
python -m models simulate --mode fed_batch --duration 24 \
    --X 0.05 --S2 5 --DO 100 \
    --glycerol-percent 17.5 --yeast-percent 24.5 --flow-ml-h 0.72 --feed-start 6 \
    --output-times 0 6 12 18 24 --summary
```

Inputs and their provenance:

| Input | Value | Provenance |
|---|---|---|
| `X₀`, `S2₀`, `DO₀` | 0.05 g/L, 5.0 g/L, 100 % | **assumed** — not stated in the paper |
| `S1₀`, `V₀`, `e1₀`, `e2₀` | 2.76 g/L, 0.1 L, 0.082, 0.874 | reported |
| feed | 175 g/L glycerol, 245 g/L yeast extract, 7.2e-4 L/h from 6 h | reported recipe, conversions applied |
| parameters | `ganjave2022.table2@1.0.0` | fitted (Table 2) |
| solver | RK4(3), rtol 1e-6, h_max 0.01 h | — |

Actual output: `ok`, exit code 0, 2447 accepted steps and 20 rejected over a
step range of 1.61e-6 h to 0.01 h, 2448 recorded points, input digest
`b9cf220e45ec1c36…`, equations version 1.1.0.

| t (h) | X (g/L) | S1 (g/L) | S2 (g/L) | DO (%) | V (L) |
|---:|---:|---:|---:|---:|---:|
| 0 | 0.0500 | 2.760 | 5.0000 | 100.000 | 0.100000 |
| 2 | — | — | — | 90.91 | — |
| 4 | — | — | — | 72.82 | — |
| 6 | 1.3010 | 2.658 | 0.2007 | 86.52 | 0.100000 |
| 12 | — | — | — | 63.87 | — |
| 24 | 8.3551 | 22.305 | 0.0823 | 67.108 | 0.112960 |

Dissolved oxygen falls continuously to a minimum near 60 % and then recovers —
the landmark shape the paper describes on p. 3 ("continuous decrease in DO …
followed by a sharp rise concomitant with the depletion of glycerol … considered
as the starting point for feeding"). One diagnostic is attached, TN-02.

Enzyme fractions at 24 h: `e1 = 0.0849`, `e2 = 0.8489`.

**This is not a reproduction.** The paper reports 20.7 g DCW/L measured and
19.44 g/L from its own model; this run reaches 8.36 g/L, because the initial
complex-substrate concentration is a caller-supplied guess (§7).

## 7. Missing data and limitations

1. **Validation level 3 is not met and cannot be met with this paper.** The
   time courses are Figures 2, 3, 5 and S3–S8. No numerical observations were
   recoverable, so nothing here is digitised and no trajectory is compared with
   a measured point.
2. **The oxygen equation was wrong here and is now corrected** (TN-04). The
   paper prints `100/C*`; this package had implemented `100*C*`, which is not
   dimensionally addable to the transfer term and pinned DO above 99.87 % for
   every initial condition tried. See `OXYGEN_BALANCE_REPORT.md`.
3. **The corrected model still does not reproduce the paper**, and the reason is
   the data, not the equation. `S2_0` is not stated anywhere in the paper, and
   it is what decides whether the culture becomes oxygen-limited:

   | `S2_0` (g/L) | min DO (%) | final DO (%) | final X (g/L) | final OUR (g O₂·L⁻¹·h⁻¹) |
   |---:|---:|---:|---:|---:|
   | 5 | 59.55 | 67.11 | 8.36 | 0.33 |
   | 10 | 22.99 | 67.03 | 9.64 | 0.33 |
   | 20 | 1.18 | 65.83 | 15.84 | 0.34 |
   | 40 | 0.56 | 0.56 | 21.10 | 0.99 |
   | 80 | 0.50 | 0.50 | 21.44 | 0.99 |
   | 150 | 0.49 | 0.49 | 21.62 | 0.99 |

   At `S2_0 ≥ 40 g/L` the model reaches the paper's reported biomass range
   (19.9–21.5 g DCW/L) with DO near zero, as p. 3 describes. **This is not
   validation.** `S2_0` was chosen during this investigation, the paper does not
   print it, no time-course data exists to check against, and the figure axes
   were not digitised. It shows only that the corrected equation *can* reach the
   reported regime and the transposed reading cannot.
4. **Table 2 prints `e20/em1`** where `e2(0)/e_m2` is meant (TN-02). Read as
   the latter; confirmed against a rendering of the table. The value is used
   either way, but the reading should be confirmed with the authors.
5. **Three initial conditions are not stated** and materially affect the
   trajectory: `X₀` (no OD600→DCW calibration), `DO₀`, `S2₀`.
6. **The optimisation is not reimplemented.** Eq. (19)–(24) need the
   constraints of Table S3, which is supplementary. Only the selected optimum is
   recorded as reported data.
7. **No protein model.** The 2.8-fold eYFP specific-activity result is a
   protein outcome; this growth model does not predict it.
8. **No scale-up and no kLa prediction.** `kLa = 133 h⁻¹` is valid for the
   500 mL baffled flask at 200 rpm with a 1:5 fill ratio and is used only
   there. `C*` is a single reported value with no stated uncertainty and no
   temperature or depth correction.
9. **Package naming.** `models/` collides with the two sibling model packages
   in one interpreter, exactly as it already does between Morris and
   Zieliński. Each suite runs in its own process.

## 9. Composition integration

The model is registered with the ScaleUp AI composition layer as **`ganjave`@0.1.0**
and is discoverable, executable and visible in the Godot editor. The contract it
declares is in `models/composition.py`; the adapter and worker are in the
composition package and contain no science.

| | |
|---|---|
| Inputs | 9 (3 required with no default, 3 reported defaults, 3 required in `fed_batch` only) |
| Outputs | 6, each carrying its final value plus the full trajectory in `extra.trajectory` |
| Withheld | `e1/e_m1`, `e2/e_m2` — computed, but deliberately unpublished as dimensionless `1` |
| Declared conversion | `mL/h → L/h` within `volume_flow`, applied inside the model |
| Refusals | 12, each with its reason and what would make it legal |
| Validation status | `implemented` / `not_yet_validated`, carried on every output |

Suite results, all exit 0:

| Suite | Result |
|---|---|
| `Models/Ganjave` | 292 passed |
| `Models/Morris` | 186 passed |
| `Models/Zielinski` | 223 passed |
| `composition` | 399 passed (270 before this work; +129) |

Composition acceptance tests: `composition/tests/test_ganjave_composition.py`,
GJ-C01…C15. Godot harnesses: `contract_boundary.gd` (840 checks, discovery and
manifest resolvability with three models) and `ganjave_graph_run.gd` (51 checks,
a real plan + run + result read-back + stale-result check).

Files changed outside this package, all required and all additive or
expectation-only: `composition/adapters/__init__.py` (registration),
`composition/diagnostics.py` (`Origin.GANJAVE`), `composition/dimensions.py`
(quantity mapping), `composition/tests/conftest.py`, `composition/tests/
test_acceptance.py`, `composition/tests/godot/contract_boundary.gd`.
`Models/Morris`, `Models/Zielinski`, `Models/Baez` and `scripts/` are
byte-identical, verified by SHA-256 over the whole tree.

## 10. Files changed in this integration

Created: `composition/composition/_workers/ganjave_worker.py`,
`composition/composition/adapters/ganjave.py`,
`composition/composition/adapters/ganjave_contract.py`,
`composition/examples/ganjave_fed_batch.json`,
`composition/tests/test_ganjave_composition.py`,
`composition/tests/godot/ganjave_graph_run.gd`.

Modified: `Models/Ganjave/models/composition.py` (the contract),
`Models/Ganjave/tests/test_acceptance.py`, `Models/Ganjave/README.md`,
`Models/Ganjave/MODEL_REPORT.md`, and the six composition files listed in §9.

No scientific equation, parameter or solver behaviour changed.

## 11. Existing suites

Run after this integration:

| Suite | Result | Exit |
|---|---|---|
| `Models/Morris` | 186 passed | 0 |
| `Models/Zielinski` | 223 passed | 0 |
| `composition` | 399 passed | 0 |

SHA-256 over 183 files in `composition`, `Models/Zielinski`, `Models/Morris`,
`Models/Baez` and `scripts`, recorded before this integration began and compared
afterwards: **6 added** (all new Ganjave integration files), **6 changed** (all
composition-side, listed in §9), **0 removed**. The Morris and Zieliński trees
and every Godot UI script are byte-identical.

**A note on the composition count.** The repository root's README records 242
tests for the composition suite; it collected 270 before this integration and 399
after. Two movements are involved. The first (242 → 270) predates this work and
is not caused by it: `composition/composition/runner.py`,
`composition/tests/conftest.py` and `composition/tests/test_acceptance.py` carried
uncommitted modifications already present in the working tree when this task
began. The second (270 → 399) is this work: 129 composition acceptance and
contract tests. Nothing
under `composition/` was touched here, and no adapter, registration or registry
entry was added for Ganjave — `python -m composition.registry` still lists
exactly `morris2011.material_balance` and `zielinski2019.rhi_process`.