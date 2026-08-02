#!/usr/bin/env bash
# Build + smoke-test the RegMap crosswalk engine image. Run from anywhere; it resolves the repo root.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
echo "Building regmap-engine:0.1 from $root ..."
docker build -f "$root/regmap_engine/docker/Dockerfile" -t regmap-engine:0.1 "$root"
cat <<'EOF'

Run it with:
  docker run --rm -p 8000:8000 regmap-engine:0.1
Then:  curl localhost:8000/health   ·   open http://localhost:8000/docs
EOF
