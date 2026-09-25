# Build from the repo root so this can COPY the model + data alongside the app:
#   docker build -f backend/Dockerfile -t regmap-api .
#   docker run -p 8000:8000 regmap-api
FROM python:3.11-slim

WORKDIR /app

# nmap binary powers SecureScan's optional high-fidelity engine (service/version + CPE). The
# socket engine works without it, but the image ships nmap so the richer engine is available.
RUN apt-get update && apt-get install -y --no-install-recommends nmap \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/app.py backend/app.py
COPY backend/identity_api.py backend/identity_api.py
COPY backend/ics_api.py backend/ics_api.py
COPY backend/verdict_store.py backend/verdict_store.py
COPY backend/settings.py backend/settings.py
COPY backend/decision_api.py backend/decision_api.py
COPY backend/policy.py backend/policy.py
COPY backend/actions.py backend/actions.py
COPY backend/ai_triage.py backend/ai_triage.py
COPY backend/llm_client.py backend/llm_client.py
COPY backend/scanner_api.py backend/scanner_api.py
COPY backend/securescan backend/securescan
COPY backend/advisor_api.py backend/advisor_api.py
COPY backend/agent_api.py backend/agent_api.py
COPY backend/agent backend/agent
# Compliance Advisor toolkit (imported by advisor_api; resolves data/models via ../.. = /app)
COPY control-advisor/scanner control-advisor/scanner
COPY backend/dashboard backend/dashboard
COPY web web
COPY models/regmap-embedder models/regmap-embedder
COPY data/processed/training_pairs.csv data/processed/training_pairs.csv
COPY data/processed/labeled_pairs.csv data/processed/labeled_pairs.csv
COPY data/processed/isolation_forest_model.pkl data/processed/isolation_forest_model.pkl
COPY data/processed/scaler.pkl data/processed/scaler.pkl
COPY data/processed/autoencoder_hai.pth data/processed/autoencoder_hai.pth
COPY data/processed/scaler_hai.pkl data/processed/scaler_hai.pkl
COPY data/processed/autoencoder_hai_meta.txt data/processed/autoencoder_hai_meta.txt

# Mirrors the local dev layout (repo_root/backend, repo_root/models, repo_root/data)
# so app.py's existing "../models" / "../data" relative paths resolve unchanged.
WORKDIR /app/backend

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
