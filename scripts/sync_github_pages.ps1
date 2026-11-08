$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$source = (Resolve-Path -LiteralPath (Join-Path $repo 'web')).Path
$destination = Join-Path $repo 'docs'
if (Test-Path -LiteralPath $destination) {
    $resolvedDestination = (Resolve-Path -LiteralPath $destination).Path
    if (-not $resolvedDestination.Equals((Join-Path $repo 'docs'), [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to write outside the repository docs directory: $resolvedDestination"
    }
} else {
    New-Item -ItemType Directory -Path $destination | Out-Null
}
foreach ($relative in @('index.html', 'app.js', 'config.js', 'scene3d.js', 'scene.css', 'style.css', 'data/ganjave_fed_batch.json', 'data/precomputed_ganjave_reference.json', 'data/model_catalog.json', 'data/zielinski_replay_view.json', 'tests/static-fallback.html', 'tests/pyodide-live.html')) {
    $from = Join-Path $source $relative
    if (-not (Test-Path -LiteralPath $from -PathType Leaf)) { throw "Missing static site source: $from" }
    $to = Join-Path $destination $relative
    $parent = Split-Path -Parent $to
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    Copy-Item -LiteralPath $from -Destination $to -Force
}
$pyodideSource = (Resolve-Path -LiteralPath (Join-Path $source 'pyodide')).Path
$pyodideDestination = Join-Path $destination 'pyodide'
New-Item -ItemType Directory -Force -Path $pyodideDestination | Out-Null
Copy-Item -Path (Join-Path $pyodideSource '*') -Destination $pyodideDestination -Recurse -Force
$assetsSource = Join-Path $source 'assets'
if (Test-Path -LiteralPath $assetsSource) {
    $assetsDestination = Join-Path $destination 'assets'
    New-Item -ItemType Directory -Force -Path $assetsDestination | Out-Null
    Copy-Item -Path (Join-Path $assetsSource '*') -Destination $assetsDestination -Recurse -Force
}
Set-Content -LiteralPath (Join-Path $destination '.nojekyll') -Value '' -NoNewline
Write-Output "GitHub Pages static files synchronized to $destination"
