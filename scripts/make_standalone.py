"""
Assemble a SEPARATE, self-contained RegMap standalone folder (code + models + data +
compliance toolkit + cross-platform launcher). The output folder is fully portable:
copy it to any Windows/Linux/macOS machine and run run.cmd / run.sh.

Usage:
    venv\\Scripts\\python.exe scripts\\make_standalone.py [OUTPUT_DIR]

Default OUTPUT_DIR:  C:\\Users\\User\\regmap-standalone   (outside the repo)
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\User\regmap-standalone"
APP = os.path.join(OUT, "app")

# (source, dest) pairs mirroring what backend/Dockerfile bakes in, so app.py's
# relative ../models and ../data paths resolve exactly as they do in the image.
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".ipynb_checkpoints", "*.db", "*.db-*")

DIRS = [
    ("backend", os.path.join(APP, "backend")),
    (os.path.join("control-advisor", "scanner"), os.path.join(APP, "control-advisor", "scanner")),
    (os.path.join("models", "regmap-embedder"), os.path.join(APP, "models", "regmap-embedder")),
]
DATA_FILES = [
    "training_pairs.csv", "labeled_pairs.csv",
    "isolation_forest_model.pkl", "scaler.pkl",
    "autoencoder_hai.pth", "scaler_hai.pkl", "autoencoder_hai_meta.txt",
]
LAUNCHER_FILES = ["launcher.py", "run.cmd", "run.sh", "README.txt"]


def copy_dir(src_rel, dst):
    src = os.path.join(ROOT, src_rel)
    if not os.path.isdir(src):
        raise SystemExit("MISSING source directory: %s" % src)
    shutil.copytree(src, dst, ignore=_IGNORE, dirs_exist_ok=True)
    print("  dir   %s" % src_rel)


def main():
    if os.path.exists(OUT):
        print("clearing existing %s" % OUT)   # clear CONTENTS (keep the root — it may be open in Explorer)
        for name in os.listdir(OUT):
            p = os.path.join(OUT, name)
            try:
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
            except Exception:
                print("  (skipping locked: %s)" % name)
    os.makedirs(APP, exist_ok=True)
    print("building standalone in: %s" % OUT)

    for src_rel, dst in DIRS:
        copy_dir(src_rel, dst)

    data_dst = os.path.join(APP, "data", "processed")
    os.makedirs(data_dst, exist_ok=True)
    for f in DATA_FILES:
        src = os.path.join(ROOT, "data", "processed", f)
        if not os.path.isfile(src):
            raise SystemExit("MISSING data file: %s" % src)
        shutil.copy2(src, os.path.join(data_dst, f))
        print("  data  %s" % f)

    # requirements.txt at the root (the launcher installs from it)
    shutil.copy2(os.path.join(ROOT, "backend", "requirements.txt"),
                 os.path.join(OUT, "requirements.txt"))
    print("  file  requirements.txt")

    # launcher + wrappers + readme
    for f in LAUNCHER_FILES:
        shutil.copy2(os.path.join(ROOT, "standalone", f), os.path.join(OUT, f))
        print("  file  %s" % f)

    # size report
    total = sum(os.path.getsize(os.path.join(dp, fn))
                for dp, _, fns in os.walk(OUT) for fn in fns)
    print("\nDONE. %s  (%.0f MB)" % (OUT, total / 1e6))
    print("Run it:  Windows -> run.cmd   |   Linux/macOS -> ./run.sh")


if __name__ == "__main__":
    main()
