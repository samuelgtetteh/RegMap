# Raw framework sources

Every file in this directory, where it came from, and its licence. **Downloaded 2026-08-02.**
Nothing here is transformed — importers in `regmap_engine/` read these and write the catalog.

Re-download everything with `scripts/fetch_frameworks.sh`.

---

## Downloaded — public domain, redistributable

All NIST publications are US Government works and therefore public domain.

### Control catalogues (OSCAL JSON) — from https://github.com/usnistgov/oscal-content

| file | framework | controls |
|---|---|---|
| `oscal/nist_80053_rev5.json` | NIST SP 800-53 Rev 5.2.0 (+ 800-53A assessment) | ~1,016 with statements |
| `oscal/nist_csf2.json` | NIST CSF 2.0 | 185 subcategories + categories |
| `oscal/nist_80171_rev3.json` | NIST SP 800-171 Rev 3 (CUI) | 97 |
| `oscal/nist_80172_rev3.json` | NIST SP 800-172 Rev 3 (enhanced CUI) | — |
| `oscal/nist_ssdf.json` | NIST SSDF, SP 800-218 v1.1 | 61 |

### 800-53 Rev 5 baselines (OSCAL profiles) — same repo
`oscal/nist_80053_baseline_{low,moderate,high,privacy}.json` — which controls each impact level
selects. These are the basis for a FedRAMP-style baseline view.

### Crosswalks / mappings

| file | mapping | notes |
|---|---|---|
| `nist_800_53_rev5_hipaa_crosswalk_full.csv` | **800-53 Rev 5 ↔ HIPAA Security Rule** | official NIST OLIR export; 222 pairs / 133 controls / 60 provisions. Was already in the repo |
| `oscal/csf_olir_all.xlsx` | **CSF 2.0 → ~23 frameworks** | NIST OLIR informative references. The single highest-value file here — see below |
| `oscal/csf_pf_to_80053r5.xlsx` | CSF **v1.1** → 800-53r5, and Privacy Framework → 800-53r5 | note this is CSF 1.1, not 2.0 |

`nist_800_53_rev5_hipaa_crosswalk.csv` is a shorter earlier export.
`nist_800_53_rev5_hipaa_crosswalk_full (2).csv` is **byte-identical** to the `_full` file — a duplicate
download, safe to delete.

#### Why `csf_olir_all.xlsx` matters
Sheet `CSF 2.0`, column *Informative References*, lists per subcategory the corresponding elements of:

> AI-SOC · BXAIOS · CCMv4.0 · **CIS Controls v8.0/8.1** · CRI Profile v2.0 · CSF v1.1 · CoP ·
> Guardian-SDK · IRP · **ISO/IEC 27001** · NICE Framework · OWASP Top 10 LLM Applications ·
> **PCI DSS** · **SCF** · SDOS · **SP 800-171 Rev 3** · SP 800-221A · **SP 800-53 Rev 5.1.1 / 5.2.0** ·
> SP 800-81r3 · SP-800-37 Rev 2 · SSDF

Because NIST's crosswalk is a US Government work, **the mapping is freely usable even where the target
framework's own text is copyrighted.** That is the legally safe half of ISO 27001, PCI DSS and CIS: we
can say *which* clause corresponds, using their identifiers, without redistributing their words.

---

## NOT downloadable — licence or paid access required

These cannot be fetched, and attempting to redistribute their control text would breach copyright. This
is the wall `docs/product_master_plan.md` §8 flags, so it is a procurement task, not an engineering one.

| framework | why | how to obtain |
|---|---|---|
| **ISO/IEC 27001:2022** / 27002 | copyrighted; sold per-seat | purchase from ISO or a national body (ANSI, BSI). Mapping ids available via the OLIR file above |
| **PCI DSS 4.0** | copyrighted; PCI SSC licence terms | free download from the PCI SSC portal after registration/agreement — **but redistribution is not permitted**. Mapping ids available via OLIR |
| **SOC 2 / Trust Services Criteria** | copyrighted (AICPA) | purchase from AICPA. Not in the OLIR export either |
| **CIS Controls v8** | free with registration; redistribution restricted | register at cisecurity.org; check terms before shipping. Mapping ids available via OLIR |
| **HITRUST CSF** | proprietary, **licence required** | commercial HITRUST licence |
| **COBIT 2019** | proprietary (ISACA), **licence required** | ISACA licence |
| **Secure Controls Framework (SCF)** | licensed content | scf ids appear in the OLIR export and are used only as mapping identifiers |

### Public but not yet fetched
Available to anyone, just not machine-readable in a form worth importing yet:

- **GDPR** — full text on EUR-Lex (Regulation 2016/679); needs parsing into articles
- **CMMC 2.0** — DoD publishes the model; largely a selection of 800-171, which we already have
- **FedRAMP** — the `GSA/fedramp-automation` repo has moved; its baselines are 800-53 profiles, which
  the NIST baselines above already cover

---

## Practical notes for whoever imports these

- **Control-id spelling differs per source** and must be normalised or nothing joins: the same control
  is `ac-2` in OSCAL, `AC-02` in OSCAL back-matter titles, `AC-2` in the OLIR CSV, and enhancements
  appear as `ac-2.3` / `AC-02(03)` / `AC-2(3)`. `regmap_engine/import_oscal.py:canon_id` handles this.
- **OSCAL leaves parameter placeholders inline** as `{{ insert: param, ac-01_odp.01 }}`. Strip or
  substitute them before embedding, or every control carries meaningless tokens.
- **SP 800-171 Rev 3 contains a free official mapping to 800-53**: each requirement's
  `links[rel=reference]` point at back-matter resources whose titles are 800-53 control ids.
- **CSF 2.0's OSCAL catalogue does *not* contain the informative references** — those are only in the
  XLSX export.
- The CSF 2.0 export URL says `json` but serves **XLSX**:
  `https://csrc.nist.gov/extensions/nudp/services/json/csf/download?olirids=all`
