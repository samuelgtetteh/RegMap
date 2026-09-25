# RegMap, Inc. Business Plan

**Prove it once. Satisfy every framework.**

Prepared by Samuel Gbli Tetteh. Stage: pre-seed / angel. Date: 2026-09-18.

All financial figures, market sizes, and dates in this plan are forward-looking projections based on the assumptions stated inline. They are estimates, not guarantees. Traction refers only to assets that exist today.

## 1. Company overview

RegMap is a compliance automation company. Our software maps the security and privacy controls an organization already operates onto the many regulatory frameworks it must satisfy, and keeps that mapping current as frameworks change. We reduce a slow, expert-driven task called regulatory crosswalking to an automated, evidence-backed workflow.

- **Mission:** make multi-framework compliance continuous, transparent, and affordable.
- **Vision:** become the mapping layer that sits underneath every compliance program, so that proving a control once proves it everywhere it applies.
- **Legal status:** to be incorporated as a Delaware C corporation at first close, the standard structure for venture and angel investment.

## 2. The problem

Modern organizations rarely live under a single compliance regime. A healthcare software vendor adopts a NIST-based program and must also satisfy the HIPAA Security Rule. A cloud company faces SOC 2, ISO 27001, and often a customer-specific or national scheme. Each framework expresses overlapping obligations in its own vocabulary and at its own level of abstraction.

The specific pain is crosswalking: stating which control in framework A satisfies, wholly or in part, a requirement in framework B. Today this is:

- **Manual.** Performed line by line by scarce compliance experts and consultants.
- **Expensive.** A single cross-framework mapping engagement can cost tens of thousands of dollars in consulting time.
- **Fragile.** It is redone whenever either framework is revised, so the mapping is stale between reviews.
- **Opaque.** The reasoning behind each mapping is rarely captured, which makes audits slow and repeat work unavoidable.

The result is a recurring bottleneck and a persistent source of error precisely at the moment a company is trying to grow into new markets that demand new certifications.

## 3. The solution

RegMap frames crosswalking as a semantic retrieval problem and solves it with a fine-tuned model.

1. **Map.** Given a control, the engine returns the ranked, scored provisions of a target framework that it satisfies. A configurable confidence threshold flags weak matches as candidate coverage gaps that deserve expert review.
2. **Evidence.** A scanning and assessment layer turns live technical findings into control-level evidence, so the compliance picture reflects the real environment, not a static questionnaire.
3. **Report.** The platform assembles an auditable, exportable compliance package (document, spreadsheet, and machine-readable formats) that records, per obligation, the suggested control, its score, and its status.
4. **Continuously.** Because a mapping is a fast automated operation rather than a consulting engagement, it can be rerun on every framework revision or on a schedule, so coverage never goes stale silently.

The design keeps a human in the loop. The engine ranks and flags; an expert confirms. It can only reduce the manual workload, never introduce an unreviewed decision, which is essential for audit-grade work.

## 4. What we have built already (traction)

This is a pre-seed raise, so traction is technical and scientific rather than commercial. What exists today:

- **A working platform.** A containerized mapping engine served over an API, plus a browser console that runs an assessment and exports an audit-ready compliance package. It runs under Docker and Kubernetes and includes usage metering for consumption-based billing.
- **Three released open-source models** under a permissive Apache-2.0 license, published on Hugging Face and as container images: a regulatory crosswalk embedder, an identity-anomaly detector, and an operational-technology and industrial-control-systems anomaly detector.
- **Reproducible benchmarks.** On held-out data, fine-tuning raises top-5 retrieval of the correct provision from 0.500 to 0.735 with bootstrap 95 percent confidence intervals, and outperforms both generic embeddings and keyword baselines. A stricter, leakage-free split confirms the gain.
- **Research credibility.** The methodology is documented in research manuscripts prepared to peer-review standard, which supports both grant applications and buyer trust.
- **Testing infrastructure.** Synthetic, ground-truth-labeled datasets and lab environments that we use to evaluate models and that also power the training funnel.

These assets mean an investor is funding go-to-market and productization, not basic research risk.

## 5. Market

We describe the market as three nested circles. All figures are estimates offered to show scale and reasoning, not precise claims.

- **Total addressable market.** Global governance, risk, and compliance software is a multi-tens-of-billions market growing at double-digit rates as regulation expands.
- **Serviceable available market.** Compliance automation for mid-market organizations that must satisfy more than one framework is a subset in the several-billion range, and cross-framework mapping is the least automated part of it.
- **Serviceable obtainable beachhead.** United States mid-market companies actively pursuing a second or third framework represent an initial obtainable segment we estimate in the hundreds of millions of dollars of annual software spend.

The tailwinds are real: the number of frameworks organizations must satisfy keeps rising, defense and critical-infrastructure suppliers face new mandates such as CMMC, and buyers increasingly expect continuous rather than point-in-time compliance.

## 6. Competition and our wedge

- **Compliance automation incumbents** (Vanta, Drata, Secureframe) are strong at evidence collection for a single framework at a time. They are weak at automated, transparent cross-framework mapping, which is our entry wedge.
- **Legacy GRC platforms** (Archer, ServiceNow GRC, OneTrust) are heavy, expensive, and aimed at large enterprises, not the fast-moving mid-market.
- **Consultancies** do crosswalking by hand today. We can sell to them as a tool as well as compete with them.

Our differentiation:

- **Automated cross-framework crosswalking** with ranked, scored, confidence-flagged mappings.
- **Transparency.** Every mapping carries a score and a provenance tag, which auditors trust more than a black box.
- **Coverage others ignore.** Operational-technology and industrial-control-systems context, relevant to critical infrastructure and defense suppliers.
- **Open models and reproducible science**, which build trust and lower the barrier for security-conscious buyers.

## 7. Business model

Software as a service, sold to mid-market companies and to compliance consultancies.

- **Starter (crosswalk):** map an existing program onto additional public-domain frameworks. Entry tier, roughly 12,000 dollars per year.
- **Continuous compliance:** ongoing mapping, evidence, and reporting across frameworks, roughly 30,000 to 40,000 dollars per year.
- **Usage add-on:** consumption-based compute units for heavy mapping workloads, already metered in the platform.
- **Services and partnerships:** paid onboarding and a partner tier for consultancies who deliver mappings to their own clients on our engine.

Target gross margin is roughly 80 to 85 percent, typical for vertical SaaS, because the marginal cost of a mapping is a small amount of compute.

## 8. Go-to-market

- **Land on the wedge.** Lead with a single, demonstrable promise: you are compliant with framework A, so here is exactly which of your existing controls already satisfy framework B, with evidence, today.
- **Sell at the moment of pain.** Target companies pursuing their second framework, and the consultancies who serve them.
- **Use the training funnel.** A hands-on, auto-graded training platform built on our ground-truth data brings in practitioners at low cost, builds brand and trust, and creates a pipeline into the paid product.
- **Motion.** Founder-led sales to the first design partners, then a repeatable mid-market motion as the growth hire builds the pipeline. This is a sales-assisted model, not pure self-serve, which is why the team scales with revenue.

## 9. Product roadmap (build order set by content licensing)

- **Green stack first (months 0 to 9).** Public-domain and government frameworks (NIST 800-53, CSF, HIPAA), powered by our own permissively licensed models. Zero content-licensing risk, and it is what the engine already does.
- **Yellow stack next (months 9 to 18).** ISO 27001, PCI DSS, SOC 2, CIS. We reference control identifiers and paraphrase intent, tag provenance, and do not redistribute copyrighted text. This is where most paying mid-market demand lives.
- **Red stack later, only when funded.** HITRUST CSF and COBIT require paid content licenses. We defer these until revenue justifies the cost, so they never block the launch.

Alongside frameworks: multi-tenant isolation, cloud and identity integrations, and our own SOC 2, because we must be compliant to sell compliance.

## 10. Technology and defensibility (moat)

- **Curated, provenance-tagged mappings** across frameworks. This is expert labor that compounds and is hard to copy.
- **Proprietary evaluation and ground truth.** Our labeled datasets and benchmarks let us prove mapping quality that competitors cannot easily reproduce.
- **Data flywheel.** Every customer confirmation or rejection of a suggested mapping improves the engine.
- **The training funnel** as a durable, low-cost acquisition and brand channel.
- **Research credibility** that shortens enterprise trust cycles and strengthens grant applications.

## 11. Team

Initial team of five (see [financial_model.md](financial_model.md) for the budget):

1. **Founder and CEO, Samuel Gbli Tetteh.** Built and released the platform, the three models, the benchmarks, and the research. Leads product, machine learning direction, fundraising, and early sales. Computing and digital media background from DePaul University.
2. **Founding platform engineer.** Multi-tenant architecture, integrations, reliability, and the customer-facing console.
3. **Machine learning engineer.** Crosswalk engine quality, the data flywheel, evaluation, and new framework pairs.
4. **Compliance subject matter expert.** Owns the curated mappings that form the moat, guides product for audit-grade trust, and anchors buyer credibility.
5. **Growth lead.** Design-partner acquisition, the training funnel, and the repeatable sales motion.

Advisors to recruit: a compliance-industry operator, a security-focused go-to-market advisor, and an academic collaborator for the STTR research partnership.

## 12. Milestones (tied to the raise)

- **Quarter 1 to 2:** ship multi-tenant authentication and the green-stack minimum viable product, start our own SOC 2, and sign three to five unpaid design partners.
- **Quarter 3 to 4:** convert design partners to paid, ship the scanner-as-evidence integration, submit and pursue an SBIR Phase I award, and reach an annual recurring revenue signal near 150,000 dollars.
- **Year 2:** ship the yellow-stack frameworks and key integrations, grow to roughly 600,000 dollars of annual recurring revenue, and raise a seed round.

## 13. Risks and mitigations

- **Funded incumbents.** Stay narrow on the crosswalking wedge until it is a clear, hard-to-copy advantage. Do not try to out-feature them on evidence collection on day one.
- **Content licensing.** Sequence the roadmap green, then yellow, then red, so proprietary-content costs never block launch.
- **We are not yet compliant ourselves.** Obtain SOC 2 early; it is both table stakes and a sales asset.
- **Single-founder execution risk.** The compliance subject matter expert and the growth lead are the two hires that de-risk this the most, so they are prioritized.
- **Model trust.** Keep the human in the loop, show scores and provenance, and lean on published benchmarks and open models to earn buyer confidence.
- **Sales-cycle length.** Use the training funnel and a low-friction starter tier to shorten time to first value.

## 14. The ask

We are raising a **750,000 dollar pre-seed round on a SAFE**, targeting angels and pre-seed funds, complemented by **275,000 to 400,000 dollars of non-dilutive grant funding**. Together this provides roughly 18 months of runway for the five-person team to reach first paid customers and a seed round. Details and structure are in [financial_model.md](financial_model.md) and [grant_and_funding_strategy.md](grant_and_funding_strategy.md).
