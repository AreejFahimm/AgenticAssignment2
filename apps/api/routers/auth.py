from __future__ import annotations

import os
import secrets
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, UploadFile

from agent.config import ROOT
from apps.api import db
from apps.api.auth import users
from apps.api.auth.users import User
from apps.api.schemas.models import LoginIn, MeOut, RegisterIn, SettingsIn, TokenOut

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=TokenOut)
def register(body: RegisterIn, response: Response):
    users.create_user(body.email, body.password, body.persona)
    tok = users.login(body.email, body.password)
    response.set_cookie("session", tok, httponly=True, samesite="lax")
    return TokenOut(token=tok)


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, response: Response):
    tok = users.login(body.email, body.password)
    response.set_cookie("session", tok, httponly=True, samesite="lax")
    return TokenOut(token=tok)


@router.post("/auth/logout")
def logout(request: Request, response: Response):
    tok = request.headers.get("authorization", "").removeprefix("Bearer ").strip() or request.cookies.get("session", "")
    db.run("delete from sessions where token=?", tok)
    response.delete_cookie("session")
    return {"ok": True}


@router.get("/me", response_model=MeOut)
def me(user: dict = User):
    return MeOut(**user)


@router.put("/me/settings", response_model=MeOut)
def put_settings(body: SettingsIn, user: dict = User):
    s = {**user["settings"], **body.model_dump(exclude={"persona"})}
    users.save_settings(user["id"], s)
    if body.persona:
        db.run("update users set persona=? where id=?", body.persona, user["id"])
        user["persona"] = body.persona
    return MeOut(id=user["id"], email=user["email"], persona=user["persona"], settings=s)


@router.post("/me/portfolio")
async def upload_portfolio(file: UploadFile, user: dict = User):
    """Incremental re-indexing: the uploaded file's chunks are embedded and added to the user's index immediately."""
    from rag.index.store import get_index
    from rag.ingest.loaders import add_uploaded_file
    name = Path(file.filename or "upload.md").name
    if Path(name).suffix.lower() not in (".md", ".txt", ".pdf"):
        raise HTTPException(415, "upload a .md, .txt or .pdf file")
    data = await file.read()
    if len(data) > 2_000_000:
        raise HTTPException(413, "file too large (max 2 MB)")
    d = ROOT / "data" / "processed" / "uploads" / user["id"]
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_bytes(data)
    chunks = add_uploaded_file(p, user["persona"])
    get_index(user["persona"]).add_items(chunks)
    return {"indexed_chunks": len(chunks), "file": name}


@router.post("/connect/gigsim")
def connect_gigsim(user: dict = User):
    s = {**user["settings"], "marketplace": "gigsim"}
    users.save_settings(user["id"], s)
    return {"connected": "gigsim"}


@router.get("/connect/upwork/start")
def upwork_start(user: dict = User):
    """Live mode: official Upwork MCP server, OAuth 2.1 (PKCE). Needs UPWORK_OAUTH_* env; otherwise explains what is missing."""
    cid, auth_url = os.getenv("UPWORK_OAUTH_CLIENT_ID"), os.getenv("UPWORK_OAUTH_AUTHORIZE_URL")
    if not cid or not auth_url:
        raise HTTPException(501, "Upwork OAuth is not configured (set UPWORK_OAUTH_CLIENT_ID / UPWORK_OAUTH_AUTHORIZE_URL). Stay in GigSim mode.")
    state = secrets.token_urlsafe(16)
    db.run("insert or replace into oauth_tokens values(?,?,?)", user["id"], "upwork_state", users._fernet().encrypt(state.encode()).decode())
    redirect = os.getenv("UPWORK_OAUTH_REDIRECT", "http://localhost:8000/connect/upwork/callback")
    return {"authorize_url": f"{auth_url}?response_type=code&client_id={cid}&redirect_uri={redirect}&state={state}"}


@router.get("/connect/upwork/callback")
async def upwork_callback(code: str, state: str, user: dict = User):
    row = db.q1("select enc from oauth_tokens where user_id=? and provider='upwork_state'", user["id"])
    if not row or users._fernet().decrypt(row["enc"].encode()).decode() != state:
        raise HTTPException(400, "bad OAuth state")
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(os.environ["UPWORK_OAUTH_TOKEN_URL"], data=dict(grant_type="authorization_code", code=code, client_id=os.environ["UPWORK_OAUTH_CLIENT_ID"],
                                                                       redirect_uri=os.getenv("UPWORK_OAUTH_REDIRECT", "")))
    r.raise_for_status()
    users.store_oauth_token(user["id"], "upwork", r.json())  # encrypted at rest, never logged
    return {"connected": "upwork"}
