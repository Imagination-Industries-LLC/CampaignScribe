"""SQLite schema management and CRUD helpers."""

from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from app.config import get_db_path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name TEXT NOT NULL DEFAULT 'Untitled Session',
    campaign_name TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    source_audio_files TEXT,
    num_speakers_detected INTEGER,
    speakers_json_path TEXT,
    transcripts_folder TEXT,
    summary_path TEXT,
    status TEXT DEFAULT 'new'
);

CREATE TABLE IF NOT EXISTS speaker_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    source_speaker_id TEXT,
    display_name TEXT,
    character_name TEXT,
    character_class TEXT,
    role TEXT,
    include_in_tracking INTEGER DEFAULT 1,
    notes TEXT,
    speech_patterns TEXT,
    sample_quotes TEXT,
    confidence TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    is_default INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


SCHEMA_BASELINE = 1

# Incremental migrations for schema changes AFTER the baseline (v1). Each entry
# is (target_version, function(conn)); they run once, in order, on existing
# databases whose PRAGMA user_version is below the target. Example:
#   def _m2(conn): conn.execute("ALTER TABLE sessions ADD COLUMN language TEXT")
#   _MIGRATIONS = [(2, _m2)]
_MIGRATIONS: List = []

# Columns callers may update via **fields. Guards the dynamic UPDATE builders
# below against unexpected/untrusted column names (the values are already
# parameterised; the column names are not).
_SESSION_COLUMNS = {
    "display_name", "campaign_name", "updated_at", "source_audio_files",
    "num_speakers_detected", "speakers_json_path", "transcripts_folder",
    "summary_path", "status",
}
_SPEAKER_COLUMNS = {
    "source_speaker_id", "display_name", "character_name", "character_class",
    "role", "include_in_tracking", "notes", "speech_patterns", "sample_quotes",
    "confidence",
}


def _apply_migrations(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == 0:
        # Fresh DB, or a pre-versioning install: CREATE TABLE IF NOT EXISTS has
        # just guaranteed the baseline schema is present.
        version = SCHEMA_BASELINE
        conn.execute(f"PRAGMA user_version = {SCHEMA_BASELINE}")
    for target, migrate in _MIGRATIONS:
        if version < target:
            migrate(conn)
            conn.execute(f"PRAGMA user_version = {target}")
            version = target


def init_db() -> None:
    db_path = get_db_path()
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(SCHEMA_SQL)
        _apply_migrations(conn)
        conn.commit()


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(get_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------- sessions ----------

def create_session(display_name: str, campaign_name: str = "",
                   source_audio_files: Optional[List[str]] = None) -> int:
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO sessions(display_name, campaign_name, source_audio_files) "
            "VALUES (?, ?, ?)",
            (display_name or "Untitled Session", campaign_name or "",
             json.dumps(source_audio_files or [])),
        )
        return int(cur.lastrowid)


def update_session(session_id: int, **fields) -> None:
    if not fields:
        return
    fields["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    invalid = set(fields) - _SESSION_COLUMNS
    if invalid:
        raise ValueError(f"update_session: unknown column(s) {sorted(invalid)}")
    cols = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [session_id]
    with get_conn() as c:
        c.execute(f"UPDATE sessions SET {cols} WHERE id = ?", vals)


def get_session(session_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as c:
        row = c.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return dict(row) if row else None


def list_sessions(search: str = "") -> List[Dict[str, Any]]:
    with get_conn() as c:
        if search:
            rows = c.execute(
                "SELECT * FROM sessions WHERE display_name LIKE ? OR campaign_name LIKE ? "
                "ORDER BY created_at DESC",
                (f"%{search}%", f"%{search}%"),
            ).fetchall()
        else:
            rows = c.execute("SELECT * FROM sessions ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def delete_session(session_id: int) -> None:
    # speaker_profiles rows are removed automatically via ON DELETE CASCADE
    # (PRAGMA foreign_keys = ON is set on every get_conn connection).
    with get_conn() as c:
        c.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


# ---------- speaker profiles ----------

def add_speaker_profile(session_id: int, profile: Dict[str, Any]) -> int:
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO speaker_profiles(session_id, source_speaker_id, display_name, "
            "character_name, character_class, role, include_in_tracking, notes, "
            "speech_patterns, sample_quotes, confidence) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                profile.get("source_speaker_id", ""),
                profile.get("display_name", ""),
                profile.get("character_name", ""),
                profile.get("character_class", ""),
                profile.get("role", "Unknown"),
                int(profile.get("include_in_tracking", 1)),
                profile.get("notes", ""),
                json.dumps(profile.get("speech_patterns", []) or []),
                json.dumps(profile.get("sample_quotes", []) or []),
                profile.get("confidence", "medium"),
            ),
        )
        return int(cur.lastrowid)


def get_speakers_for_session(session_id: int) -> List[Dict[str, Any]]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM speaker_profiles WHERE session_id = ? ORDER BY source_speaker_id",
            (session_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["speech_patterns"] = json.loads(d.get("speech_patterns") or "[]")
        except Exception:
            d["speech_patterns"] = []
        try:
            d["sample_quotes"] = json.loads(d.get("sample_quotes") or "[]")
        except Exception:
            d["sample_quotes"] = []
        out.append(d)
    return out


def update_speaker_profile(profile_id: int, **fields) -> None:
    if not fields:
        return
    if "speech_patterns" in fields and not isinstance(fields["speech_patterns"], str):
        fields["speech_patterns"] = json.dumps(fields["speech_patterns"] or [])
    if "sample_quotes" in fields and not isinstance(fields["sample_quotes"], str):
        fields["sample_quotes"] = json.dumps(fields["sample_quotes"] or [])
    invalid = set(fields) - _SPEAKER_COLUMNS
    if invalid:
        raise ValueError(f"update_speaker_profile: unknown column(s) {sorted(invalid)}")
    cols = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [profile_id]
    with get_conn() as c:
        c.execute(f"UPDATE speaker_profiles SET {cols} WHERE id = ?", vals)


def delete_speakers_for_session(session_id: int) -> None:
    with get_conn() as c:
        c.execute("DELETE FROM speaker_profiles WHERE session_id = ?", (session_id,))


# ---------- prompts ----------

def list_user_prompts() -> List[Dict[str, Any]]:
    with get_conn() as c:
        rows = c.execute(
            "SELECT * FROM user_prompts WHERE is_default = 0 ORDER BY name"
        ).fetchall()
    return [dict(r) for r in rows]


def add_user_prompt(name: str, content: str) -> int:
    with get_conn() as c:
        cur = c.execute(
            "INSERT INTO user_prompts(name, content, is_default) VALUES (?, ?, 0)",
            (name, content),
        )
        return int(cur.lastrowid)


def update_user_prompt(prompt_id: int, name: str, content: str) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn() as c:
        c.execute(
            "UPDATE user_prompts SET name = ?, content = ?, updated_at = ? WHERE id = ?",
            (name, content, now, prompt_id),
        )


def delete_user_prompt(prompt_id: int) -> None:
    with get_conn() as c:
        c.execute("DELETE FROM user_prompts WHERE id = ? AND is_default = 0", (prompt_id,))
