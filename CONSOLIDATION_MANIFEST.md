# RegMap Platform: consolidation manifest

Date: 2026-09-25

This file records the consolidation that brought the full RegMap build into this
folder so that `regmap-platform` can become the single home for the complete
business. Everything here was **copied** from the main research repo
(`ai-cybersecurity-portfolio`). Nothing was moved or deleted, and no existing file
in this folder was overwritten (the copy used no-clobber, so any file that already
existed here was left exactly as it was).

## What this folder already had (the engine product)
- `regmap_engine/` the crosswalk engine: API (`/map`, `/eval`, `/pairs`, `/health`, `/usage`) and its own product website in `regmap_engine/web/`, plus auth, login, and paywall.
- `models/regmap-embedder` the fine-tuned crosswalk model.
- `data/processed` and `data/raw` the crosswalk training and evaluation data.
- `docker/` and `k8s/` under `regmap_engine/`, `notebooks/`, `paper/`, and the product docs.

## What was copied in (the rest of the complete business)
- `backend/` the full platform application: `app.py` (the `/map` endpoint plus the Monitor and Assess console), `dashboard/`, `securescan/`, `advisor_api.py`, the event simulators, and the `Dockerfile` that builds the full-platform image.
- `web/` the platform and training landing site (the "Prove you can do the job" site served at port 2500). Note: this is a **different** site from `regmap_engine/web/`, which is the engine product site. Both now live here.
- `control-advisor/` the scanner and advisor toolkit that `backend/advisor_api.py` imports.
- `auth_service/` the standalone login and registration proxy (source only; the live `auth.sqlite3` credentials database was intentionally not copied).
- `business_plan/` the angel and pre-seed package (markdown plus Word versions).
- `tests/` the test suite.
- Additional `docs/` (design system, training curriculum, roadmaps, and more) and additional `notebooks/`, merged without overwriting anything.
- `paper/regmap/front1_security_reframe/` and `paper/regmap/front2_regtech_pivot/` the two reframed paper versions with their built PDFs, plus `RESUBMISSION_TWO_FRONTS.md`.

## What was intentionally NOT copied (and why)
These are large runtime or research assets, not business essentials. They remain in the main repo and can be brought over on demand.

- **`models/qwen2.5-1.5b-instruct` (about 2.9 GB).** The local language model used only by the optional conversational compliance interview. Without it, the interview falls back to canonical questions. To bring it over:
  ```
  cp -rn /c/Users/User/ai-cybersecurity-portfolio/models/qwen2.5-1.5b-instruct /c/Users/User/regmap-platform/models/
  ```
- **`data/raw` (about 15 GB).** Research and training datasets for the anomaly models (for example HAI SWaT and LANL auth). Not needed to run the compliance product. The crosswalk data the product needs is already here in `data/processed`. To bring specific raw datasets over, copy just the subfolders you need with `cp -rn`.

## How to run the complete business from this folder
- **Crosswalk engine only:** `uvicorn serve:app --app-dir regmap_engine --host 0.0.0.0 --port 8000` then open `http://localhost:8000/`.
- **Full platform (Monitor, Assess, Labs, the screenshot landing):** build and run the image from `backend/Dockerfile` (the `regmap-api` image) and open port 2500. The backend expects `models/regmap-embedder` (present) and `data/processed` (present) relative to the repo root.

## Follow-up decisions to finish the consolidation
1. **Commit these additions in this repo** once you have reviewed them (`git add` then `git commit`). They are currently untracked.
2. **Reconcile the two entry points.** `regmap_engine/serve.py` (engine) and `backend/app.py` (full platform) both exist here now. Decide which is the canonical product runtime, or how they compose, so there is one clear way to run the business.
3. **Reconcile any model and data paths** the copied `backend/app.py` expects, so the full platform runs cleanly from this folder.
4. **Own SOC 2 and multi-tenant isolation** remain on the roadmap (see `docs/` and the business plan) before selling.

## Source of truth
The main repo `ai-cybersecurity-portfolio` was left untouched by this consolidation. These files are copies. Until you decide otherwise, edits made in one place will not appear in the other.
