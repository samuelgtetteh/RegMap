# Build then export the engine as ONE self-contained tarball you can ship to any Docker host.
# The host needs no internet and no source — just: docker load -i regmap-engine-0.1.tar
$ErrorActionPreference = "Stop"
$root = (Resolve-Path "$PSScriptRoot\..\..").Path
$tag  = "regmap-engine:0.1"
$out  = Join-Path $root "dist\regmap-engine-0.1.tar"
New-Item -ItemType Directory -Force (Split-Path $out) | Out-Null
Write-Host "Building $tag ..."
docker build -f "$root\regmap_engine\docker\Dockerfile" -t $tag $root
Write-Host "Exporting -> $out ..."
docker save $tag -o $out
Write-Host "`nShip this one file: $out"
Write-Host "On the host:  docker load -i regmap-engine-0.1.tar; docker run --rm -p 8000:8000 $tag"
