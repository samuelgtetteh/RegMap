# Public model releases — insert text for the NIW petition brief & personal statement

The petition brief and personal statement are not in this repository. Below is ready-to-paste
wording capturing that **all three models** have been publicly released as open, reusable,
standalone systems. Accurate as of 2026-07-17. Cite **Exhibits 11A, 12A, 13A** (and 18/19 for reuse).

**Verifiable public links (all Apache-2.0):**

| Model | Hugging Face | Docker (GHCR) | GitHub Release |
|---|---|---|---|
| RegMap (NIST→HIPAA mapping) | huggingface.co/stetteh/regmap-embedder | ghcr.io/samuelgtetteh/regmap-embedder | v0.1-regmap |
| Hybrid Identity Anomaly Detector | huggingface.co/stetteh/identity-anomaly | ghcr.io/samuelgtetteh/identity-anomaly | v0.1-identity |
| OT/ICS Intrusion Detector | huggingface.co/stetteh/otics-anomaly | ghcr.io/samuelgtetteh/otics-anomaly | v0.1-otics |

---

## A. Petition brief (formal, third person)

*Suggested placement: the "well positioned to advance the endeavor" section and/or the
"benefit to the United States / dissemination" discussion.*

> Beyond building and validating his research prototypes, the petitioner has released one of them —
> RegMap, a machine-learning model that maps NIST SP 800-53 security controls to the corresponding
> HIPAA Security Rule provisions — as an open, freely licensed tool that any U.S. organization can
> use immediately. The model is published on the Hugging Face model hub, distributed as a
> self-contained downloadable release, and packaged as a runnable Docker service, all under the
> permissive Apache-2.0 license (Exhibit 11A). This transforms the work from a private research
> result into public infrastructure: compliance teams, managed service providers, and under-resourced
> state and local government offices — organizations that frequently cannot afford commercial
> compliance-mapping software — can adopt it at no cost. The same model has also been reused as a
> component across the petitioner's broader security platform (Exhibits 18 and 19), demonstrating
> durable, transferable value rather than a one-off artifact. Publicly releasing and operationally
> reusing his own research is direct evidence both that the petitioner is well positioned to advance
> the proposed endeavor and that the endeavor produces tangible benefits for the United States
> through open dissemination.

*(Optional, if a metrics-honest line is desired):* RegMap is designed as an assistive retrieval
tool that surfaces the most relevant HIPAA provisions for an expert to confirm (the correct
provision appears among its top five suggestions approximately 74% of the time), accelerating
compliance mapping while keeping a qualified human in the loop.

---

## B. Personal statement (first person)

*Suggested placement: where you discuss impact, dissemination, or your commitment to making the
work useful.*

> I have not kept this work in a drawer. I released RegMap — my model that maps NIST SP 800-53
> controls to HIPAA Security Rule provisions — as a free, open-source model that anyone can use
> today: it is published on Hugging Face, downloadable as a self-contained package, and available as
> a ready-to-run Docker service, all under the Apache-2.0 license. I did this because the
> organizations that most need help with compliance — small clinics, non-profits, and state and
> local agencies — are often the least able to pay for commercial tools. By putting RegMap in the
> open and reusing it as a building block across my broader security platform, I am trying to make
> rigorous, AI-assisted compliance capability available to the people and institutions across the
> United States who would otherwise go without it. Carrying my research all the way to a published,
> reusable tool is exactly the kind of contribution I intend to keep making.

---

## C. Combined version — all three models (use for brief or statement)

*Brief (third person):*
> The petitioner has not confined his research to publications: he has released all three of his
> models as open, standalone tools that any U.S. organization can use at no cost, each on the
> Hugging Face model hub, as a downloadable release, and as a runnable Docker service under the
> Apache-2.0 license — RegMap (NIST SP 800-53 → HIPAA compliance mapping), a hybrid-identity anomaly
> detector (credential-compromise and insider-threat detection), and an OT/ICS intrusion detector
> for critical-infrastructure sensor data (Exhibits 11A, 12A, 13A). The same models are reused as
> components of his integrated security platform (Exhibits 18–19). Releasing and operationally
> reusing his own research is direct evidence that the petitioner is well positioned to advance the
> proposed endeavor and that the endeavor delivers concrete, openly disseminated benefits to the
> United States — especially to under-resourced organizations that cannot afford commercial tools.

*Personal statement (first person):*
> I have released all three of my models — RegMap for compliance mapping, my identity anomaly
> detector, and my OT/ICS intrusion detector — as free, open-source tools on Hugging Face,
> as downloadable packages, and as ready-to-run Docker services. I did this because the
> organizations that most need these capabilities — small clinics, utilities, and local agencies —
> are often the least able to pay for them. Putting my work in the open, where anyone in the country
> can use it, is how I intend to serve the national interest.
