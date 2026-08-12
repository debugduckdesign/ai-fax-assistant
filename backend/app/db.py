import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from app.config import Settings, get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'operator')),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS call_events (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    user_id TEXT,
    conversation_id TEXT,
    to_number TEXT,
    status TEXT NOT NULL,
    reason TEXT,
    transcript_excerpt TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_call_events_user_id ON call_events(user_id);
CREATE INDEX IF NOT EXISTS idx_call_events_case_id ON call_events(case_id);
CREATE INDEX IF NOT EXISTS idx_call_events_created_at ON call_events(created_at);
"""


def connect(settings: Settings | None = None) -> sqlite3.Connection:
    settings = settings or get_settings()
    conn = sqlite3.connect(settings.database_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_connection(settings: Settings | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(settings)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    with get_connection(settings) as conn:
        conn.executescript(SCHEMA)
