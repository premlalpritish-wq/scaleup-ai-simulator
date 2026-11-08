# Lin et al. (2001) — the complete simulation model, standalone

An isolated package that implements **only** what Lin, Mathiszik, Xu, Enfors and
Neubauer print in *Determination of the Maximum Specific Uptake Capacities for
Glucose and Oxygen in Glucose-Limited Fed-Batch Cultivations of Escherichia
coli*, Biotechnology and Bioengineering 73(5):347-357, 2001
([doi:10.1002/bit.1078](https://doi.org/10.1002/bit.1078)):

* the seven differential equations of the Appendix ("THE COMPLETE SIMULATION
  MODEL", printed **p. 356**);
* the subsidiary-variable chain and its two correction branches (printed
  **pp. 356-357**);
* the initial-value equations for `rS`, `rO` and `mu_max` (printed **p. 356**);
* the pulse-based uptake-capacity method, equation (1) (printed **p. 351**);
* Table I, the parameters and initial variables (printed **p. 348**), including
  the four rows the paper prints twice;
* the reported end-of-culture capacities stated in the abstract (printed
  **p. 347**);
* the cultivation context those numbers belong to (printed **pp. 348-349**).

Nothing else. No other model in this repository is touched, imported or coupled
to.

**Location:** `Models/Lin/`, beside `Models/Baez/`, `Models/nanchen/` and
`Models/Simensen/`. Run its commands from that directory.

---

## ⚠️ Read this before quoting any number from here

**This package is a transcription of printed equations, not a reproduction of
the paper's figures.**

It evaluates the model the paper prints, at inputs the caller supplies. It
therefore:

* **does not predict** any specific fermentation of the paper. The paper prints
  no digitised trajectory, so there is nothing to reproduce;
* **does not reproduce Figures 1-9**, and does not claim to;
* **never substitutes a default** for a value the paper does not print. `cS`,
  `cO`, `kLa`, `DOT*` and `H` have no defaults, and calling
  `SimulationParameters.from_culture` without them is an error that names them;
* **is not the insulin simulation's model.** See "Process context" below.

## What is implemented

| Component | What it is | Where |
|---|---|---|
| Differential system (1)-(7) | `V. = F`; `X. = (mu - F/V) X`; `S. = -(F/V)(S - Si) - qS X`; `DOT. = kLa(DOT* - DOT) - qO X H`; `A. = -(F/V) A + (qAp - qAc) X`; `rS. = YES/X mu - rS(qESd + mu)`; `rO. = YEO/X mu - rO(qEOd + mu)` | `lin2000.model.derivatives` |
| Initial values | `mu_max = (qSmax - qm) YX/S,ox`; `rS0 = cS mu_max/(qESd + mu_max)`; `rO0 = cO mu_max/(qEOd + mu_max)` | `lin2000.model.SimulationParameters` |
| Subsidiary chain | `qScap`, `qOcap`, `qS`, `qSox`, `qmr`, `qSoxan`, `qSoxen`, `qOs`, `qSof`, `qAc`, `qSofan`, `qSofen`, `qAcan`, `qAcen`, `qAp`, `qO`, `mu` | `lin2000.model.subsidiary` |
| Correction branches | the oxygen-capacity clamp and the maintenance floor the Appendix prints | `lin2000.model.subsidiary` (`oxygen_capacity_clamped`, `maintenance_reduced_below_qm`) |
| Pulse method (1) | `qScap = (dS + INT(F Si)) / (V X (tR - tP))` | `lin2000.model.qScap_from_pulse` |
| Integration | classical RK4 over the printed system | `lin2000.model.simulate` |

### Table I (printed p. 348), the two printed columns

| Parameter | Unit | W3110 (exponential feed) | RB791 (constant feed) |
|---|---|---|---|
| `KS` | g/L | 0.035 | 0.01 |
| `KA` | g/L | 0.1 | 0.1 |
| `qm` | g/(g h) | 0.03 | 0.03 |
| `qSmax` | g/(g h) | 1.86 | 1.5 |
| `qOmax` | g/(g h) | 0.607 | 0.65 |
| `qAc,max` | g/(g h) | 0.15 | 0.14402 |
| `YX/S,ox` | g/g | 0.51 | 0.51 |
| `CS`, `CA` | mol C/g | 0.0333 | 0.0333 |
| `CX` | mol C/g | 0.04 | 0.04 |
| `YO/S`, `YO/A` | g/g | 1.067 | 1.067 |
| `YX/S,of` | g/g | 0.15 | 0.15 |
| `YA/S` | g/g | 0.667 | 0.667 |
| `YX/A` | g/g | 0.35085 | 0.35085 |
| `Si` | g/L | 532 | 200 |
| `X0` | g/L | 0.121 | 0.0001 |
| `S0` | g/L | 0.5 | 5 |
| `V0` | L | 7 | 4 |


Four rows print **two** values because the paper models the uptake systems in
two ways: `qESd` (0 or 0.9), `qEOd` (0, 0.35 or 0.55), `YES/X` (---, 0.51 or
0.1) and `YEO/X` (---, 0.23 or 0.1). Footnote **c** is the value 0 ("No change in
qOcap and qScap is considered"); footnote **d** is the growth-dependent value.
`variant="growth_dependent"` (the default) selects the footnote-d set, which is
what the Appendix's equations (6) and (7) describe; `variant="constant_capacity"`
selects footnote c.

### The five constants the paper does not value

| Symbol | Meaning | Why there is no default |
|---|---|---|
| `cS` | factor in the initial-value equation for `rS` | defined, never valued |
| `cO` | factor in the initial-value equation for `rO` | defined, never valued |
| `kLa` | volumetric oxygen transfer coefficient in equation (4) | not printed for these cultivations |
| `DOT*` | saturation dissolved oxygen tension in equation (4) | printed as a symbol, never valued |
| `H` | Henry's-law constant in equation (4) | the **nomenclature** prints `14000 % L g-1`; Table I does not |

`H` is transcribed from the nomenclature rather than Table I, and is still a
required run input, because passing it is the caller's statement that the
nomenclature value applies to their run. The other four have no value anywhere.

### Using it

```python
from lin2000.model import SimulationParameters, feed_constant, simulate

p = SimulationParameters.from_culture(
    "w3110_exponential", cS=1.0, cO=1.0, kLa=60.0, DOT_star=100.0, H=14000.0,
)
result = simulate(p, feed_constant(0.0532), t_end=1.0, dt=0.005)
final = result.final()
final.state.X        # g/L
final.subsidiary.mu  # 1/h
final.subsidiary.qO  # g/(g h)
```

## Process context (and what this package does *not* connect to)

This model belongs to a **different experiment** from the composition layer's
target process, and it says so:

| | Lin et al. (2001) | Zielinski et al. (2019), the composition layer's target |
|---|---|---|
| strain | *E. coli* K12 W3110 / RB791 (lacIq) | *E. coli* 20 IBA 1 (CSH50R derivative) |
| construct | pDSCrimi or pKK177GlucC/pUBS520, **not induced** | pIBAINS |
| medium | phosphate-buffered mineral salt (Teich et al. 1998) | GMS |
| reactor | 15 L or 6 L Biostat ED | 7.5 L Bioflo Celligen 310 |
| scale | 7 L or 4 L | 4 L |
| mode | fed-batch, exponential then constant feed | batch with pH-stat glucose feeding |
| temperature | 35 degC | 30 degC |

No parameter, port or compatibility claim is transferred across that boundary.
This package adds no adapter registration, so `python -m composition.registry`
does not list it.

## Running it

```
cd Models/Lin
python -m lin2000 --validate           # the fidelity checks, exit 0 iff they pass
python -m lin2000 --check manifest.json
python -m lin2000 --run --cS 1 --cO 1 --kLa 60 --DOT-star 100 --H 14000
python -m pytest tests                 # 107 tests
```

## Not distributed

The reference PDF beside the package is a publication by other authors and is
not read at run time. What the tests read is the extracted page text in
`lin2000/data/paper_pages.json`, regenerable from the PDF with
`lin2000.source.rebuild_paper_pages()` (a developer step needing pypdf). A
normal run of the package opens no PDF at all.

## Known limitations

* **No digitised data.** No figure is transcribed. A run evaluates the printed
  model; it does not reproduce the authors' curves.
* **Two printed unit systems for the capacities.** Table I prints `g g-1 h-1`
  and the abstract prints `mmol g-1 h-1`. There is no printed molar mass, so the
  two are separate dimensions and the package never converts between them.
* **Equation (1)'s numerator.** The printed denominator is a biomass mass times
  time, so the numerator must be a glucose mass; the paper describes the pulse
  as a concentration, so the caller multiplies by V.
* **Equation (2)'s symbols.** The extracted text garbles the biomass balance's
  symbols; the arithmetic uses `F/V` because the notation defines F and V.
* **A passing test does not establish scientific validity.** It establishes that
  this implementation matches the printed equations and the printed table.
