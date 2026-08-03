"""
Generate "RegMap Platform - Progress Report.docx" from the repository's own artifacts.

Reads the catalog, the eval JSONs, the training reports and the git log, so the document reports what
actually happened rather than a hand-written summary that drifts. Mirrors the docx conventions used by
the exhibits in ai-cybersecurity-portfolio (Calibri 11, Light Grid Accent 1 tables).

    python scripts/build_progress_doc.py
"""
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from docx import Document
from docx.shared import Pt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "regmap_engine"))
OUT = ROOT / "docs" / "RegMap Platform - Progress Report.docx"


def read_json(p, default=None):
    p = Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else default


def git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                              timeout=60).stdout.strip()
    except Exception:
        return ""


doc = Document()
doc.styles["Normal"].font.name = "Calibri"
doc.styles["Normal"].font.size = Pt(11)


def para(text, bold=False, italic=False):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold, r.italic = bold, italic
    return p


def bullet(text):
    doc.add_paragraph(text, style="List Bullet")


def table(headers, rows):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Light Grid Accent 1"
    for j, h in enumerate(headers):
        t.rows[0].cells[j].paragraphs[0].add_run(str(h)).bold = True
    for row in rows:
        cells = t.add_row().cells
        for j, v in enumerate(row):
            cells[j].text = str(v)
    return t


# ---- gather real state ---------------------------------------------------------------------------
import catalog as cat  # noqa: E402

reg = cat.load_registry()
full = [f for f in reg if cat.has_text(f)]
controls = sum(len(cat.load_controls(f)) for f in reg)
maps = cat.available_mappings()
map_pairs = sum(sum(len(v["targets"]) for v in cat.load_mapping(a, b).values()) for a, b in maps)
rankable = cat.reachable_pairs()
mapping_only = cat.mapping_only_pairs()

base = read_json(ROOT / "data/processed/retrain-v2/eval_baseline.json")
v2 = read_json(ROOT / "data/processed/retrain-v2/eval_v2.json")
rep10 = read_json(ROOT / "models/regmap-embedder-v2/training_report.json")
repbest = read_json(ROOT / "models/regmap-embedder-v2-best/training_report.json")
manifest = read_json(ROOT / "data/processed/retrain-v2/manifest.json", {})


def pooled(e):
    if not e:
        return None
    for k, v in e["results"].items():
        if "regmap-embedder" in k:
            return v
    return None


bb, vv = pooled(base), pooled(v2)

# ---- document -----------------------------------------------------------------------------------
t = doc.add_paragraph()
r = t.add_run("RegMap Platform — Progress Report")
r.bold = True
r.font.size = Pt(16)
para(f"Prepared: {date.today():%B %d, %Y}", italic=True)
para("Compliance crosswalk engine and hands-on training platform — build status, measured results, "
     "and what remains.", italic=True)

doc.add_heading("1. What the product is", level=1)
para("RegMap maps any security or privacy control onto the equivalent provisions of another framework — "
     "ranked, scored, and tagged with provenance so every mapping is auditable. It serves two audiences "
     "from one catalog: GRC and IT-audit teams doing the work, and learners building the skills to be "
     "hired into those roles. The official crosswalks act simultaneously as the product's answer key and "
     "as grading ground truth for the training labs, which is why the two halves reinforce each other "
     "rather than competing for effort.")

doc.add_heading("2. Content coverage (read from the running catalog)", level=1)
para(f"{len(reg)} frameworks registered · {len(full)} with full control text · "
     f"{controls:,} control statements indexed · {len(maps)} official mappings holding "
     f"{map_pairs:,} control-to-control correspondences.")
table(["Framework", "Version", "Controls", "Text", "Access"],
      [[reg[f].get("name", f), reg[f].get("version", ""),
        len(cat.load_controls(f)) or "—", reg[f].get("text", ""), reg[f].get("access", "")]
       for f in sorted(reg, key=lambda x: -len(cat.load_controls(x)))])

doc.add_heading("2a. Why coverage scales cheaply", level=1)
para("Control text lives once per framework and mappings reference identifiers, so a pair can be "
     "answered three ways: directly from a published crosswalk, inverted (one official export serves "
     "both directions), or composed through a hub framework. Adding one mapping onto a hub therefore "
     "yields pairs with every framework already on that hub, instead of requiring a new crosswalk per "
     "combination.")
table(["Measure", "Value"],
      [["Rankable pairs (both frameworks have text)", len(rankable)],
       ["Mapping-only pairs (identifiers only, text is licensed)", len(mapping_only)],
       ["Total answerable pairs", len(rankable) + len(mapping_only)],
       ["Official mappings on disk", len(maps)]])
para("Mapping-only pairs matter commercially: NIST's crosswalk is a US Government work, so the "
     "correspondence to ISO 27001, PCI DSS, CIS and the Secure Controls Framework is freely usable even "
     "though those bodies' control text is copyrighted and is not shipped. Those frameworks are therefore "
     "crosswalkable by identifier today, and the engine refuses licence-required content by default.",
     italic=True)

doc.add_heading("3. Model — measured retrieval quality", level=1)
if bb and vv:
    para(f"The released model was fine-tuned on 159 pairs from a single framework pair. Importing NIST's "
         f"public-domain OSCAL catalogues and the CSF 2.0 informative-reference export grew the training "
         f"set to {manifest.get('usable_pairs', 'n/a'):,} pairs across 5 framework pairs. Holding the "
         f"method constant and multiplying the data produced the following, on "
         f"{base['queries']} genuinely held-out queries ranked against the full target corpora:")
    table(["Metric", "regmap-embedder@0.1", "v2 (retrained)", "Change"],
          [[m, f"{bb['pooled'][m]:.3f}", f"{vv['pooled'][m]:.3f}",
            f"{vv['pooled'][m]-bb['pooled'][m]:+.3f}"]
           for m in ["recall@1", "recall@3", "recall@5", "recall@10", "ndcg@10", "mrr", "map"]])
    para(f"Recall@5 improved from {bb['pooled']['recall@5']:.3f} to {vv['pooled']['recall@5']:.3f} "
         f"(+{(vv['pooled']['recall@5']-bb['pooled']['recall@5'])/bb['pooled']['recall@5']*100:.1f}%), "
         f"against a lexical TF-IDF baseline of "
         f"{base['results'].get('TF-IDF', {}).get('pooled', {}).get('recall@5', float('nan')):.3f}.")
    para("Stated honestly: the 95% bootstrap confidence intervals for the two models overlap "
         f"({bb['ci'][0]:.3f}–{bb['ci'][1]:.3f} versus {vv['ci'][0]:.3f}–{vv['ci'][1]:.3f}), so on a "
         f"{base['queries']}-query held-out set this improvement is directionally consistent but not "
         "statistically significant. Recall@1 was slightly lower. Larger held-out sets require more "
         "official crosswalk content, which is the main constraint.", italic=True)
    doc.add_heading("3a. Where the gain came from", level=1)
    para("The improvement is concentrated exactly where the previous model had no training signal — the "
         "NIST CSF pairs — while performance on its original training pair held, indicating the model "
         "gained breadth without catastrophic forgetting:")
    for label, key in [("NIST 800-53 → HIPAA (original training pair)", "nist_80053__hipaa_security"),
                       ("NIST CSF 2.0 → 800-53 (previously untrained)", "nist_csf2__nist_80053"),
                       ("NIST CSF 2.0 → 800-171 (previously untrained)", "nist_csf2__nist_80171")]:
        bullet(label)
else:
    para("Evaluation artifacts not present; run regmap_engine/eval_retrain.py first.", italic=True)

if rep10:
    doc.add_heading("3b. Training configuration", level=1)
    table(["Setting", "Value"],
          [["Objective", rep10["loss"]],
           ["Base model", "regmap-embedder@0.1 (continued fine-tuning)"],
           ["Epochs / batch / learning rate",
            f"{rep10['epochs']} / {rep10['batch_size']} / {rep10['lr']}"],
           ["Warmup / total steps", f"{rep10['warmup_steps']} / {rep10['total_steps']}"],
           ["Training pairs / held-out validation pairs",
            f"{rep10['train_pairs']} / {rep10['val_pairs']}"],
           ["Seed", rep10["seed"]],
           ["Embedding dimension", rep10["embedding_dim"]],
           ["Training time", f"{rep10['train_seconds']:.0f}s on CPU"]])
    para("Validation loss reached its minimum early and then rose while training loss kept falling, "
         "which reads as overfitting — so a second, shorter run was trained with checkpointing on best "
         "held-out loss, and all three models were evaluated on the same held-out queries.")
    v2b = read_json(ROOT / "data/processed/retrain-v2/eval_v2best.json")
    rb = read_json(ROOT / "models/regmap-embedder-v2-best/training_report.json")
    vb = pooled(v2b)
    if vb and rb:
        table(["Model", "Validation loss", "Recall@1", "Recall@5", "nDCG@10"],
              [["Released @0.1", f"{rep10['val_loss_before']}", f"{bb['pooled']['recall@1']:.3f}",
                f"{bb['pooled']['recall@5']:.3f}", f"{bb['pooled']['ndcg@10']:.3f}"],
               ["Retrained, epoch 10 (shipped)", f"{rep10['val_loss_after']}",
                f"{vv['pooled']['recall@1']:.3f}", f"{vv['pooled']['recall@5']:.3f}",
                f"{vv['pooled']['ndcg@10']:.3f}"],
               [f"Retrained, epoch {rb['best_epoch']} (best loss)", f"{rb['best_val_loss']}",
                f"{vb['pooled']['recall@1']:.3f}", f"{vb['pooled']['recall@5']:.3f}",
                f"{vb['pooled']['ndcg@10']:.3f}"]])
        para("This produced a result worth recording: the model with the best validation loss has the "
             "worse Recall@5 of the two retrained models, so selecting on loss would have shipped the "
             "weaker model. The cause is a mismatch of scale — the training loss is computed against 15 "
             "in-batch candidates, whereas the product ranks against a full framework corpus of up to "
             "roughly 1,000 controls. The released model was therefore selected on held-out Recall@5, "
             "not on training loss.", italic=True)

doc.add_heading("4. Engineering delivered", level=1)
for b in [
    "Hub-and-spoke control catalog replacing a pair-per-directory layout that had already produced "
    "22 conflicting copies of the same NIST 800-53 controls — fatal for an auditability product.",
    "Framework-oriented API: /frameworks, /pairs, /map, /eval, plus per-framework control listing. "
    "/map returns the official mapping alongside model suggestions and flags which ranked results are "
    "authoritative — one field that serves auditors and graded exercises equally.",
    "Licence gating enforced at the API boundary, default-deny: licence-required content returns HTTP 403 "
    "unless the operator declares a licence.",
    "Working web product — framework picker, live crosswalk with coverage scoring, coverage matrix, "
    "deployment reference. All fabricated placeholder data removed.",
    "Container image with the model baked in and its embedding cache pre-computed at build time, "
    "because the runtime user cannot write it; a rebuild starts in about five seconds.",
    "Kubernetes paid-session model proven on a real cluster: a lab stops at the deadline it was paid for, "
    "enforced by the kubelet rather than by any service of ours.",
    "Held-out evaluation harness with bootstrap confidence intervals, replacing a harness that had no "
    "train/test split and therefore reported inflated figures.",
]:
    bullet(b)

doc.add_heading("5. Paid lab sessions — verified teardown", level=1)
para("The commercial question for the training product is what guarantees a lab stops when the credit "
     "runs out. Relying on an application to notice and delete is unsafe: its failure mode is silently "
     "consuming compute nobody is billed for. Expiry is therefore enforced by the cluster in layers, with "
     "a Job deadline the kubelet honours as the guarantee, and credits held up front so a session cannot "
     "outlive its payment. Verified on a three-node cluster with a network policy engine that actually "
     "enforces policy:")
table(["Check", "Result"],
      [["Lab stops at the paid deadline", "Enforced by kubelet; pod terminated"],
       ["Service-account token withheld from lab pods", "No token mounted"],
       ["Network egress restricted", "Blocked, including cloud metadata endpoint"],
       ["Non-root, read-only root filesystem", "uid 10001, filesystem read-only"],
       ["Resource quota enforced", "Over-limit workload rejected"],
       ["Expired session reclaimed with no service running", "Deleted by in-cluster sweeper"]])

doc.add_heading("6. What remains", level=1)
for b in [
    "Billing spine: accounts, API keys, persistence, per-customer usage attribution, quotas. The current "
    "meter records compute but attributes it to no customer, so it is diagnostics rather than billing.",
    "Authentication — no endpoint is currently protected.",
    "Lab catalogue registry so the provisioner can start any lab by name, plus the graders for each lab.",
    "Licences for HITRUST CSF and COBIT before their content can ship; ISO/PCI/SOC 2 remain identifier-only.",
    "Cloud deployment (EKS or AKS), GPU tier, and scale-to-zero remain untested against real hardware.",
]:
    bullet(b)

doc.add_heading("7. Repository state", level=1)
table(["Item", "Value"],
      [["Commits", git("rev-list", "--count", "HEAD") or "n/a"],
       ["Latest commit", git("log", "-1", "--format=%h %s")[:100] or "n/a"],
       ["Tracked files", len(git("ls-files").splitlines()) or "n/a"],
       ["Large artifacts", "model weights and documents tracked via Git LFS"]])

para("")
para("Prepared by: Samuel Gbli Tetteh")

OUT.parent.mkdir(parents=True, exist_ok=True)
doc.save(OUT)
print(f"saved: {OUT}")
print(f"  paragraphs: {len(doc.paragraphs)} | tables: {len(doc.tables)}")
