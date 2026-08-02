#!/usr/bin/env bash
# Build then export the engine as ONE self-contained tarball you can ship to any Docker host.
# The host needs no internet and no source — just: docker load -i regmap-engine-0.1.tar
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
tag="regmap-engine:0.1"
out="$root/dist/regmap-engine-0.1.tar"
mkdir -p "$(dirname "$out")"
echo "Building $tag ..."
docker build -f "$root/regmap_engine/docker/Dockerfile" -t "$tag" "$root"
echo "Exporting -> $out ..."
docker save "$tag" -o "$out"
echo ""
echo "Ship this one file: $out"
echo "On the host:  docker load -i regmap-engine-0.1.tar && docker run --rm -p 8000:8000 $tag"
