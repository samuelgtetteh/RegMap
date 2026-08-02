"""
Assemble a ready-to-publish RegMap release into dist/regmap-embedder/ and zip it.

Combines: the fine-tuned model (models/regmap-embedder) + the packaging assets
(packaging/regmap/: LICENSE, README model card, regmap_map.py, example.py, requirements.txt) +
a deduplicated HIPAA corpus generated from data/processed/labeled_pairs.csv.

The result is self-contained — a user unzips it and runs `python example.py`, or uploads the folder
to the Hugging Face Hub. dist/ is git-ignored (the model already lives in models/); this release is
reproducible by re-running this script.

Run:  venv\\Scripts\\python.exe scripts\\make_regmap_release.py
"""
import shutil
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC_MODEL = ROOT / "models" / "regmap-embedder"
ASSETS = ROOT / "packaging" / "regmap"
CORPUS_SRC = ROOT / "data" / "processed" / "labeled_pairs.csv"
OUT = ROOT / "dist" / "regmap-embedder"
ZIP = ROOT / "dist" / "regmap-embedder-release.zip"

ASSET_FILES = ["LICENSE", "README.md", "regmap_map.py", "example.py", "requirements.txt",
               "serve.py", "Dockerfile"]


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SRC_MODEL, OUT)                       # model files (config/safetensors/tokenizer/…)
    for name in ASSET_FILES:                              # overlay packaging assets (README overrides)
        shutil.copy(ASSETS / name, OUT / name)

    df = pd.read_csv(CORPUS_SRC).dropna(subset=["hipaa_text"]).drop_duplicates(subset=["hipaa_text"])
    df[["hipaa_citation", "hipaa_text"]].to_csv(OUT / "hipaa_corpus.csv", index=False)

    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(OUT.parent))

    print(f"release: {OUT}")
    print(f"  corpus provisions: {len(df)}")
    print(f"  files: {sorted(p.name for p in OUT.iterdir())}")
    print(f"  zip: {ZIP} ({ZIP.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    build()
