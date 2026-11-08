# Ganjave et al. (2022) — cybernetic growth and fed-batch model

An executable model of the growth equations in:

> S. D. Ganjave, V. A. J. E. S. Waghmare, P. P. Wangikar, *High cell density
> cultivation of E. coli in shake flasks for the production of recombinant
> proteins*, Biotechnology Reports 33 (2022) e00694.
> [doi:10.1016/j.btre.2021.e00694](https://doi.org/10.1016/j.btre.2021.e00694)

It implements the paper's equations (1)–(16): the cybernetic response
functions, the enzyme-allocation dynamics, the batch balances (8)–(11), the
fed-batch balances (12)–(16), and the volume balance. Everything else the
paper describes is out of scope and says so.

---

## ⚠️ Read this before treating any output as a result

**A simulation that runs is not a reproduction of the paper.**

Two things stand between this package and a validated reproduction:

1. **The paper's time courses are figures, not data.** No trajectory here has
   been compared against a measured point, because there are no measured
   points to compare against in the main paper. Validation level 3 (paper
   reproduction) is **not met**.
2. **Three initial conditions are not stated in the paper** — initial biomass,
   initial dissolved oxygen and initial complex-substrate concentration. They
   are required from the caller and are never defaulted. They materially
   determine the trajectory.

The oxygen balance **was** a third obstruction, and it has been resolved: the
package had transcribed the printed factor `100/C*` as the product `100*C*`,
which pinned dissolved oxygen near 100 %. That is corrected, with the evidence
in [TN-04](#transcription-decisions) and the independent checks in
`tests/test_oxygen_balance.py`.

This package therefore computes: *what the printed equations do, from a stated
starting state*. It does not claim the paper is reproduced, and its outputs
should not be quoted as predictions of the published process.

---

## Quick start

```bash
cd Models/Ganjave
python -m pytest tests          # 292 tests

python -m models parameters     # the Table 2 parameter set, as JSON
python -m models reference      # reported conditions and outcomes
python -m models interface      # the composition interface and its refusals

# batch, 6 h
python -m models simulate --mode batch --duration 6 \
    --X 0.05 --S2 5 --DO 100 --summary

# fed-batch with the recipe the paper selected (17.5 % w/v glycerol,
# 24.5 % w/v yeast extract, 0.72 mL/h from 6 h), 24 h
python -m models simulate --mode fed_batch --duration 24 \
    --X 0.05 --S2 5 --DO 100 \
    --glycerol-percent 17.5 --yeast-percent 24.5 --flow-ml-h 0.72 --feed-start 6 \
    --output-times 0 6 12 18 24 --summary
```

That run ends at `X = 8.36 g/L`, `S1 = 22.30 g/L`, `S2 = 0.082 g/L`,
`DO = 67.1 %`, `V = 0.11296 L`, with dissolved oxygen falling from 100 % to a
minimum near 60 % and recovering — the landmark shape the paper describes, but
well short of the magnitudes it reports. See [limitations](#known-limitations)
for why, and `MODEL_REPORT.md` §6 for the full comparison.

Exit codes: `0` success, `1` the run failed, `2` the arguments were wrong.

```python
from models.initial import build_initial_conditions
from models.fed_batch import FeedProgram
from models.simulation import simulate

conditions = build_initial_conditions(X=0.05, S2=5.0, DO=100.0, mode="fed_batch")
feed = FeedProgram.from_recipe(17.5, 24.5, 0.72, start_time_h=6.0)
result = simulate(
    initial_conditions=conditions, duration_h=24.0, mode="fed_batch", feed=feed
)
result.final_state.X          # g/L
result.times_h                 # the whole trajectory
result.provenance.input_digest # what this run was
```

---

## What is implemented

| Equation | Statement | Where |
|---|---|---|
| (1) | `X − S1/Y11 − S2/Y12 − DO/Yo1 = 0` | `models/kinetics.py`, as a checkable residual (TN-01) |
| (2) | `X − S2/Y22 − DO/Yo2 = 0` | likewise |
| (3) | `r1 = (S1/(K11+S1))·(S2/(K12+S2))·(DO/(Ko,1+DO))` | `response_r1` |
| (4) | `r2 = (S2/(K22+S2))·(DO/(Ko,2+DO))` | `response_r2` |
| (5) | `mu_k = mum_k·(e_k/e_mk)·r_k` | `specific_growth_1/2` |
| (6) | `mu = mu1 + mu2` | `specific_growth_rates` |
| (7) | `d(e_k/e_mk)/dt = (mum_k+beta_k)·r_k − (mu+beta_k)·(e_k/e_mk)` | `enzyme_fraction_derivative` |
| (8) | `dX/dt = mu·X` | `models/batch.py` |
| (9) | `dS1/dt = −(mu1/Y11)·X` | `models/batch.py` |
| (10) | `dS2/dt = −(mu1/Y12 + mu2/Y22)·X` | `models/batch.py` |
| (11) | `d(DO)/dt = kLa·(100−DO) − (100/C*)·(mu1/Yo1 + mu2/Yo2)·X` | `models/batch.py` (TN-04) |
| (12) | `dX/dt = (mu − F/V)·X` | `models/fed_batch.py` |
| (13) | `dS1/dt = (S10 − S1)·F/V − (mu1/Y11)·X` | `models/fed_batch.py` |
| (14) | `dS2/dt = (S20 − S2)·F/V − (mu1/Y12 + mu2/Y22)·X` | `models/fed_batch.py` |
| (15) | `d(DO)/dt = kLa·(100−DO) − (DO)·F/V − (100/C*)·(mu1/Yo1 + mu2/Yo2)·X` | `models/fed_batch.py` (TN-04) |
| (16) | `dV/dt = F` | `models/fed_batch.py` |

The **enzyme state is a normalised fraction**, `e_k/e_mk`, not an enzyme
concentration: eq. (5) multiplies `mum_k` by the ratio and eq. (7)
differentiates it directly, so `e_mk` is never needed as a number.

Batch and fed-batch are **separate** right-hand sides. Batch has no dilution
and no volume term; a feed supplied to a batch run is refused rather than
silently ignored.

## Transcription decisions

Every one is in `models/kinetics.py::TRANSCRIPTION_NOTES`, surfaced on every
run as a diagnostic, and covered by a test.

| Note | Issue | Decision |
|---|---|---|
| TN-01 | eq. (1)/(2) read like mass balances | implemented as checkable residuals, **not** integrated; the balances are eq. (8)–(16) |
| TN-02 | Table 2 prints the second initial enzyme ratio as `e20/em1` | read as `e2(0)/e_m2 = 0.874`; the printed string is kept in the parameter's quote. **Unresolved — needs the authors** |
| TN-03 | DO enters as a percentage | carried as a percentage throughout; conversion to g/L needs `C*` and is explicit |
| TN-04 | eq. (11)/(15) print the oxygen factor as `100/C*`, a **quotient** | this package had read it as the product `100*C*`, because the PDF text layer drops the fraction bar. **Corrected** to the printed quotient. Verified against a 9× rendering of the page, against the unit algebra in `models/dimensions.py`, and against the paper's own reported behaviour |
| TN-05 | eq. (13)/(14) need g/L; recipes are printed in % w/v | 1 % w/v = 10 g/L, applied explicitly at the API boundary |

### TN-04 in detail

The printed equation is

```
d(DO)/dt = kLa(100 - DO) - (100/C*) * (mu1/Yo1 + mu2/Yo2) * X        eq. (11)
```

Three independent checks fix that reading, and none of them is "the simulation
looks better":

| Check | Result |
|---|---|
| **The rendered page.** At 9× the factor is visibly a fraction: `100` sits 8.3 pt above `C*`, while tokens printed side by side in the same equation agree to under 0.01 pt. The text layer contains no solidus, which is exactly how the error was made. |
| **Unit algebra** (`models/dimensions.py`). `(mu1/Yo1 + mu2/Yo2)*X` is an oxygen uptake rate in M·L⁻³·T⁻¹; dividing by `C*` and scaling by the printed 100 gives %/h, which is the dimension of `d(DO)/dt` and of the `kLa(100-DO)` term beside it. Multiplying by `C*` gives M²·L⁻⁶·T⁻¹, which cannot be added to it. The module's `Dimension.__add__` refuses the unlike sum. |
| **The paper's own account.** p. 3 reports a continuous DO decline over the first 6 h followed by a sharp rise at substrate depletion, DO "close to zero" once feeding starts, and p. 7 states growth is oxygen-limited beyond 6 h. Under the product reading DO stays above 99.87 % for every initial condition tried, so none of that is reachable. |

The parameter values were not touched; only the transcription changed, and
`EQUATIONS_VERSION` was raised to `1.1.0` so runs recorded under the old
reading cannot be mistaken for runs under the new one.

## Parameters

`Models/Ganjave/data/reference_parameters.json` holds Table 2 with each value's
unit, quantity, provenance and printed location.

| Symbol | Value | Unit | Provenance |
|---|---:|---|---|
| `mum1` | 1.497 | 1/h | fitted (Table 2) |
| `mum2` | 0.834 | 1/h | fitted |
| `K11` / `K12` / `K22` | 0.131 / 36.154 / 1.001 | g/L | fitted |
| `Ko1` / `Ko2` | 0.326 / 8.944 | % | fitted |
| `Y11` / `Y12` / `Y22` | 0.440 / 0.881 / 0.254 | g/g | fitted |
| `Yo1` / `Yo2` | 0.925 / 1.219 | g/g | fitted |
| `e1(0)` / `e2(0)` | 0.082 / 0.874 | 1 | fitted (initial states of eq. 7) |
| `beta1` / `beta2` | 0.001 / 0.028 | 1/h | fitted |
| `kLa` | 133 | 1/h | **reported**, measured by gassing-out/in for the 500 mL baffled flask at 200 rpm (p. 3) |
| `C*` | 0.0075 | g/L | **reported** (notation table, p. 2) |

Table 2 is a *fitted* set: the paper estimates it against six fed-batch
experiments with a hybrid genetic-algorithm/`fmincon` scheme (p. 5), then
validates on two more. The values are printed, but they are a fit rather than a
measurement, and the package keeps that visible.

### Initial conditions

| State | Paper | Provenance recorded |
|---|---|---|
| `S1₀` = 2.76 g/L | yes (p. 2) | `reported` |
| `V₀` = 0.1 L (100 mL) | yes (p. 2) | `reported` |
| `e1₀`, `e2₀` | yes (Table 2) | `reported` |
| `X₀` | **no** | `assumed` — required from the caller |
| `S2₀` | **no** | `assumed` — required from the caller |
| `DO₀` | **no** | `assumed` — required from the caller |

The paper reports an initial OD600 of 0.05 and **no OD600-to-dry-cell-weight
calibration**, so `X₀` cannot be derived from it. Nothing is substituted.

## Numerical method

Classical fourth-order Runge-Kutta with step-doubling error control
(`models/solver.py`). Documented tolerances (`rtol`, `atol`), step limits and
step budget, all recorded with the result.

The default `h_max` is **0.01 h**, and that is not arbitrary: the reported
`kLa = 133 h⁻¹` relaxes the dissolved-oxygen state with a time constant of
7.5 ms while biomass runs at `mu ≈ 0.6–1.5 h⁻¹`. Explicit RK4 is stable only
while `h·kLa < 2.8`.

A state that leaves its physical range causes a **rejected step**, not a
clipped value; a non-finite value is an immediate failure. Integration failures
return structured diagnostics and **no trajectory**.

## Composition interface

`python -m models interface` prints the ports. Each carries a quantity key, a
unit, a temporal basis and a value state, versioned against the composition
contracts (`0.1.0`); a mismatch is refused rather than assumed.

Connections this model **refuses**, each with a reason:

* dissolved oxygen ↔ mass fraction — 100 % is 0.0075 g/L (`C*`); connecting
  them would rescale every oxygen quantity by ~13333;
* dissolved oxygen ↔ mass concentration — needs `C*` and an explicit
  conversion;
* complex substrate ↔ mass fraction or component mass — a lumped mixture with
  one fitted yield and no component identity;
* glycerol concentration ↔ mass flow, and biomass concentration ↔ mass — a
  concentration is not a flow or a total.

The package **is** registered with the composition layer under the identifier
`ganjave`: `python -m composition.runner --list-models` lists it, and
`--describe-model ganjave@0.1.0` prints its manifest. See
[Composition](#composition) for the port surface and what it refuses.

## Reference data

Measured outcomes, the authors' model predictions and optimisation decisions
are stored as **separate records** in `data/reference_experiments.json`, and
the simulator never returns them:

* 20.7 g DCW/L measured (abstract) and 19.9–21.5 g/L across trials (p. 7);
* 19.44 g DCW/L — the authors' **model prediction**, labelled as such;
* the selected recipe: 17.5 % w/v glycerol, 24.5 % w/v yeast extract,
  0.72 mL/h;
* 2.8-fold higher eYFP specific activity in the 3 L bioreactor — a
  protein-expression result this growth model does not predict.

## Validation policy

| Level | Status |
|---|---|
| 1. Equation tests against independent hand calculations | **met** — `tests/test_kinetics.py`, `test_batch.py`, `test_fed_batch.py` |
| 2. Numerical tests against independently computed fixtures | **met** — the volume balance against its closed form, plus tolerance convergence in `test_fed_batch.py` |
| 3. Comparison against the paper's reported measurements | **not met** — the time courses are figures; no numerical observations were recoverable |

### The oxygen balance specifically

`tests/test_oxygen_balance.py` (66 tests) covers GJ-O2-01…08: the source
transcription, dimensional consistency, the transfer term, each consumption
contribution, the percentage/concentration relationship, batch/fed-batch
convention, regression, and the preservation of what is still unknown. Five of
them re-measure the printed page when the article PDF and PyMuPDF are available,
which is how the `100/C*` factor was identified as a fraction rather than a
product.

## Composition

The model is registered with the ScaleUp AI composition layer under the
identifier **`ganjave`**, version `0.1.0`.

```
cd composition
python -m composition.runner --list-models
python -m composition.runner --describe-model ganjave@0.1.0
python -m composition.runner --graph examples/ganjave_fed_batch.json --result out.json
```

| | |
|---|---|
| Adapter | `composition/composition/adapters/ganjave.py` |
| Worker | `composition/composition/_workers/ganjave_worker.py` (own subprocess: all three models ship a top-level `models` package) |
| Connection contract | `composition/composition/adapters/ganjave_contract.py` |
| Contract declaration | `models/composition.py` — the model declares its own ports; the adapter derives the manifest from them |
| Acceptance tests | `composition/tests/test_ganjave_composition.py` (GJ-C01…C15) |

**Inputs.** Three are required with **no default**, because the paper does not
state them: `initial_biomass_concentration`, `initial_complex_substrate_concentration`
and `initial_dissolved_oxygen`. Four carry *reported* defaults the paper does
state (glycerol 2.76 g/L, volume 0.1 L, feed start 0 h). The three feed ports are
required in `fed_batch` mode only.

**Outputs.** `biomass_concentration`, `glycerol_concentration`,
`complex_substrate_concentration`, `dissolved_oxygen`, `culture_volume` and
`simulation_time`. The composition contract has no time-series value type, so
each output carries the final value as its number and the **whole trajectory** in
`extra.trajectory`, with its own time axis, units and quantity. The two ODE
states `e1/e_m1` and `e2/e_m2` are computed but deliberately **not** published:
as a dimensionless `1` they would be connectable to every dimensionless value in
the repository, which is a connection that looks legal and means nothing.

**Units.** `g/L` for concentrations, `L` for volume, `mL/h` for the volumetric
feed rate, `h` for time, `%` for dissolved oxygen. `L/h` is deliberately *not* a
declared unit: the contract registers `mL/h` for `volume_flow`, so the port
declares the unit the paper's Table 1 prints and the model converts to its own
`L/h` basis internally, with the conversion declared.

**What is refused**, each with a reason in the diagnostic: a concentration as a
total mass (needs a volume), a concentration as a mass flow, a volumetric feed
rate as a mass flow (needs a density), dissolved oxygen as a mass fraction or a
concentration (100 % is `C*` = 0.0075 g/L, so the two differ by ~10⁴), and the
lumped complex substrate as a mass fraction or a component mass.

**Validation status is carried, not implied.** Every result carries
`implementation_status: implemented` and `reproduction_status: not_yet_validated`.
The Godot editor surfaces it: the graph-run harness asserts that a successful
result never presents itself as a reproduction of the paper.

## Out of scope

Not implemented, and not to be added without a separate task and its own
inputs and validation: genetic-algorithm parameter estimation, multi-objective
optimisation and Pareto fronts (eq. 19–24 need the constraints of Table S3),
protein expression and inclusion-body models, automatic scale-up from shake
flask to 3 L bioreactor, kLa prediction for other geometries, and any
digitised figure data.

## Known limitations

1. **No reproduction claim.** See the warning at the top.
2. **Three initial conditions are caller-supplied** and materially determine the
   trajectory. In particular the initial complex-substrate concentration `S2_0`
   is not stated anywhere in the paper, and it is what decides whether the
   culture becomes oxygen-limited: across a sweep of `S2_0`, dissolved oxygen
   reaches ~0.5 % and biomass settles near 21 g/L for `S2_0 ≥ 40 g/L`, but only
   ~60 % and ~8 g/L at `S2_0 = 5 g/L`. The paper's reported biomass range is
   19.9–21.5 g DCW/L. **That agreement is not a validation**: `S2_0` was chosen
   during this investigation, the paper does not state it, and no time-course
   data exists to check against. It shows only that the corrected equation can
   reach the regime the paper describes, whereas the transposed reading cannot.
3. **TN-02 remains open.** Table 2 prints `e20/em1` where `e2(0)/e_m2` is meant;
   read as the latter, and every run reports the ambiguity.
4. **No figure data is digitised.** Nothing in this package was read off a
   plot, so nothing here is a digitised point.
5. **The DO convention is inherited, not verified experimentally.** `C*` is a
   single reported value (0.0075 g/L) used for a shake flask at 200 rpm with no
   depth or temperature correction; the paper reports no uncertainty for it.
6. `models/` is a top-level package name shared with `Models/Morris` and
   `Models/Zielinski`, as in those two packages. Each suite must run in its own
   process; that is the existing repository convention.

## Layout

```
Models/Ganjave/
  pyproject.toml            no dependencies, standard library only
  README.md                 this file
  MODEL_REPORT.md           what was built, verified, and what is missing
  OXYGEN_BALANCE_REPORT.md  the eq. (11)/(15) investigation, in full
  schemas/
    units.py                quantities and units, keyed by (quantity, symbol)
    provenance.py           Provenance, SourceRef, Parameter, Observation
    parameters.py           the versioned Table 2 parameter set
    state.py                State, InitialConditions, state validation
  models/
    kinetics.py             eq. (1)-(7) and the transcription notes
    batch.py                eq. (8)-(11)
    fed_batch.py            eq. (12)-(16) and the feed program
    dimensions.py           unit algebra for the oxygen balance
    paper_equations.py      reading the article's printed equations and glyphs
    solver.py               RK4(3) step-doubling integration
    simulation.py           orchestration, run provenance, input digest
    initial.py              initial-condition builder with honest provenance
    reference.py            the paper's reported data
    composition.py          the composition contract: ports, refusals, validation status
    dimensions.py           unit algebra for the oxygen balance
    diagnostics.py          structured diagnostics
    __main__.py             the command line entry point
  data/
    reference_parameters.json
    reference_experiments.json
  tests/                    292 tests
```