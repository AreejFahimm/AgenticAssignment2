"""Users, sessions and encrypted OAuth token store (E4). Passwords: PBKDF2-SHA256. Tokens: Fernet, key from env."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid

from cryptography.fernet import Fernet
from fastapi import Depends, Header, HTTPException, Request

from apps.api import db

DEFAULT_SETTINGS = dict(hourly_rate=None, floor=None, weekly_connects_budget=60, connects_spent_this_week=0, autonomy="suggest",
                        saved_searches=[dict(name="Default", query="", interval_minutes=240)], marketplace="gigsim", filters=dict(min_budget=0))


def _hash(pw: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000).hex()


def create_user(email: str, password: str, persona: str) -> dict:
    if db.q1("select id from users where email=?", email.lower()):
        raise HTTPException(409, "email already registered")
    salt = secrets.token_bytes(16)
    uid = "u-" + uuid.uuid4().hex[:10]
    db.run("insert into users values(?,?,?,?,?,?,?)", uid, email.lower(), _hash(password, salt), salt.hex(), persona, json.dumps(DEFAULT_SETTINGS), time.time())
    return dict(id=uid, email=email.lower(), persona=persona)


def login(email: str, password: str) -> str:
    u = db.q1("select * from users where email=?", email.lower())
    if not u or not hmac.compare_digest(u["pw_hash"], _hash(password, bytes.fromhex(u["salt"]))):
        raise HTTPException(401, "invalid credentials")
    tok = secrets.token_urlsafe(32)
    db.run("insert into sessions values(?,?,?)", tok, u["id"], time.time())
    return tok


def current_user(request: Request, authorization: str = Header(default="")) -> dict:
    tok = authorization.removeprefix("Bearer ").strip() or request.cookies.get("session", "")
    s = db.q1("select user_id from sessions where token=?", tok) if tok else None
    if not s:
        raise HTTPException(401, "not signed in")
    u = db.q1("select id,email,persona,settings from users where id=?", s["user_id"])
    u["settings"] = json.loads(u["settings"])
    return u


User = Depends(current_user)


def save_settings(user_id: str, settings: dict) -> None:
    db.run("update users set settings=? where id=?", json.dumps(settings), user_id)


# ---------- encrypted OAuth tokens ----------
def _fernet() -> Fernet:
    key = os.getenv("TOKEN_ENC_KEY")
    if not key:  # dev fallback derived from APP_SECRET_KEY; production MUST set TOKEN_ENC_KEY
        key = base64.urlsafe_b64encode(hashlib.sha256(os.getenv("APP_SECRET_KEY", "dev-only-change-me").encode()).digest()).decode()
    return Fernet(key)


def store_oauth_token(user_id: str, provider: str, token: dict) -> None:
    db.run("insert or replace into oauth_tokens values(?,?,?)", user_id, provider, _fernet().encrypt(json.dumps(token).encode()).decode())


def load_oauth_token(user_id: str, provider: str) -> dict | None:
    r = db.q1("select enc from oauth_tokens where user_id=? and provider=?", user_id, provider)
    return json.loads(_fernet().decrypt(r["enc"].encode())) if r else None


def seed_reviewer() -> None:
    """Preloaded reviewer login (credentials come from env, never the repo)."""
    email = os.getenv("REVIEWER_EMAIL", "reviewer@gigbid.demo")
    pw = os.getenv("REVIEWER_PASSWORD")
    if pw and not db.q1("select id from users where email=?", email):
        create_user(email, pw, os.getenv("REVIEWER_PERSONA", "ai_ml_engineer"))
