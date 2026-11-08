# Composed-Process Validation Plan (Phase 1)

**Question asked:** can ScaleUp AI use a scientifically defensible *composition* of
literature-derived models to predict an independently reported experimental process?

**Answer: no. No cross-model composition in this repository currently qualifies.**

This is a finding, not a deferral. It is stated here in Phase 1 — before any dataset was
curated, any configuration frozen, or any prediction produced — because the alternative
would have been to assemble a graph that executes and call that a demonstration.

---

## 1. The boundary matrix

`composition/composition/cross_model.py` declares every ordered pair of registered
models. There are nine. Two are permitted; **both are same-model**.

| From → To | Stance | Permitted |
|---|---|---|
| Morris → Morris | `permitted` (conservation, Ch. 4 premise) | **yes** |
| Ganjave → Ganjave | `permitted_forward_cascade` | **yes** |
| Morris → Ganjave | `no_shared_quantity` | no |
| Ganjave → Morris | `no_shared_quantity` | no |
| Morris → Zieliński | `refused_component_identity` | no |
| Zieliński → Morris | `refused_component_identity` | no |
| Ganjave → Zieliński | `refused_dimensional_only` | no |
| Zieliński → Ganjave | `refused_dimensional_only` | no |
| Zieliński → Zieliński | `refused_no_supplyable_port` | no |

**There is no permitted boundary between two different models.** A composition, by
definition, requires one. Every cross-model pair is refused on scientific grounds, and
each refusal names why in the model's own terms rather than on dimensional vocabulary.

### Why each cross-model pair fails

**Morris ↔ Ganjave — `no_shared_quantity`.** Morris is a non-reacting control-volume
engine: it conserves declared masses and fractions and has nowhere to declare a yield, a
rate constant or a reaction. Feeding a culture into it would need a component set the
culture does not publish, and drawing a balance around a reaction it cannot express would
be arithmetically valid and physically wrong. Independently: the quantity vocabularies
are disjoint. Morris publishes `mass` and `mass_fraction`; Ganjave publishes
`mass_concentration`, `dimensionless`, `volume`, `time`. There is no port pair to refuse.

**Morris ↔ Zieliński — `refused_component_identity`.** Zieliński publishes process roles,
not conserved chemical entities; no stream of its own carries a component amount or a
mass fraction, and its manifest declares `component_identity` unsupported in those words.
A Morris port either names a component (and the names will not agree) or is a
control-volume total whose every entering unit must be attributable to one (and it is
not). From the Zieliński side the refusal is stronger: a balance drawn across a boundary
whose model publishes neither component identity nor reaction terms is the case CG-09
names explicitly as numerically valid and physically wrong.

**Ganjave ↔ Zieliński — `refused_dimensional_only`.** Both describe an *E. coli*
fed-batch culture, and neither quantity nor unit is what stands between them. Different
strain, construct, medium, scale, objective, five years apart. This is the boundary the
shipped `rejected_cross_model_dcw.json` example exercises: both ports are
`mass_concentration` in `g/L`, both describe an *E. coli* culture, and the connection is
refused anyway. A matching quantity here is a coincidence of vocabulary.

**Zieliński → Zieliński — `refused_no_supplyable_port`.** Its ports are the operating
conditions, measurements and transcribed values of a single reported experiment. None is
a stream another run could take. Two connected instances would both describe the same
published batch, asserting a relationship no source states.

---

## 2. The two permitted boundaries, and why neither is validatable

### Morris → Morris — permitted, but no bioprocess target exists

The boundary is sound: conservation across adjacent non-reacting control volumes is the
premise Chapter 4 exists to apply. Its shipped example is brass alloying.

It cannot validate a *cultivation* process. To use Morris for the Ganjave fed-batch one
would have to encode bioprocess stoichiometry — a glycerol-to-biomass yield, a substrate
uptake rate — into a balance engine that by construction has nowhere to put one. That is
not composing existing models; it is writing a new model and calling the composition a
demonstration. No published source supplies that yield for this system, and inventing it
is exactly what the task forbids.

### Ganjave → Ganjave — permitted, and explicitly *not* validated by the paper

The forward cascade carries the first culture's residual glycerol into a second culture's
`initial_glycerol_concentration`, under the model's declared assumption. The project's own
rule text already records the limitation:

> "The cascade is permitted under the model's declared assumption, **not validated by
> it**: nothing in the paper seeds a second culture from the first."

I confirmed this against the paper. Ganjave et al. (2022) cultivate five proteins — eYFP,
LkADH, CbFDH, GcADH, PDGF — as **five parallel shake flasks** under one feed recipe, not
as a sequential train:

> "The selected optimized recipe was tested for a range of proteins that show different
> extent of soluble expression in *E. coli*. … These fed-batch results were compared with
> the conventional batch cultivation of these proteins."

There is no two-stage culture anywhere in the paper. The cascade therefore has **no
experimental counterpart**, and evaluating it would require inventing a second culture's
initial biomass, substrate and dissolved oxygen with no observation to compare against.

---

## 3. Candidate processes considered and rejected

| Candidate | Rejected because |
|---|---|
| Morris → Morris → Ganjave, modelling the fed-batch reactor as a control volume | Morris↔Ganjave is refused (`no_shared_quantity`); encoding bioprocess yields into a non-reacting balance is model invention, and no source supplies the yield |
| Ganjave → Ganjave forward cascade vs. the paper's five-protein experiment | The five cultures are parallel replicates, not a cascade. No experimental counterpart exists |
| Ganjave → Zieliński, substituting the paper's cultures for each other | Explicitly refused (`refused_dimensional_only`); the shipped refusal example exists precisely to keep this connection closed |
| Morris → Zieliński, drawing a control-volume balance over the insulin process graph | Refused (`refused_component_identity`); Zieliński declares component identity unsupported |
| Two Zieliński instances | Refused (`refused_no_supplyable_port`); both would describe the same published batch |
| Baez (2014) as a third participant | Not in `REGISTRATIONS`; no adapter or worker exists, so it cannot participate in any graph |

---

## 4. What is missing

Stated specifically, so a future change can be proposed with its own evidence rather
than smuggled in as a connection.

1. **A published model with bioprocess stoichiometry that shares a quantity vocabulary
   with Ganjave.** Morris is the only other registered process model and it is
   deliberately organism-free. Connecting them needs a yield coefficient, which Morris has
   no port for and no source would supply.
2. **An experimental two-stage culture**, to give the permitted Ganjave cascade a
   measurement to predict. Ganjave 2022 contains none.
3. **A component/entity vocabulary shared between a process graph and a balance engine.**
   Zieliński's process roles (`wet_biomass`, `inclusion_biomass`, `chromatographic_fraction`)
   are not conserved entities, and the manifest says so.
4. **Independent measurements for a cascade**, separate from issue 2: even a published
   two-stage protocol would need its time courses, not just an endpoint.

Absent any of these, no composed-process validation is scientifically possible here.
Writing a connection anyway would produce a graph that runs and a report that says
`permitted`, which is precisely the failure mode this task exists to catch.

---

## 5. What is taken forward instead, and under what label

The strongest scientifically defensible evaluation the repository *does* support is a
**single-model** one, and it is worth doing: the paper reports real experimental data that
was explicitly held out of parameter estimation, and it is already digitised with
quantified uncertainty.

**Target:** Ganjave et al. (2022), fed-batch *E. coli* HCD in shake flask.

- **Paper Fig. 2** (printed p. 5) — 30 % glycerol, 40 % yeast extract, 0.52 mL/h.
  Caption: *"Model fitting."* **The parameters were estimated here. Not independent
  evidence.**
- **Paper Fig. 3** (printed p. 6) — 20 % glycerol, 30 % yeast extract, 0.78 mL/h.
  Caption: *"Model validation: Goodness of fit of the model with the experimental data that
  **was not used for estimation of model parameters**."* **This is the held-out
  experiment.**
- **Paper Fig. 5** (printed p. 7) — 17.5 % glycerol, 24.5 % yeast extract, 0.72 mL/h, the
  selected optimum, with experimental marks for all five proteins and a model curve.

**Label — stated everywhere, and not negotiable:**

> This evaluates **a model**, not a **composition**. It does not satisfy the task's stated
> objective of composed-process validation, and no result from it may be reported as
> evidence about composed processes.

It is taken forward because the same evidence base answers a strictly weaker and
genuinely answerable question — *does the implementation reproduce what the authors
measured, at a recipe their own parameter fitting never saw?* — and because a real,
quantified answer (pass or fail) is more useful than an empty one.

---

## 6. A correction the existing work carries

`Models/Ganjave/tools/run_scientific_validation.py` justifies comparing only against the
authors' plotted model curve:

> "The comparison is against the paper's own plotted model prediction, which is the right
> target: matching the *measured* points would require refitting the parameters against
> them."

**That justification is incorrect, and it has held back the only comparison that matters.**
Comparing against held-out measurements requires no refitting — that is what held-out data
is *for*. The parameters were fitted on Fig. 2; the Fig. 3 measurements are explicitly
"not used for estimation of model parameters"; Fig. 5 uses a different feed recipe again.
Both are legitimately comparable with the parameters frozen.

Consequences recorded here, not acted on unilaterally:

- `reports/GANJAVE_SCIENTIFIC_VALIDATION.md` states "No trajectory has been compared
  against a measured point." `Models/Ganjave/data/validation_results.json` contains
  exactly such a comparison (`biomass_vs_measured_points`, 6 PDGF points with combined
  uncertainty 0.7125 g/L), explicitly marked "never used as a target". The report and the
  data disagree; the data is correct.
- `Models/Ganjave/data/validation_fig5.json` is named for Fig. 5 and cites the held-out
  experiment as "Fig. 3", while `figure_reference_data.json` keys the held-out experiment
  as figure `"5"` and the selected optimum as `"6"`. **The dataset's figure keys do not
  match the paper's figure numbers.** Anyone auditing a traceable citation would look up
  the wrong figure. Corrected in the dataset built for this task.

Neither is fixed in place here: the fixture carries pre-registered criteria and a results
file derived from it, and rewriting either would destroy the audit trail that makes them
worth having. The corrections are applied in the new dataset, which states the paper's
figure numbers explicitly.

---

## 7. Evaluation design

Deliberately small, per "prioritise the smallest process that supports a meaningful
quantitative test".

| Phase | Artefact |
|---|---|
| 2 — dataset | `data/ganjave2022/observations.json`, built from `figure_reference_data.json` with paper figure numbers, per-point provenance and uncertainty; `data/ganjave2022/PROVENANCE.md` |
| 3 — freeze | `data/ganjave2022/frozen_configuration.json`, `data/ganjave2022/assumption_register.json` |
| 4 — protocol | `data/ganjave2022/evaluation_protocol.json`, written before the run, carrying the fixture's already-frozen criteria A–D unchanged plus new measured-points thresholds |
| 5 — execute | `composition/tools/evaluate_heldout_biomass.py`, through `python -m composition.runner` |
| 6 — report | `reports/COMPOSED_PROCESS_SCIENTIFIC_VALIDATION.md` |
| 7 — tests | `composition/tests/test_heldout_validation.py`, `composition/tests/test_evaluation_dataset.py` |

**Contamination disclosure.** Criteria A–D in `validation_fig5.json` were fixed before
`validation_results.json` was produced and are reused unchanged. The measured-points
thresholds in the new protocol are derived from the digitisation uncertainty and from the
authors' own model-versus-measurement agreement — neither depends on our output — **but I
had already read `validation_results.json`, including `biomass_vs_measured_points`, before
writing them.** That comparison is therefore reported as post hoc with thresholds stated
in advance, and is not claimed as a blind test. Criteria A–D are unaffected.

**No fitting.** The parameter set is Table 2 as printed, loaded as fitted. Nothing is
refit, no initial condition is tuned against an observation, and no criterion is
re-selected after seeing a result.
