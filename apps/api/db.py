"""Tiny SQLite persistence for users, sessions, runs and run events (swap for Postgres via DATABASE_URL in prod).

Every query that touches user data takes user_id (tenant scoping, E4)."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

from agent.config import ROOT

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
create table if not exists users(id text primary key, email text unique, pw_hash text, salt text, persona text, settings text, created real);
create table if not exists sessions(token text primary key, user_id text, created real);
create table if not exists oauth_tokens(user_id text, provider text, enc text, primary key(user_id, provider));
create table if not exists runs(thread_id text primary key, user_id text, kind text, job_id text, proposal_id text, title text, status text,
    decision text, fit real, risk real, bid real, connects int, category text, tokens int default 0, usd real default 0, latency_ms int default 0,
    created real, updated real, summary text);
create table if not exists run_events(id integer primary key autoincrement, thread_id text, user_id text, ts real, kind text, data text);
create index if not exists ev_thread on run_events(thread_id, id);
create table if not exists pipeline(user_id text, proposal_id text, job_id text, title text, category text, status text, updated real, primary key(user_id, proposal_id));
create table if not exists feedback(id integer primary key autoincrement, user_id text, thread_id text, kind text, reason text, ts real);
"""


def db() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            p = os.getenv("APP_DB") or str(ROOT / "data" / "processed" / "app.sqlite")
            if p != ":memory:":
                Path(p).parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(p, check_same_thread=False, isolation_level=None)
            _conn.row_factory = sqlite3.Row
            _conn.executescript(SCHEMA)
        return _conn


def reset_for_tests() -> None:
    global _conn
    with _lock:
        if _conn:
            _conn.close()
        _conn = None


def q(sql: str, *args) -> list[dict]:
    with _lock:
        return [dict(r) for r in db().execute(sql, args).fetchall()]


def q1(sql: str, *args) -> dict | None:
    r = q(sql, *args)
    return r[0] if r else None


def run(sql: str, *args) -> None:
    with _lock:
        db().execute(sql, args)


def add_event(thread_id: str, user_id: str, kind: str, data: dict) -> None:
    run("insert into run_events(thread_id,user_id,ts,kind,data) values(?,?,?,?,?)", thread_id, user_id, time.time(), kind, json.dumps(data, default=str))
