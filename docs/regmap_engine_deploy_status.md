# RegMap engine — containerize → K8s → dynamic provisioning: status & resume

**Resume pointer.** Where the "make RegMap a production-ready, deployable service" workstream stands, what's
verified, what's running, and the exact next steps. Related: `regmap_engine/`, `provisioner/`,
`docs/product_master_plan.md` (§4 deploy, §7 usage-based pricing), `docs/product_roadmap.md` (Phase 0 · F),
**`docs/hosted_saas_roadmap.md`** (the paid-access build: auth · persistence · attributed metering · Stripe).

> **2026-08-02.** Delivery model decided: **hosted multi-tenant SaaS on managed K8s (EKS/AKS) with metered
> compute**, including paid per-user practice environments — which makes the **`provisioner/`** work in item 5
> below the keystone of the revenue product, not a side experiment. Note that `provisioner/` is **absent from
> this repo** (only described here), so none of its claims are verifiable from this tree; recover it from the
> parent repo or rebuild. Item 3 ("billing reconciliation") is blocked on a customer-identity layer that does
> not exist yet — see `docs/hosted_saas_roadmap.md` Phase B.

_Last updated: 2026-08-01._

---

## Goal
Turn the RegMap multi-framework crosswalk engine into a **standalone, production-ready service** that runs
in **any environment (CPU/GPU)**, bills **per hardware use**, deploys on **Kubernetes**, and lets a
**user's choice spin up an isolated environment on demand** (the training-product core loop).

## What's built & VERIFIED (works)
1. **Metered engine API** — `regmap_engine/serve.py`: `/map` `/eval` `/pairs` `/health` `/usage`.
   - Auto-detects CPU/GPU device; version-stamps every response (engine/model) for reproducibility.
   - **Usage metering** = per-request **Compute Units** (CPU-sec, GPU-sec ×`REGMAP_GPU_CU_MULT` default 8),
     `x-regmap-compute-units`/`x-regmap-device` headers, a `METER {…}` stdout event per request, cumulative
     `/usage`. This is the technical basis for pay-per-hardware-use billing.
2. **Docker image** — `regmap_engine/docker/`: any-environment (default = GPU-capable that also runs CPU;
   `--build-arg TORCH_INDEX=…/cpu` = slim CPU; `…/cuXXX` = pinned CUDA). Model baked in, offline
   (`HF_HUB_OFFLINE`), **non-root** (uid 10001). Ship as source or one tarball (`save-image.*`); manifest in
   `SHIP.md`. Built & tested locally: container served all endpoints incl. metering.
3. **GHCR image (production)** — slim CPU pushed and **digest-pinned**:
   `ghcr.io/samuelgtetteh/regmap-engine:0.1-cpu` @ `sha256:aebf4f73d76a38a4847e4a5c4a60d3c0fa24f6bb2ce305bffa7b8c77723237b1`
   (2.17 GB; **private** package). Any-env local image `regmap-engine:0.1` (8.72 GB) is NOT pushed.
4. **Kubernetes** — `regmap_engine/k8s/`: Deployment+Service+HPA+NetworkPolicy (kustomize) + opt-in GPU
   Deployment + KEDA scale-to-zero. **Verified running on Docker Desktop multi-node K8s**: pod pulls the
   private GHCR image (pull secret) and serves `/health` `/map` (metered) `/usage`. Deployment is
   digest-pinned; `imagePullSecrets: ghcr`.
5. **Dynamic session provisioner** — `provisioner/` (the "user choice → K8s creation" piece):
   - `app.py` (FastAPI + kubernetes client): `POST /sessions` creates an isolated **namespace + Deployment +
     Service + NetworkPolicy + ResourceQuota + copied ghcr pull secret**; `GET /sessions` (with live state),
     `GET /sessions/{id}`, `DELETE /sessions/{id}`, `POST /reap`, **background TTL reaper**. Runs in-cluster
     (RBAC) or local kubeconfig.
   - `ui.html` — front-end served at `/`: Start-a-session form + live table (state pills
     provisioning→ready→terminating, TTL countdown, copy-access, Stop) + event log, polling every 2.5s.
   - **Verified end-to-end** locally against Docker Desktop: one Start created `sess-<id>`, pod pulled the
     GHCR image, rolled out ready, lab answered `/health` through its Service; UI served (HTTP 200).

## Committed
- `f29b8775` — engine + docker + k8s + metering + docs.
- `47316af1` — k8s digest-pin + pull-secret docs.
- (this commit) — `provisioner/` (app.py, ui.html, requirements.txt) + this status doc.
- **Still uncommitted / not created:** provisioner `rbac.yaml`, in-cluster `deployment.yaml`, `README.md`
  (see "intended next").

## Currently RUNNING (ephemeral, machine state — not code)
- Provisioner: `uvicorn app:app` on **127.0.0.1:8090** (mode `kubeconfig`). Front-end: **http://localhost:8090**.
- Cluster: `docker-desktop` context, 4-node kind-based K8s.
- Namespaces: `regmap` (the standing engine Deployment + `ghcr` pull secret — the provisioner copies this
  secret into each session); at least one `sess-*` session (auto-reaps at TTL ~30 min).
- To restart the provisioner after a reboot:
  `cd repo && venv/Scripts/python.exe -m uvicorn app:app --app-dir provisioner --host 127.0.0.1 --port 8090`

## What we INTENDED to do next (pick up here)
1. **Finish productionizing the provisioner (then commit `provisioner/`):**
   - `provisioner/rbac.yaml` — ServiceAccount + (Cluster)Role + binding, least-privilege: manage namespaces
     and, within them, deployments/services/pods/networkpolicies/resourcequotas/secrets; read the source
     `ghcr` secret.
   - `provisioner/deployment.yaml` — run the provisioner **in-cluster** (uses the SA; `mode: in-cluster`).
   - `provisioner/README.md` — local test vs in-cluster; the flow diagram; security notes.
2. **GPU tier:** build + push the **CUDA** image (`--build-arg TORCH_INDEX=…/cuXXX`), set `REGMAP_IMAGE_GPU`,
   test the `gpu` tier (needs a GPU node — not local). Wire KEDA scale-to-zero.
3. **Billing reconciliation:** scrape `METER`/`/usage` (app-level CU) and Prometheus + DCGM (infra CPU/GPU-sec
   per namespace) → per-tenant invoicing. (Phase 1.)
4. **Product integration:** the provisioner UI is standalone; wire "Start lab" in the real app front-end +
   `auth_service` (identify the user, gate tiers) to call `POST /sessions`.
5. **Real content:** replace the sample CSF↔800-53 pair with the official **OLIR import** (`import_olir.py`).
6. **Hardening (commercial):** pin exact dep versions + digest-pin base image; SBOM (CycloneDX) + image
   signing (cosign); authN/API-keys + rate-limiting on the engine and the provisioner; multi-arch (arm64)
   builds; define the supported-environment matrix. Lab workloads: swap in real target images per lab.
7. **Licensing (blocking for those frameworks):** acquire **HITRUST CSF** + **COBIT** licenses before
   shipping their control content (NIST/gov content is public domain and already usable).

## One-command resume checks
```
docker images | grep regmap-engine                      # local images (0.1 any-env, 0.1-cpu GHCR)
kubectl get ns -l app.kubernetes.io/managed-by=regmap-provisioner   # active sessions
kubectl -n regmap get deploy,pods                        # standing engine deployment
curl -s localhost:8090/health                            # provisioner (if still running)
```
