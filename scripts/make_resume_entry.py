"""Generate a concise, copy-ready resume entry (Word) for the AI cybersecurity project."""
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

doc = Document()
n = doc.styles["Normal"]; n.font.name = "Calibri"; n.font.size = Pt(10.5)
n.paragraph_format.space_after = Pt(2); n.paragraph_format.line_spacing = 1.0


def head(t):
    p = doc.add_paragraph(); r = p.add_run(t); r.bold = True; r.font.size = Pt(12)
    r.font.color.rgb = RGBColor(0x1F, 0x38, 0x64); p.paragraph_format.space_before = Pt(10); p.paragraph_format.space_after = Pt(4)


def note(t):
    p = doc.add_paragraph(); r = p.add_run(t); r.italic = True; r.font.size = Pt(9)
    r.font.color.rgb = RGBColor(0x66, 0x66, 0x66); return p


def titleline(left, right):
    p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(1)
    r = p.add_run(left); r.bold = True; r.font.size = Pt(11)
    tab = p.add_run("\t" + right); tab.font.size = Pt(10)
    # right-align the date via a right tab stop
    from docx.enum.text import WD_TAB_ALIGNMENT
    from docx.shared import Inches
    p.paragraph_format.tab_stops.add_tab_stop(Inches(6.5), WD_TAB_ALIGNMENT.RIGHT)
    return p


def bullet(t):
    p = doc.add_paragraph(style="List Bullet"); p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.0
    # allow simple **bold** segments
    import re
    parts = re.split(r"(\*\*.*?\*\*)", t)
    for seg in parts:
        if seg.startswith("**") and seg.endswith("**"):
            r = p.add_run(seg[2:-2]); r.bold = True
        else:
            p.add_run(seg)
    for r in p.runs:
        r.font.size = Pt(10.5)
    return p


title = doc.add_paragraph(); tr = title.add_run("Resume entry — AI Cybersecurity Research Platform")
tr.bold = True; tr.font.size = Pt(14)
note("Copy ONE option into your resume. Match your resume's tense/format. Keep only the bullets that fit "
     "your one page — the numbers are the parts recruiters scan for.")

head("Option A — full project entry (4 bullets; recommended)")
titleline("AI‑Driven Cybersecurity Research Platform — Independent Research", "2026")
bullet("Designed and built an end‑to‑end machine‑learning security platform unifying hybrid‑identity "
       "anomaly detection, OT/ICS intrusion detection, and automated **NIST SP 800‑53 → HIPAA** "
       "compliance mapping, with a real‑time record→decide→act decisioning layer and an "
       "**“assess → detect → comply”** console (network scan → CVE/KEV/EPSS → NIST controls).")
bullet("Authored **3 first‑author research papers** (two under review at ACM *Digital Threats: Research "
       "and Practice*, one at TMLR) and released **3 open, reproducible models** on Hugging Face and "
       "Docker/GHCR (Apache‑2.0).")
bullet("Fine‑tuned a semantic‑retrieval model to **Recall@5 0.74** for NIST→HIPAA crosswalking "
       "(vs. 0.50 baseline); built a LANL red‑team lateral‑movement detector at **0.96 recall @ 10% FPR**; "
       "and identified and eliminated **label leakage** that had falsely inflated an ICS detector to AUC 1.0.")
bullet("Operated a **22‑hour continuous live‑monitoring** deployment at **0.996 precision / 0.998 recall** "
       "over ~100,000 ground‑truth‑labelled events. **Stack:** Python, PyTorch, scikit‑learn, "
       "sentence‑transformers, FastAPI, Docker, nmap.")

head("Option B — condensed (2 bullets, tighter)")
titleline("AI‑Driven Cybersecurity Research Platform — Independent Research", "2026")
bullet("Built a unified ML security platform (hybrid‑identity + OT/ICS anomaly detection, automated "
       "NIST 800‑53→HIPAA compliance mapping, real‑time decisioning); authored **3 research papers** "
       "(ACM DTRAP, TMLR) and released **3 open models** (Hugging Face, Docker).")
bullet("Fine‑tuned NIST→HIPAA retrieval to **Recall@5 0.74**; LANL detector **0.96 recall @ 10% FPR**; "
       "ran a **22‑h live deployment at 0.996 precision**. Python, PyTorch, scikit‑learn, FastAPI, Docker.")

head("Option C — one line (if space is critical)")
bullet("**AI Cybersecurity Research Platform (2026):** unified ML platform for identity/OT‑ICS anomaly "
       "detection and automated NIST→HIPAA compliance mapping; 3 papers (ACM DTRAP, TMLR), 3 open models; "
       "NIST→HIPAA Recall@5 0.74, 22‑h live run at 0.996 precision. Python/PyTorch/FastAPI/Docker.")

note("Tip: if you have a “Publications” or “Projects” section elsewhere, move the 3‑papers line there and "
     "keep the platform + metrics here to avoid repetition.")

out = r"c:\Users\User\Resume_AI_Security_Project.docx"
doc.save(out); print("saved:", out)
