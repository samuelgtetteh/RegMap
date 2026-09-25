# Compliance tab tracker

The plan to turn the Compliance tab (`web/compliance.html`) from a demo into a tool GRC and IT teams
pay to use. Start here for anything on the Compliance surface. Sibling: `docs/build_tracker.md` (whole
product), `docs/design_system.md` (locked layout). No em-dashes or en-dashes (founder rule).

Last updated: 2026-09-25.

## Goal

Make the Compliance tab the fastest, most trustworthy way for a team to prove that the controls they
already operate satisfy any framework they must meet, and to keep that current. It has to be worth
paying for, which means it must save real consulting hours and produce audit-grade output, not just
return a ranked list.

## Current state (built)

- **Map a control** tab: pick a source framework + control (or free text) and a target framework; ranked,
  scored results; official mappings marked; live coverage tiles. Wired to `/map`.
- **Coverage and gaps** tab: map a whole catalog framework to a target; coverage percent and the official
  gap list. Wired to `/map/bulk`.
- Engine, auth, metering (Compute Units) and quotas already exist behind it.

## Feature request being built now: bring your own framework

**What:** let a team load their own internal or self-built control framework (their IT/security control
set) and map it to any framework in the catalog. This is the wedge for teams whose starting point is not
a public framework but their own program.

- **Input:** paste controls (one per line, `id, text` or just text), or upload a CSV/JSON file.
- **Map:** the model ranks each of the user's controls against the chosen target framework and returns
  scored suggestions per control. No official crosswalk exists for a custom source, so results are
  clearly labelled model suggestions, not authoritative.
- **Free for now, with a limit:** free tier caps the number of controls mapped per run
  (`REGMAP_CUSTOM_FREE_MAX`, default 25). The paid version raises or removes the cap and unlocks the
  workflow features below. Metered in Compute Units like every other model call.
- **Endpoint:** `POST /map/custom` `{target, controls:[{id,title?,text}], top_k}`.
- **UI:** a third tab, "Your framework", in `web/compliance.html`.

Status: [x] backend endpoint (`POST /map/custom`) · [x] frontend tab ("Your framework") · [x] free-limit
+ paid note (`REGMAP_CUSTOM_FREE_MAX`, default 25) · [ ] export of results (next).

## Recommendations: what makes this a must-have paid tool

Ordered by impact. Each notes why it matters and a suggested free/paid split. These are for review, not
yet committed.

### Tier 1: the workflow that justifies payment
1. **Bring your own framework (this request).** Teams live in their own control set. FREE limited, PAID unlimited.
2. **Human-in-the-loop review and status.** For every suggested mapping, let the user Accept / Reject /
   Edit, set a status (Met / Partial / Gap / Not applicable), and add a note. The engine suggests, an
   expert confirms; this is the audit-grade loop the business plan promises. PAID.
3. **Saved projects and persistence.** A mapping is a project you return to, not a one-off query. Save a
   named crosswalk, reopen, and track progress over time. PAID (free = ephemeral, no save).
4. **Audit-ready export.** One click to a shareable compliance package (DOCX, XLSX, JSON) with, per
   obligation: suggested control, score, provenance, status, note, evidence link. The `/advisor` layer
   already builds DOCX/XLSX; wire it here. FREE watermarked / limited, PAID full.
5. **Evidence attachment.** Attach or link evidence (a document, a scan result, a ticket) to each control,
   so the crosswalk doubles as the audit binder. PAID.

### Tier 2: depth and trust
6. **Coverage dashboard and heatmap.** A matrix of your program against many target frameworks at once,
   colored by coverage, with drill-down. Turns one mapping into a portfolio view. PAID.
7. **Map to many frameworks at once.** Submit your control set and get coverage against N targets in one
   run (SOC 2 + ISO 27001 + HIPAA together). PAID.
8. **Gap remediation guidance.** For each gap, suggest the control to implement and a starter policy
   statement (reuses the advisor's drafting). PAID.
9. **Confidence thresholds and triage.** Let the user set a confidence cutoff; auto-flag low-confidence
   matches as "needs review" so effort goes where it matters. FREE basic, PAID tunable.
10. **Explainability.** Show why a mapping was suggested (the matched phrases, the route, the provenance),
    which auditors trust over a black box. FREE.

### Tier 3: scale, integration, stickiness
11. **Versioned crosswalks and drift.** Track framework versions (800-53 Rev5 to Rev6) and re-run to show
    what changed, so coverage never goes stale silently. PAID.
12. **Continuous re-mapping.** Schedule re-runs on a cadence or on framework updates; tie into the
    console's Continuous monitoring. PAID.
13. **Collaboration.** Multiple users, assignments, comments, an approval trail. PAID (team plans).
14. **API and bulk import.** A team can push their control set and pull mappings programmatically, and
    import from GRC tools (Vanta, Drata, spreadsheets). PAID.
15. **Templates and journeys.** Pre-built starting points for common paths (SOC 2 to ISO 27001, HIPAA to
    800-53), so a new user reaches value in one click. FREE.
16. **Framework library growth.** Ship the coming-soon frameworks (ISO, SOC 2, PCI, CIS, CMMC, etc.); the
    tool is only as valuable as the frameworks it covers. Ongoing.

## Free vs paid (proposed)

- **Free:** map a control, free-text mapping, small custom uploads (cap 25 controls), basic coverage and
  the official gap list, explainability, templates. Enough to prove value and pull the funnel.
- **Paid:** unlimited custom mapping, review/status workflow, saved projects, evidence, full export,
  coverage dashboard, multi-target mapping, remediation guidance, versioning, continuous re-mapping,
  collaboration, API. This is the "do the actual audit work" tier.

## Build order

1. [x] Bring your own framework (endpoint + tab + free limit). DONE 2026-09-25.
2. [ ] Export results of any mapping to XLSX/JSON (extend to DOCX via the advisor).
3. [ ] Review + status workflow (needs light persistence).
4. [ ] Saved projects (needs the billing DB or a new table).
5. [ ] Coverage dashboard / multi-target.
6. [ ] The rest of Tier 2 and 3 in priority order.

## Change log

- 2026-09-25: created. Feature: bring your own framework built (POST /map/custom, "Your framework" tab,
  free cap 25 controls/run). Recommendations recorded above for review.
