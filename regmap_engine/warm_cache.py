"""
Pre-compute the embedding cache for every populated framework, then exit.

Run at image build time (see docker/Dockerfile). Without this, every container start re-encodes the
whole catalog before it can serve.

Measured on this machine (CPU, 1,441 controls across 5 frameworks): ~27 s cold vs ~9 s warm, and the
warm figure is almost entirely loading the model itself. So the cache saves roughly 17 s per start —
worth having for k8s rollout and scale-up latency, and it grows with the catalog, but it is seconds
rather than the minutes an earlier estimate suggested.

It has to happen at build time specifically, because the container runs as a non-root user while /app
is root-owned: a running container cannot write the cache at all, so it would silently re-encode on
every single boot.

    python warm_cache.py
"""
import sys

import catalog as cat
import serve


def main():
    if not serve._load_model():
        print("[warm] no embedder available — nothing to cache (the engine will serve TF-IDF)")
        return 0

    reg = cat.load_registry()
    populated = [fid for fid, f in reg.items() if f.get("controls")]
    if not populated:
        print("[warm] no framework catalogs are populated — nothing to cache")
        return 0

    total = 0
    for fid in populated:
        controls = cat.load_controls(fid)
        ids, mat, how = serve._embed_framework(fid, controls)
        total += len(ids)
        print(f"[warm] {fid:<16} {len(ids):>5} controls  {mat.shape}  {how}")

    files = sorted(p.name for p in serve.EMB_CACHE.glob("*.npz")) \
        if serve.EMB_CACHE.is_dir() else []
    if not files:
        print("[warm] FAILED: no cache files written", file=sys.stderr)
        return 1
    print(f"[warm] cached {total} embeddings across {len(files)} frameworks in {serve.EMB_CACHE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
