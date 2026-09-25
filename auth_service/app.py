import hashlib
import json
import os
import secrets
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "auth.sqlite3"
REDMAP_BASE_URL = os.getenv("REDMAP_BASE_URL", "http://127.0.0.1:2500")

app = FastAPI(title="Environment Authentication Service", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "templates")), name="static")


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            username TEXT NOT NULL,
            issued_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _normalize_username(value: str) -> str:
    return value.strip().lower()


def _hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return salt.hex() + ":" + derived.hex()


def _verify_password(password: str, stored_hash: str) -> bool:
    salt_hex, digest_hex = stored_hash.split(":", 1)
    salt = bytes.fromhex(salt_hex)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000).hex()
    return secrets.compare_digest(derived, digest_hex)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8)


class ResetPasswordRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    new_password: str = Field(..., min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class ToolResponse(BaseModel):
    name: str
    description: str


@app.on_event("startup")
def startup_event() -> None:
    init_db()


@app.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> dict:
    username = _normalize_username(payload.username)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    existing = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    password_hash = _hash_password(payload.password)
    conn.execute(
        "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
        (username, password_hash, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return {"message": f"User '{username}' registered successfully"}


@app.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    username = _normalize_username(payload.username)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT password_hash FROM users WHERE username = ?", (username,)).fetchone()
    if not row or not _verify_password(payload.password, row["password_hash"]):
        conn.close()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    token = secrets.token_urlsafe(32)
    issued_at = datetime.utcnow().isoformat()
    expires_at = (datetime.utcnow() + timedelta(hours=12)).isoformat()
    conn.execute(
        "INSERT INTO sessions (token, username, issued_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, username, issued_at, expires_at),
    )
    conn.commit()
    conn.close()
    return TokenResponse(access_token=token, username=username)


@app.post("/reset-password")
def reset_password(payload: ResetPasswordRequest) -> dict:
    username = _normalize_username(payload.username)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    password_hash = _hash_password(payload.new_password)
    conn.execute("UPDATE users SET password_hash = ? WHERE username = ?", (password_hash, username))
    conn.commit()
    conn.close()
    return {"message": f"Password updated for '{username}'"}


def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT username, expires_at FROM sessions WHERE token = ?", (token,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    expires_at = datetime.fromisoformat(row["expires_at"])
    if datetime.utcnow() > expires_at:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
        conn.close()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")

    conn.close()
    return {"username": row["username"]}


def _fetch_json_from_redmap(path: str) -> dict:
    url = f"{REDMAP_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        body = response.read().decode("utf-8")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"raw": body}


@app.get("/redmap/status")
def redmap_status(user: dict = Depends(get_current_user)) -> dict:
    try:
        health = _fetch_json_from_redmap("/health")
        overview = _fetch_json_from_redmap("/decision/overview")
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=exc.code, detail="Unable to reach RedMap") from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="RedMap is unavailable") from exc

    return {
        "service": "redmap",
        "reachable": True,
        "username": user["username"],
        "health": health,
        "overview": overview,
    }


@app.get("/whoami")
def whoami(user: dict = Depends(get_current_user)) -> dict:
    return {"username": user["username"]}


@app.get("/tools", response_model=list[ToolResponse])
def list_tools(user: dict = Depends(get_current_user)) -> list[ToolResponse]:
    return [
        ToolResponse(name="regmap-api", description="Compliance mapping tool"),
        ToolResponse(name="control-advisor", description="Control recommendation tool"),
        ToolResponse(name="backend-health", description="Service health checks"),
    ]


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(BASE_DIR / "templates" / "login.html")


@app.get("/login.html", include_in_schema=False)
def login_page() -> FileResponse:
    return FileResponse(BASE_DIR / "templates" / "login.html")


@app.get("/tools.html", include_in_schema=False)
def tools_page() -> FileResponse:
    return FileResponse(BASE_DIR / "templates" / "tools.html")


@app.get("/login-page", include_in_schema=False)
def login_page_alias() -> FileResponse:
    return FileResponse(BASE_DIR / "templates" / "login.html")


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8002, reload=False)
