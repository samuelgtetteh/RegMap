# Training program — practical, industry-ready curriculum

How we take someone who **wouldn't normally qualify** and make them **job-ready for cybersecurity analyst
and senior IT-audit/GRC roles** — by *doing the job*, graded against real answers, with an evidence trail
employers trust. Related: [[product-master-plan]] `docs/product_master_plan.md`, `docs/product_roadmap.md`,
`docs/regmap_engine_deploy_status.md`.

## Design principles (how, not just what)
1. **Competency-based, not content-based.** Every unit = a *skill* → a *practical lab* that proves it →
   *auto-graded against ground truth* → *evidence* mapped to a **NIST NICE** work-role task. Reading supports
   the doing; it is never the deliverable.
2. **Realistic artifacts.** Learners produce what the job produces: triage decisions, detections (Sigma),
   findings, workpapers, risk memos, control mappings, exec summaries — not quiz answers.
3. **Scaffolded to senior.** Foundations → role skill → judgment (prioritization, risk, communication) →
   capstone → portfolio. Senior readiness = *judgment + communication + leading assessments*, trained explicitly.
4. **Evidence for skills-based hiring.** Output is a NICE-aligned transcript ("performed these tasks, scored
   X") that lets a non-traditional candidate pass the "you don't qualify" filter.

---

## Track 0 — Foundations (everyone)
| Skill | Practical lab | Anchor reading / content |
|---|---|---|
| Networking & packets | Read a pcap; identify the anomaly | Chris Sanders, *Practical Packet Analysis*; Kurose, *Computer Networking: Top-Down* |
| Linux & CLI | Triage a host from the shell | W. Shotts, *The Linux Command Line* (free) |
| Windows & AD | Find the risky logon in Windows event logs | Microsoft docs; *Windows Security Internals* |
| Cloud fundamentals | Spot the misconfigured S3/IAM | AWS/Azure fundamentals; *Cloud Security for Dummies* (or vendor free tiers) |
| Identity & logging | Trace an identity across logs | NIST SP 800-63; vendor SIEM docs |

## Track A — Cybersecurity / SOC Analyst → Senior
| Skill | Practical lab (auto-graded) | Anchor reading |
|---|---|---|
| Alert triage | **SOC-triage lab** (built): mark 10 events, scored on accuracy/precision/recall vs ground truth | Don Murdoch, *Blue Team Handbook: SOC/SIEM/Threat Hunting* |
| Log/SIEM investigation | Pivot through logs to scope an incident | Chris Sanders, *Applied Network Security Monitoring*; Bejtlich, *Practice of NSM* |
| Phishing & email analysis | Analyze headers/attachments; verdict + IOCs | vendor blogs; PhishTool-style workflows |
| Malware triage (static/dynamic) | Classify a sample safely; extract IOCs | *Practical Malware Analysis* (Sikorski) |
| Detection engineering | **Write a Sigma rule** that catches the technique, tested against logs | MITRE ATT&CK; Sigma docs; Elastic/Splunk detection guides |
| Threat hunting | Hypothesis-driven hunt; find the beacon | Roberts & Brown, *Intelligence-Driven Incident Response* |
| Incident response | Contain/eradicate/recover playbook + timeline | *Incident Response & Computer Forensics* (Luttgens) |
| Vuln prioritization (bridge) | **Scan → CVSS/KEV/EPSS prioritize → map to control → remediate** (engine built) | Magnusson, *Practical Vulnerability Management*; NIST 800-40 |

**Cert alignment (map, don't teach-to-test):** Security+, CySA+, BTL1, GCIH/GCIA.
**NICE roles:** Cyber Defense Analyst (PR-CDA), Cyber Defense Incident Responder (PR-CIR), Threat Analyst.

## Track B — IT Audit / GRC → Senior
| Skill | Practical lab (auto-graded) | Anchor reading |
|---|---|---|
| Control frameworks & mapping | **RegMap**: map a control in framework X to Y; score coverage/gaps | NIST SP 800-53 / CSF 2.0 (public domain); ISO 27001/27002 |
| Risk assessment | Run an assessment; quantify & rank risks | Hubbard & Seiersen, *How to Measure Anything in Cybersecurity Risk*; NIST SP 800-30 |
| RMF / authorization | Walk a system through 800-37 steps; select/tailor controls | NIST SP 800-37, 800-53A |
| Control testing / ITGC | Test access, change mgmt, ops; pass/fail with evidence | Davis & Schiller, *IT Auditing: Using Controls to Protect Information Assets* |
| Evidence & workpapers | Collect evidence, document a test, write a workpaper | ISACA *CISA Review Manual*; *Auditing IT Infrastructures for Compliance* |
| Findings & reporting | Write a defensible finding + remediation + risk rating | audit report exemplars; AICPA SOC 2 guidance |
| Framework programs | SOC 2 / PCI DSS / HIPAA readiness gap analysis | AICPA TSC; PCI DSS 4.0; HIPAA Security Rule |
| Third-party / vendor risk | Assess a vendor; produce a risk decision | Rasner, *Cybersecurity and Third-Party Risk* |

**Cert alignment:** CISA, CRISC, ISO 27001 Lead Auditor, (CISSP for senior breadth).
**NICE roles:** Security Control Assessor (SP-RSK / OV), Risk Manager, IT Program Auditor.

## Senior-readiness layer (both tracks)
Trained explicitly, because it's what separates analyst from senior:
- **Judgment:** prioritization under uncertainty, risk quantification, threat modeling.
- **Communication:** write the exec summary, brief a finding, defend a rating. (Graded on clarity + accuracy.)
- **Leadership:** scope and lead an assessment, review others' work, mentor.
- Reading: *How to Measure Anything in Cybersecurity Risk*; *The Phoenix Project* (culture/flow);
  *Cybersecurity Myths and Misconceptions* (Spafford et al.).

---

## What we need to BUILD (in order)
1. **Content model + authoring pipeline** — schema: track → module → lesson (concept+reading) → lab
   (sandbox + **grader/ground-truth**) → challenge → capstone. One lab template so authoring is cheap.
2. **The labs themselves (ground truth = the grader).** Priority first set: SOC triage (done), vuln
   prioritization (engine done), one audit lab (control mapping via RegMap), phishing, detection-engineering
   (Sigma). Each needs a realistic dataset + the correct answers.
3. **Auto-grader** per lab type: classification metrics (triage), rule-matches-events (detection), control-
   mapping correctness (audit), evidence-completeness (workpaper). Reuse the SOC-triage grader pattern.
4. **NICE-aligned evidence/transcript** — tag every lab to NICE tasks; emit a shareable, verifiable record
   (the hiring differentiator).
5. **Feedback + mentorship + community** — AI tutor (own models) for hints; human review for written
   artifacts; cohort/classroom mode.
6. **Capstones + portfolio** — end-of-track realistic engagement (a mock SOC shift; a mock audit) that
   produces a portfolio piece. Ideally **employer-sponsored capstones** (apprenticeship funding path).
7. **Assessment integrity** — versioned answer keys, plagiarism/collusion checks, per-user datasets where
   feasible (ties into the per-session K8s provisioner already built).

## Phasing (fits `product_roadmap.md`)
- **Phase 0:** 3 auto-graded labs (SOC triage · vuln prioritization · one audit/RegMap lab) + content model
  + NICE tags on those three. This is the credible MVP for the "wouldn't-qualify" wedge.
- **Phase 1:** 10–15 labs across both tracks; capstones; classroom mode; transcript/portfolio export.
- **Phase 2+:** employer-sponsored capstones; apprenticeship/workforce-funding partnerships; senior-layer
  depth; full NICE work-role coverage.

## Honest constraints
- Content authoring scales with labs — the template + auto-grader keep it cheap; realistic *datasets* are the
  real work.
- COBIT/HITRUST content needs licenses (tracked); build the audit track on **NIST/ISO/AICPA/PCI** first.
- "Real industry experience" is strongest with **employer capstones + apprenticeship funding** — pursue those
  partnerships early; the platform is the delivery vehicle.
