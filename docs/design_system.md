# Design system — look & feel decision

The website's visual direction, decided so every page is consistent. Living reference page (artifact):
built alongside this doc. Related: `docs/product_master_plan.md`, the landing page.

## The decision
Credible-but-approachable: **serious enough that an employer/auditor trusts it, warm enough that a
career-changer isn't intimidated.** We emulate the best-in-class rather than invent:
- **Linear** — precision, dark base, disciplined motion, tight type hierarchy. (Marketing + app chrome.)
- **Stripe** — trust, polish, one restrained gradient accent, great docs. (Marketing + GRC surfaces.)
- **Datadog / Tenable** — information density done right. (The console/workbench.)
- **Duolingo** — encouraging, legible feedback. (The learn→do→graded loop only — a hint, not the whole site.)
- **Avoid:** gamer-neon (TryHackMe/HTB); AI-generated cream+serif+terracotta; Inter/Space-Grotesk-as-default.

## Tokens
**Color** — deep ink base, one confident indigo accent, semantic severity kept separate from the accent.
```
--bg:#0B0F17  --surface:#111826  --surface-2:#0E1420  --line:#1E2A3C  --line-2:#2A3A52
--ink:#EAF1FB  --muted:#93A6BD  --faint:#63758F
--accent:#6E8BFF  --accent-2:#87A2FF  --accent-soft:rgba(110,139,255,.14)
--ok:#3DDC84  --warn:#F0B429  --crit:#FF5C7A     (severity — NOT the accent)
light theme: --bg:#F6F8FC --surface:#FFFFFF --ink:#0E1626 --accent:#3E63DD (mirror the rest)
```
Both themes are first-class (`prefers-color-scheme` + `data-theme` override). Neutrals carry a slight blue
bias (chosen, not default grey).

**Type** — differentiate from the AI-default. In the **product** (real webfonts allowed):
display = **General Sans** or **Geist**; body = **Inter** (or system) at ~65ch; data/console = a mono
(Geist Mono / Cascadia). In **artifacts** (font-CDN blocked by CSP): a tuned system stack + strong
weight/tracking, or embed one display face as a data URI. Type scale fixed; headings `text-wrap:balance`;
uppercase labels get letter-spacing; digits use `tabular-nums`.

**Layout** — centered, generous marketing (`max-width:1180px`), dense data-first console. Cards with soft
1px borders + subtle shadow; rounded 12–16px (not `rounded-lg` everywhere).

**Motion** — purposeful, Linear-style: scroll-reveal, hover lift, console state transitions
(provisioning→ready pulses). Respect `prefers-reduced-motion`. One orchestrated moment (an animated live
console in the hero) beats scattered effects.

**Voice** — plain, from the user's side. "Prove you can do the job." Buttons say the action; feedback is
specific and encouraging, never condescending.

## Where it applies
Marketing/landing, the app shell (nav/tabs), the Assess/Monitor console (already Tenable-style — align its
tokens to the above), the learning loop, and the RegMap/GRC surfaces. The provisioner UI already uses this
palette — treat it as the first component-level implementation.
