/* Shared shell for every page: injects the header/nav, wires the theme toggle and scroll-reveal.
   A page opts in with <body data-page="home"> and by linking site.css + this file. Add a new app =
   add one entry to NAV below + drop a new <app>.html that links these two files. */
(function () {
  // The site's pages. Add an app here and it appears in the nav on every page.
  const NAV = [
    { id: "home",       label: "Home",       href: "/" },
    { id: "dashboard",  label: "Dashboard",  href: "/dashboard" },      // the existing live app
    { id: "labs",       label: "Labs",       href: "/labs.html" },
    { id: "compliance", label: "Compliance", href: "/compliance.html" },
    { id: "pricing",    label: "Pricing",    href: "/pricing.html" },
  ];

  const page = document.body.dataset.page || "";
  const links = NAV.map(n =>
    `<a href="${n.href}"${n.id === page ? ' class="active"' : ""}>${n.label}</a>`).join("");

  const header = document.createElement("header");
  header.className = "site-header";
  header.innerHTML =
    `<div class="site-nav pad">
       <a class="brand" href="/"><span class="logo"></span>RegMap</a>
       <nav class="nav-links">${links}</nav>
       <span class="nav-sp"></span>
       <button class="icon-btn" id="themeToggle" title="Toggle theme" aria-label="Toggle theme">◐</button>
       <a class="btn ghost sm" href="/dashboard">Open app</a>
       <a class="btn primary sm" href="#start">Start free</a>
     </div>`;
  document.body.prepend(header);

  // theme toggle (mirrors the OS default, then lets the user override)
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
