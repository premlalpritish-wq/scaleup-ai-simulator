# Research explorer — checkpoint

Date: 2026-11-02. State: complete and verified; only `docker build` is unexecuted.

## Key paths

| Path | Role |
|---|---|
| `web/research/index.html`, `app.js`, `style.css`, `config.js` | Browser page (static, no deps) |
| `api/research.py` | Adapter over `composition.workflow.execute.run_workflow`; case projection, gaps, reports, runs, feedback |
| `api/app.py` | Adds `/api/research/*` and serves `/research/*` (allow-list); graph routes untouched |
| `api/Dockerfile`, `.dockerignore` | Deployment: copies `api/research.py`, `composition/composition`, `composition/workflow`, `composition/workflow_runs`, `web/research` |
| `api/tests/test_research_api.py`, `api/tests/conftest.py` | 28 tests (adapter + staged deployment + HTTP) |
| `web/tests/research_explorer.mjs` | 27 headless-Chrome checks |
| `reports/RESEARCH_EXPLORER.md` | Full documentation (interface, honesty rules, API, deployment) |

## Verified commands

```
python -m pytest api/tests -q                          # 28 passed
python -m pytest composition/tests -q --basetemp composition/.artifacts/pytest-basetemp
                                                       # 790 passed, 0 failed/errors/skipped
python -m pytest composition/tests/test_research_workflow.py -q   # 20 passed
node web/tests/research_explorer.mjs                   # 27 passed, 0 failed
godot --headless --path . --script res://composition/tests/godot/research_workflow_scene.gd
                                                       # 75 checks passed
```

## Decisions

* Case served from shipped artifacts (`composition/workflow_runs/pecan`), with an
  independent quote re-check; mismatch → HTTP 503, no evidence.
* `extraction_method`, `details`, `observations` are recorded, never encoded as
  evidence (`input.recorded_not_used`), because the workflow verifies curated
  passages rather than mining text.
* Non-pecan organism → 422 `evidence_not_applicable`, `result: null`.
* Encoder now marks analogue-species claims `hypothesis=True` (was always False in
  the fixture); artifacts regenerated.
* Feedback persisted only with `SCALEUP_FEEDBACK_DIR`; response states which.

## Fixed defects found during this work

1. Analogue claims were not flagged as hypotheses at claim level (encoder fix).
2. Dockerfile omitted `composition/workflow/model_package` → workflow graph
   invalid in a staged deployment (fixed; guarded by
   `test_a_staged_deployment_runs_the_workflow_from_copies_only`).

## Blockers / next steps

* `docker build -f api/Dockerfile .` not run: Docker daemon unavailable here.
  Run it, then `docker run -p 8080:8080` and open `/research/`.
* Optional: second test suite run of `Models/*` not repeated (unchanged by this
  work; composition suite covers integration).


## Godot pecan evidence scene (added after this checkpoint)

| Path | Role |
|---|---|
| `scripts/pecan_workflow.gd`, `scenes/pecan_workflow.tscn` | Step graph + evidence panel + outputs/unresolved/case tabs; reads `composition/workflow_runs/<case>/` |
| `scripts/workshop.gd` | Header button `PecanWorkflowButton` → `_on_pecan_pressed` |
| `composition/tests/godot/pecan_workflow_scene.gd` | 25 headless checks |

Verified: `godot --headless --path . --script composition/tests/godot/pecan_workflow_scene.gd`
→ 25 passed, 0 failures; `research_workflow_entry.gd` → 15 passed (workshop header intact);
`workshop.gd` parses. Launch: open the project, press **Pecan evidence workflow**, or
`scenes/pecan_workflow.tscn` directly. Not verified: rendered screenshots (headless only).



## Pecan 3D physical replay (updated)

| Path | Role |
|---|---|
| `scripts/pecan_process_sim.gd`, `scenes/pecan_replay.tscn`, `scripts/pecan_replay.gd` | Animated TRIzol-extraction bench: 5 timed operations (tissue transfer, dispensing, mixing, centrifugation, upper-phase transfer), deterministic `apply_clock(t)`, orbit camera, object picking, evidence/outputs/limitations tabs (reuses `ResultsPanel`). Vessels publish an `Opening` marker and the pipette a `TipMarker`; the pipette is aimed at the marker and the stream/droplets are derived from those two transforms. |
| `scripts/workshop.gd` | Header button `PecanReplayButton` → `_on_pecan_replay_pressed` |
| `composition/tests/godot/pecan_replay_scene.gd` | 54 headless checks (motion, separation, spatial alignment, camera independence, scrubbing, evidence, limits) |
| `composition/tests/godot/pecan_replay_gui_capture.gd` | Saves 6 GUI screenshots to `composition/.artifacts/` |
| `scripts/pecan_lab_view.gd` | Removed (superseded by the physical simulation) |

Verified: 54 headless checks pass; GUI captured with D3D12 at 7 instants
(`sim_1_tissue_in_air.png` … `sim_7_dispensing_closeup.png`), showing the tissue in
flight, the tip aligned over the tube mouth with the stream and droplets entering
the vessel, mixing wobble+bubbles, the tube in the spinning rotor, two separated
phases and the second tube receiving the upper phase.

| `composition/tests/godot/pecan_replay_gui_capture.gd` | Saves two GUI screenshots to `composition/.artifacts/` |

Verified: headless 26 passed; GUI captured with D3D12 (1600×950) at stage 2 (green, direct)
and stage 7 (amber, analogue, reference card). Launch: `godot --path . scenes/pecan_replay.tscn`
or the workshop header button. Zielinski replay files untouched.

