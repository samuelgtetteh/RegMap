# RegMap design system (LOCKED)

**Status: LOCKED baseline. This is the final layout.** Frozen 2026-09-25, marked by git tag
`design-baseline-v1` (the design system landed in commit `c702245`). Every page and every future change
extends this system. Do not diverge from it. No em-dashes or en-dashes anywhere (founder style rule).

## The rule

- **This layout is final.** Build on top of it. New pages and features reuse the tokens and components
  below; they do not introduce a second visual language.
- **Token names are stable.** You may retune a token's *value*, never rename or remove it, because every
  page depends on the names. Add new tokens rather than repurposing existing ones.
- **The source of truth is the code**, in this order: `web/assets/site.css` (tokens + components),
  `web/assets/shell.js` (the injected nav/shell), `web/assets/app.css` (interactive-tool components),
  `web/assets/img/*.svg` (imagery). This doc describes them; if they disagree, the code wins and this
  doc gets corrected.
- **When you change CSS or JS, bump the cache-bust version** on the `?v=` query in every page's
  `<link>`/`<script>` (currently `?v=3`), or browsers serve a stale copy.
- **Imagery is hand-authored SVG, not icons and not emoji.** Art lives in `web/assets/img/`. If an image
  generator is wired up later, generated raster art may be added for hero/marketing only; the UI stays SVG.
- **Any future visual change is recorded here** in the Change log at the bottom, with its commit.

## Design language

Linear (crisp dark canvas, tight type, gradient accents, disciplined motion) + Vanta (compliance trust:
coverage rings, status badges, framework grids) + Datadog (dense data panels for the console). Training
surfaces borrow TryHackMe / HackTheBox energy (terminal, graded, XP) inside the same system. Dark first,
with a first-class light theme (`prefers-color-scheme` + `data-theme` override).

## Tokens (as implemented in site.css)

Dark base:
```
--bg:#0A0D17  --surface:#10141F  --surface-2:#0C0F19  --elev:#151B2B
--line:#1E2637  --line-2:#2C3650
--ink:#EAEFFB  --muted:#96A3BE  --faint:#5F6C88
--accent:#6366F1  --accent-2:#8B5CF6  --cyan:#22D3EE  --accent-soft:rgba(99,102,241,.15)
--grad: linear-gradient(135deg,var(--accent),var(--accent-2))
--ok:#34D399  --warn:#FBBF24  --crit:#FB7185          (severity, kept separate from the accent)
--sans:"Inter",system-ui,...   --mono:"JetBrains Mono",ui-monospace,...
--radius:16px  --radius-sm:11px  --gut:clamp(18px,3.4vw,60px)
```
Light theme mirrors it: `--bg:#F6F8FD --surface:#FFFFFF --ink:#0D1424 --accent:#5457E6` (rest follows).
Digits use `tabular-nums`; uppercase labels get letter-spacing; headings use `text-wrap:balance`.

## Components (the locked vocabulary)

- **Shell / nav** injected by `shell.js`: sticky blurred header, gradient brand mark, `.nav-links`
  (desktop) with a **mobile hamburger menu** (`.mobile-menu`) below 860px, theme toggle, `Open app` +
  `Start free`. Nav entries live in the `NAV` array in `shell.js`.
- **Layout primitives:** `.bleed` (full width), `.pad` (the single side gutter), `.section` /
  `.section.tight`, `.band` (tinted strip), `.divider`, `.row-head` (heading + link).
- **Buttons:** `.btn.primary` (gradient), `.btn.ghost`, `.btn.sm`.
- **Hero:** `.hero` + `.hero-wrap` (two columns, stacks under 900px) + `.hero-art` (image, `width:100%`)
  + `.chip` (live status pill) + `.grad-text` (gradient headline span).
- **Stat row:** `.stat-row` of `.cell > .stat` (`.k` label, `.n` number, `.d` delta). The proof strip.
- **Tiles / cards:** `.tile` with an optional `.thumb` (image or SVG banner, `object-fit:cover`) and
  `.body`. `.grid` auto-fills them.
- **Pillars:** the two-product cards (`.pillar` in the homepage `<style>`), image banner + body + CTA.
- **Steps:** `.step` (numbered `.no` label + heading + copy), used for process rows.
- **Panels (console):** `.panel` + `.panel-head` + `.panel-body`.
- **Coverage ring:** `.ring` (conic-gradient donut, set `--p` 0-100 and `--ring` color inline).
- **Pills / badges:** `.pill.ok|warn|crit|info`.
- **Data table:** `table.dt` (Datadog-style).
- **Motion:** `.reveal` scroll-reveal; hover lift on tiles/buttons; respects `prefers-reduced-motion`.

## Page shell pattern (how to add a page without diverging)

1. `<body data-page="ID">` where `ID` matches a `NAV` entry (or a new one).
2. In `<head>`, link the shared assets with the current cache-bust version:
   `assets/site.css?v=N`, `assets/app.css?v=N` (only if it uses tool components), and before `</body>`
   `assets/shell.js?v=N` (plus `assets/api.js?v=N` if it calls the engine).
3. Build the page from the components above. Page-specific CSS goes in a small `<head><style>` block that
   uses the tokens; do not fork the token set.
4. Imagery: reference SVGs from `assets/img/`. No emoji, no icon fonts.
5. Include the Google Fonts preconnect + Inter/JetBrains Mono link (see any existing page) so type matches.

## Responsive rules (locked)

- Mobile menu below 860px; `.nav-desk` items hide, the hamburger shows.
- Grids/pillars/hero stack on phones; `.stat-row` goes 2-up; buttons go full width.
- Grid and flex children carry `min-width:0` so wide content (images) cannot force horizontal scroll.
- `body{overflow-x:hidden}` is the backstop. Verified: at phone width `scrollWidth == clientWidth`.
- Wide, dense content (tables, diagrams) scrolls inside an `.scroll-x` wrapper, never the page body.

## Pages on the system

`index.html` (two-pillar landing), `compliance.html` (map + coverage/gaps), `labs.html` (graded
training), `pricing.html` (CU pricing), `console.html` (compliance console at `/dashboard`). Served by
`main.py` (`uvicorn main:app`) from the `web/` shell.

## Change log

- **2026-09-25 `c702245` (LOCKED baseline, tag `design-baseline-v1`).** New design system (Linear +
  Vanta + Datadog), SVG imagery, rebuilt homepage and compliance console, mobile menu, responsive
  hardening, cache-busting. This is the final layout; entries below record changes on top of it.
- **2026-09-25 console content.** Framework catalog now also lists the 10 coming-soon frameworks with a
  "coming soon" pill and their planned control counts (registry `planned` field, surfaced as
  `/frameworks` `planned_controls`); a "coming soon" stat added. Answerable-pairs panel now lists every
  pair in a scrollable list (`.scrolllist`) instead of truncating with "and N more". No token or
  component changes.
- **2026-09-25 console continuous monitoring.** Added a "Continuous monitoring" section between the
  panels and "Do the work": coming-soon cards for Identity and OT/ICS control monitoring (confirm mapped
  controls are operating). Reuses existing components; no token changes.
- **2026-09-25 animated monitoring previews.** Replaced the static monitoring banners with looping
  animated SVGs (SMIL, `repeatCount=indefinite`): `img/mon-identity.svg` (live signal, travelling pulse,
  sweeping scan bar, periodic anomaly) and `img/mon-otics.svg` (telemetry breaching a control threshold).
  New `.mon-banner` shows the full animation without cropping (unlike `.thumb` which uses object-fit
  cover). Animated SVGs are the "looped video" pattern for previews of coming-soon capabilities; there is
  no video generator wired, and SVG stays crisp and tiny. Verified frames advance in the browser.
