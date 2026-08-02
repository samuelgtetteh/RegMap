# Build + smoke-test the RegMap crosswalk engine image. Run from anywhere; it resolves the repo root.
$ErrorActionPreference = "Stop"
$root = (Resolve-Path "$PSScriptRoot\..\..").Path
Write-Host "Building regmap-engine:0.1 from $root ..."
docker build -f "$root\regmap_engine\docker\Dockerfile" -t regmap-engine:0.1 $root
Write-Host "`nRun it with:"
Write-Host "  docker run --rm -p 8000:8000 regmap-engine:0.1"
Write-Host "Then:  curl localhost:8000/health   ·   open http://localhost:8000/docs"
