/* ============================================================================
   Construction-page engine. A page declares itself with data-* on <body> and an
   empty <main id="uc">; this fills it with a hero and a looped, animated SVG that
   previews what the finished page will show. Animation is SMIL (works with no
   extra library) so every preview loops forever on its own.

   Body data attributes:
     data-title    the page name (H1)
     data-eyebrow  the section it belongs to (Company, Resources, Solutions, Legal)
     data-blurb    one or two sentences on what is coming
     data-scene    which animated preview to render (see SCENES below)
     data-bullets  optional "a|b|c" feature list
     data-cycle    optional "x|y|z" labels for scenes that cycle text
     data-caption  optional caption under the preview
     data-more     optional "Label::/href::desc | ..." related-page cards
   ============================================================================ */
(function () {
  const b = document.body, d = b.dataset;
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---- tiny SVG helpers ----------------------------------------------------
  const NS = 420, NH = 320;
  const frame = inner => `
    <svg viewBox="0 0 ${NS} ${NH}" class="uc-svg" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Animated preview">
      <defs>
        <linearGradient id="ucg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#6366F1"/><stop offset="1" stop-color="#8B5CF6"/>
        </linearGradient>
        <linearGradient id="ucg2" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stop-color="#8B5CF6"/><stop offset="1" stop-color="#22D3EE"/>
        </linearGradient>
      </defs>
      <rect x="0" y="0" width="${NS}" height="${NH}" fill="var(--surface-2)"/>
      ${inner}
    </svg>`;
  // a set of texts that fade in one after another and loop forever
  const cycle = (labels, x, y, size, weight) => {
    const each = 1.9, dur = (labels.length * each).toFixed(2);
    return labels.map((l, i) => `
      <text x="${x}" y="${y}" font-family="Inter,system-ui,sans-serif" font-size="${size}" font-weight="${weight || 700}"
            fill="var(--ink)" text-anchor="middle" opacity="0">${esc(l)}
        <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.08;0.44;0.5"
                 dur="${dur}s" begin="${(i * each).toFixed(2)}s" repeatCount="indefinite"/>
      </text>`).join("");
  };
  const pulse = (cx, cy, r, fill, begin) => `
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="${fill}">
      <animate attributeName="opacity" values="0.35;1;0.35" dur="1.8s" begin="${begin || 0}s" repeatCount="indefinite"/>
      <animate attributeName="r" values="${r};${r * 1.25};${r}" dur="1.8s" begin="${begin || 0}s" repeatCount="indefinite"/>
    </circle>`;

  // ---- scenes --------------------------------------------------------------
  const SCENES = {
    // roles cycling in a spotlight card over a stack of role cards (Careers)
    roles(cy) {
      const roles = cy || ["Security Engineer", "GRC Analyst", "ML Engineer", "Founding Account Exec", "Curriculum Lead"];
      const stack = [0, 1, 2].map(i => `
        <rect x="70" y="${196 + i * 26}" width="280" height="20" rx="6" fill="var(--surface)" stroke="var(--line)"/>
        <rect x="82" y="${203 + i * 26}" width="${120 - i * 20}" height="6" rx="3" fill="var(--line-2)"/>`).join("");
      return frame(`
        <rect x="60" y="70" width="300" height="96" rx="16" fill="var(--surface)" stroke="url(#ucg)" stroke-width="1.5"/>
        <text x="210" y="104" font-family="JetBrains Mono,monospace" font-size="11" fill="var(--accent)" text-anchor="middle" letter-spacing="2">NOW HIRING</text>
        ${cycle(roles, 210, 138, 20)}
        ${stack}
        ${pulse(96, 80, 5, "var(--ok)", 0)}`);
    },
    // network of nodes connecting (About / team)
    network() {
      const nodes = [[90, 90], [210, 60], [330, 100], [140, 190], [280, 200], [210, 250]];
      const links = [[0, 1], [1, 2], [0, 3], [1, 4], [3, 5], [4, 5], [2, 4]];
      const line = ([a, bb], i) => {
        const [x1, y1] = nodes[a], [x2, y2] = nodes[bb];
        return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="url(#ucg2)" stroke-width="2" opacity="0.25">
          <animate attributeName="opacity" values="0.1;0.8;0.1" dur="3s" begin="${(i * 0.35).toFixed(2)}s" repeatCount="indefinite"/></line>`;
      };
      const dot = ([x, y], i) => `<circle cx="${x}" cy="${y}" r="10" fill="url(#ucg)">
        <animate attributeName="r" values="8;12;8" dur="2.6s" begin="${(i * 0.3).toFixed(2)}s" repeatCount="indefinite"/></circle>`;
      return frame(links.map(line).join("") + nodes.map(dot).join("") +
        `<text x="210" y="300" font-family="Inter,sans-serif" font-size="12" fill="var(--muted)" text-anchor="middle">One team, one source of truth</text>`);
    },
    // a document whose lines "type" in, page by page (Documentation / Help)
    docs() {
      const line = (y, w, begin) => `
        <rect x="150" y="${y}" width="0" height="7" rx="3.5" fill="var(--line-2)">
          <animate attributeName="width" values="0;${w};${w};0" keyTimes="0;0.3;0.9;1" dur="6s" begin="${begin}s" repeatCount="indefinite"/></rect>`;
      let lines = "";
      for (let i = 0; i < 7; i++) lines += line(96 + i * 20, 120 - (i % 3) * 24, (i * 0.4).toFixed(2));
      return frame(`
        <rect x="130" y="60" width="200" height="210" rx="12" fill="var(--surface)" stroke="var(--line)"/>
        <rect x="130" y="60" width="200" height="26" rx="12" fill="url(#ucg)"/>
        <rect x="130" y="74" width="200" height="12" fill="var(--surface)"/>
        <text x="150" y="78" font-family="JetBrains Mono,monospace" font-size="10" fill="#fff">docs / getting-started</text>
        ${lines}
        <rect x="150" y="60" width="4" height="210" fill="url(#ucg2)" opacity="0.5"/>`);
    },
    // a terminal running a request -> response loop (API reference)
    api() {
      const rows = [
        ["$ curl -s /map -d @control.json", "#22D3EE", 0],
        ['> matching against NIST 800-53 ...', "var(--muted)", 1.1],
        ['{ "target": "SC-13", "score": 0.84,', "var(--ok)", 2.2],
        ['  "official": true, "why": ["crypto"] }', "var(--ok)", 3.0],
      ];
      const line = ([t, c, delay]) => `
        <text x="42" y="0" font-family="JetBrains Mono,monospace" font-size="11" fill="${c}" opacity="0">${esc(t)}
          <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.06;0.9;1" dur="6s" begin="${delay}s" repeatCount="indefinite"/>
          <animate attributeName="y" values="${230};${118 + rows.indexOf([t, c, delay]) * 0}" dur="0.01s" fill="freeze"/></text>`;
      // place rows at fixed y for clarity
      const placed = rows.map(([t, c, delay], i) => `
        <text x="42" y="${120 + i * 26}" font-family="JetBrains Mono,monospace" font-size="11" fill="${c}" opacity="0">${esc(t)}
          <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.05;0.85;1" dur="6.5s" begin="${delay}s" repeatCount="indefinite"/></text>`).join("");
      return frame(`
        <rect x="30" y="70" width="360" height="180" rx="12" fill="#0b0f1e" stroke="var(--line)"/>
        <circle cx="48" cy="88" r="4" fill="#ff5f56"/><circle cx="62" cy="88" r="4" fill="#ffbd2e"/><circle cx="76" cy="88" r="4" fill="#27c93f"/>
        <text x="370" y="92" font-family="JetBrains Mono,monospace" font-size="10" fill="#5f6b8a" text-anchor="end">regmap api</text>
        ${placed}`);
    },
    // animated benchmark bars (Benchmarks)
    bars() {
      const vals = [0.62, 0.78, 0.71, 0.88, 0.83];
      const labels = ["TF-IDF", "BM25", "Embed", "RegMap", "RegMap+"];
      const bar = (v, i) => {
        const x = 60 + i * 62, full = 170, h = Math.round(full * v), y = 240 - h;
        return `<g>
          <rect x="${x}" y="${240 - full}" width="34" height="${full}" rx="6" fill="var(--surface)"/>
          <rect x="${x}" y="240" width="34" height="0" rx="6" fill="url(#ucg)">
            <animate attributeName="height" values="0;${h};${h};0" keyTimes="0;0.35;0.85;1" dur="5s" begin="${(i * 0.15).toFixed(2)}s" repeatCount="indefinite"/>
            <animate attributeName="y" values="240;${y};${y};240" keyTimes="0;0.35;0.85;1" dur="5s" begin="${(i * 0.15).toFixed(2)}s" repeatCount="indefinite"/></rect>
          <text x="${x + 17}" y="262" font-family="Inter,sans-serif" font-size="10" fill="var(--muted)" text-anchor="middle">${labels[i]}</text>
        </g>`;
      };
      return frame(`<line x1="48" y1="240" x2="380" y2="240" stroke="var(--line)"/>` + vals.map(bar).join("") +
        `<text x="210" y="52" font-family="Inter,sans-serif" font-size="13" font-weight="700" fill="var(--ink)" text-anchor="middle">Retrieval quality (nDCG@5)</text>`);
    },
    // a changelog timeline populating in sequence (Changelog)
    timeline() {
      const items = ["Two-pillar launch", "Bring your own framework", "Audit-ready export", "SSO + 2FA", "Coverage heatmap"];
      const row = (t, i) => {
        const y = 78 + i * 42, begin = (i * 0.5).toFixed(2);
        return `<g opacity="0"><animate attributeName="opacity" values="0;1;1" keyTimes="0;0.15;1" dur="6s" begin="${begin}s" repeatCount="indefinite"/>
          <circle cx="90" cy="${y}" r="7" fill="url(#ucg)"/>
          <rect x="112" y="${y - 10}" width="250" height="20" rx="6" fill="var(--surface)" stroke="var(--line)"/>
          <text x="124" y="${y + 4}" font-family="Inter,sans-serif" font-size="12" fill="var(--ink)">${esc(t)}</text></g>`;
      };
      return frame(`<line x1="90" y1="70" x2="90" y2="260" stroke="var(--line-2)" stroke-width="2"/>` + items.map(row).join(""));
    },
    // service status dots, all green and pulsing (Status)
    status() {
      const svc = ["Compliance engine", "Crosswalk API", "Console", "Accounts", "Exports"];
      const row = (t, i) => {
        const y = 84 + i * 40;
        return `<g>
          <rect x="60" y="${y - 16}" width="300" height="32" rx="9" fill="var(--surface)" stroke="var(--line)"/>
          <text x="80" y="${y + 4}" font-family="Inter,sans-serif" font-size="12.5" fill="var(--ink)">${esc(t)}</text>
          <text x="316" y="${y + 4}" font-family="JetBrains Mono,monospace" font-size="10" fill="var(--ok)" text-anchor="end">operational</text>
          ${pulse(340, y, 5, "var(--ok)", (i * 0.25).toFixed(2))}</g>`;
      };
      return frame(`<text x="210" y="52" font-family="Inter,sans-serif" font-size="13" font-weight="700" fill="var(--ink)" text-anchor="middle">All systems operational</text>` +
        svc.map(row).join(""));
    },
    // a shield with a scanning sweep and a check (Security / Responsible disclosure)
    shield() {
      return frame(`
        <path d="M210 66 L300 96 V176 C300 224 258 250 210 266 C162 250 120 224 120 176 V96 Z"
              fill="var(--surface)" stroke="url(#ucg)" stroke-width="2.5"/>
        <clipPath id="sh"><path d="M210 66 L300 96 V176 C300 224 258 250 210 266 C162 250 120 224 120 176 V96 Z"/></clipPath>
        <g clip-path="url(#sh)">
          <rect x="120" y="66" width="180" height="18" fill="url(#ucg2)" opacity="0.6">
            <animate attributeName="y" values="66;248;66" dur="3.2s" repeatCount="indefinite"/></rect>
        </g>
        <path d="M182 168 l20 20 l40 -44" fill="none" stroke="var(--ok)" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" opacity="0">
          <animate attributeName="opacity" values="0;0;1;1;0" keyTimes="0;0.4;0.5;0.9;1" dur="3.2s" repeatCount="indefinite"/></path>
        <text x="210" y="300" font-family="Inter,sans-serif" font-size="12" fill="var(--muted)" text-anchor="middle">Scanning. Controls verified.</text>`);
    },
    // an envelope with a paper plane flying off in a loop (Contact)
    envelope() {
      return frame(`
        <rect x="120" y="110" width="180" height="120" rx="12" fill="var(--surface)" stroke="var(--line)"/>
        <path d="M120 122 L210 180 L300 122" fill="none" stroke="var(--line-2)" stroke-width="2"/>
        <g>
          <path d="M0 0 L26 10 L6 14 L2 26 Z" fill="url(#ucg)" transform="translate(196,150)">
            <animateTransform attributeName="transform" type="translate"
              values="196,150; 300,70; 360,30" keyTimes="0;0.7;1" dur="3s" repeatCount="indefinite"/>
            <animate attributeName="opacity" values="1;1;0" keyTimes="0;0.7;1" dur="3s" repeatCount="indefinite"/>
          </path>
        </g>
        <text x="210" y="270" font-family="Inter,sans-serif" font-size="12" fill="var(--muted)" text-anchor="middle">We usually reply within one business day</text>`);
    },
    // a legal document with check marks ticking in sequence (Privacy/Terms/Cookies/Licensing)
    legal(cy) {
      const clauses = cy || ["Clear language", "Your data, your control", "No dark patterns", "Reviewed regularly"];
      const row = (t, i) => {
        const y = 100 + i * 38, begin = (i * 0.6).toFixed(2);
        return `<g>
          <rect x="150" y="${y - 14}" width="180" height="10" rx="5" fill="var(--line-2)"/>
          <circle cx="132" cy="${y - 9}" r="9" fill="none" stroke="var(--ok)" stroke-width="2"/>
          <path d="M127 ${y - 9} l4 4 l7 -8" fill="none" stroke="var(--ok)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" opacity="0">
            <animate attributeName="opacity" values="0;0;1;1" keyTimes="0;0.2;0.35;1" dur="5s" begin="${begin}s" repeatCount="indefinite"/></path>
          <text x="150" y="${y + 14}" font-family="Inter,sans-serif" font-size="11" fill="var(--muted)">${esc(t)}</text></g>`;
      };
      return frame(`
        <rect x="110" y="60" width="240" height="210" rx="12" fill="var(--surface)" stroke="var(--line)"/>
        <rect x="132" y="76" width="120" height="12" rx="6" fill="url(#ucg)"/>
        ${clauses.map(row).join("")}`);
    },
    // a persona with flows into a framework grid (Solutions segments)
    segment(cy) {
      const who = (cy && cy[0]) || "Your team";
      const cells = [];
      for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) {
        const i = r * 3 + c, x = 250 + c * 40, y = 96 + r * 44;
        cells.push(`<rect x="${x}" y="${y}" width="32" height="34" rx="6" fill="var(--surface)" stroke="var(--line)">
          <animate attributeName="stroke" values="var(--line);var(--accent);var(--line)" dur="4s" begin="${(i * 0.3).toFixed(2)}s" repeatCount="indefinite"/></rect>
          ${pulse(x + 16, y + 17, 3, "var(--accent)", (i * 0.3).toFixed(2))}`);
      }
      return frame(`
        <circle cx="110" cy="160" r="34" fill="url(#ucg)"/>
        <text x="110" y="165" font-family="Inter,sans-serif" font-size="11" font-weight="700" fill="#fff" text-anchor="middle">${esc(who)}</text>
        <path d="M150 160 H235" stroke="url(#ucg2)" stroke-width="2" stroke-dasharray="6 6">
          <animate attributeName="stroke-dashoffset" values="24;0" dur="1s" repeatCount="indefinite"/></path>
        ${cells.join("")}
        <text x="290" y="250" font-family="Inter,sans-serif" font-size="11" fill="var(--muted)" text-anchor="middle">Every framework, covered</text>`);
    },
    generic() {
      return frame(`
        ${pulse(210, 150, 40, "url(#ucg)", 0)}
        <text x="210" y="230" font-family="Inter,sans-serif" font-size="13" fill="var(--muted)" text-anchor="middle">Building something great</text>`);
    },
  };

  // ---- render --------------------------------------------------------------
  const cyc = d.cycle ? d.cycle.split("|").filter(Boolean) : null;
  const sceneFn = SCENES[d.scene] || SCENES.generic;
  const art = sceneFn(cyc);
  const bullets = (d.bullets || "").split("|").filter(Boolean);
  const more = (d.more || "").split("|").map(s => s.trim()).filter(Boolean).map(s => {
    const [label, href, desc] = s.split("::");
    return `<a href="${esc(href)}"><b>${esc(label)}</b><span>${esc(desc || "")}</span></a>`;
  }).join("");

  const host = document.getElementById("uc");
  if (!host) return;
  host.className = "section pad bleed uc-hero";
  host.innerHTML = `
    <div class="uc-grid">
      <div class="uc-copy">
        <div class="eyebrow">${esc(d.eyebrow || "RegMap")}</div>
        <span class="uc-badge"><span class="uc-dot"></span>Page under construction</span>
        <h1>${esc(d.title || "Coming soon")}</h1>
        <p class="uc-blurb">${esc(d.blurb || "")}</p>
        ${bullets.length ? `<ul class="uc-list">${bullets.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
        <div class="uc-cta">
          <a class="btn primary" href="/">Back to home</a>
          <a class="btn ghost" href="/compliance.html">Open the compliance engine</a>
        </div>
        <p class="uc-note">This page is still being built. The preview beside it loops through what the finished page will show.</p>
        ${more ? `<div class="uc-more">${more}</div>` : ""}
      </div>
      <div class="uc-art">
        ${art}
        <div class="uc-cap">${esc(d.caption || "live preview")}</div>
      </div>
    </div>`;
})();
