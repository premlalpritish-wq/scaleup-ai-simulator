# Baez et al. (2014) — reported observations and the printed feed equation

An isolated package that holds **only** what is explicitly specified in
Baez, Majdalani & Shiloach, *Production of recombinant protein by a novel
oxygen-induced system in Escherichia coli*, Microbial Cell Factories
2014, 13:50 ([doi:10.1186/1475-2859-13-50](https://doi.org/10.1186/1475-2859-13-50)):

* the two reported batch specific growth rates (printed **p. 2**);
* the exponential fed-batch feed equation and its four printed parameters
  (printed **p. 6**);
* the four reported fed-batch endpoint readings (printed **p. 3**);
* the cultivation and induction conditions those readings were obtained under
  (printed **pp. 5–6**).

Nothing else. No other model in this repository is touched, imported or
coupled to. Everything this package adds lives under `Models/Baez/`; the other
model packages and the composition layer are read-only to it.

**Location:** `Models/Baez/`, beside `Models/Morris/` and `Models/Zielinski/`.
Run its commands from that directory.

---

## ⚠️ Read this before quoting any number from here

**This package is a transcription with provenance, not a simulator.**

It reports numbers that were read out of a published paper, and it evaluates
one equation that the paper prints, at inputs the caller supplies. It
therefore:

* **does not predict** growth, biomass, GFP or fluorescence;
* **does not model** dissolved oxygen, oxygen transfer or oxygen limitation;
* **does not fit** anything. The two growth rates are two readings, not a
  curve, and no growth law is offered in their place;
* **does not convert** 109000 FU into 494 mg/L. Both are stored, in their own
  dimensions, and the paper states no relation between them for this culture;
* **never substitutes a default** for a value the paper does not print. `X_F`,
  `V_F`, `t_F` and `t` have no defaults, and calling `feed_rate()` without
  them is an error that names all four.

---

## What is implemented

| Component | What it is | Where |
|---|---|---|
| A — growth-rate observations | 1.08 h⁻¹ at 30% and 1.00 h⁻¹ at 300% air saturation, as **reported observations** on p. 2. No fit. | `baez2014/observations.py` |
| B — feed equation | `F(t) = ((mu_set/Y_XS) + m) * (X_F*V_F/S_F) * exp(mu_set*(t - t_F))`, as printed on p. 6, output in L/h. | `baez2014/equations.py`, `baez2014/feed_rate.py` |
| C — fed-batch endpoint | 29.1 g/L (DW), 494 mg/L, 109000 FU, 7.1 g/L, as **reported observations** on p. 3. | `baez2014/observations.py` |

The printed parameters, from p. 6:

| Symbol | Value | Unit as printed | Origin |
|---|---|---|---|
| `mu_set` | 0.35 | `1/h` | reported |
| `Y_XS` | 1.28 | `g/g` | reported |
| `m` | 0.12 | `g/g h` | reported (kept as `g/(g h)`) |
| `S_F` | 141 | `g/L` | reported |

The four run inputs, **required for every call**, with no defaults:

| Symbol | Meaning | Why there is no default |
|---|---|---|
| `X_F` | biomass concentration at fed-batch onset | p. 6 defines it, prints no value |
| `V_F` | volume at fed-batch onset | p. 6 defines it, prints no value. The 4 L on p. 6 is the initial **batch** volume, not `V_F` |
| `t_F` | fed-batch start time | p. 3 says when feeding started relative to the culture, but no time value enters the printed equation |
| `t` | evaluation time | the paper prints `F(t)` as a function, never a value of it |

### Using it

```python
from baez2014.feed_rate import feed_rate

result = feed_rate(t=6.0, t_F=5.0, X_F=10.0, V_F=4.0)
result.feed_rate_l_per_h      # L/h, from the printed parameters
result.parameters_are_reported  # True -- nothing was overridden
result.to_quantity()          # the same number as a DERIVED quantity with its inputs named
```

Units may be stated per input and are converted into the unit the paper
prints; an unregistered unit, or one of the wrong dimension, raises.

```python
feed_rate(t=6.0, t_F=5.0, X_F=10_000.0, V_F=4000.0,
          units={"X_F": "mg/L", "V_F": "mL"})   # same point, same answer
```

Omitting a run input, or evaluating at `t < t_F`, is refused rather than
guessed:

```python
feed_rate(t=6.0)          # MissingRunInput: ['X_F', 'V_F', 't_F']
feed_rate(t=4.0, t_F=5.0, X_F=10.0, V_F=4.0)   # FeedTimeBeforeStart
```

`V_F` must be strictly positive: a bioreactor holding no culture is not a
fed-batch culture. `X_F` = 0 stays allowed — it is a boundary of the printed
expression, not a missing vessel.

```python
feed_rate(t=6.0, t_F=5.0, X_F=10.0, V_F=0.0)   # ValueError: V_F must be strictly positive
feed_rate(t=5.0, t_F=5.0, X_F=0.0, V_F=4.0)    # 0.0 -- allowed
```

### Numerical range

`math.exp` overflows for a long enough elapsed time, and an extreme product can
leave the float range. Both raise `FeedRateNumericalError`, a subclass of
`FeedRateError`:

```python
feed_rate(t=1e6, t_F=0.0, X_F=10.0, V_F=4.0)   # FeedRateNumericalError
```

**That is a limit of the arithmetic, not of the process.** The package imposes
no maximum cultivation time and draws no biological conclusion from the
failure. Equally, a feed rate it *does* return for a time or a condition the
paper never reported is mathematical extrapolation of a printed formula — not a
validated process prediction.

---

## What is deliberately absent

Each exclusion is recorded with its reason in
`baez2014.equations.MISSING_MODELS`, so an absence is documented rather than
mistaken for an oversight.

| Not implemented | Why |
|---|---|
| a Monod or any other growth equation | the paper prints two batch readings and states the difference is not significant; two points do not define a function |
| a dissolved-oxygen differential equation | no gas balance is printed anywhere in the paper |
| an oxygen-transfer / uptake model | gas rate and agitation are printed (p. 6); `kLa`, OUR and OTR are not |
| a kinetic model of GFP expression | the paper reports endpoints and says the system is "dynamically responsive"; no rate constant is printed |
| a fluorescence ↔ GFP mass conversion | both readings are printed side by side on p. 3 with no stated relation for this culture; `FU` has its own dimension |
| a digitised time series | no dataset defining coordinates and digitisation provenance has been supplied |
| coupling to the Morris or Zieliński models | out of scope, and the paper supplies no shared component identity; no adapter is registered and no identifier is guessed |

---

## Provenance rules

* Every value carries a provenance class: `reported` (read from the printed
  page), `derived` (computed by the one registered equation), `unknown`
  (holds `None`, never `0`).
* Every reported value carries its **printed page**, its **printed text** and,
  where one exists, its **printed unit**.
* Reported values are `observed_reference`; computed values are `computed`.
  Nothing in this package moves a number from one class to the other.
* Printed page = PDF page here: the article is paginated 1–7 and pages 2–7
  carry a footer stating their own page number. `tests/test_source_provenance.py`
  checks those footers rather than assuming the mapping.
* `tests/test_citation_fidelity.py` checks every quoted fragment against the
  extracted text of the page it is cited to, and every reported value
  **strictly**.

---

## Requirements

| Tool | Version |
|---|---|
| **Python** | 3.11 or newer |

**No third-party dependency.** The standard library only. (pypdf appears in
one function, `source.rebuild_paper_pages`, which regenerates the extracted
page text by hand and is never called by a run.)

## Running the tests

From `Models/Baez`. `tests/conftest.py` puts the package and the test helper on
`sys.path` and pins pytest's `basetemp` inside the package, so no `PYTHONPATH`
is needed and the run does not depend on the host's temp directory being
writable.

```bash
cd Models/Baez && python -m pytest tests        # 195 tests
```

| Result | Count |
|---|---|
| passed | **195** |
| failed | 0 |
| skipped | 0 |
| errors | 0 |

195 collected, 195 executed, none skipped. Two guards that used to *skip*
because of a path-resolution mistake now execute and pass: they discover the
repository root by walking up and inspecting the real
`composition/composition/adapters` directory.

This suite can also be collected in the same process as a sibling model suite:

```bash
cd <repository root>
python -m pytest Models/Baez/tests Models/Morris/tests       # 381 passed
python -m pytest Models/Baez/tests Models/Zielinski/tests    # 418 passed
```

The three-way run (`Models/Baez/tests Models/Morris/tests
Models/Zielinski/tests`) still fails, with
`ModuleNotFoundError: No module named 'models.zielinski_2019'` while loading
Zieliński's `conftest.py`. That is **pre-existing and unrelated to this
package**: Morris and Zieliński each ship a top-level `models` package, and
running `python -m pytest Models/Morris/tests Models/Zielinski/tests` fails
identically with Baez absent. Fixing it would mean changing one of those two
models, which is out of scope here.

## The manifest

```bash
cd Models/Baez && python -m baez2014                        # print the manifest as JSON
cd Models/Baez && python -m baez2014 --check manifest.json  # exit 0 only if it is current
```

`manifest.json` is a committed snapshot of what the package declares, and a
test fails if the two ever differ.

## Regenerating the extracted page text

Developer-only. It needs `pypdf`, which is not a runtime dependency, and it is
never called by the model.

```bash
cd Models/Baez
python -c "from baez2014.source import rebuild_paper_pages; rebuild_paper_pages()"
```

The PDF is located by walking up from the package to the repository root and
preferring `<repository root>/papers/Baez et al 2014.pdf`, falling back to the
package-local copy that sits beside this package (the convention the other two
model packages follow). The selection is deterministic and the rule that
matched is returned by `resolve_source_pdf()`.

Pass `output_path=` to write somewhere other than
`baez2014/data/paper_pages.json`. The test suite always does, so no test can
overwrite the tracked snapshot; one test asserts the snapshot's digest is
unchanged afterwards, and another asserts the regenerated text is identical to
it.

## Layout

```
Models/Baez/
  Baez et al 2014.pdf           package-local copy of the article (gitignored)
  pyproject.toml               package metadata, no dependencies
  manifest.json                committed snapshot of baez2014.manifest.build_manifest()
  README.md                    this file
  MODEL_REPORT.md              what was built, what was verified, what is absent
  baez2014/
    source.py                  citation, printed-page evidence, PDF resolution,
                               extracted page text
    units.py                   explicit unit whitelist, dimension-checked
    provenance.py              provenance classes, EvidenceRef, Quantity
    equations.py               the one executable equation, and the seven absences
    feed_rate.py               feed_rate(), its validation, the reported parameters
    observations.py            the reported readings and the setup conditions
    manifest.py                what this package declares about itself
    __main__.py                the manifest CLI
    data/paper_pages.json      normalised text of each printed page
  fixtures/
    build_feed_rate_fixtures.py   independent fixture calculator
    feed_rate_fixtures.json       the fixtures it produced
  tests/                       195 tests
    _baez_testkit.py           paths and repository discovery, uniquely named
    conftest.py                fixtures and the pinned basetemp
    test_feed_rate.py          equation, fixtures, units, parameters, validation
    test_observations.py       the reported readings
    test_source_provenance.py  provenance invariants, page numbering, PDF
    test_citation_fidelity.py  quotes and values checked against page text
    test_exclusions.py         the seven absences, and isolation from the
                               composition layer
    test_units.py              the unit registry
    test_manifest.py           manifest snapshot and CLI
```

## Known limitations

* **`X_F`, `V_F`, `t_F` are unvalued by the paper.** Every number this package
  computes depends on values a caller must supply. That is stated at the call,
  in `UNVALUED_RUN_INPUTS` and in the manifest.
* **FU and mg/L cannot be reconciled here.** A caller who wants GFP in mg/L
  from a fluorescence reading needs a calibration this paper does not print.
* **Citations are checked against extracted text, not against the typeset
  page.** `source.page_contains` tolerates line-end hyphenation, so a quoted
  phrase can match across a hyphen that the printed column breaks on. Reported
  *values* are always checked strictly.
* **The isolation guards need a repository checkout.** They discover the
  repository root by walking up and inspecting
  `composition/composition/adapters`. Run outside a checkout they **fail** with
  an actionable message rather than skipping — a skip previously hid them
  after the package moved. See §Testing for what that means for running this
  suite from a copied directory.
* **A passing test does not establish scientific validity.** It establishes
  that this implementation matches the specification it was given.

## Not distributed

The reference PDF at `papers/Baez et al 2014.pdf` is a publication by other
authors and is not read at run time, and neither is the package-local copy.
What the tests read is the extracted page text in
`baez2014/data/paper_pages.json`, regenerable from the PDF with
`baez2014.source.rebuild_paper_pages()` (a developer step needing pypdf; see
§Regenerating the extracted page text).

A normal run of the package opens no PDF at all. The one exception is the
regeneration test, which reads the PDF on purpose and writes its output to a
temporary directory.