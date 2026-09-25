"""
Assemble a ready-to-publish Identity Anomaly Detector release into dist/identity-anomaly/ and zip it.
Combines the trained model (isolation_forest_model.pkl + scaler.pkl) with the packaging assets
(packaging/identity/) and the shared Apache-2.0 LICENSE. dist/ is git-ignored; reproducible.

Run:  venv\\Scripts\\python.exe scripts\\make_identity_release.py
"""
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "packaging" / "identity"
DATA = ROOT / "data" / "processed"
LICENSE = ROOT / "packaging" / "regmap" / "LICENSE"
OUT = ROOT / "dist" / "identity-anomaly"
ZIP = ROOT / "dist" / "identity-anomaly-release.zip"

MODEL_FILES = ["isolation_forest_model.pkl", "scaler.pkl"]
ASSET_FILES = ["identity_score.py", "serve.py", "example.py", "requirements.txt",
               "README.md", "Dockerfile"]


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    for f in MODEL_FILES:
        shutil.copy(DATA / f, OUT / f)
    for f in ASSET_FILES:
        shutil.copy(ASSETS / f, OUT / f)
    shutil.copy(LICENSE, OUT / "LICENSE")
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(OUT.parent))
    print(f"release: {OUT}")
    print(f"  files: {sorted(p.name for p in OUT.iterdir())}")
    print(f"  zip: {ZIP} ({ZIP.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    build()
