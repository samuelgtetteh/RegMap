#!/usr/bin/env bash
# End-to-end test of the engine on Docker Desktop's built-in Kubernetes.
# Prereqs: Docker Desktop > Settings > Kubernetes > Enable Kubernetes (wait until green),
#          and the image built locally: docker build -f regmap_engine/docker/Dockerfile -t regmap-engine:0.1 .
set -euo pipefail
NS=regmap
root="$(cd "$(dirname "$0")/../.." && pwd)"

echo "== context =="; kubectl config current-context
echo "== apply manifests =="
kubectl apply -k "$root/regmap_engine/k8s"
echo "== wait for rollout (model warm-up can take ~2 min) =="
kubectl -n "$NS" rollout status deploy/regmap-engine --timeout=210s
kubectl -n "$NS" get pods -o wide

echo "== port-forward svc/regmap-engine 8010:80 =="
kubectl -n "$NS" port-forward svc/regmap-engine 8010:80 >/tmp/regmap-pf.log 2>&1 &
PF=$!
trap 'kill $PF 2>/dev/null || true' EXIT
for i in $(seq 1 20); do curl -sf localhost:8010/health >/dev/null 2>&1 && break; sleep 1; done

echo "== GET /health =="; curl -s localhost:8010/health; echo
echo "== POST /map (metering headers) =="
curl -s -D - -o /tmp/k8s-map.json -X POST localhost:8010/map -H 'content-type: application/json' \
  -d '{"text":"encrypt data at rest","pair":"nist_csf2__nist_80053","top_k":3}' | grep -i "x-regmap\|HTTP/"
echo "--- body ---"; cat /tmp/k8s-map.json; echo
echo "== GET /usage =="; curl -s localhost:8010/usage; echo
echo
echo "OK. Tear down with:  kubectl delete -k regmap_engine/k8s"
