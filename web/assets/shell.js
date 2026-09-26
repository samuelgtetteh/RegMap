/* Shared shell for every page: injects the header/nav (with a mobile menu), the theme toggle, and
   scroll-reveal. A page opts in with <body data-page="..."> and by linking site.css + this file.
   Add an app = add one entry to NAV below + drop a new <app>.html that links these two files. */
(function () {
  const NAV = [
    { id: "home",       label: "Home",       href: "/" },
    { id: "compliance", label: "Compliance", href: "/compliance.html" },
    { id: "policy",     label: "Policy",     href: "/policies.html" },
    { id: "labs",       label: "RegMap University", href: "/labs.html" },
    { id: "pricing",    label: "Pricing",    href: "/pricing.html" },
    { id: "dashboard",  label: "Console",    href: "/dashboard" },
  ];

  // Ambient backlight layer (see .rm-ambient in site.css): injected once, behind everything.
  if (!document.querySelector(".rm-ambient")) {
    const amb = document.createElement("div");
    amb.className = "rm-ambient";
    amb.setAttribute("aria-hidden", "true");
    document.body.prepend(amb);
  }

  const page = document.body.dataset.page || "";
  const link = (n, cls) => `<a href="${n.href}" class="${cls}${n.id === page ? " active" : ""}">${n.label}</a>`;
  const links = NAV.map(n => link(n, "")).join("");
  const mlinks = NAV.map(n => link(n, "m-link")).join("");

  const header = document.createElement("header");
  header.className = "site-header";
  header.innerHTML =
    `<div class="site-nav pad">
       <a class="brand" href="/"><span class="logo"></span>RegMap</a>
       <nav class="nav-links">${links}</nav>
       <span class="nav-sp"></span>
       <a class="nav-desk" id="acctLink" href="/account.html" style="color:var(--muted);font-size:14px;font-weight:600;padding:0 4px">Sign in</a>
       <a class="btn ghost sm nav-desk" href="/labs.html">Learning Hub</a>
       <a class="btn primary sm nav-desk" href="/compliance.html">Start free</a>
       <button class="icon-btn" id="themeToggle" title="Toggle theme" aria-label="Toggle theme">◐</button>
       <button class="icon-btn nav-toggle" id="navToggle" aria-label="Open menu" aria-expanded="false">≡</button>
     </div>
     <div class="mobile-menu pad" id="mobileMenu" hidden>
       ${mlinks}
       <a href="/account.html" class="m-link" id="acctLinkM">Sign in</a>
       <div class="m-cta">
         <a class="btn ghost sm" href="/labs.html">Learning Hub</a>
         <a class="btn primary sm" href="/compliance.html">Start free</a>
       </div>
     </div>`;
  document.body.prepend(header);

  // Full company footer, injected once here so it is identical on every page. Any per-page <footer> is
  // removed first. Product links go to real pages; company/resources/legal are placeholders for now.
  (function buildFooter() {
    document.querySelectorAll(".site-footer").forEach(f => f.remove());
    const f = document.createElement("footer");
    f.className = "site-footer pad bleed";
    f.innerHTML =
      `<div class="footer-top">
         <div class="footer-brand">
           <a class="brand" href="/"><span class="logo"></span>RegMap</a>
           <p>Compliance automation and graded skills. Map the controls you operate onto every framework
              you must satisfy, and prove your team can do the work.</p>
           <div class="footer-social">
             <a href="https://www.linkedin.com/company/regmap" target="_blank" rel="noopener" aria-label="LinkedIn">LinkedIn</a>
             <a href="https://github.com/regmap" target="_blank" rel="noopener" aria-label="GitHub">GitHub</a>
             <a href="https://x.com/regmap" target="_blank" rel="noopener" aria-label="X">X</a>
           </div>
         </div>
         <div class="footer-col"><h4>Product</h4>
           <a href="/compliance.html">Compliance engine</a>
           <a href="/compliance.html#gaps">Coverage and gaps</a>
           <a href="/compliance.html#custom">Bring your own framework</a>
           <a href="/labs.html">Graded labs</a>
           <a href="/dashboard">Console</a>
           <a href="/pricing.html">Pricing</a>
         </div>
         <div class="footer-col"><h4>Solutions</h4>
           <a href="/compliance.html">Automate compliance</a>
           <a href="/labs.html">Prove you can do the job</a>
           <a href="/for-grc-teams.html">For GRC teams</a>
           <a href="/for-consultancies.html">For consultancies</a>
           <a href="/for-practitioners.html">For practitioners</a>
         </div>
         <div class="footer-col"><h4>Resources</h4>
           <a href="/documentation.html">Documentation</a>
           <a href="/api-reference.html">API reference</a>
           <a href="/benchmarks.html">Benchmarks</a>
           <a href="/changelog.html">Changelog</a>
           <a href="/status.html">Status</a>
         </div>
         <div class="footer-col"><h4>Company</h4>
           <a href="/about.html">About</a>
           <a href="/careers.html">Careers</a>
           <a href="/contact.html">Contact</a>
           <a href="/security.html">Security</a>
           <a href="/responsible-disclosure.html">Responsible disclosure</a>
         </div>
       </div>
       <div class="footer-bottom">
         <span>&copy; ${new Date().getFullYear()} RegMap, Inc. &middot; Prove it once. Satisfy every framework.</span>
         <span class="legal">
           <a href="/privacy.html">Privacy</a><a href="/terms.html">Terms</a><a href="/cookies.html">Cookies</a><a href="/licensing.html">Licensing</a>
         </span>
       </div>`;
    document.body.appendChild(f);
  })();

  // mobile menu toggle
  const menu = document.getElementById("mobileMenu");
  const toggle = document.getElementById("navToggle");
  const setMenu = open => {
    menu.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    toggle.textContent = open ? "×" : "≡";
  };
  toggle.addEventListener("click", () => setMenu(menu.hidden));
  menu.addEventListener("click", e => { if (e.target.closest("a")) setMenu(false); });
  addEventListener("resize", () => { if (innerWidth > 860) setMenu(false); });

  // theme toggle: remember the user's choice across pages and tabs (localStorage), falling back to the
  // OS preference until they pick one. Applied on every page load so the choice survives navigation.
  const root = document.documentElement;
  const THEME_KEY = "regmap.theme";
  const osTheme = () => (matchMedia("(prefers-color-scheme:light)").matches ? "light" : "dark");
  const storedTheme = () => { try { return localStorage.getItem(THEME_KEY); } catch (e) { return null; } };
  const applyTheme = t => root.setAttribute("data-theme", t === "light" ? "light" : "dark");
  applyTheme(storedTheme() || osTheme());
  document.getElementById("themeToggle").addEventListener("click", () => {
    const cur = root.getAttribute("data-theme") || osTheme();
    const next = cur === "dark" ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem(THEME_KEY, next); } catch (e) {}
  });
  // keep other open tabs in sync when the choice changes
  addEventListener("storage", e => { if (e.key === THEME_KEY && e.newValue) applyTheme(e.newValue); });
  // follow the OS/browser theme live, but only until the user makes an explicit choice
  const mq = matchMedia("(prefers-color-scheme:light)");
  const onOS = () => { if (!storedTheme()) applyTheme(osTheme()); };
  mq.addEventListener ? mq.addEventListener("change", onOS) : mq.addListener(onOS);

  // scroll-reveal for anything with .reveal
  const io = new IntersectionObserver(es => es.forEach(e => {
    if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
  }), { threshold: 0.12 });
  const observe = () => document.querySelectorAll(".reveal:not(.in)").forEach(el => io.observe(el));
  document.addEventListener("DOMContentLoaded", observe);
  observe();

  // Reflect sign-in state in the header: "Sign in" for guests, "Account" when signed in.
  // Also show an Admin link to a site administrator only.
  fetch("/auth/session", { credentials: "same-origin" })
    .then(r => (r.ok ? r.json() : null))
    .then(s => {
      if (!s || !s.authenticated) return;
      const a = document.getElementById("acctLink"), am = document.getElementById("acctLinkM");
      if (a) a.textContent = "Account";
      if (am) am.textContent = "Account";
      if (s.admin) {
        const nav = document.querySelector(".nav-links");
        if (nav && !document.getElementById("adminNav")) {
          const link = document.createElement("a");
          link.id = "adminNav"; link.href = "/admin.html"; link.textContent = "Admin";
          if (page === "admin") link.className = "active";
          nav.appendChild(link);
        }
      }
    })
    .catch(() => {});

  // Product analytics beacon (admin-only reporting; see docs/analytics_tracker.md). Anonymous first-party
  // visitor id; sends a pageview on load and exposes window.rmTrack(name, props) for feature events.
  (function analytics() {
    let vid = "";
    try {
      vid = localStorage.getItem("regmap.vid") || "";
      if (!vid) { vid = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(36).slice(2)); localStorage.setItem("regmap.vid", vid); }
    } catch (e) {}
    function send(events) {
      try {
        const body = JSON.stringify({ visitor_id: vid, events: events });
        if (navigator.sendBeacon) navigator.sendBeacon("/analytics/collect", new Blob([body], { type: "application/json" }));
        else fetch("/analytics/collect", { method: "POST", headers: { "content-type": "application/json" }, body: body, keepalive: true, credentials: "same-origin" });
      } catch (e) {}
    }
    window.rmTrack = (name, props) => send([{ name: name, path: location.pathname, referrer: document.referrer || "", props: props || {} }]);
    window.rmTrack("pageview", { title: document.title });
  })();
})();
