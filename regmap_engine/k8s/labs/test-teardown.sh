#!/usr/bin/env bash
# Prove the paid-lab teardown design on a real cluster, before any product is built around it.
#
# This is step 1 of the build order in docs/lab_sessions_design.md. If these checks do not pass,
# nothing else in the lab product is worth building: the whole commercial model depends on a session
# reliably stopping when the credit it was paid for runs out.
#
# Setup (once):
#   kind create cluster --name regmap-labs --config kind-cluster.yaml
#   kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.28.2/manifests/calico.yaml
#   kubectl -n kube-system rollout status ds/calico-node --timeout=420s
#   kind load docker-image regmap-engine:0.2-cpu --name regmap-labs
#   kubectl apply -f sweeper.yaml
#
# Then:
#   bash test-teardown.sh [seconds_paid]      # default 90
set -uo pipefail

SECS="${1:-90}"
S="sess-test$$"
IMAGE="${LAB_IMAGE:-regmap-engine:0.2-cpu}"
HERE="$(cd "$(dirname "$0")" && pwd)"
pass=0; fail=0

ok()   { echo "  PASS  $1"; pass=$((pass+1)); }
bad()  { echo "  FAIL  $1"; fail=$((fail+1)); }
hdr()  { echo; echo "== $1"; }

cleanup() { kubectl delete ns "$S" --wait=false >/dev/null 2>&1 || true; }
trap cleanup EXIT

hdr "create session $S (paid for ${SECS}s)"
# Labels cannot contain ':', so the expiry is written with '-' in the time part; the sweeper converts.
EXPIRES=$(date -u -d "+${SECS} seconds" +%Y-%m-%dT%H-%M-%SZ)
sed -e "s|__SESSION__|$S|g" -e "s|__SECONDS__|$SECS|g" -e "s|__EXPIRES__|$EXPIRES|g" \
    -e "s|__IMAGE__|$IMAGE|g" -e "s|__TIER__|cpu-small|g" \
    "$HERE/session-template.yaml" | kubectl apply -f - >/dev/null || { echo "apply failed"; exit 1; }
echo "  expires-at=$EXPIRES"

for _ in $(seq 1 40); do
  sleep 3
  POD=$(kubectl -n "$S" get pod -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
  [ -n "${POD:-}" ] && [ "$(kubectl -n "$S" get pod "$POD" -o jsonpath='{.status.phase}')" = "Running" ] && break
done
[ -n "${POD:-}" ] && ok "lab pod running ($POD)" || { bad "lab pod never started"; exit 1; }

hdr "isolation"
kubectl -n "$S" exec "$POD" -- ls /var/run/secrets/kubernetes.io/serviceaccount/ >/dev/null 2>&1 \
  && bad "API-server token IS mounted — the learner can reach the control plane" \
  || ok "no service-account token mounted"

# NetworkPolicy: needs a CNI that enforces it. kindnet (Docker Desktop) silently ignores policies, so a
# pass here is only meaningful on Calico/Cilium.
if kubectl -n "$S" exec "$POD" -- python -c "
import socket,sys; socket.setdefaulttimeout(6)
try: socket.create_connection(('1.1.1.1',443)); sys.exit(1)
except Exception: sys.exit(0)" >/dev/null 2>&1; then
  ok "egress blocked by NetworkPolicy (CNI enforces it)"
else
  bad "egress ALLOWED — NetworkPolicy not enforced (kindnet? install Calico/Cilium)"
fi

kubectl -n "$S" exec "$POD" -- python -c "
import socket,sys; socket.setdefaulttimeout(5)
try: socket.create_connection(('169.254.169.254',80)); sys.exit(1)
except Exception: sys.exit(0)" >/dev/null 2>&1 \
  && ok "cloud metadata endpoint blocked" \
  || bad "cloud metadata REACHABLE — instance credentials exposed"

[ "$(kubectl -n "$S" exec "$POD" -- id -u 2>/dev/null)" = "10001" ] \
  && ok "runs as non-root (uid 10001)" || bad "not running as uid 10001"

kubectl -n "$S" exec "$POD" -- touch /rotest >/dev/null 2>&1 \
  && bad "root filesystem is writable" || ok "root filesystem read-only"

hdr "resource containment"
kubectl -n "$S" apply -f - >/dev/null 2>&1 <<EOF
apiVersion: v1
kind: Pod
metadata: {name: greedy}
spec:
  restartPolicy: Never
  automountServiceAccountToken: false
  securityContext: {runAsNonRoot: true, runAsUser: 10001, seccompProfile: {type: RuntimeDefault}}
  containers:
    - name: c
      image: $IMAGE
      resources: {requests: {cpu: "8", memory: 32Gi}, limits: {cpu: "8", memory: 32Gi}}
      securityContext: {allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: {drop: ["ALL"]}}
EOF
[ $? -ne 0 ] && ok "over-limit pod rejected by quota/LimitRange" \
             || bad "over-limit pod ACCEPTED — a session can outgrow its quota"

hdr "THE GUARANTEE: does the lab stop at its paid deadline?"
echo "  waiting up to $((SECS + 90))s..."
reason=""
for _ in $(seq 1 $(( (SECS + 90) / 5 ))); do
  sleep 5
  reason=$(kubectl -n "$S" get job lab -o jsonpath='{.status.conditions[?(@.type=="Failed")].reason}' 2>/dev/null)
  [ "$reason" = "DeadlineExceeded" ] && break
done
[ "$reason" = "DeadlineExceeded" ] \
  && ok "Job hit DeadlineExceeded — kubelet enforced it, no service of ours involved" \
  || bad "Job did NOT hit its deadline (reason='${reason:-none}') — THE BILLING GUARANTEE IS BROKEN"

[ -z "$(kubectl -n "$S" get pods -o name 2>/dev/null)" ] \
  && ok "lab pod terminated" || bad "lab pod still present after the deadline"

echo
echo "== $pass passed, $fail failed"
echo "   Not covered here: GPU tier, real autoscaling/KEDA, payment capture, multi-tenant scale."
echo "   The sweeper (layer 4) is verified separately — expire a namespace, stop the provisioner,"
echo "   and confirm the CronJob in regmap-system still deletes it."
exit $(( fail > 0 ))
