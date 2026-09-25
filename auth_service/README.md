# Environment Authentication Service

This folder adds a lightweight authentication layer that protects access to environment tools using a local SQLite database.

## What it provides
- User registration with a salted PBKDF2 password hash
- Login issuing a bearer token
- Protected tool listing route that requires authentication
- Local SQLite storage in auth_service/auth.sqlite3

## Run it locally
```bash
cd auth_service
pip install -r requirements.txt
python app.py
```

## Run it with Docker
```bash
cd auth_service
docker build -t auth-service:latest .
docker compose up -d
```

Once started, the login page is available at:
- http://127.0.0.1:8002/login.html

Then use these endpoints:
- POST /register
- POST /login
- GET /whoami (requires Bearer token)
- GET /tools (requires Bearer token)

This service is isolated from the existing RegMap Docker image and does not modify it.
