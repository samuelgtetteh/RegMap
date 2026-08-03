# Paid lab sessions on Kubernetes — design

**The loop:** a learner clicks *Start lab* → pays (or spends credit) → an isolated environment spins up
on Kubernetes → they practise against real systems → **when the credit runs out, everything winds down.**

This is Phase D of `docs/hosted_saas_roadmap.md`. Written 2026-08-02.

---

## The one question that decides the architecture

> **What guarantees the lab stops when the money runs out?**

The obvious design — *the provisioner watches balances and deletes namespaces when credit hits zero* —
is wrong, because its failure mode is **silently burning money**. If the provisioner crashes, is
wedged, loses its watch connection, or the billing service lags, labs keep running and nobody is
charged for them. On a GPU node pool that is expensive within minutes.

**So expiry must be enforced by the cluster, not by our application.** Nothing that has to stay alive
should be load-bearing for shutdown.

### Layered teardown (defence in depth)

| layer | mechanism | survives | role |
|---|---|---|---|
| **1** | **`Job` + `activeDeadlineSeconds`** | everything of ours being dead | **the guarantee.** kubelet kills the pod. No external service involved |
| 2 | `ResourceQuota` + `LimitRange` per namespace | provisioner down | caps what one session can ever consume or spawn |
| 3 | provisioner reaper loop | — | reclaims namespaces, frees names/IPs/etcd objects |
| 4 | in-cluster `CronJob` sweeper (every 1 min) | **provisioner down** | `delete ns` where the expiry label is in the past |
| 5 | namespace deletion + ownerReferences | — | garbage-collects everything the session made |

Layer 1 is the design decision that matters. Layers 3–5 are hygiene.

### Why `Job`, not `Deployment`
A Deployment's controller restarts pods forever — exactly the wrong behaviour for something that must
end. `activeDeadlineSeconds` on a Job is a hard wall the kubelet enforces. Lab sessions are inherently
finite, so Job is the correct primitive. (`ttlSecondsAfterFinished` then cleans up the Job object.)

---

## Credit model: hold up front, refund the remainder

Do **not** meter as you go and hope to stop in time. Derive the deadline *from the payment*:

```
1. user picks a tier (cpu-small / cpu-large / gpu) and clicks Start
2. seconds = min(credits_held / rate(tier), MAX_SESSION_SECONDS)
3. RESERVE that credit immediately (debit the balance now)
4. create the Job with activeDeadlineSeconds = seconds
5. on teardown, measure actual runtime and REFUND the unused credit
```

This makes overspend **structurally impossible**: a session cannot outlive the payment, because the
deadline was computed from it. A crashed provisioner cannot overspend either — the worst case is a
namespace lingering with no pod in it, which costs nothing.

### Extending a session
`activeDeadlineSeconds` cannot be changed on a running Job. Two options:

- **v1 (recommended): fixed blocks.** "Add 30 minutes" starts a *new* session. Simple, and it keeps the
  hard guarantee intact.
- later: run the timer as a sidecar that the provisioner can signal. More flexible, but shutdown then
  depends on our code again — only do this once the billing path is proven.

### Two meters, deliberately different
| product | billed on | why |
|---|---|---|
| **lab sessions** | **wall-clock × tier** | you are renting hardware for a duration; wall-clock is exactly the thing being consumed |
| crosswalk API (`/map`) | deterministic work units | wall-clock there would charge the customer for *our* queueing — see the roadmap's CU redesign |

Do not unify these. They are different goods.

**Source of truth for lab runtime:** the Job's `.status.startTime` / `.status.completionTime`. Simple,
authoritative, needs no extra infrastructure. Reconcile against Prometheus (and DCGM for GPU) later —
useful for margin analysis and for catching drift, but not needed to bill correctly on day one.

---

## Isolation — the part that is a real security problem

Learners are invited to attack workloads **inside your cluster**. Treat every lab pod as hostile.

- **Namespace per session.** The unit of isolation, quota, network policy and billing.
- **`automountServiceAccountToken: false`.** Otherwise the learner has a token and can talk to the API
  server from inside the lab. This is the most commonly missed setting and the most serious.
- **NetworkPolicy, default-deny egress.** Allow only what the lab genuinely needs. A lab must not reach
  the control plane, the provisioner, the database, other sessions, or the cloud metadata endpoint
  (`169.254.169.254` — instance credentials live there).
- **Pod Security admission**: `restricted` where the lab allows it; `baseline` only if it needs
  capabilities, and then justify it per lab.
- **Dedicated node pool** in cloud, with taints/tolerations, so lab workloads never share a node with
  the control plane or the engine.
- **No persistent volumes** for v1. Ephemeral sessions have nothing to exfiltrate later.

---

## Local test rig — VERIFIED 2026-08-02

**Use `kind`, not Docker Desktop's built-in Kubernetes.** Two reasons, the first decisive:

1. Docker Desktop's cluster uses **kindnet, which does not enforce NetworkPolicy**. Policies are
   accepted by the API server and silently do nothing, so lab isolation would look correct while being
   absent — worse than no test. With kind you set `disableDefaultCNI: true` and install Calico, which
   does enforce it. (Note: `docs/regmap_engine_deploy_status.md` lists NetworkPolicy as "verified
   running"; that most likely meant "applied without error". Treat it as unverified.)
2. Enabling Docker Desktop Kubernetes **restarts the Docker engine**, stopping every other running
   container. kind creates containers alongside them and `kind delete cluster` leaves no trace.

Rig, all committed under `regmap_engine/k8s/labs/`:

```
kind create cluster --name regmap-labs --config kind-cluster.yaml   # 1 control-plane + 2 labelled workers
kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.28.2/manifests/calico.yaml
kubectl -n kube-system rollout status ds/calico-node --timeout=420s
kind load docker-image regmap-engine:0.2-cpu --name regmap-labs     # no registry needed
kubectl apply -f sweeper.yaml
bash test-teardown.sh 60
```

`regmap-engine:0.2-cpu` stands in as the lab workload, so no new image is needed to prove mechanics.

### Verified ✅ — `test-teardown.sh`, 9/9 passing
| check | result |
|---|---|
| **Job hits `DeadlineExceeded` at the paid deadline** | **kubelet enforced it, nothing of ours involved** |
| lab pod terminated afterwards | pod gone |
| `automountServiceAccountToken: false` | no token at `/var/run/secrets/...` |
| **NetworkPolicy enforced** | egress to `1.1.1.1:443` blocked (Calico) |
| cloud metadata `169.254.169.254` blocked | blocked |
| non-root + read-only rootfs | uid 10001, `/` not writable |
| `ResourceQuota` / `LimitRange` | over-limit pod rejected `Forbidden` |
| **sweeper (layer 4)** | deleted an expired namespace from its in-cluster CronJob, parsing the expiry label correctly |

The first row is the commercial result: **a lab cannot outlive what was paid for it, even if every
service we run is dead.**

### Still NOT testable here ⚠️
- **GPU tier** — no GPU on this machine.
- **Real autoscaling / KEDA scale-to-zero** — needs a cloud node pool that can actually scale.
- **Payment capture** — stub Stripe; only the hold/refund arithmetic is testable.
- **Multi-tenant scale** — three local nodes prove mechanics, not capacity.
- **Idle detection** — needs an activity signal from a real lab workload.

---

## Build order

1. **Prove the guarantee first, with no product around it.** A Job with `activeDeadlineSeconds`, plus a
   namespace, quota and the CronJob sweeper — applied by hand. Confirm a lab dies on time with the
   provisioner stopped. If this does not hold, nothing else is worth building.
2. **Provisioner service** (`POST /sessions`, `GET /sessions/{id}`, `DELETE`, reaper). It is described
   as verified in `regmap_engine_deploy_status.md` but is **absent from this repo** — recover it from
   the parent repo or rebuild. Either way it must be re-verified against this design, because it was
   built around Deployments and a TTL reaper, i.e. layer 3 only.
3. **Credit ledger** — needs the Phase B database (`accounts`, `api_keys`, `usage_events`). Sessions are
   just another `usage_events` row type. Do not build a second billing system.
4. **Auth + quota gate** so a session cannot start without credit — Phase B again. Until then any test
   must stub identity.
5. **Cloud** (EKS/AKS) with a tainted lab node pool, a real CNI, and then the GPU tier.

**Dependency worth stating plainly:** steps 3 and 4 are Phase B. A paid lab loop cannot exist before
there are accounts, credits and authentication — so the K8s work can be *proven* now (step 1) but
cannot be *sold* until the billing spine lands.

---

## Open decisions

1. **Session length cap** — what is `MAX_SESSION_SECONDS`? Bounds worst-case spend per click.
2. **Idle detection** — kill a lab nobody is interacting with, or bill it as paid-for? Idle-kill is
   kinder and cheaper but needs an activity signal from the lab.
3. **Warm pool** — cold-start a lab per click (slow, cheap) or keep a small warm pool (fast, costs
   money while idle)? Affects the felt quality of "click and go".
4. **EKS vs AKS** — still open from the roadmap; decides the node-pool and CNI specifics.
