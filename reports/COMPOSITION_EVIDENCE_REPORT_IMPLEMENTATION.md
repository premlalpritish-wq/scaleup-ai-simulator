# Evidence-Backed Composition Report — Implementation

**Status:** implemented and verified. All regression suites at or above their recorded baseline.

## The problem this solves

Four different questions share a vocabulary in a composition tool, and only one of them
is about whether the software worked:

1. Did the connection hold **mechanically**? (quantity, unit, direction, component, ordering)
2. Does it **mean** anything between *these two models*?
3. Did it **run**?
4. Is any of it **scientifically validated**?

A graph can be mechanically clean, semantically refused, unrun, and entirely unvalidated
at the same time. Before this work the runner reported a `status` and a list of
diagnostics, which collapses all four into "did it succeed". The dry-to-wet biomass
connection in `examples/rejected_cross_model_dcw.json` is the clearest illustration: it
is dimensionally perfect, scientifically refused, never executed, and its participating
models have no validation claim at all. Nothing in the result document said which of
those was which.

The report makes the distinction explicit and inspectable, for every graph the runner is
asked about — including refused ones, plan-only ones, and ones that never reached the
engine.

---

## 1. Architecture changes

### Data flow

```
CompositionGraph ──validate/plan──▶ CompositionEngine.execute()
                                          │
                                          ├─ diagnostics  (already emitted by the
                                          │                engine's mechanical rules)
                                          └─ cross_model.check()  (the declared policy)
                                                    │
                                                    ▼
                                        report.build_report(graph, loaded,
                                                            diagnostics, result)
                                                    │
                                                    ▼
                                    CompositionResult.composition_report
                                                    │
                                    CompositionResult.to_dict()["composition_report"]
                                                    │
                                          runner writes the result JSON
                                                    │
                                                    ▼
                                   Godot CompositionReportPanel (Report tab)
```

One report, built in one place, carried on the document the runner already writes. No
parallel compatibility system, no second rule table in the UI.

### Files changed

| File | Change |
|---|---|
| `composition/composition/report.py` | **New.** Builds the report. Pure description; decides nothing. |
| `composition/composition/cross_model.py` | `Verdict` gains `evidence_basis` and `assumptions`; `Boundary` gains `assumptions`. Distinguishes refusal from uncertainty. |
| `composition/composition/contracts.py` | `CompositionResult` gains `composition_report` (defaulted) and serialises it. |
| `composition/composition/engine.py` | Builds the report on all three exit paths (invalid, plan-only, executed). |
| `composition/composition/runner.py` | `_error_result` carries a report; the bad-input path no longer crashes on a non-mapping graph. |
| `scripts/composition_report_panel.gd` | **New.** The Report tab. |
| `scripts/main.gd` | Adds the tab, renders the report, marks it stale. |
| `composition/tests/test_composition_report.py` | **New.** 55 tests. |
| `composition/tests/godot/palette_graph_run.gd` | +46 checks for the real UI workflow. |

### Schema extension to the rule layer (smallest backward-compatible change)

`Verdict` already carried `permitted: bool` plus a `stance` slug. It could not distinguish
*"a source says these cannot be connected"* from *"nobody has written down whether they
can"*. Both were `permitted=False`, `stance="refused_unclassified"` vs
`"refused_dimensional_only:mass_concentration"` — recoverable from the slug, but the slug
is a label, not a contract.

Two fields, both defaulted, so every existing construction site and test is unaffected:

```python
evidence_basis: str = "documented_incompatibility"
    # "documented_incompatibility" | "evidence_limited" | "permitted"
assumptions: tuple[str, ...] = ()
```

`Boundary` gains `assumptions` too, so each boundary carries its own premise rather than
one boundary's being applied to another — a bug found and fixed during implementation,
when the Ganjave premise leaked onto the Morris boundary and every Morris→Morris
connection reported as `permitted_conditionally`.

The Ganjave cascade premise is **read from the model**, not restated:

```python
_GANJAVE_CASCADE_ASSUMPTION = (
    "ganjave/initial_glycerol_concentration: "
    + next(rule.assumption for rule in _INPUT_CONTRACT
           if rule.port_id == "initial_glycerol_concentration"),
)
```

A test asserts the report's assumption string contains the contract's own words, so a
paraphrase or a drift would fail rather than pass quietly.

---

## 2. Report schema

`composition-report/1`. Top level: `schema`, `reading_guide`, `graph`, `execution`,
`connections`, `science`.

### `execution` — whether it ran

`attempted`, `plan_only`, `status`, `results_produced`, `result_count`, `run_id`,
`reproducibility`, `error_count`, `warning_count`, `results_invalidated`, `note`.

`note` distinguishes the three quite different causes of "no results": refused before
execution (with errors), plan-only by request, and a valid-but-empty graph. Collapsing
them into one message would be a claim nobody made.

### `connections[]` — every attempted connection

| Field | Meaning |
|---|---|
| `connection_id` | as declared |
| `source` / `destination` | 14 fields each: instance, model id **and version**, port, quantity, unit, label, direction, temporal basis, component identity, provenance requirement, required, usable, description |
| `dimensional` | `result` ∈ `compatible` / `incompatible` / `unknown`, `decided_by`, `note` |
| `semantic` | `result`, `rule`, `stance`, `reason`, `evidence_basis`, `quantity_pair`, `assumptions`, `evidence`, `unresolved`, `remediation` |
| `disposition` | one of five words, below |
| `disposition_explanation` | one sentence a reader can act on |
| `diagnostic` | the engine's own diagnostic, verbatim: `code`, `severity`, `message`, `remediation`, `origin` |
| `evidence` / `assumptions` / `unresolved` / `remediation` | mirrored from `semantic` for convenience |
| `other_diagnostics` | any further diagnostics naming this connection |

**Dispositions — five, never a single boolean:**

| Disposition | Meaning |
|---|---|
| `mechanically_invalid` | A contract, type, unit, direction, component or ordering rule failed. |
| `scientifically_refused` | Nothing mechanical objected; a declared rule rejects it with cited evidence. |
| `permitted_conditionally` | A source supports it, under stated assumptions. |
| `permitted` | Permitted with no per-connection assumption recorded. |
| `unresolved` | Nobody has written down whether it is allowed. Evidence-limited, **not** a finding of physical incompatibility. |

The mapping is `report.disposition_for(blocking_diagnostic, verdict)` — public, because
the Godot panel keys its colours off it and a consumer needs the mapping itself, not the
sentence that produced it. Three branches, in this order:

1. A mechanical diagnostic fires → `mechanically_invalid`. A semantic refusal is never
   presented in place of a specific mechanical failure.
2. `connection.cross_model_refused` → `scientifically_refused`, **unless**
   `evidence_basis == "evidence_limited"`, which gives `unresolved`.
3. Nothing refused → `permitted_conditionally` if the rule carries assumptions,
   `permitted` otherwise.

### `science` — validation status

`models[]` carries each instance's `implementation_status`, `reproduction_status`,
where that status came from, and the model's own declared limitations
(`declared_unsupported_capabilities`, `declared_missing_information`,
`declared_missing_models`, `assumptions`).

`combined_graph` **always** reports `independently_validated: false` and
`status: "not_established"`, with the basis stated. This is not a placeholder to be
filled in later; it is the correct answer. Composing two models produces a system no
published source has evaluated, and validation evidence for a part is a statement about
that part. `execution_is_not_validation` states the rule in words next to the number.

### Unknown versus empty

`"not_documented"` means *nobody said*. `[]` means *somebody said nothing*. They are
different and a test holds them apart, because collapsing them would let an empty list
read as an absence of concerns.

---

## 3. Evidence-source mapping

Every displayed claim points at a real source. The report adds no evidence of its own;
it carries forward what `cross_model` and the manifests already declare.

| Report field | Comes from | Not invented |
|---|---|---|
| `semantic.evidence` | `cross_model.Boundary.evidence` + the per-pair reason | cited papers, DOIs, and file paths in the rule table |
| `semantic.reason` | `cross_model.Verdict.reason` | the rule's own prose |
| `semantic.assumptions` | `Boundary.assumptions`; the Ganjave one is read from `ganjave_contract.INPUT_CONTRACT` | the model's own words |
| `semantic.unresolved` | `cross_model` `unresolved` | what would have to exist first |
| `diagnostic.*` | the engine's `ModelDiagnostic.to_dict()` | verbatim, including remediation |
| `science.models[].limitations` | `manifest.unsupported_capabilities`, `.missing_information`, `.assumptions` | the model's own manifest |
| `science.models[].*_status` | the model's `validation_claim` via `output.value.extra` | only Ganjave publishes one; the rest read `not_documented` |
| `science.combined_graph` | always `not_established` | never derived from the parts |

Verified on the refused example: 7 evidence entries, all resolving to a real paper, DOI,
or repository path.

**Nothing was upgraded.** Ganjave's own claim is `reproduction_status: not_yet_validated`
and the report reproduces exactly that; a test asserts it and would fail if a passing
test run ever improved it.

---

## 4. The distinction that actually earns its keep

For `rejected_cross_model_dcw.json`:

```json
{
  "disposition": "scientifically_refused",
  "dimensional": {
    "result": "compatible",
    "decided_by": "composition.cross_model",
    "note": "The mechanical checks all passed -- which is why this connection is
             the dangerous kind. Quantity, unit, direction and component identity
             are satisfied; a compatibility rule rejects it anyway, on meaning."
  },
  "semantic": {
    "result": "refused",
    "rule": "composition.cross_model",
    "stance": "refused_dimensional_only:mass_concentration",
    "evidence_basis": "documented_incompatibility",
    "quantity_pair": ["mass_concentration", "mass_concentration"]
  }
}
```

`dimensional.result == "compatible"` alongside `disposition ==
"scientifically_refused"` is the whole point. An implementation that reported
`compatible: false`, or that reported only one of the two, would hide the reason the rule
exists.

---

## 5. Godot integration

One new tab, **Report**, in the existing `TabContainer`. No redesign; it uses the
conventions of `ValidationPanel` (card + labelled row + severity colour).

- **Every run.** `_on_runner_finished` calls `_report.show_report(payload)`. Because the
  runner publishes a report on every document, a refused graph gets one too.
- **Shape rejection is distinguished from runner silence.** `GraphDocument.validate_shape()`
  runs in GDScript and short-circuits the Run button, so the runner is never invoked.
  `show_graph_problems()` says exactly that — "the editor rejected this graph's shape
  before the runner was invoked" — rather than showing "no report", which would read as
  "the runner had nothing to say".
- **Unknown schema.** The panel declares the schema it renders and refuses to guess at
  fields it does not recognise.
- **Staleness.** `_invalidate_results()` *marks* the report stale with a banner rather
  than clearing it. A report is an argument, not a number: a reader part-way through an
  assessment who adds a connection should be able to finish reading it, told it describes
  the graph as it stood before that edit. `_discard_results()` clears instead, and is used
  where a different graph replaces this one (`_on_new_pressed`, `_load_graph_file`) — there
  the old assessment is about a document that no longer exists.
- **No rules of its own.** The panel holds no model id, no quantity pair, no port id. A
  harness check greps its source for all three, because a second rule table is exactly
  the failure this design exists to prevent.

---

## 6. Test results

### New

| Suite | Result |
|---|---|
| `composition/tests/test_composition_report.py` | **55 passed** |

Covers all eight required cases:

- **Case 1** — mechanical failure stays mechanical and stays specific: the diagnostic
  message is asserted byte-identical to the engine's, no `connection.cross_model_refused`
  is emitted alongside it, and a cyclic graph's connections are attributed to
  `order.cycle_detected` via `detail.connections` rather than reading as `permitted`.
- **Case 2** — dry biomass to wet biomass: both quantity definitions, matching units,
  `dimensional: compatible`, the stance, 7 evidence entries, the unresolved conversion
  question, `results: []`.
- **Case 3** — permitted connections: Morris → Morris is `permitted` with no assumptions;
  Ganjave → Ganjave is `permitted_conditionally` with the model's own premise quoted; no
  connection's JSON contains "validated", "verified" or "reproduced".
- **Case 4** — unclassified pairs: `evidence_limited`, disposition `unresolved`, and the
  reason explicitly says it is *not* a documented finding of physical incompatibility.
- **Case 5** — staleness: `results_invalidated` recorded; a stale report carries no
  results; the report has no `results` field to go stale in the first place.
- **Case 6** — provenance: `brass_alloying/out:A:w:Cu` keeps its three-record chain
  (`source` → `transfer` → `source`); the recomputed output names `brass_alloying`, not
  the upstream charge; no transfer claims a conversion that did not happen.
- **Case 7** — machine-readable: JSON round-trip, survives the actual runner subprocess,
  schema declared and versioned, every key present, `not_documented` ≠ `[]`.
- **Case 8** — real Godot workflow: +46 checks in `palette_graph_run.gd`.

### Regressions — all at or above baseline

| Suite | Baseline | Now |
|---|---|---|
| Composition | 448 passed | **503 passed** (+55) |
| `contract_boundary.gd` | 840 | **840** |
| `ganjave_graph_run.gd` | 51 | **51** |
| `palette_graph_run.gd` | 174 | **220** (+46) |
| Morris | 186 | **186** |
| Zieliński | 223 | **223** |
| Baez | 193 passed / 2 failed | **193 passed / 2 failed** |

The two Baez failures are the pre-existing stale counts in
`Models/Baez/tests/test_exclusions.py` — `test_no_adapter_worker_was_added_for_this_model`
and `test_the_composition_registry_lists_only_the_pre_existing_models` — which hard-code 2
workers and 2 registered models and were written before Ganjave was added. Unrelated to
this work, untouched, and reported separately as required.

No assertion was weakened and no unrelated test rewritten. No model, equation, parameter,
solver or validation status was modified.

### Two real bugs found and fixed

- **`move_child` on the wrong node** in `mark_stale` — an error on every staleness event.
- **`run_graph` crashed with `AttributeError`** on a non-mapping input (a JSON array),
  because its error path assumed `graph.get(...)`. A clean "bad input" refusal became a
  crash about the runner. Now reads defensively; `test_an_unreadable_document_still_carries_a_report`
  covers it.
- **The plan-only report was empty** — the engine's plan-only branch returned before the
  report was attached. Now built there too, so a plan-only run has as much to report as a
  full one, and its note says validation and ordering completed while execution did not.

---

## 7. Known limitations

1. **`not_documented` is the answer for most models.** Only Ganjave publishes a
   `validation_claim` through the composition boundary. Morris and Zieliński report
   `not_documented`, which means *this boundary publishes no claim* — neither a validated
   model nor an unvalidated one. Exposing a real claim for them requires a decision about
   where validation evidence lives per model; that is a separate piece of work.

2. **No shipped example exercises `refused_unclassified` end to end.** Every quantity
   Ganjave can publish and Zieliński can accept is currently covered by a rule. Case 4 is
   therefore tested at the rule and mapping level, and a test asserts this fact about the
   registry so that adding an uncovered port fails loudly and makes a refusal example
   buildable — rather than the gap going unnoticed.

3. **Godot's global class cache is a gitignored build artifact.** A new `class_name` must
   be scanned in before headless `--script` runs can resolve it
   (`godot --headless --path . --editor --quit`). This affects any newly added panel and is
   not specific to this work, but it will bite the next person who adds a file.

4. **The report is built by the engine, so it reflects the engine's view.** It cannot
   report on a graph the engine refused to parse — `empty_report()` says so explicitly
   rather than emitting an assessment that reads like a clean run.

5. **Provenance is referenced, not recomputed.** Whether a balance closed is established
   by that balance's own residuals in `result.results[].residuals`. The report deliberately
   does not infer it, and a test asserts it never claims a balance closed.

---

## 8. Fields that remain unknown or unsupported

| Field | State |
|---|---|
| `science.models[].implementation_status` / `reproduction_status` | `not_documented` for Morris and Zieliński; the model's own words for Ganjave |
| `science.combined_graph.independently_validated` | always `false` — correct, not missing |
| `semantic.*` where `check()` returns `None` | `not_applicable`, with a note that this is not a judgement in either direction |
| `source`/`destination` for an unresolvable port | `not_documented` rather than a guess |
| Remediation | the rule's, or `not_documented` where the rule states none |

No confidence score, conversion factor, evidence citation or scientific conclusion was
invented anywhere. Where support was absent, the field says so.
