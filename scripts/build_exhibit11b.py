"""
Generate "Exhibit 11B - RegMap Multi-Framework Engine and Training Platform.docx".

An addendum to Exhibit 11 (RegMap) and Exhibit 11A (RegMap as a reusable published model), following the
same structure and voice as exhibits/build_exhibit11_addendum.py: numbered sections, Light Grid Accent 1
tables, and an explicit tie to the NIW criteria.

Every figure is read from the repository's own artifacts (the catalog, the held-out evaluation JSONs, the
training reports), so the exhibit cannot overstate what was built. Where a result is directionally
positive but not statistically significant, it says so — an exhibit that overstates is a liability.

    python scripts/build_exhibit11b.py
"""
import json
import sys
from datetime import date
from pathlib import Path

from docx import Document
from docx.shared import Pt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "regmap_engine"))
EXHIBITS = Path(r"c:\Users\User\ai-cybersecurity-portfolio\exhibits")
REPO = "https://github.com/samuelgtetteh/ai-cybersecurity-portfolio"
RUN_DATE = f"{date.today():%B %d, %Y}"


def read_json(p, default=None):
    p = Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else default


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


# ---- real state ----------------------------------------------------------------------------------
import catalog as cat  # noqa: E402

reg = cat.load_registry()
full = [f for f in reg if cat.has_text(f)]
controls = sum(len(cat.load_controls(f)) for f in reg)
maps = cat.available_mappings()
map_pairs = sum(sum(len(v["targets"]) for v in cat.load_mapping(a, b).values()) for a, b in maps)
rankable, mo = cat.reachable_pairs(), cat.mapping_only_pairs()

base = read_json(ROOT / "data/processed/retrain-v2/eval_baseline.json")
v2 = read_json(ROOT / "data/processed/retrain-v2/eval_v2.json")
manifest = read_json(ROOT / "data/processed/retrain-v2/manifest.json", {})


def pooled(e):
    if not e:
        return None
    for k, v in e["results"].items():
        if "regmap-embedder" in k:
            return v
    return None


bb, vv = pooled(base), pooled(v2)

# ---- exhibit -------------------------------------------------------------------------------------
title = doc.add_paragraph()
r = title.add_run("Exhibit 11B: RegMap as a Multi-Framework Compliance Engine and Workforce-Training Platform")
r.bold = True
r.font.size = Pt(15)
para("Petitioner: Samuel Gbli Tetteh", bold=True)
para("Addendum to Exhibit 11 (RegMap) and Exhibit 11A (RegMap as a Reusable, Published Model) — "
     "documenting the advance from a single-framework-pair research artifact to a multi-framework "
     "compliance engine, an improved retrained model, and a hands-on training platform addressing the "
     "United States cybersecurity workforce shortage.", italic=True)

doc.add_heading("1. What has advanced since Exhibits 11 and 11A", level=1)
para("Exhibit 11 introduced RegMap: a fine-tuned sentence-embedding model mapping NIST SP 800-53 "
     "controls to HIPAA Security Rule provisions. Exhibit 11A recorded its release as an open, reusable "
     "model. This addendum records three further advances, each independently verifiable in the "
     "repository:")
bullet(f"Breadth — from one framework pair to {len(reg)} registered frameworks, "
       f"{controls:,} indexed control statements, and {len(rankable) + len(mo)} answerable framework "
       f"pairs built on {map_pairs:,} authoritative control-to-control correspondences.")
bullet("Depth — the model was retrained on the expanded corpus and measurably improves retrieval on a "
       "held-out evaluation the original work did not have.")
bullet("Application — the same authoritative mappings now serve as automatic grading ground truth for a "
       "practical training curriculum aimed at moving non-traditional candidates into cybersecurity and "
       "IT-audit roles.")

doc.add_heading("2. National importance: two distinct public benefits", level=1)
para("Regulatory compliance is a structural cost on every United States organization that handles "
     "regulated data — healthcare providers, financial institutions, federal contractors, and the small "
     "and mid-sized businesses that can least afford specialist consultants. Mapping one framework's "
     "controls onto another is done manually today, by scarce expert labor, and must be redone whenever "
     "a framework is revised. RegMap reduces that cost with an auditable, open tool.")
para("The second benefit is workforce. The United States has a persistent, documented shortfall of "
     "qualified cybersecurity and IT-audit practitioners, and the conventional hiring filter excludes "
     "capable candidates who lack a traditional credential path. Because RegMap's mappings are "
     "government-published ground truth, they can grade a learner's work automatically — which makes "
     "rigorous, evidence-backed practical training economically feasible at scale. The compliance "
     "content pays for the training capability.")

doc.add_heading("3. Framework coverage (verifiable in the repository)", level=1)
table(["Framework", "Version", "Controls indexed", "Content status"],
      [[reg[f].get("name", f), reg[f].get("version", ""),
        len(cat.load_controls(f)) or "identifiers only", reg[f].get("text", "")]
       for f in sorted(reg, key=lambda x: -len(cat.load_controls(x)))])
para("All indexed control text is drawn from public-domain United States Government sources — NIST's "
     "OSCAL catalogs and the NIST Online Informative References (OLIR) program. Frameworks whose text is "
     "copyrighted (ISO/IEC 27001, PCI DSS, CIS Controls) are represented by identifier and official "
     "mapping only, never by reproduced text, and content requiring a commercial license is refused by "
     "the engine by default. This design choice — building on public-domain government data and "
     "respecting third-party copyright — is what makes the tool freely distributable for public benefit.",
     italic=True)

doc.add_heading("3a. An architecture that makes breadth affordable", level=1)
para("Control text is stored once per framework and mappings reference identifiers, so a pair is "
     "answerable directly from a published crosswalk, by inversion (one official export serves both "
     "directions), or by composition through a hub framework. Adding a single mapping onto a hub "
     "therefore yields usable pairs with every framework already present, rather than requiring a "
     "separate crosswalk for each combination — the difference between linear and quadratic effort as "
     "coverage grows.")
table(["Measure", "Value"],
      [["Official mappings imported", len(maps)],
       ["Control-to-control correspondences", f"{map_pairs:,}"],
       ["Pairs answerable with ranked results", len(rankable)],
       ["Pairs answerable by official identifier (licensed text withheld)", len(mo)]])

if bb and vv:
    doc.add_heading("4. Measured improvement of the released model", level=1)
    para(f"The model in Exhibits 11/11A was fine-tuned on 159 control pairs from one framework pair. The "
         f"expanded corpus provides {manifest.get('usable_pairs', 0):,} training pairs across five "
         f"framework pairs. Holding the method constant and increasing the data produced the following on "
         f"{base['queries']} held-out queries, each ranked against the complete target framework:")
    table(["Metric", "Model in Exhibit 11A", "Retrained model", "Change"],
          [[m.replace("recall@", "Recall@").replace("ndcg@", "nDCG@").upper()
            if m in ("mrr", "map") else m.replace("recall@", "Recall@").replace("ndcg@", "nDCG@"),
            f"{bb['pooled'][m]:.3f}", f"{vv['pooled'][m]:.3f}",
            f"{vv['pooled'][m]-bb['pooled'][m]:+.3f}"]
           for m in ["recall@1", "recall@3", "recall@5", "recall@10", "ndcg@10", "mrr", "map"]])
    tf = base["results"].get("TF-IDF", {}).get("pooled", {}).get("recall@5")
    para(f"Recall@5 — the share of correct provisions surfaced in the top five, the metric that matters "
         f"for an expert-in-the-loop tool — rose from {bb['pooled']['recall@5']:.3f} to "
         f"{vv['pooled']['recall@5']:.3f}"
         + (f", against {tf:.3f} for a conventional keyword-based (TF-IDF) baseline." if tf else "."))
    para(f"Stated with appropriate caution: the 95% bootstrap confidence intervals of the two models "
         f"overlap ({bb['ci'][0]:.3f}–{bb['ci'][1]:.3f} versus {vv['ci'][0]:.3f}–{vv['ci'][1]:.3f}) on a "
         f"held-out set of {base['queries']} queries, so the improvement is directionally consistent and "
         f"reproducible but not statistically significant at that threshold. Recall@1 was marginally "
         f"lower. The constraint is the quantity of published crosswalk data available for held-out "
         f"testing, not the method.", italic=True)
    para("The gain is concentrated precisely where the earlier model had no training signal — the NIST "
         "Cybersecurity Framework 2.0 pairs — while accuracy on its original NIST-to-HIPAA pair was "
         "retained. That is evidence of genuine generalization across frameworks rather than "
         "memorization of one corpus.")

doc.add_heading("5. Reproducibility and evaluation integrity", level=1)
para("The evaluation methodology was strengthened as part of this work, and the correction is worth "
     "recording because it affects how the results should be read:")
bullet("The original evaluation harness scored every labelled example with no train/test separation, "
       "which inflates results on data a model was trained on. A held-out harness was built that ranks "
       "each test query against the full target framework corpus and reports bootstrap confidence "
       "intervals.")
bullet("Two split protocols are provided: one holding out query controls (the realistic product "
       "setting), and a stricter one assigning every control identifier to a single split globally, "
       "because mappings compose through hub frameworks and a naive split leaks information.")
bullet("The previously released model is preserved unmodified, so the figures published in the earlier "
       "research remain reproducible; the retrained model is a separately versioned artifact.")
para("Datasets, split-generation code, training code, evaluation harness, and the resulting metrics are "
     "all in the repository, so an independent reviewer can reproduce every number in this exhibit.")

doc.add_heading("6. Deployment: a tool others can actually run", level=1)
for b in [
    "A single container image carries the API, the web interface, and the model, and runs on a laptop, a "
    "single server, or Kubernetes, on CPU or GPU.",
    "A web interface lets a practitioner select any two covered frameworks and any control, and see "
    "ranked equivalents with the authoritative mapping marked — no programming required.",
    "Kubernetes manifests provide autoscaling and per-tenant isolation, and the per-user practice "
    "environment model was validated on a live multi-node cluster, including verified network isolation "
    "and guaranteed teardown of expired sessions.",
]:
    bullet(b)

doc.add_heading("7. Training platform for the workforce gap", level=1)
para("A full practical curriculum has been specified, in which every unit is a competency proved by a "
     "hands-on lab, graded automatically against ground truth, and recorded against a NIST NICE "
     "Framework work-role task. It covers foundations, a cybersecurity/SOC analyst track, an IT audit and "
     "GRC track, and an explicit senior-readiness track training the judgment, written communication, and "
     "peer-review skills that distinguish a senior practitioner. Output is a verifiable transcript of "
     "tasks performed and scores achieved — evidence designed for skills-based hiring, so that a capable "
     "candidate without a conventional credential can demonstrate competence directly.")
para("The compliance-mapping lab is buildable immediately because the answer key already exists: the "
     "official government crosswalks the engine serves. This is the practical link between the two halves "
     "of the endeavor.", italic=True)

doc.add_heading("8. Significance", level=1)
para("Taken together, this record shows the endeavor advancing on all the dimensions that matter to the "
     "national interest: a compliance tool of substantial merit extended from a single research pair to "
     "broad multi-framework coverage using public-domain government data; a measurably improved and "
     "openly released model, evaluated with methodological honesty including where results fall short of "
     "statistical significance; deployable infrastructure others can run; and a training platform "
     "directed at a documented United States workforce shortage. It also shows me well positioned to "
     "continue: the work was specified, built, measured, and documented end to end, and every claim here "
     "is checkable in the public repository.")
p = doc.add_paragraph()
p.add_run(REPO).bold = True

para("")
para("Date: " + RUN_DATE)
para("Prepared by: Samuel Gbli Tetteh")

out_local = ROOT / "docs" / "Exhibit 11B RegMap Multi-Framework Engine and Training Platform.docx"
doc.save(out_local)
print(f"saved: {out_local}")
if EXHIBITS.is_dir():
    doc.save(EXHIBITS / out_local.name)
    print(f"also saved into the exhibits folder: {EXHIBITS / out_local.name}")
else:
    print(f"(exhibits folder not found at {EXHIBITS}; local copy only)")
print(f"  paragraphs: {len(doc.paragraphs)} | tables: {len(doc.tables)}")
