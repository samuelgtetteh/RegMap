# Training curriculum — full specification

**Purpose.** Take someone who would normally be filtered out ("you don't qualify") and make them
genuinely employable in a **cybersecurity analyst** or **IT audit / GRC** role — then carry them to
**senior**. By doing the job, graded against real ground truth, producing an evidence trail an employer
can verify.

This expands `docs/training_curriculum.md` (in the parent repo) from a track outline into a
**buildable specification**: every lab is defined in enough detail that an engineer can implement it
without further design decisions.

Related: `docs/lab_sessions_design.md` (how a paid lab session runs on K8s),
`docs/hosted_saas_roadmap.md` (the product), `docs/product_master_plan.md` §3 (the pedagogy).

---

## 1. Design rules that constrain every lab

1. **Competency, not content.** A unit is a *skill* → a *lab that proves it* → *auto-graded against
   ground truth* → *evidence tagged to a NIST NICE work-role task*. Reading supports the doing and is
   never the deliverable.
2. **The grader is the lab.** If you cannot state the correct answer in machine-checkable form, it is not
   a lab yet. Seeded ground truth is the design, not an afterthought — this is the moat
   (`product_master_plan.md` §3.2).
3. **Realistic artifacts.** Learners produce triage verdicts, Sigma rules, findings, workpapers, risk
   memos, control mappings, exec summaries. Never quiz answers.
4. **Judgment is taught explicitly.** Prioritisation under uncertainty, risk framing, and written
   communication are what separate analyst from senior. They get their own graded track, not a footnote.
5. **Every lab is a paid session.** It must fit the session model: an image (or images), a Pod Security
   level, a resource tier, a deadline, and a teardown. See §6.
6. **Per-learner variation.** Where feasible the seed is parameterised per session, so answers cannot be
   shared. This is why the seeded-generator pattern matters more than static datasets.

---

## 2. Lab specification schema

Every lab in §4 is defined by these fields. A lab is "buildable" when all are filled.

| field | meaning |
|---|---|
| `id` | stable slug, e.g. `soc-triage-01` |
| `track` / `level` | 0-Foundations, A-SOC, B-Audit, S-Senior · L1 entry · L2 practitioner · L3 senior |
| `skill` | the single competency proved |
| `environment` | what spins up in the session (images, services, ports) |
| `dataset` | where the data comes from, and how it is parameterised per learner |
| `ground_truth` | the machine-checkable correct answer, and how it is seeded |
| `deliverable` | exactly what the learner submits |
| `grader` | the metric and the algorithm |
| `pass` | the threshold, and why it is set there |
| `nice_task` | NICE work-role task id(s) for the transcript |
| `tier` / `minutes` | compute tier and expected session length (drives price) |
| `status` | built · partial · to-build, with the dependency |

---

## 3. Role outcomes this curriculum targets

| target role | track | seniority evidence required |
|---|---|---|
| SOC Analyst T1 | 0 + A(L1) | triage accuracy, escalation discipline |
| SOC Analyst T2 / IR | A(L2) | scoping an incident, timeline, containment decisions |
| Detection Engineer | A(L2-L3) | rules that fire on technique and not on noise |
| Threat Hunter | A(L3) | hypothesis → evidence → finding, without an alert to start from |
| IT Auditor | 0 + B(L1) | control testing with evidence, defensible workpapers |
| Senior IT Auditor / GRC Lead | B(L2-L3) + S | scoping an audit, risk rating defence, reviewing others' work |
| Compliance / Framework Lead | B(L3) + S | multi-framework programme, gap remediation plan |
| Security Analyst → Senior | A(L3) + S | prioritisation under uncertainty, exec communication |

**Cert alignment** (map, never teach-to-test): Security+, CySA+, BTL1, GCIH/GCIA (track A); CISA, CRISC,
ISO 27001 Lead Auditor, CISSP for senior breadth (track B).

---

## 4. The lab catalogue

Status key: **BUILT** = exists today · **PARTIAL** = component exists · **TO BUILD**.

### Track 0 — Foundations (everyone, L1)

**`found-net-01` — Read a packet capture and find the anomaly**
- environment: single pod, tcpdump/tshark + a static pcap, browser terminal · tier cpu-small · 45 min
- dataset: synthesised pcap; the generator injects one of N anomaly classes (beaconing, DNS
  exfiltration, cleartext credential, port scan) chosen by session seed
- ground_truth: the generator records anomaly class + the offending 5-tuple + packet indices
- deliverable: anomaly class + source/dest + one-sentence justification
- grader: exact match on class and 5-tuple; justification keyword-scored, human-reviewable
- pass: class correct AND 5-tuple correct
- nice_task: T0155 (analyse network traffic) · status: **TO BUILD** (generator is the work)

**`found-linux-01` — Triage a compromised Linux host from the shell**
- environment: one pod with a seeded filesystem (rogue cron, SUID binary, unexpected listener,
  modified `authorized_keys`) · cpu-small · 45 min
- ground_truth: seeder writes a manifest of exactly which artefacts it planted
- deliverable: list of indicators found, with paths
- grader: precision/recall against the manifest; false positives penalised
- pass: recall ≥ 0.75 with precision ≥ 0.60 · nice_task: T0175 · status: **TO BUILD**

**`found-windows-01` — Find the risky logon in Windows event logs**
- environment: log-analysis pod, seeded EVTX/JSON · cpu-small · 45 min
- dataset: derived from the identity generator already in `live-target-lab`
- ground_truth: the generator knows which account/host pair is the burst
- deliverable: account, host set, logon type, why it is suspicious
- grader: exact match on account; Jaccard on host set
- pass: account correct · nice_task: T0259 · status: **PARTIAL** — reuse `identity_generator.py`

**`found-cloud-01` — Spot the cloud misconfiguration**
- environment: **LocalStack + `cloud-target-lab` seeder** · baseline PSS (LocalStack needs root) ·
  cpu-large · 45 min
- ground_truth: `seed.py` plants a public S3 bucket, an over-permissive security group and IAM issues;
  `verify.py` already checks them
- deliverable: list of misconfigurations with resource ids
- grader: `verify.py` (exists) → precision/recall vs seeded set
- pass: recall ≥ 0.80 · nice_task: T0163 · status: **PARTIAL** — images exist; blocked on the
  LocalStack image repair and a baseline-PSS session variant (see `lab_sessions_design.md`)

**`found-identity-01` — Trace an identity across systems** · cpu-small · 30 min · **TO BUILD**
- correlate one principal across auth, VPN and app logs; grader checks the reconstructed session chain

### Track A — SOC / Blue team

**`soc-triage-01` — Triage a live alert feed (L1)** — *the flagship, closest to built*
- environment: **`identity-anomaly` detector + `live-target-lab` generator**, 2 containers, one pod ·
  restricted PSS, uid 10001 (verified) · cpu-small · 60 min
- dataset: generator streams synthetic logins with behavioural attack bursts; `ANOMALY_RATE` and burst
  parameters are per-session seed
- ground_truth: **free** — the generator knows which events it made anomalous
- deliverable: TP/FP verdict on each surfaced alert + escalate/close decision
- grader: precision, recall, F1, plus false-negative penalty on the true bursts
- pass: F1 ≥ 0.70 and no missed burst · nice_task: T0214, T0258
- status: **PARTIAL — verified running in K8s.** Blocker: the generator posts to platform-prefixed
  routes (`/identity/score`, `/decision/verdicts/{id}/feedback`) while the standalone detector serves
  `/score`. Needs the platform backend or a small path-rewriting adapter.

**`soc-siem-01` — Pivot through logs to scope an incident (L2)** · cpu-large · 90 min · **TO BUILD**
- ground_truth: the scenario generator records the full blast radius (hosts, accounts, times)
- grader: set overlap on scoped entities; over-scoping penalised as much as under-scoping
- pass: F1 ≥ 0.70 on the entity set · nice_task: T0163, T0175

**`soc-phish-01` — Analyse a phishing email (L1)** · cpu-small · 45 min · **TO BUILD**
- deliverable: verdict + extracted IOCs + header-based justification
- ground_truth: generated message with known IOCs and a known verdict
- grader: IOC recall/precision; verdict exact · nice_task: T0258

**`soc-detect-01` — Write a Sigma rule that catches the technique (L2)** — *highest-value lab*
- environment: log store + Sigma→query converter + evaluation harness · cpu-large · 90 min
- dataset: an attack log slice **plus** a benign "noise" slice from the same environment
- ground_truth: labelled attack events and benign events
- deliverable: a Sigma rule
- grader: run the rule against both slices → **true positives on attack, false positives on benign**.
  This is the honest metric: a rule that matches everything scores zero
- pass: TP ≥ 0.80 of attack events AND FP rate ≤ 0.01 on benign · nice_task: T0696 · **TO BUILD**

**`soc-hunt-01` — Hypothesis-driven hunt, no alert to start from (L3)** · cpu-large · 120 min · **TO BUILD**
- deliverable: hypothesis, query trail, finding or a defensible "nothing found"
- grader: did they find the seeded beacon; **a well-argued negative on a clean dataset also passes** —
  half the sessions are seeded clean, which is what teaches judgment rather than pattern-matching
- pass: correct conclusion + evidence trail · nice_task: T0742

**`soc-ir-01` — Contain, eradicate, recover (L2-L3)** · cpu-large · 120 min · **TO BUILD**
- deliverable: action plan + timeline + comms note
- grader: ordered-action checklist against a rubric; timeline entries matched to seeded events
- pass: all containment actions present, none destructive-before-evidence · nice_task: T0041

**`soc-malware-01` — Static/dynamic triage of a sample (L2)** · isolated egress-denied pod · 90 min ·
**TO BUILD.** Use only synthetic or knowingly-benign samples — never live malware in a shared cluster.

**`soc-vuln-01` — Scan → prioritise (CVSS/KEV/EPSS) → map to control → remediate (L2)**
- environment: target lab + the scan/decision engine (`/scan`, `/advisor` exist in the platform)
- ground_truth: seeded vulnerable services with known CVEs; the "correct" priority order is computable
  from KEV/EPSS at session time
- deliverable: ranked remediation plan with justification
- grader: rank correlation (Spearman) against the computed order + control mapping correctness via RegMap
- pass: ρ ≥ 0.7 and control mapping ≥ 0.8 · nice_task: T0028 · status: **PARTIAL** — engine exists

### Track B — IT Audit / GRC

**`aud-map-01` — Map a control across frameworks (L1)** — *fully buildable today*
- environment: **the RegMap engine** (`regmap-engine:0.2-cpu`) · cpu-small · 45 min
- dataset: the live catalog — 6 frameworks, 1,544 controls, 34 answerable pairs
- ground_truth: **free and authoritative** — the official crosswalks already loaded (222 NIST↔HIPAA,
  737 CSF→800-53, 310 CSF→800-171, 157 800-171→800-53). `/map` returns `official.target_ids`
- deliverable: for each presented control, select the provisions that map
- grader: precision/recall vs `official.target_ids`; partial credit per provision
- pass: F1 ≥ 0.70 · nice_task: T0267 · status: **TO BUILD (UI only)** — no data or modelling work
  needed, which makes this the cheapest real lab in the catalogue

**`aud-gap-01` — Framework gap analysis (L2)** · cpu-small · 90 min · **TO BUILD**
- deliverable: coverage report — which target-framework provisions are unaddressed
- ground_truth: computable by set difference over the official mapping
- grader: exact set comparison on the gap list · pass: F1 ≥ 0.80 · nice_task: T0177

**`aud-itgc-01` — Test ITGCs: access, change management, operations (L2)**
- environment: seeded "company" — a small app + user store + change log · cpu-large · 90 min
- ground_truth: seeder plants specific control failures (a terminated user still active, a change
  without approval, a failed backup)
- deliverable: pass/fail per control **with the evidence that supports it**
- grader: control verdict match **and** evidence-completeness check — a right answer with no evidence
  fails, which is the actual audit standard
- pass: all seeded failures found, evidence attached · nice_task: T0176 · **TO BUILD**

**`aud-workpaper-01` — Produce a defensible workpaper (L2)** · cpu-small · 60 min · **TO BUILD**
- grader: structured rubric (objective, scope, procedure, sample, result, conclusion) — deterministic
  presence/quality checks, then human or LLM-assisted review for reasoning quality

**`aud-finding-01` — Write a finding with a defensible risk rating (L2-L3)** · 60 min · **TO BUILD**
- grader: rating within one band of the seeded severity, **and** justification consistent with the
  rating. Deliberately allows a defensible non-modal answer — auditors must argue, not guess

**`aud-risk-01` — Quantitative risk assessment (L3)** · 90 min · **TO BUILD**
- deliverable: ranked risk register with quantified exposure
- grader: rank correlation against the seeded loss model; calibration check on stated ranges
- nice_task: T0161 · reading: Hubbard & Seiersen

**`aud-rmf-01` — Walk a system through NIST 800-37 (L3)** · 120 min · **TO BUILD**
- deliverable: categorisation, tailored control baseline, assessment plan
- ground_truth: the **800-53 baseline profiles already downloaded** (LOW 149 / MODERATE / HIGH 370
  control selections) make the correct tailored baseline computable
- grader: set comparison against the correct baseline + justification for each tailoring decision
- status: **PARTIAL** — the baseline data is on disk but not yet modelled (it needs a control-selection
  feature, not a framework entry — see the download audit in `build_log.md`)

**`aud-soc2-01` / `aud-pci-01` — Readiness gap analysis (L3)** · **TO BUILD, licence-gated.** Mappings
exist via the OLIR export (PCI 551, ISO 389) but the control *text* is not shippable — so these labs can
be built on **identifiers and our own paraphrases** only. See `data/raw/SOURCES.md`.

**`aud-vendor-01` — Third-party risk assessment (L2)** · 60 min · **TO BUILD**
- deliverable: vendor risk decision + conditions
- grader: rubric + whether the seeded disqualifying finding was caught

### Track S — Senior readiness (both tracks, L3)

This is what actually converts "can do tasks" into "can hold a senior role", and it is the part most
programmes omit.

**`sen-prioritise-01` — Prioritise under uncertainty and defend it**
- 20 competing items, insufficient time, incomplete information; some information is *deliberately
  contradictory*
- grader: the defence is graded, not the ranking. There is no single correct order; there are
  indefensible ones (ignoring KEV-listed exploited vulns, treating all criticals equally)
- **TO BUILD** · this is the single best predictor of senior readiness

**`sen-exec-01` — Write the executive summary**
- input: a full technical finding set. output: one page for a non-technical executive
- grader: accuracy (no claim unsupported by the findings) + readability + decision-usefulness. Rubric
  plus LLM-assisted scoring with human spot-check · **TO BUILD**

**`sen-review-01` — Review someone else's work**
- input: a deliberately flawed workpaper or triage set with seeded errors of known type
- grader: which seeded errors were caught, and whether feedback was actionable
- **TO BUILD** · directly trains the reviewing skill a senior is hired for

**`sen-scope-01` — Scope and plan an assessment**
- deliverable: scope, sampling approach, timeline, resourcing
- grader: rubric + whether the scope covers the seeded material risks · **TO BUILD**

**`sen-brief-01` — Defend a finding under challenge**
- a simulated stakeholder pushes back with plausible counter-arguments
- grader: did they hold a correct position, concede a genuinely wrong one, and stay evidence-based.
  **Conceding when the challenge is right is a pass condition** · **TO BUILD** (needs the tutor model)

### Capstones (end of track, portfolio artifact)

- **`cap-soc-01` — A full mock SOC shift.** 3 hours, live feed, mixed real incidents and noise, one
  genuine incident requiring escalation. Graded end-to-end: triage accuracy, escalation timing,
  handover note quality.
- **`cap-audit-01` — A full mock audit.** Scope → test → evidence → findings → report → exec summary,
  against a seeded company with known deficiencies. Produces a portfolio-grade report.
- Both are **employer-sponsorable**: a real employer can supply the scenario, which is the strongest
  bridge to hiring and to apprenticeship funding.

---

## 5. Evidence — the hiring differentiator

A completed track emits a **verifiable transcript**, not a certificate:

- per lab: NICE task id, score, date, session id, and the **grader version** used
- per track: aggregate competency profile, capstone artifact, reviewer notes
- shareable link an employer can verify; scores traceable to a versioned answer key

This is the mechanism that lets a non-traditional candidate defeat the "you don't qualify" filter:
*specific tasks performed, measured against ground truth, independently checkable.*

**Assessment integrity** is a hard requirement, not a nicety: versioned answer keys, per-session seeds so
answers cannot be shared, and collusion detection. Per-session parameterisation is why the K8s
session model matters pedagogically and not just commercially.

---

## 6. How a lab maps onto the session model

Each lab supplies exactly what `k8s/labs/session-template.yaml` needs:

```
lab_id · images[] · pod_security (restricted | baseline + justification)
tier (cpu-small | cpu-large | gpu) · minutes → activeDeadlineSeconds
ports · env · seed_parameters · grader_entrypoint · artifact_paths
```

Two constraints already learned the hard way:
- **`restricted` PSS is the default and most images need forcing to non-root.** The SOC pair works at
  uid 10001; **LocalStack does not run non-root at all**, so any LocalStack lab needs `baseline` and an
  explicit justification.
- **A lab needs a catalogue entry, not hand-substituted YAML.** Building that registry is the next
  engineering step, and it is what turns "we ran a lab" into "the provisioner starts any lab by name".

---

## 7. Build order

1. **Lab catalogue registry + grader interface.** One schema, one grader contract. Without this every
   lab is bespoke and the programme cannot scale.
2. **`aud-map-01`** — cheapest real lab in the catalogue: the answer key is already loaded and served.
   Build it first to prove the loop end to end.
3. **`soc-triage-01`** — unblock the path prefix (adapter or platform), then ship. Highest realism.
4. **`found-cloud-01`** — repair the LocalStack image, add the baseline-PSS variant, reuse `verify.py`.
5. **`soc-detect-01`** — the Sigma lab; needs the benign-noise corpus, which is the real work.
6. **Transcript + NICE tagging** across those four. That is a sellable programme.
7. **Senior layer** (`sen-*`) — needs the tutor model for challenge/defence labs.
8. Breadth: remaining Track A and B labs; capstones; employer-sponsored scenarios.

---

## 8. Honest constraints

- **Datasets are the work, not the platform.** Every lab's cost is dominated by producing a realistic
  environment with known-correct answers. The seeded-generator pattern (as in `live-target-lab` and
  `cloud-target-lab`) is the only approach that scales, because it yields ground truth for free *and*
  gives per-learner variation.
- **Written deliverables cannot be fully auto-graded.** Workpapers, exec summaries and finding defences
  need rubric + LLM assistance + human spot-check. Do not pretend otherwise; budget for review.
- **Licensed frameworks bound Track B.** COBIT and HITRUST need licences; ISO/PCI/SOC 2 text cannot be
  shipped. Build the audit track on NIST/CSF/HIPAA (public domain, already loaded) and use official
  mapping identifiers plus original paraphrases for the rest.
- **"Real industry experience" is strongest via employer capstones and apprenticeship funding.** The
  platform is the delivery vehicle; the partnerships are what make the outcome claim credible.
- **Senior roles are not reachable by labs alone.** Labs can train judgment, communication and review —
  they cannot substitute for scope of responsibility. State that honestly: this programme makes someone
  *ready to be hired into* senior work, evidenced by demonstrated judgment, not automatically senior.
