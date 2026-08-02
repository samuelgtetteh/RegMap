# RegMap crosswalk engine — Kubernetes

Deploy the engine on Kubernetes. Designed to test **locally on Docker Desktop's built-in Kubernetes**
(no registry needed — it uses the image already in your local Docker store) and to run unchanged on a
real cluster / k3s (on-prem).

## Test it on Docker Desktop Kubernetes
1. **Enable K8s:** Docker Desktop → Settings → **Kubernetes** → *Enable Kubernetes* → wait until the
   indicator is green. (`kubectl` ships with Docker Desktop.)
2. **Build the image** (if you haven't): `docker build -f regmap_engine/docker/Dockerfile -t regmap-engine:0.1 .`
3. **Run the test:** `regmap_engine/k8s/test.sh` (Git Bash) or `regmap_engine/k8s/test.ps1` (PowerShell).
   It applies the manifests, waits for the pod to become ready, port-forwards, and curls
   `/health`, `/map` (showing the metering headers), and `/usage`.

Manual version:
```
kubectl apply -k regmap_engine/k8s
kubectl -n regmap rollout status deploy/regmap-engine
kubectl -n regmap port-forward svc/regmap-engine 8010:80
curl localhost:8010/health
kubectl delete -k regmap_engine/k8s          # tear down
```
> Docker Desktop K8s finds `regmap-engine:0.1` because it shares the local image store; the Deployment
> uses `imagePullPolicy: IfNotPresent`. On a real cluster, push to a registry and set the Deployment's
> `image:` to `<registry>/regmap-engine@sha256:<digest>` (digest-pinned = reproducible).

## Registry & pull secret (multi-node / production)
A multi-node cluster (incl. Docker Desktop's kind-based multi-node) does **not** share your local image
store — nodes pull from a registry. The Deployment is **digest-pinned** to a GHCR image
(`ghcr.io/samuelgtetteh/regmap-engine@sha256:…`) and references an `imagePullSecrets: [ghcr]`.

Build (slim CPU), push, and pin:
```
docker build -f regmap_engine/docker/Dockerfile --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cpu \
  -t ghcr.io/samuelgtetteh/regmap-engine:0.1-cpu .
docker push ghcr.io/samuelgtetteh/regmap-engine:0.1-cpu
docker inspect --format '{{index .RepoDigests 0}}' ghcr.io/samuelgtetteh/regmap-engine:0.1-cpu   # -> put in deployment.yaml
```
Create the pull secret (GHCR packages are private by default) — the secret is **not** committed:
```
kubectl create namespace regmap
kubectl -n regmap create secret docker-registry ghcr \
  --docker-server=ghcr.io --docker-username=<you> --docker-password=<PAT with read:packages>
```
(On this machine the secret was created from the existing Docker Desktop credential:
`printf ghcr.io | docker-credential-desktop get`.) Then `kubectl apply -k regmap_engine/k8s`.

## What's in here
| File | Purpose | Local (Docker Desktop) |
|---|---|---|
| `namespace.yaml` | `regmap` namespace (tenant/billing boundary) | ✅ |
| `deployment.yaml` | CPU tier — probes tuned for model warm-up, non-root, hardened `securityContext` | ✅ |
| `service.yaml` | ClusterIP spanning cpu+gpu pods | ✅ |
| `hpa.yaml` | CPU autoscaling (needs metrics-server; applies as no-op without it) | ✅ applies |
| `networkpolicy.yaml` | default-deny ingress + in-namespace allow | ✅ applies (enforced on Calico/Cilium) |
| `kustomization.yaml` | the core set above (`kubectl apply -k`) | ✅ |
| `gpu-deployment.yaml` | **opt-in** GPU tier (nodeSelector + `nvidia.com/gpu`, `REGMAP_DEVICE=cuda`, `replicas: 0`) | ⛔ needs GPU node |
| `keda-scaledobject.yaml` | **opt-in** KEDA 0→N→0 scale-to-zero for the GPU tier | ⛔ needs KEDA |

## How this maps to the product goals
- **Pay for the hardware you use:** `hpa.yaml` scales the CPU tier with load; `keda-scaledobject.yaml`
  scales the GPU tier **to zero** when idle (zero GPU spend). The app already meters per request
  (`/usage`, `x-regmap-compute-units`) — infra metering (Prometheus/DCGM per namespace) reconciles to it.
- **Any environment:** one image, two Deployments (cpu / gpu); the Service load-balances both tiers.
- **Multi-tenant / on-prem:** namespace-per-tenant + NetworkPolicy; the same manifests run on k3s on a
  customer's hardware (their metal → compute free, per the pricing).

See also `../docker/SHIP.md` (image build + ship) and `docs/product_roadmap.md` (where K8s sits in the plan).
