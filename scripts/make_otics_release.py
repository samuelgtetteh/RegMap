"""
Assemble a ready-to-publish OT/ICS Intrusion Detector release into dist/otics-anomaly/ and zip it.
Combines the trained autoencoder (autoencoder_hai.pth + scaler_hai.pkl + autoencoder_hai_meta.txt)
with the packaging assets (packaging/otics/) and the shared Apache-2.0 LICENSE. dist/ is git-ignored.

Run:  venv\\Scripts\\python.exe scripts\\make_otics_release.py
"""
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "packaging" / "otics"
DATA = ROOT / "data" / "processed"
LICENSE = ROOT / "packaging" / "regmap" / "LICENSE"
OUT = ROOT / "dist" / "otics-anomaly"
ZIP = ROOT / "dist" / "otics-anomaly-release.zip"

MODEL_FILES = ["autoencoder_hai.pth", "scaler_hai.pkl", "autoencoder_hai_meta.txt"]
ASSET_FILES = ["otics_score.py", "serve.py", "example.py", "requirements.txt",
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
