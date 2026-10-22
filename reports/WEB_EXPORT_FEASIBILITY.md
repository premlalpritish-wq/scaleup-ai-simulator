# Web export feasibility

Date checked: 2026-10-22. This records the checkout and local toolchain as found; it does not claim a deployed or browser-tested Godot build.

## Repository baseline

- Godot project: Godot 4.7 feature set; installed executable is 4.7.2.stable.official.ed1daf0bf.
- Startup scene in the current working tree: `scenes/workshop.tscn`, the interactive shake-flask workshop. The project also includes the Zieliński replay at `scenes/replay3d.tscn` and the composition editor.
- `project.godot` selects Forward+ and Jolt Physics. No export preset was present at the repository root.
- No model-viewer physics bodies were found in the workshop scene path; the vessel is a visual model and must not be presented as a fluid simulation.
- The viewer reads and writes `user://workshop_graphs` and `user://workshop_results`, resolves `res://` assets, and uses `OS.execute` through `scripts/runner.gd` to start the local Python runner. The GDScript runner passes local paths and the graph file to that subprocess.
- The existing Python execution boundary is `composition/composition/runner.py`; model execution, contracts, compatibility and provenance live in the registered Python adapters and composition engine.
- The project files, model packages, frozen Ganjave inputs, tests and baseline documents were already modified or untracked before this web-demo work. Those files were left intact. Current branch: `main`, six commits ahead of `origin/main`; remote: `https://github.com/premlalpritish-wq/scaleup-ai-simulator.git`.

## Export test and blockers

The installed Godot version was invoked with `--headless --path . --export-release Web ...`. The editor reported that `export_presets.cfg` does not exist. The configured Godot export-template directory contained zero files, so even a newly created preset cannot be exported with this installation. The headless editor also reported it could not write its per-user editor configuration under `%APPDATA%\Godot` in this sandbox. No HTML export was produced, and Chromium did not run an exported Godot application.

Two source-level issues also prevent treating the current native viewer as a ready web build:

1. Forward+ is a desktop renderer; Godot 4.7 lists Compatibility as the web renderer. The current project has no web renderer override. Godot's web export uses WebGL 2.0; a Compatibility-rendered build would need an actual export and Chromium run before this viewer could be accepted. [Godot 4.7 feature list](https://docs.godotengine.org/en/4.7/about/list_of_features.html)
2. `OS.execute` is the Python execution boundary used by the current GDScript viewer. The Godot OS documentation lists Android, iOS, Linux, macOS and Windows as implemented targets, not Web. The viewer cannot launch Python in a browser; this path must be replaced with HTTPS API requests before web export. [Godot OS API](https://docs.godotengine.org/en/4.7/classes/class_os.html)

Godot requires an installed export template and an export preset for command-line export. [Godot export documentation](https://docs.godotengine.org/en/4.7/tutorials/export/exporting_projects.html)

## Decision

The current checkout cannot produce a reliable browser build as configured. This work supplies a browser-native viewer and an HTTPS-oriented execution API because the native viewer currently depends on both an unsupported web renderer configuration and a desktop subprocess boundary. A Godot Web export was not ruled out after adaptations: selecting the Compatibility renderer and replacing `OS.execute` with the same hosted API are feasible code changes, but no export template was available here to test their effect in Chromium. The Godot export choice therefore remains an unverified limitation, not a claim that Godot Web is technically impossible.

The browser viewer uses a small, self-contained WebGL renderer for a schematic vessel. This avoids a client framework download and external font/CDN dependency. The liquid geometry is empty before a live result and is sized only from the returned `culture_volume` values; it shows no bubbles, mixing, flow or spatial gradients. The Zieliński model is identified as a literature replay and is not exposed as a live prediction.

## Acceptance status

- Native Godot export in this environment: **blocked before export** (no preset, no templates, editor profile not writable).
- Exported-app Chromium checks: **not run** (no exported application).
- Browser-native viewer and real API execution: automated acceptance files are in `web/tests/workflow.html`; the browser workflow could not run because the sandbox denied loopback socket access. API runner tests, including a real Ganjave execution, did run and pass; see `reports/WEB_DEMO_DEPLOYMENT.md`.
