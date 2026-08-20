"""
db.py
Lightweight SQLite persistence for StudyForge.

Kits are owned by either a logged-in user (owner_type='user', owner_id=user
id as text) or an anonymous guest (owner_type='guest', owner_id=a client-
generated UUID stored in the browser's localStorage). This lets history and
recovery work immediately with zero signup friction, while login exists
purely to make that history follow a student across devices.
"""

import json
import os
import sqlite3
import time
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "studyforge.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS kits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_type TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                title TEXT,
                source_text TEXT,
                kit_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS qa_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kit_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (kit_id) REFERENCES kits (id) ON DELETE CASCADE
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_kits_owner ON kits (owner_type, owner_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qa_kit ON qa_history (kit_id)")


# ---------- Users ----------

def create_user(email: str, password_hash: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email.strip().lower(), password_hash, _now()),
        )
        return cur.lastrowid


def get_user_by_email(email: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


# ---------- Kits ----------

def create_kit(owner_type: str, owner_id: str, title: str, source_text: str, kit: dict) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO kits (owner_type, owner_id, title, source_text, kit_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (owner_type, owner_id, title, source_text, json.dumps(kit), _now()),
        )
        return cur.lastrowid


def list_kits(owner_type: str, owner_id: str) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, title, created_at, kit_json FROM kits
               WHERE owner_type = ? AND owner_id = ? ORDER BY created_at DESC""",
            (owner_type, owner_id),
        ).fetchall()
        results = []
        for row in rows:
            kit = json.loads(row["kit_json"])
            results.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "created_at": row["created_at"],
                    "summary_preview": (kit.get("summary") or "")[:160],
                    "concept_count": len(kit.get("concepts") or []),
                }
            )
        return results


def get_kit(kit_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM kits WHERE id = ?", (kit_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["kit"] = json.loads(result["kit_json"])
        return result


def delete_kit(kit_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM qa_history WHERE kit_id = ?", (kit_id,))
        conn.execute("DELETE FROM kits WHERE id = ?", (kit_id,))


def migrate_guest_kits(guest_id: str, user_id: int) -> None:
    """Called on signup/login so a student doesn't lose kits they forged before creating an account."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE kits SET owner_type = 'user', owner_id = ? WHERE owner_type = 'guest' AND owner_id = ?",
            (str(user_id), guest_id),
        )


# ---------- Q&A history ----------

def add_qa(kit_id: int, question: str, answer: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO qa_history (kit_id, question, answer, created_at) VALUES (?, ?, ?, ?)",
            (kit_id, question, answer, _now()),
        )


def list_qa(kit_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT question, answer, created_at FROM qa_history WHERE kit_id = ? ORDER BY created_at ASC",
            (kit_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())