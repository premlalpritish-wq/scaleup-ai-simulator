# Godot Web export feasibility

Checked 2026-10-22 with Godot `4.7.2.stable.official.ed1daf0bf` on Windows NT 10.0.26300.0. The repository was at base commit `b621f24a319647757fee46cbbdd314bd8b629335` with the verification worktree changes described in [WEB_DEMO_DEPLOYMENT.md](WEB_DEMO_DEPLOYMENT.md).

## Template and preset check

The installed version requires templates matching `4.7.2.stable`. The default `%APPDATA%/Godot/export_templates` directory exists but contains no version directory or template files. No `export_presets.cfg` existed at the repository root.

To make a minimal export attempt, a temporary `Web` preset was written at the root and removed afterward. With Godot's profile redirected to the writable verification temp directory, the export failed specifically because it could not find:

- `export_templates/4.7.2.stable/web_nothreads_debug.zip`
- `export_templates/4.7.2.stable/web_nothreads_release.zip`

The expected output `.test-tmp/godot-export/index.html` was not created. No matching templates were installed or downloaded. The temporary preset was removed; this test leaves no export preset in the project.

## Source constraints

- The current project selects Forward+ and Jolt Physics. Godot 4.7's web target requires the Compatibility renderer; a Compatibility export has not been produced or run in Chromium.
- The original GDScript viewer uses `OS.execute()` to start local Python through `scripts/runner.gd`. That desktop subprocess boundary is not available in Web. The exported viewer would need HTTPS API requests at this boundary.
- The shake-flask vessel is a schematic visual model, not a fluid dynamics simulation. The browser-native version uses returned culture-volume data and does not add bubbles, mixing, flow, or spatial gradients.

## Feasibility and acceptance

Preserving the original viewer is feasible in principle by selecting the web-compatible renderer and replacing only the desktop Python subprocess boundary with the hosted API. This has not been implemented or verified as a Godot export. Matching templates are the immediate blocker to a minimal build; after installing them, the next acceptance steps are export under Compatibility, inspect the generated HTML/wasm assets, and run the app in Chromium against the API.

The hosted browser-native viewer does not depend on a Godot export. Its implementation, local regression results, and browser limitation are recorded in [WEB_DEMO_DEPLOYMENT.md](WEB_DEMO_DEPLOYMENT.md).
## Update — successful export achieved 2026-10-22

Godot 4.7.2.stable and its 4.7.2.stable export templates were installed into a temporary location and %APPDATA%/Godot/export_templates. The project exported successfully (exit code 0) with a single-threaded Web preset on the Compatibility-capable WebGPU/WebGL 2.0 target. The exported build started in Chromium: the title, WebGL 2.0 Compatibility renderer, and 3D scene loaded.

Blocking limitations (project-code, not toolchain):
1. Could not locate the composition package. — the GDScript resolves the Python package via repository-root paths.
2. OS::execute() / create_process() is unavailable in the Web runtime, so scripts/runner.gd cannot launch Python.

Conclusion: the Godot viewer CAN be exported and renders in Chrome, but live scientific execution requires replacing the OS.execute boundary with the verified Pyodide runner (or the hosted API). The web-native viewer remains the verified live-execution baseline.

