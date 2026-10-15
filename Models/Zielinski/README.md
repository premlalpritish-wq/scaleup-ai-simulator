# Zieliński et al. (2019) — recombinant human insulin process model

An executable, evidence-traceable representation of the process described in
*"Expression and purification of recombinant human insulin from E. coli 20 strain"*,
Protein Expression and Purification 157 (2019) 63–69.

**Read [`MODEL_REPORT.md`](MODEL_REPORT.md) first.** It states exactly what the model
does and does not compute, and documents five contradictions found in the source.

## Quick start

```bash
python run_model.py          # build the graph, run both modes, write out/
python -m pytest tests -q    # 223 tests
```

No third-party runtime dependencies. `pytest` is needed only for the tests.

## What it is

A typed process graph (15 operations, 17 material streams) with:

- **Provenance on every number** — `reported`, `derived`, `digitized`, `assumed` or
  `unknown`, each with a page-level citation to the paper and the source wording.
- **Unknown values that stay unknown** — carried as `None` with a recorded reason. They
  are never replaced by zero or a default. This is enforced in `Quantity.__post_init__`,
  which raises if an `unknown` quantity is given a value.
- **Transparent derivations** — every computed value carries its equation and its fully
  expanded inputs, including source unit, normalized unit and the provenance of each
  input.
- **Two execution modes with a hard wall between them.** Evidence replay restates
  observations and applies accounting identities. Predictive execution starts from
  declared inputs only and **fails closed**, naming the missing equation, input or model.

## What it is not

It is not a predictive simulator. The paper reports no kinetics, no oxygen-transfer data,
no AU calibration and no purification model, so the model declares eight absent models
explicitly and refuses to invent them. Running predictive mode with no inputs resolves
nothing — 23 unresolved targets — which is the correct outcome.

In particular it does **not**: fit Monod or biomass kinetics, simulate folding, model
CFD/mixing/oxygen transfer, predict scale-up, invent purification recoveries, or convert
AU into grams, molarity or IU. The spectrophotometer was calibrated with water (§2.18),
so the AU scale is instrument-relative and no such conversion exists in the unit registry.

## Layout

| Path | Contents |
|---|---|
| `scaleup_ai/` | canonical paper-agnostic core: units, provenance, process graph, equations, engine, serialization, reporting |
| `models/zielinski_2019.py` | the model itself — nodes, streams, quantities, evidence, equation wiring |
| `models/data/` | digitized Fig. 3 trajectory; extracted article text used to verify citations |
| `tests/` | 223 tests, including AT-001..AT-026 (`test_acceptance_criteria.py`) |
| `out/` | generated artifacts (`graph.json`, `evidence_record.json`, `quantities.csv`, `computed.csv`, `run_summary.md`) |
| `run_model.py` | CLI entry point |

## Citations are verified, not trusted

`tests/test_paper_fidelity.py` checks the model's citations against text extracted from
the article PDF: all **131 reported scalar values** are found verbatim on the page the
model cites, as are both endpoints of every reported range, every number and subject
reagent of every preserved formula, and every `original_text` quote.

## Acceptance

`tests/test_acceptance_criteria.py` implements AT-001 … AT-026, each criterion mapped
to a named test class through an explicit `AT_COVERAGE` table that the suite checks for
completeness.

The acceptance tests were themselves validated by **mutation testing**: each criterion
was confirmed to fail when the model is deliberately broken. All 13 effective mutations
were caught, including two that exposed a real gap — nothing originally pinned the
*reported* source values, so a contradiction could have been "resolved" by quietly
editing 285 mL to 306.07 mL and every arithmetic check would still have passed. The
pinned-value table in `TestAT007ConflictingEvidencePreserved` now prevents that.

To regenerate the verification dataset from the PDF:

```python
from models.source import rebuild_paper_pages
rebuild_paper_pages()   # rewrites models/data/paper_pages.json
```

## Using it

```python
from models.zielinski_2019 import build_engine, predict
from scaleup_ai import ExecutionMode, Provenance, Quantity

engine = build_engine()

# Replay the paper: reported conditions and observations + supported accounting.
run = engine.run(mode=ExecutionMode.EVIDENCE_REPLAY)
run.summary.to_dict()["graph_is_predictive"]   # -> False, always

# Ask for something the paper cannot support: fails closed with a stated reason.
r = predict("node:N15:insulin_mass_from_au")
r.is_resolved           # -> False
r.unresolved.reason     # -> "... requires extinction coefficient epsilon280, ..."

# Ask for something it can: supply declared inputs, get a labelled prediction.
engine.run(mode=ExecutionMode.PREDICTIVE, inputs={
    "stream:S03_wet_biomass:wet_biomass_total":
        Quantity("wet_biomass_total", "wet biomass", Provenance.ASSUMED, 560.0, "g"),
})
```

## Provenance rules

| Class | Meaning | Must carry |
|---|---|---|
| `reported` | stated in the paper | `EvidenceRef` (source, PDF page, printed page, section) |
| `derived` | computed by a transparent equation | `method` + `inputs` |
| `digitized` | read from a published figure | `Uncertainty` + method |
| `assumed` | supplied by the implementer | an `Assumption` with rationale |
| `unknown` | unavailable | a reason; never a value |

Ranges reported by the paper (`15–16 h`, `70–120 mg/dL`, `95–96%`) are stored as ranges
and are never collapsed to a point value. Any equation that would need one fails with a
structured reason instead.

## Provenance of this package

`scaleup_ai/` is the canonical ScaleUp AI core for this repository and is deliberately
paper-agnostic: no Zieliński-specific type is defined inside it. It is intended to be
hoisted to a shared location when further models are added, so that models do not each
grow their own `ProcessState` / `ProcessGraph` / evidence representation.