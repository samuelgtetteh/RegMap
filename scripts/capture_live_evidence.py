"""
Capture live-run evidence from the running platform for the exhibit:
  * raw JSON from /decision/stats and /decision/metrics (all/identity/ics)  -> verifiable capture
  * a self-contained HTML report rendering the real numbers + timestamp      -> screenshot for Exhibit 20

Writes both into exhibits/evidence/. Run while RedMap + the event sources are up:
    venv\\Scripts\\python.exe scripts\\capture_live_evidence.py
"""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

BASE = "http://localhost:2500"
OUT = Path(__file__).resolve().parent.parent / "exhibits" / "evidence"
OUT.mkdir(parents=True, exist_ok=True)


def get(path):
    with urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read().decode())


def uptime():
    try:
        out = subprocess.run(["docker", "ps", "--format", "{{.Names}}: {{.Status}}"],
                             capture_output=True, text=True, timeout=15).stdout
        return [l for l in out.splitlines() if any(n in l for n in
                ("RedMap", "identity-event-source", "ics-event-source"))]
    except Exception:
        return []


ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
stats = get("/decision/stats")
metrics = {m: get("/decision/metrics" + ("" if m == "all" else f"?model={m}")) for m in ("all", "identity", "ics")}
ups = uptime()

raw = {"captured_at": ts, "uptime": ups, "stats": stats, "metrics": metrics}
(OUT / f"live_run_evidence_{stamp}.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")


def row(label, val):
    return f"<tr><td>{label}</td><td><b>{val}</b></td></tr>"


def mrow(m):
    d = metrics[m]
    return (f"<tr><td>{m}</td><td>{d['labeled']:,}</td><td>{d['precision']}</td><td>{d['recall']}</td>"
            f"<td>{d['specificity']}</td><td>{d['tp']:,} / {d['fp']:,} / {d['fn']:,} / {d['tn']:,}</td></tr>")


html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Live Run Evidence</title>
<style>
 body{{font:14px/1.5 system-ui,Segoe UI,Roboto,sans-serif;background:#0d1117;color:#e6edf6;margin:0}}
 .wrap{{max-width:900px;margin:0 auto;padding:26px 20px}}
 h1{{font-size:20px;margin:0 0 2px}} .sub{{color:#8aa0bd;font-size:13px}}
 table{{width:100%;border-collapse:collapse;margin:14px 0}}
 th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid #243044}}
 th{{color:#8aa0bd;font-size:11px;text-transform:uppercase;letter-spacing:.5px}}
 .big{{font-size:26px;font-weight:700}} .ok{{color:#2ecc71}}
 .card{{background:#131a26;border:1px solid #243044;border-radius:10px;padding:14px 16px;margin:12px 0}}
 code{{font-size:11px;color:#8aa0bd;white-space:pre-wrap}}
 .grid{{display:flex;gap:22px;flex-wrap:wrap}} .stat b{{font-size:22px}} .stat span{{color:#8aa0bd;font-size:11px;display:block;text-transform:uppercase}}
</style></head><body><div class="wrap">
<h1>RegMap Platform — Live Run Evidence</h1>
<div class="sub">Captured {ts} · source: the platform's own /decision/stats and /decision/metrics endpoints</div>
<div class="card"><div class="grid">
  <div class="stat"><b>{stats['verdicts']:,}</b><span>verdicts (FIFO-capped)</span></div>
  <div class="stat"><b>{stats['labeled']:,}</b><span>labelled</span></div>
  <div class="stat"><b>{stats['flagged']:,}</b><span>flagged</span></div>
  <div class="stat"><b class="ok">{metrics['all']['precision']}</b><span>overall precision</span></div>
  <div class="stat"><b class="ok">{metrics['all']['recall']}</b><span>overall recall</span></div>
</div></div>
<div class="card"><b>Continuous uptime</b>
<table><tbody>{''.join(row('', u) for u in ups) or row('uptime','(containers not detected)')}</tbody></table></div>
<div class="card"><b>Live detection metrics (from the ground-truth-labelled trail)</b>
<table><thead><tr><th>model</th><th>labelled</th><th>precision</th><th>recall</th><th>specificity</th><th>TP / FP / FN / TN</th></tr></thead>
<tbody>{mrow('all')}{mrow('identity')}{mrow('ics')}</tbody></table>
<div class="sub">by model: {json.dumps(stats.get('by_model'))}</div></div>
<details class="card"><summary class="sub">raw JSON (as returned by the API)</summary>
<code>{json.dumps({'stats':stats,'metrics':metrics}, indent=2)}</code></details>
</div></body></html>"""
(OUT / "live_run_evidence.html").write_text(html, encoding="utf-8")

print("wrote:")
print(" ", OUT / f"live_run_evidence_{stamp}.json")
print(" ", OUT / "live_run_evidence.html")
print("uptime:", ups)
print("overall precision/recall:", metrics["all"]["precision"], metrics["all"]["recall"])
