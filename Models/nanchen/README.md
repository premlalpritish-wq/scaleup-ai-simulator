# Nanchen, Schicker & Sauer (2006) — Pirt's chemostat relation, standalone

An isolated package that implements **only** what Nanchen, Schicker and Sauer
print as a growth-physiology model in *Nonlinear Dependency of Intracellular
Fluxes on Growth Rate in Miniaturized Continuous Cultures of Escherichia coli*,
Applied and Environmental Microbiology 72(2):1164-1172, 2006
([doi:10.1128/AEM.72.2.1164-1172.2006](https://doi.org/10.1128/AEM.72.2.1164-1172.2006)):

* **Pirt's chemostat relation**, printed as equation (3) on **p. 1167**:
  `qglc = mu / Yglc_max + mglc`;
* the paper's **own fitted parameters** for that relation, from Table 1 on
  **p. 1167**: for *E. coli* MG1655 at 37 °C, `mglc = 0.37 +/- 0.09`
  mmol gdw⁻¹ h⁻¹ and `Yglc_max = 76 +/- 3` gdw mol⁻¹;
* the readings the text states in the same context (no acetate below 0.4 h⁻¹,
  washout above 0.7 h⁻¹, OD600→dry-weight factor 0.41 g/OD);
* the cultivation context those numbers belong to (**pp. 1164-1165**).

Nothing else. No other model in this repository is touched, imported or coupled
to.

**Location:** `Models/nanchen/`, beside `Models/Lin/` and `Models/Simensen/`.
Run its commands from that directory.

---

## ⚠️ Read this before quoting any number from here

**This package evaluates one printed relation; it does not reproduce the paper's
flux analysis.**

* It **does not implement** the ¹³C metabolic-flux-ratio equations (the paper's
  equations (1) and (2)). Those need GC-MS mass-distribution vectors that the
  paper does not tabulate, and the paper states it solved them iteratively from
  random starting values. With no tabulated input, an implementation would have
  to invent the data, so they are declared absent.
* It **does not reproduce** Fig. 4 or Fig. 5. The fit's data points are plotted,
  not tabulated.
* It **is not the insulin simulation's model.** See "Process context" below.

## What is implemented

| Component | What it is | Where |
|---|---|---|
| Equation (3) | `qglc = 1000 * mu / Yglc_max + mglc`, in mmol gdw⁻¹ h⁻¹ | `nanchen2006.model.q_glc` |
| Equation (3), inverted | `mu = (q - mglc) * Yglc_max / 1000`, in h⁻¹ | `nanchen2006.model.mu_from_q_glc` |
| Observed yield | `Y = mu / qglc`, below `Yglc_max` whenever maintenance is non-zero | `nanchen2006.model.biomass_yield` |
| Fitted parameters | Table 1, MG1655, "This study" | `nanchen2006.model.THIS_STUDY` |
| Context | strain, no construct, M9 medium, mini-scale chemostat, 10 mL, 37 °C | `nanchen2006.context` |

### The factor of 1000

The printed equation adds a term in **mol** (`mu / Yglc_max`, because `Yglc_max`
is printed in gdw mol⁻¹) to a term in **mmol** (`mglc`, printed in
mmol gdw⁻¹ h⁻¹). The model declares `MOL_PER_MMOL = 1000` and applies it, so the
answer comes back in the unit the table prints. Nothing is fitted; a mol is
1000 mmol. At `mu = 0.4 h⁻¹` the relation gives 5.633 mmol gdw⁻¹ h⁻¹.

### Table 1's comparison rows are not encoded

Table 1 also lists eight published strains beside the paper's own row. Their
column alignment is not recoverable from the extracted text with confidence
(blank yield cells and "Unknown" temperatures collapse in the linearised text),
so only the row this model's parameters come from is encoded. The omission is
recorded in `model.COMPARISON_TABLE_NOTE` and in the manifest.

## Process context (and what this package does *not* connect to)

| | Nanchen et al. (2006) | Zielinski et al. (2019), the composition layer's target |
|---|---|---|
| strain | *E. coli* MG1655 (F⁻ rph-1), non-recombinant | *E. coli* 20 IBA 1 (CSH50R derivative) |
| construct | none | pIBAINS |
| medium | M9 minimal, 1 g/L glucose, pH 7.0 | GMS |
| reactor | 17-mL Hungate tube, water bath | 7.5 L Bioflo Celligen 310 |
| scale | 10 mL | 4 L |
| mode | continuous chemostat, steady state | batch with pH-stat glucose feeding |
| temperature | 37 °C | 30 °C |

No parameter is transferred across that boundary. This package adds no adapter
registration, so `python -m composition.registry` does not list it.

## Running it

```
cd Models/nanchen
python -m nanchen2006 --validate           # the fidelity checks, exit 0 iff they pass
python -m nanchen2006 --check manifest.json
python -m nanchen2006 --run --mu 0.4
python -m pytest tests                     # 46 tests
```

## Known limitations

* **No flux analysis.** Equations (1) and (2) are declared, not implemented.
* **One row of Table 1.** The eight comparison strains are not transcribed.
* **The printed equation mixes mol and mmol.** The 1000 is stated, not hidden.
* **A passing test does not establish scientific validity.** It establishes that
  this implementation matches the printed relation and the printed parameter row.
