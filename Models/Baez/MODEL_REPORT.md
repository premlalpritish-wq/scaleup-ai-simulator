# MODEL_REPORT — Baez et al. (2014)

What was implemented, how it was verified, and what is knowingly absent.

**A passing software test verifies that this implementation matches the
specification it was given. It does not independently establish scientific
validity or predictive capability.** The package contains no predictive
capability beyond evaluating one printed equation at the caller's own inputs.

Source: A. Baez, N. Majdalani, J. Shiloach, *Production of recombinant protein
by a novel oxygen-induced system in Escherichia coli*, Microbial Cell
Factories 2014, 13:50. doi:10.1186/1475-2859-13-50.

---

## 1. Contract → implementation

| Specification item | Implemented in | Verified by |
|---|---|---|
| A. Growth-rate observations, p. 2 | `observations.growth_rate_observations()` | `test_observations.py`, `test_citation_fidelity.py` |
| B. Feed equation and printed parameters, p. 6 | `equations.EQUATIONS`, `feed_rate.feed_rate()`, `feed_rate.REPORTED_PARAMETERS` | `test_feed_rate.py`, `test_units.py`, `test_citation_fidelity.py` |
| C. Fed-batch endpoint, p. 3 | `observations.fed_batch_endpoint()` | `test_observations.py`, `test_citation_fidelity.py` |
| Provenance: page, unit, printed text | `provenance.py`, `source.py`, `data/paper_pages.json` | `test_source_provenance.py`, `test_citation_fidelity.py` |
| Manifest and metadata | `manifest.build_manifest()`, `manifest.json`, `__main__.py` | `test_manifest.py` |
| Exclusions declared, not implemented | `equations.MISSING_MODELS` (7 entries) | `test_exclusions.py` |
| Numerical fixtures, computed independently | `fixtures/build_feed_rate_fixtures.py`, `fixtures/feed_rate_fixtures.json` | `test_feed_rate.py` |

## 2. What the paper prints, and where

Every value below was checked against the extracted text of the page it is
attributed to (`tests/test_citation_fidelity.py`, strict matching for values).

| Printed page | Content used |
|---|---|
| p. 2 | "the specific growth rate of the culture at 30% (1.08/h) and 300% (1.00/h)"; "No significant changes (p = 0.05)" |
| p. 3 | "After 3 hours at 300% air saturation, GFP fluorescence reached 109000 FU (494 mg/L) ... the cell concentration reached 29.1 g/L (DW) ... acetate accumulation reached 7.1 g/L"; fed-batch onset at five hours; induction one hour later by raising dO 2 from 30% to 300% |
| p. 5 | 5 L bioreactor, 37 °C, pH 7.0, inoculation at OD600 0.2–0.3, batch set point 30% air saturation |
| p. 6 | `F(t) = feed rate (L/h)` with `mu_set` (0.35 1/h), `Yx/s` (1.28 g/g), `m` (0.12 g/g h), `S_F` (141 g/L); induction by raising dO 2 to 300% air saturation; air 0.075 vvm, 100 rpm; fed-batch initial batch volume 4 L |

Printed page = PDF page was not assumed: the article is paginated 1–7 and
pages 2–7 carry a footer stating their own printed page number, which
`test_source_provenance.py` asserts page by page. Page 1 carries the journal
line and no footer, and the package says so rather than quoting one.

### Locating the article PDF

`source.resolve_source_pdf()` walks up from the package until it finds a
directory holding both `papers/` and `Models/`, then prefers
`<repository root>/papers/Baez et al 2014.pdf`, falling back to the
package-local copy beside the package. It returns the rule that matched. Fixed
depth arithmetic (`parents[n]`) is not used anywhere: it is what broke when
this package was relocated, and a test asserts no `parents[n]` survives in
`source.py`. A missing PDF raises `SourcePdfNotFound` listing every path
searched.

### Not in the paper, and therefore not in the package

`X_F`, `V_F` and `t_F` are **defined but not valued**. The 4 L printed on p. 6
is the initial *batch* volume, before fed-batch begins; it is recorded as a
cultivation condition and explicitly labelled "not `V_F`"
(`test_source_provenance.py::test_four_litre_batch_volume_is_not_recorded_as_V_F`).
Consequently all four run inputs are required and none is defaulted.

## 3. The equation as implemented

```
F(t) = (mu_set/Y_XS + m) * (X_F * V_F / S_F) * exp(mu_set * (t - t_F))     [L/h]
```

Dimensional check, asserted in `test_feed_rate.py`:
`(mu_set/Y_XS + m)` is a specific rate and `X_F*V_F/S_F` is a volume, so the
output is a volume rate; `exp(...)` is dimensionless. The registry encodes
this by giving `1/h` and `g/(g h)` **one** dimension (`SPECIFIC_RATE`) —
registering them as unlike dimensions would forbid the paper's own sum.

`FU` is deliberately a dimension of its own: `convert(109000, "FU", "mg/L")`
raises.

## 4. Numerical verification

Fixtures are produced by `fixtures/build_feed_rate_fixtures.py`, which does not
import the package. It computes the non-exponential part in exact rational
arithmetic (`Fraction`) and the exponential with `decimal.Decimal` at 60
significant digits; the implementation uses IEEE-754 doubles and `math.exp`.
The two paths share no code, and agreement to 1e-12 relative is what two
different numerical paths should give.

| Fixture | Inputs | Expected L/h (independent) | Implementation | Relative difference |
|---|---|---|---|---|
| `feed_at_onset` | X_F 10 g/L, V_F 4 L, t_F = t = 5 h | 1.116134751773049645e-1 | 0.11161347517730497 | 0.0 |
| `one_hour_after_onset` | t = 6 h | 1.583870606098325244e-1 | 0.15838706060983251 | 0.0 |
| `three_hours_after_onset` | t = 8 h | 3.189523721313407102e-1 | 0.31895237213134064 | 1.7e-16 |
| `same_point_in_other_units` | 10000 mg/L, 4000 mL, t = 6 h | 1.583870606098325244e-1 | 0.15838706060983251 | 0.0 (identical to the base case) |
| `overridden_parameters` | mu_set 0.5, Y_XS 1.0, m 0.1, t = 7 h | 4.626862686738800401e-1 | 0.46268626867388 | 0.0 |
| `zero_biomass_at_onset` | X_F = 0 g/L | 0.0 | 0.0 | exact |

Every case agrees to within one double-precision rounding (worst case
1.7e-16 relative), against a declared tolerance of 1e-12.

The exact rational pre-factor and exponent argument are stored alongside each
fixture (for example `feed_at_onset` has pre-factor `1259/11280` L/h and
exponent argument `0`), so the arithmetic can be redone by hand.

**The fixture inputs are not paper values.** `X_F`, `V_F`, `t_F` and `t` are
illustrative numbers chosen to exercise the formula; they are marked as such in
the fixture file, and no test or documentation presents them as measurements.

## 5. Validation rules

Applied to caller-supplied numbers; none of them is a claim about the biology.

| Rule | Behaviour |
|---|---|
| `X_F`, `V_F`, `t_F`, `t` missing | `MissingRunInput` naming every missing input; never defaulted |
| `t < t_F` | `FeedTimeBeforeStart` |
| `V_F` = 0 | `ValueError`: a bioreactor holding no culture is not a fed-batch culture. `X_F` = 0 stays allowed — a boundary of the printed expression, not a missing vessel |
| non-numeric input (including `bool`) | `TypeError` |
| NaN or infinite input | `ValueError` |
| negative run input or parameter | `ValueError` |
| `S_F` or `Y_XS` = 0 | `ValueError` (the expression divides by it) |
| unit unregistered, or of the wrong dimension | `UnitError` |
| parameter overridden | evaluated, and recorded in `deviations` with `parameters_are_reported = False` |
| `exp` overflow, or a non-finite result | `FeedRateNumericalError`, a subclass of `FeedRateError`; never a raw `OverflowError` |

Determinism: identical inputs give bit-identical output, verified in-process
and across two fresh interpreter subprocesses.

### What the numerical limit is not

`FeedRateNumericalError` reports that the float range was exceeded. It is
deliberately worded to say that this is a limit of evaluating the printed
formula and not a statement about the culture: **no maximum cultivation time is
invented**, and a value the package *does* return for a time or condition the
paper never reported is mathematical extrapolation, not a validated process
prediction. A test asserts that wording, so it cannot quietly drift into
implying a biological bound.

## 6. Provenance model

`Provenance.REPORTED → Basis.OBSERVED`, `Provenance.DERIVED → Basis.COMPUTED`,
`Provenance.UNKNOWN → Basis.UNRESOLVED`, enforced in `Quantity.__post_init__`:

* a `reported` quantity without evidence is refused;
* a `derived` quantity without a method, or without named inputs, is refused;
* an `unknown` quantity with a value is refused;
* a numeric quantity needs a registered unit.

The six reported readings are the only `reported` quantities in the package.
The feed-rate result is the only `derived` one, and it names all eight inputs
it used.

## 7. The seven absences

Recorded in `equations.MISSING_MODELS` with `why_needed`, `missing_inputs` and
`why_not_implemented`:

`kinetics.growth_law`, `kinetics.dissolved_oxygen_balance`,
`transfer.oxygen_uptake`, `expression.gfp_kinetics`,
`calibration.fluorescence_to_gfp_mass`, `data.digitised_trajectory`,
`coupling.other_models`.

`test_exclusions.py` asserts the absence structurally as well: the package
contains exactly one executable equation, exactly the eight modules listed
below, the full function surface of the package is enumerated and pinned, the
only data file shipped is the extracted page text, the only non-stdlib import
is the optional page-text rebuild, and no adapter registration or worker was
added anywhere outside `Models/Baez/`.

The three isolation checks now **execute** rather than skipping. They discover
the repository root by walking up and inspecting
`composition/composition/adapters`, assert that file never mentions this
package, assert the only worker modules are `morris_worker.py` and
`zielinski_worker.py`, and run `python -m composition.registry` to confirm it
lists exactly the two pre-existing models. A separate test asserts those
guards carry no skip marker, and another asserts discovery *fails loudly*
outside a checkout rather than skipping.

## 8. Tests

Run each suite from its own directory.

| Suite | Collected | Passed | Skipped | Result |
|---|---|---|---|---|
| `Models/Baez/tests` | 195 | **195** | 0 | green |
| `composition/tests` (pre-existing) | 242 | 242 | 0 | green, unmodified |
| `Models/Morris/tests` (pre-existing) | 186 | 186 | 0 | green, unmodified |
| `Models/Zielinski/tests` (pre-existing) | 223 | 223 | 0 | green, unmodified |

Combined collection, run from the repository root:

| Invocation | Result |
|---|---|
| `pytest Models/Baez/tests Models/Morris/tests` | **381 passed**, exit 0 |
| `pytest Models/Baez/tests Models/Zielinski/tests` | **418 passed**, exit 0 |
| `pytest Models/Baez/tests Models/Morris/tests Models/Zielinski/tests` | exit 4 — `ModuleNotFoundError: No module named 'models.zielinski_2019'` |
| `pytest Models/Morris/tests Models/Zielinski/tests` (**Baez absent**) | exit 4 — the identical error |

The three-way failure is **pre-existing and not caused by this package**:
Morris and Zieliński each ship a top-level `models` package, and the last row
reproduces it with Baez absent. Fixing it would require changing one of those
two models, which this package must not do.

`python -m composition.registry` reports only `morris2011.material_balance` and
`zielinski2019.rhi_process`, exit code 0. `Models/Zielinski/out/` is unchanged:
176 reported rows plus 20 computed rows, the same 196 values, byte-identical to
their pre-task digests.

Baez suite breakdown: `test_feed_rate.py` 58, `test_source_provenance.py` 46,
`test_exclusions.py` 29, `test_citation_fidelity.py` 23, `test_observations.py`
19, `test_manifest.py` 12, `test_units.py` 10 (the sum is more than 195 where
parametrised cases share a definition; the authoritative figure is the
collected count).

## 9. File map

| File | Role |
|---|---|
| `baez2014/source.py` | citation, DOI, printed-page arithmetic, repository-root and PDF resolution, page-text extraction, `page_contains` |
| `baez2014/units.py` | unit whitelist, dimensions, conversion |
| `baez2014/provenance.py` | `Provenance`, `Basis`, `EvidenceRef`, `Quantity`, `ReportedObservation`, `Condition` |
| `baez2014/equations.py` | the one executable equation; the seven declared absences |
| `baez2014/feed_rate.py` | `feed_rate()`, validation, numerical-range handling, the four reported parameters, `UNVALUED_RUN_INPUTS` |
| `baez2014/observations.py` | the six reported readings, ten setup conditions, lookups, serialisation |
| `baez2014/manifest.py` | what the package declares about itself |
| `baez2014/__main__.py` | `python -m baez2014 [--check PATH]` |
| `baez2014/data/paper_pages.json` | normalised text of printed pages 1–7 |
| `fixtures/build_feed_rate_fixtures.py` | the independent calculator |
| `fixtures/feed_rate_fixtures.json` | the fixtures and their exact rational parts |
| `manifest.json` | committed manifest snapshot, checked by a test and by `--check` |
| `tests/_baez_testkit.py` | paths and structural repository-root discovery, uniquely named so it cannot collide with a sibling suite |
| `tests/conftest.py` | fixtures only, plus the pinned `basetemp`; defines nothing a test module imports |

## 10. Unresolved items and limitations

1. **FU ↔ GFP mass remains unresolved.** The paper prints both readings on
   p. 3 and states no conversion for this fed-batch culture. The package stores
   them separately in different dimensions and offers no factor. (p. 3 also
   prints specific activities for other experiments; those are not this
   culture's endpoint and are not used here.)
2. **Growth as a function of dissolved oxygen remains unresolved.** Two batch
   readings, reported as not significantly different, with no functional form
   printed.
3. **The run inputs are unvalued.** Any feed-rate number depends on values the
   caller supplies.
4. **Citation checking is against extracted text**, so line-end hyphenation is
   tolerated for quoted phrases (`source.page_contains`). Reported values are
   checked strictly.
5. **No registration in the composition layer.** `manifest.json` records
   `registered_in_composition_registry: false` and why: no model id and version
   were agreed with that layer, and none is guessed. `composition/` was not
   modified.
6. **The isolation guards require a repository checkout.** Outside one they
   fail with an actionable message rather than skipping — deliberately, since
   a skip is what let them silently stop running when this package moved.
7. **The three-way combined run still fails**, on the pre-existing collision
   between the Morris and Zieliński `models` packages. Demonstrated to occur
   with Baez absent; out of scope here because it would mean modifying one of
   those two models.
8. **Tests cannot establish scientific validity.** They establish agreement
   with the specification.