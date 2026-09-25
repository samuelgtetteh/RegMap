/* Shared shell for every page: injects the header/nav (with a mobile menu), the theme toggle, and
   scroll-reveal. A page opts in with <body data-page="..."> and by linking site.css + this file.
   Add an app = add one entry to NAV below + drop a new <app>.html that links these two files. */
(function () {
  const NAV = [
    { id: "home",       label: "Home",       href: "/" },
    { id: "compliance", label: "Compliance", href: "/compliance.html" },
    { id: "labs",       label: "Labs",       href: "/labs.html" },
    { id: "pricing",    label: "Pricing",    href: "/pricing.html" },
    { id: "dashboard",  label: "Console",    href: "/dashboard" },
  ];

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
       <button class="icon-btn" id="themeToggle" title="Toggle theme" aria-label="Toggle theme">◐</button>
       <a class="btn ghost sm nav-desk" href="/dashboard">Open app</a>
       <a class="btn primary sm nav-desk" href="/compliance.html">Start free</a>
       <button class="icon-btn nav-toggle" id="navToggle" aria-label="Open menu" aria-expanded="false">≡</button>
     </div>
     <div class="mobile-menu pad" id="mobileMenu" hidden>
       ${mlinks}
       <div class="m-cta">
         <a class="btn ghost sm" href="/dashboard">Open app</a>
         <a class="btn primary sm" href="/compliance.html">Start free</a>
       </div>
     </div>`;
  document.body.prepend(header);

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

  // theme toggle (mirror the OS default, then let the user override)
  const root = document.documentElement;
  document.getElementById("themeToggle").addEventListener("click", () => {
    const cur = root.getAttribute("data-theme") ||
      (matchMedia("(prefers-color-scheme:light)").matches ? "light" : "dark");
    root.setAttribute("data-theme", cur === "dark" ? "light" : "dark");
  });

  // scroll-reveal for anything with .reveal
  const io = new IntersectionObserver(es => es.forEach(e => {
    if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
  }), { threshold: 0.12 });
  const observe = () => document.querySelectorAll(".reveal:not(.in)").forEach(el => io.observe(el));
  document.addEventListener("DOMContentLoaded", observe);
  observe();
})();
