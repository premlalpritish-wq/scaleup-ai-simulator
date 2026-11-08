# MODEL_REPORT — Lin et al. (2001)

What was implemented, how it was verified, and what is knowingly absent.

**A passing software test verifies that this implementation matches the printed
equations and the printed parameter table it was given. It does not
independently establish scientific validity or predictive capability.** The
package reproduces no figure of the paper: the paper prints no digitised
trajectory.

Source: H. Y. Lin, B. Mathiszik, B. Xu, S.-O. Enfors, P. Neubauer,
*Determination of the Maximum Specific Uptake Capacities for Glucose and Oxygen
in Glucose-Limited Fed-Batch Cultivations of Escherichia coli*, Biotechnology
and Bioengineering 73(5):347-357, 2001. doi:10.1002/bit.1078.

---

## 1. Why this paper has a model, and the others in the same corpus do not

The Appendix is titled "THE COMPLETE SIMULATION MODEL" and prints the whole
model: seven differential equations, the initial-value equations, and the
subsidiary-variable chain, with Table I supplying every parameter the equations
use. That is a closed, self-contained model in the paper's own experimental
context, so a paper-faithful standalone implementation is possible, and this
package is it.

## 2. Contract → implementation

| Printed item | Page | Implemented in | Verified by |
|---|---|---|---|
| Differential system (1)-(7) | 356 | `model.derivatives` | `tests/test_model.py` |
| Initial values, `mu_max` | 356 | `model.SimulationParameters` | `tests/test_model.py` |
| Subsidiary chain | 356-357 | `model.subsidiary` | `tests/test_model.py`, `validate` |
| Oxygen-capacity clamp | 357 | `model.subsidiary` | `validate`, `tests/test_model.py` |
| Maintenance floor | 357 | `model.subsidiary` | `validate`, `tests/test_model.py` |
| Pulse method (1) | 351 | `model.qScap_from_pulse` | `tests/test_manifest_and_isolation.py` |
| Table I | 348 | `parameters.TABLE_I` | `validate`, `tests/test_source_fidelity.py` |
| Abstract capacities | 347 | `parameters.REPORTED_CAPACITIES` | `validate`, `tests/test_source_fidelity.py` |
| Cultivation context | 348-349 | `context.EXPERIMENTAL_CONTEXT` | `validate` |
| Unit whitelist | — | `units.UNITS` | `tests/test_manifest_and_isolation.py` |
| Manifest | — | `manifest.build_manifest`, `manifest.json` | `tests/test_manifest_and_isolation.py` |

## 3. Fidelity: what is checked, and how

Every check is structural evidence about the transcription, and the same checks
run in two places (`python -m lin2000 --validate`, and the composition layer's
`test_paper_model_fidelity.py`), so there is one definition rather than two.

* **Page numbering is evidenced.** The article is paginated 347-357 and each page
  from 348 states its own number at the head or foot of the column
  (`source.page_states_its_own_number`). `pdf_page = printed_page - 346` is
  therefore checked, not assumed.
* **Table I's values are on Table I's page.** Each of the 38 printed numbers is
  looked up verbatim on printed p. 348.
* **The abstract's capacities are on the abstract page** (printed p. 347).
* **Every context quote is on its cited page.**
* **Every declared equation cites a page that exists and has text.**
* **A hand-worked evaluation of the printed chain.** W3110 with `cS = cO = 1` at
  the initial state must give `qScap = 1.86`, `qOcap = 0.607`, the oxygen-capacity
  clamp must fire (`qOs` is clamped to `qOcap`), and `mu` must come out at
  `0.45360 1/h`.
* **Both correction branches fire.** The oxygen clamp fires at the initial state;
  the maintenance floor is forced with a reduced `qOmax` and must set
  `qmr = qSox = qSoxen` with `qSoxan = 0`, exactly as printed.
* **The printed derivative expressions are reproduced** term by term at a state
  the test constructs.
* **The model runs.** Integration is finite, biomass rises under feed, and a
  constant feed grows the volume by exactly `F * t`.

## 4. What is knowingly absent

1. **No digitised trajectory.** No figure is transcribed, so a run evaluates the
   printed model rather than reproducing the authors' curves. The absence is
   declared in `manifest.MISSING_MODELS`.
2. **`cS`, `cO`, `kLa` and `DOT*` are unvalued.** The Appendix defines them and
   prints no number for them; they are required run inputs with no default.
3. **`H` is transcribed from the nomenclature**, `14000 % L g-1`, and is still a
   required run input, because supplying it is the caller's statement that it
   applies to their run.
4. **The two capacity dimensions are not reconciled.** Table I prints
   `g g-1 h-1`; the abstract prints `mmol g-1 h-1`; no molar mass is printed.
5. **Equation (2)'s symbols are not quoted.** The extracted text garbles them;
   the arithmetic is `F/V` because the notation defines F and V. The values it
   implies are asserted numerically instead.
6. **No composition registration.** The paper's process is not the composition
   layer's target; no adapter was added and `composition/` registers nothing new.
7. **Tests cannot establish scientific validity.** They establish agreement with
   the printed equations and table.
