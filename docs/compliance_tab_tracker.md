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

## Next up (GREEN-LIT, building now): the audit-grade workflow

Decision (2026-09-25): build the workflow that turns a mapping from a query into a deliverable an auditor
accepts. This is the single biggest jump from demo to paid tool, because it is exactly the consulting
hours we save. Three linked pieces, built in this order. All three are the PAID tier (free stays
query-only), except a lightweight in-session review that works before sign-in.

### A. Review + status (per suggested mapping)
For every suggested control-to-target mapping, the analyst decides:
- **Action:** Accept / Reject / Edit (swap in a different target control).
- **Status:** Met / Partial / Gap / Not applicable.
- **Note:** free-text justification.
The engine suggests, the expert confirms. This is the human-in-the-loop the business plan promises.

- [x] UI: inline controls on each result row (Accept/Reject, a status select, a note field), plus a
      per-control roll-up. DONE 2026-09-25 on the "Your framework" and "Map a control" tabs.
- [x] Works in-session immediately (state held in `DECISIONS` in the page); persists once saved (piece B).
- [x] Usability: drag-and-drop a CSV/JSON file onto the "Your framework" box; caps lifted while
      enforcement is off (see build_tracker pre-launch note).
- [ ] NEXT: persist it (piece B, saved projects) so review survives a reload.

### B. Saved projects (persistence)
A **project** = a named crosswalk: the source control set (custom or catalog), the target framework, and
every decision/status/note/evidence link. Reopen and continue; track progress over time.

- [x] Data model in `billing.py` (dual-dialect, keyed by `account_id`): DONE 2026-09-25. Went with a
      single `projects` table carrying the full working state as JSON (`data` = target, top_k, controls,
      decisions) instead of a separate `project_items` table. Simpler for now; split out later if needed.
- [x] Endpoints: `GET/POST /projects`, `GET/PUT/DELETE /projects/{id}` in serve.py, behind
      `auth.require_key`, scoped to the account. Verified CRUD end to end. (Rename is a PUT with `name`.)
- [x] UI: project bar on the "Your framework" tab (name, Save, Open project, New, Delete) with autosave
      on decision changes; opening a project restores the controls, target and review state, then re-maps.

### C. Audit-ready export
One click to a shareable package from a project (or the current in-session mapping).

- [x] `GET /projects/{id}/export?fmt=json|csv|xlsx|docx`. DONE 2026-09-25. Built from the saved review
      (openpyxl for XLSX, python-docx for DOCX, stdlib for JSON/CSV). Frontend: an "Export…" dropdown on
      the project bar that saves first, then downloads. Verified all four formats produce valid files.
- [x] Columns per source control: Source ID, Source control, Status, Mapped to (accepted targets +
      titles), Rejected, Note.
- [ ] Later: add score/provenance/evidence columns and a paid gate (all formats are free pre-launch).

### Build order for this workflow
1. [x] A (in-session review UI) on the "Your framework" and "Map a control" results. DONE 2026-09-25.
2. [x] B1 (schema + `GET/POST /projects`, `GET/PUT/DELETE /projects/{id}`). DONE 2026-09-25.
3. [x] B2 (Save/Open UI + autosave), which makes A durable. DONE 2026-09-25.
4. [x] C (export json/csv/xlsx/docx). DONE 2026-09-25.
5. [ ] Gate paid pieces behind an entitlement; keep in-session review free. (Enforcement is off for
      pre-launch, so nothing is gated yet.)

### Open decisions before/while building
- **Entitlement flag:** how "paid" is represented. Simplest now: a boolean/`features` column on the
  account (operator-set), checked by these endpoints. Full billing (Stripe) is Phase C in `build_log.md`.
- **DB:** SQLite is fine for now (already durable via the PVC); Postgres when multi-writer is needed.
- **In-session vs account:** review works before sign-in (ephemeral); saving/exporting requires an account.

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
5. **Evidence attachment. DONE 2026-09-25.** Each source control has an Evidence section (label + link)
   to attach a document, scan result, or ticket, so the crosswalk doubles as the audit binder. Stored in
   `DECISIONS[sid].evidence` (saved with the project) and rendered on both the "Map a control" and "Your
   framework" tabs. Flows into export as an **Evidence** column (`_EXPORT_COLS` + `_export_rows` in
   `serve.py`) across JSON/CSV/XLSX/DOCX. Verified end to end. Later: file upload/storage (links only for
   now), and the paid gate. PAID (planned).

### Tier 2: depth and trust
6. **Coverage dashboard and heatmap. DONE 2026-09-25.** The multi-target result now renders as a
   dashboard: a coverage tile per framework (big % covered, matched/total, avg score, bar) above a
   heatmap matrix whose cells are shaded by match strength (`covColor`). Drill-down: clicking a tile or a
   column header loads that framework into the single-target review above (re-maps the same controls) so
   you can review and export it in depth. Built on `/map/custom/multi` (#7); no new endpoint. PAID
   (planned). Later: per-cell drill-down to the exact suggestion, and add coverage to export.
7. **Map to many frameworks at once. DONE 2026-09-25.** `POST /map/custom/multi {targets:[...],controls,
   threshold}` maps one control set onto up to 8 frameworks in a single run, returning per control the
   best-matching target control in each framework (id, score, why) plus a per-framework coverage summary
   (matched/total at a score threshold, avg score). Front end: a "Compare coverage across several
   frameworks" panel on the "Your framework" tab (checkbox picker + a coverage matrix table with a
   sticky coverage row). Backend helper `_best_per_control`. Verified end to end. This is the data spine
   for the coverage heatmap (#6). PAID (planned). Later: drill-down from a cell into the single-target review. 
8. **Gap remediation guidance.** For each gap, suggest the control to implement and a starter policy
   statement (reuses the advisor's drafting). PAID.
9. **Confidence thresholds and triage. DONE 2026-09-25.** A threshold slider above each result set (on
   both "Map a control" and "Your framework") flags every match below the cutoff as a "needs review" pill
   and dims the row, with a live "N of M need review" count. The chosen threshold persists
   (`localStorage regmap.confThreshold`). Pure view over the returned scores (`triageBar`/`applyTriage`/
   `wireTriage`), no refetch. FREE basic; PAID would add auto-actions (bulk-set status on the flagged).
10. **Explainability. DONE 2026-09-25.** Every suggested mapping now shows *why* it matched: the salient
    terms shared by the query and the target control, as chips under each result. Backend `_why_terms`
    in `serve.py` (stemmed overlap, stopword-filtered) adds a `why: [...]` array to each result on `/map`
    and `/map/custom`; the front end renders `whyChips` on both the "Map a control" and "Your framework"
    tabs. The route/provenance (official / derived / no-route) was already shown via the route badge. FREE.

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
2. [ ] **The audit-grade workflow (GREEN-LIT, next): review + status, then saved projects, then export.**
       See "Next up" above for the A/B/C plan, schema, endpoints and step order.
3. [ ] Coverage dashboard / multi-target.
4. [ ] The rest of Tier 2 and 3 in priority order.

## Change log

- 2026-09-25: created. Feature: bring your own framework built (POST /map/custom, "Your framework" tab,
  free cap 25 controls/run). Recommendations recorded for review.
- 2026-09-25: green-lit the audit-grade workflow (review + status, saved projects, export) as the next
  build; recorded the A/B/C plan, data model and endpoints under "Next up".
- 2026-09-25: built Explainability (#10, Tier 2, FREE): `_why_terms` on the backend adds stemmed,
  stopword-filtered shared terms as `why` on `/map` and `/map/custom` results; `whyChips` renders them
  under each result on both tabs.
- 2026-09-25: built Evidence attachment (#5, last Tier-1 item): per-control label+link evidence stored in
  DECISIONS[sid].evidence, saved with the project, rendered on both tabs, and exported as an Evidence
  column across all four formats. Verified end to end. Tier 1 is now complete.
- 2026-09-25: built Multi-target mapping (#7, Tier 2): `POST /map/custom/multi` + `_best_per_control`;
  "Compare coverage across several frameworks" panel with a checkbox picker and a coverage matrix on the
  "Your framework" tab. Verified end to end (2 controls x 3 frameworks).
- 2026-09-25: built Coverage dashboard/heatmap (#6, Tier 2): coverage tiles per framework + heatmap-shaded
  matrix (`covColor`) + drill-down from a tile/column into the single-target review. No new endpoint.
- 2026-09-25: built Confidence triage (#9, Tier 2): a threshold slider that flags low-confidence matches
  as "needs review" on both tabs, with a live count and a persisted threshold. Tier 2 items #6, #7, #9,
  #10 done; only #8 (gap remediation guidance) remains in Tier 2.
