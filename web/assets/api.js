/* RegMap API client, shared by every page. Thin wrapper over fetch that surfaces the engine's
   error detail instead of a bare status code, so the UI can say what actually went wrong (an
   unlicensed framework returns 403 with a reason, and the user should see that reason).

   Everything here talks to the same origin, since serve.py hosts both the API and this site. */
(function () {
  /* ---- API key ------------------------------------------------------------
     Kept for pilot customers and operators who paste a key directly. When the user has an active
     session (cookie-based auth), the key is cleared from localStorage so it does not sit there
     unnecessarily. The session cookie (HttpOnly, same-origin) is the secure path; the localStorage
     key is only the fallback for unauthenticated API access. */
  const KEY_STORE = "regmap.apiKey";
  const getKey = () => { try { return localStorage.getItem(KEY_STORE) || ""; } catch (e) { return ""; } };
  const setKey = k => { try { k ? localStorage.setItem(KEY_STORE, k.trim())
                                : localStorage.removeItem(KEY_STORE); } catch (e) {} };
  // Once a session is confirmed, remove the API key from localStorage - the cookie takes over.
  function _clearKeyIfAuthed(s) {
    if (s && s.authenticated && getKey()) { setKey(""); }
  }

  async function call(path, opts) {
    // Attach the key if we have one. Harmless when the engine runs open.
    opts = opts || {};
    // Send the session cookie. It is HttpOnly, so this is the only way the browser can authenticate -
    // script cannot read it, which is precisely why a session beats a token in localStorage.
    opts.credentials = "same-origin";
    const k = getKey();
    if (k) opts.headers = Object.assign({}, opts.headers, { Authorization: "Bearer " + k });
    let r;
    try {
      r = await fetch(path, opts);
    } catch (e) {
      throw new Error("Cannot reach the engine, is it running?");
    }
    let body = null;
    try { body = await r.json(); } catch (e) { /* non-JSON error page */ }
    if (!r.ok) {
      let detail = (body && (body.detail || body.message)) || `HTTP ${r.status}`;
      if (r.status === 401) {
        detail = getKey()
          ? "That API key was rejected, it may be revoked, or the account deactivated."
          : "This instance requires an API key. Use the key button in the header to add one.";
      } else if (r.status === 402 && detail && typeof detail === "object") {
        detail = `Monthly allowance exhausted: ${detail.used_cu} of ${detail.allowance_cu} CU used on `
               + `the ${detail.plan} plan. ${detail.remedy}.`;
      } else if (r.status === 403) {
        detail = typeof detail === "string" ? detail : "This endpoint needs an admin-scoped key.";
      } else if (r.status === 429) {
        detail = `Rate limited, ${detail}. Retry in `
               + `${r.headers.get("retry-after") || "a moment"}s.`;
      } else if (r.status === 413) {
        detail = typeof detail === "object" ? (detail.error + ", " + detail.remedy) : detail;
      }
      const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      err.status = r.status;
      err.body = body;
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
    getKey, setKey,
    hasKey:     ()             => !!getKey(),
    me:         ()             => call("/me"),
    pricing:    ()             => call("/pricing"),
    session:    ()             => call("/auth/session").then(s => { _clearKeyIfAuthed(s); return s; }),
    register:   (email, password, name) => post("/auth/register", { email, password, name }),
    login:      (email, password)       => post("/auth/login", { email, password }),
    logout:     ()             => post("/auth/logout", {}),
    createKey:  (label)        => post("/auth/keys", { label }),
    verify:        (token)     => post("/auth/verify", { token }),
    verifyResend:  ()          => post("/auth/verify/resend", {}),
    resetRequest:  (email)     => post("/auth/reset/request", { email }),
    reset:         (token, new_password) => post("/auth/reset", { token, new_password }),
    passwordChange:(current_password, new_password) => post("/auth/password", { current_password, new_password }),
    totpSetup:     ()          => post("/auth/totp/setup", {}),
    totpEnable:    (code)      => post("/auth/totp/enable", { code }),
    totpDisable:   (password)  => post("/auth/totp/disable", { password }),
    loginTotp:     (pending, code) => post("/auth/login/totp", { pending, code }),
    oauthProviders:()          => call("/auth/oauth/providers"),
    health:     ()             => call("/health"),
    frameworks: ()             => call("/frameworks"),
    pairs:      ()             => call("/pairs"),
    controls:   (fid, withText) => call(`/frameworks/${encodeURIComponent(fid)}/controls`
                                        + (withText ? "?include_text=true" : "")),
    map:        (payload)      => post("/map", payload),
    bulk:       (payload)      => post("/map/bulk", payload),
    custom:     (payload)      => post("/map/custom", payload),
    customMulti:(payload)      => post("/map/custom/multi", payload),
    remediate:  (payload)      => post("/remediate", payload),
    projects:      ()            => call("/projects"),
    projectGet:    (id)          => call("/projects/" + encodeURIComponent(id)),
    projectCreate: (payload)     => post("/projects", payload),
    projectUpdate: (id, payload) => call("/projects/" + encodeURIComponent(id),
                                    { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) }),
    projectDelete: (id)          => call("/projects/" + encodeURIComponent(id), { method: "DELETE" }),
    projectDrift:  (id)          => call("/projects/" + encodeURIComponent(id) + "/drift"),
    projectRecheck:(id)          => post("/projects/" + encodeURIComponent(id) + "/recheck", {}),
    monitorRun:    ()            => post("/monitor/run", {}),
    members:       (id)          => call("/projects/" + encodeURIComponent(id) + "/members"),
    memberAdd:     (id, payload) => post("/projects/" + encodeURIComponent(id) + "/members", payload),
    memberRemove:  (id, acct)    => call("/projects/" + encodeURIComponent(id) + "/members/" + encodeURIComponent(acct), { method: "DELETE" }),
    comments:      (id)          => call("/projects/" + encodeURIComponent(id) + "/comments"),
    commentAdd:    (id, payload) => post("/projects/" + encodeURIComponent(id) + "/comments", payload),
    activity:      (id)          => call("/projects/" + encodeURIComponent(id) + "/activity"),
    approve:       (id, payload) => post("/projects/" + encodeURIComponent(id) + "/approve", payload || {}),
    learningGet:   (key)         => call("/learning/" + encodeURIComponent(key)),
    learningPut:   (key, data)   => call("/learning/" + encodeURIComponent(key),
                                    { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ data }) }),
    transcriptPublish:(data, id) => post("/learning/transcript", { data, id }),
    transcriptGet: (id)          => call("/transcript/" + encodeURIComponent(id)),
    savedPolicies: ()            => call("/policies/saved"),
    savedPolicyGet:(id)          => call("/policies/saved/" + encodeURIComponent(id)),
    savedPolicyCreate:(payload)  => post("/policies/saved", payload),
    savedPolicyUpdate:(id, payload) => call("/policies/saved/" + encodeURIComponent(id),
                                    { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(payload) }),
    savedPolicyDelete:(id)       => call("/policies/saved/" + encodeURIComponent(id), { method: "DELETE" }),
    exercise:   (payload)      => post("/exercise", payload),
    grade:      (payload)      => post("/exercise/grade", payload),
    evaluate:   (payload)      => post("/eval", payload),

    /* Escape before interpolating control text into HTML, control statements contain quotes,
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
