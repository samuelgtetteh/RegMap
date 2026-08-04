/* RegMap API client — shared by every page. Thin wrapper over fetch that surfaces the engine's
   error detail instead of a bare status code, so the UI can say what actually went wrong (an
   unlicensed framework returns 403 with a reason, and the user should see that reason).

   Everything here talks to the same origin, since serve.py hosts both the API and this site. */
(function () {
  async function call(path, opts) {
    let r;
    try {
      r = await fetch(path, opts);
    } catch (e) {
      throw new Error("Cannot reach the engine — is it running?");
    }
    let body = null;
    try { body = await r.json(); } catch (e) { /* non-JSON error page */ }
    if (!r.ok) {
      const detail = (body && (body.detail || body.message)) || `HTTP ${r.status}`;
      const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      err.status = r.status;
      throw err;
    }
    return body;
  }

  const post = (path, payload) => call(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });

  window.RegMap = {
    health:     ()             => call("/health"),
    frameworks: ()             => call("/frameworks"),
    pairs:      ()             => call("/pairs"),
    controls:   (fid, withText) => call(`/frameworks/${encodeURIComponent(fid)}/controls`
                                        + (withText ? "?include_text=true" : "")),
    map:        (payload)      => post("/map", payload),
    bulk:       (payload)      => post("/map/bulk", payload),
    exercise:   (payload)      => post("/exercise", payload),
    grade:      (payload)      => post("/exercise/grade", payload),
    evaluate:   (payload)      => post("/eval", payload),

    /* Escape before interpolating control text into HTML — control statements contain quotes,
       ampersands and angle brackets, and this content ultimately comes from imported files. */
    esc(s) {
      return String(s == null ? "" : s).replace(/[&<>"']/g, c =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    },

    /* Route -> how much an auditor should trust it. Mirrors catalog.py's precedence. */
    routeBadge(route, authoritative) {
      if (authoritative) return { cls: "ok", label: route === "inverted" ? "official (inverted)" : "official" };
      if (route && route.startsWith("derived")) return { cls: "warn", label: route };
      return { cls: "crit", label: route || "no route" };
    },
  };
})();
