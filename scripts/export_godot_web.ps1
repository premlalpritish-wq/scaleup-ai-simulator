$ErrorActionPreference = "Stop"
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $repo
$godot = "D:\Godot\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64_console.exe"
$outDir = "export/web"
$preset = @"
config_version=5

[preset.0]

name="Web"
platform="Web"
runnable=true
advanced_options=false
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter="assets/zielinski_replay_result.json,assets/pecan/*.json"
exclude_filter="composition/*,data/*,Models/*,papers/*,*.pdf"
export_path="export/web/index.html"
patches=PackedStringArray()
encryption_include_filters=""
encryption_exclude_filters=""
seed=0
encrypt_pck=false
encrypt_directory=false
script_export_mode=1

[preset.0.options]

variant/extensions_support=false
vram_texture_compression/for_desktop=true
vram_texture_compression/for_mobile=false
html/export_icon=true
html/title="ScaleUp AI Composition"
html/head_include="<script type=\"module\" src=\"godot_pyodide_bridge.js\"></script>"
html/canvas_resize_policy=2
html/focus_canvas_on_start=true
html/experimental_virtual_keyboard=false
progressive_web_app/enabled=false
"@
$preset | Set-Content -LiteralPath (Join-Path $repo "export_presets.cfg") -Encoding utf8 -NoNewline
New-Item -ItemType Directory -Force -Path (Join-Path $repo $outDir) | Out-Null
& $godot --headless --path $repo --export-release "Web" (Join-Path $repo (Join-Path $outDir "index.html"))
if ($LASTEXITCODE -ne 0) { throw "Godot export failed with exit code $LASTEXITCODE" }
Copy-Item -LiteralPath (Join-Path $repo "web\godot_pyodide_bridge.js") -Destination (Join-Path $repo (Join-Path $outDir "godot_pyodide_bridge.js")) -Force
$pySrc = Join-Path $repo "web\pyodide"
$pyDst = Join-Path $repo (Join-Path $outDir "pyodide")
if (Test-Path -LiteralPath $pyDst) { Remove-Item -LiteralPath $pyDst -Recurse -Force }
Copy-Item -LiteralPath $pySrc -Destination $pyDst -Recurse -Force
Write-Output "Export complete: $outDir"