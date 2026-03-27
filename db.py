"""
db.py — database initialisation, CRUD, and version history.

All writes go through save_row(), which:
  1. Writes the new state to the main table (INSERT or UPDATE) in a transaction
  2. Appends a snapshot to <table>_history with who changed what and when
  3. Returns the row id

History is append-only. Rows are never deleted from history.
"""

import sqlite3
import json
import os
from datetime import datetime, timezone
import schema as _s


DB_PATH = os.environ.get("DB_PATH", "archive.db")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _field_sql_type(field):
    t = field["type"]
    if t == "integer":
        return "INTEGER"
    return "TEXT"  # everything else stored as TEXT (JSON for multilingual/keywords)


def init_db():
    """Create tables from SCHEMA if they don't exist. Safe to call on every startup."""
    table = _s.SCHEMA["table_name"]
    fields = _s.SCHEMA["fields"]

    col_defs = ["id INTEGER PRIMARY KEY AUTOINCREMENT"]
    for f in fields:
        sql_type = _field_sql_type(f)
        not_null = " NOT NULL" if f.get("required") else ""
        col_defs.append(f'"{f["name"]}" {sql_type}{not_null}')

    col_defs += [
        "created_at TEXT NOT NULL",
        "updated_at TEXT NOT NULL",
        "created_by TEXT",
        "updated_by TEXT",
    ]

    create_main = f"""
        CREATE TABLE IF NOT EXISTS "{table}" (
            {", ".join(col_defs)}
        )
    """

    # History table: one row per save, stores full JSON snapshot + diff summary
    create_history = f"""
        CREATE TABLE IF NOT EXISTS "{table}_history" (
            history_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            row_id       INTEGER NOT NULL,
            saved_at     TEXT NOT NULL,
            saved_by     TEXT,
            action       TEXT NOT NULL,
            snapshot     TEXT NOT NULL,
            diff_summary TEXT
        )
    """

    # Users table
    create_users = """
        CREATE TABLE IF NOT EXISTS users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            username     TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role         TEXT NOT NULL DEFAULT 'editor',
            created_at   TEXT NOT NULL
        )
    """

    with _connect() as conn:
        conn.execute(create_main)
        conn.execute(create_history)
        conn.execute(create_users)
        conn.commit()


def reset_db():
    """Drop main and history tables and recreate them from current SCHEMA. All row data is lost."""
    table = _s.SCHEMA["table_name"]
    with _connect() as conn:
        conn.execute(f'DROP TABLE IF EXISTS "{table}_history"')
        conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        conn.commit()
    init_db()


def table_row_count():
    """Return number of rows in the main table, or 0 if the table doesn't exist yet."""
    table = _s.SCHEMA["table_name"]
    with _connect() as conn:
        try:
            return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        except sqlite3.OperationalError:
            return 0


def _now():
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row):
    if row is None:
        return None
    d = dict(row)
    # Deserialise JSON fields
    for f in _s.SCHEMA["fields"]:
        if f["type"] in ("multilingual", "keywords") and d.get(f["name"]):
            try:
                d[f["name"]] = json.loads(d[f["name"]])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


def _serialise_for_db(data):
    """Convert Python dicts/lists to JSON strings for storage."""
    out = {}
    for f in _s.SCHEMA["fields"]:
        val = data.get(f["name"])
        if val is None:
            out[f["name"]] = None
            continue
        if f["type"] in ("multilingual", "keywords") and isinstance(val, (dict, list)):
            out[f["name"]] = json.dumps(val, ensure_ascii=False)
        else:
            out[f["name"]] = val
    return out


def _diff_summary(old, new):
    """Return a short human-readable list of changed field labels."""
    if old is None:
        return "new record"
    changed = []
    field_labels = {f["name"]: f["label"] for f in _s.SCHEMA["fields"]}
    for f in _s.SCHEMA["fields"]:
        name = f["name"]
        old_val = old.get(name)
        new_val = new.get(name)
        if str(old_val) != str(new_val):
            changed.append(field_labels.get(name, name))
    return ", ".join(changed) if changed else "no changes"


def list_rows(search=None, limit=200, offset=0):
    table = _s.SCHEMA["table_name"]
    params = []
    where = ""

    if search:
        searchable = [f["name"] for f in _s.SCHEMA["fields"] if f.get("searchable", True)]
        clauses = [f'"{col}" LIKE ?' for col in searchable]
        where = "WHERE " + " OR ".join(clauses)
        params = [f"%{search}%" for _ in searchable]

    with _connect() as conn:
        rows = conn.execute(
            f'SELECT * FROM "{table}" {where} ORDER BY id DESC LIMIT ? OFFSET ?',
            params + [limit, offset]
        ).fetchall()
        total = conn.execute(
            f'SELECT COUNT(*) FROM "{table}" {where}', params
        ).fetchone()[0]

    return [_row_to_dict(r) for r in rows], total


def get_row(row_id):
    table = _s.SCHEMA["table_name"]
    with _connect() as conn:
        row = conn.execute(
            f'SELECT * FROM "{table}" WHERE id = ?', (row_id,)
        ).fetchone()
    return _row_to_dict(row)


def save_row(data, username, row_id=None):
    """
    INSERT (row_id=None) or UPDATE (row_id=int) a row, and append to history.
    Returns the row_id.
    Raises ValueError on validation errors.
    """
    table = _s.SCHEMA["table_name"]

    # Validate required fields
    for f in _s.SCHEMA["fields"]:
        if f.get("required") and not data.get(f["name"]):
            raise ValueError(f'Field "{f["label"]}" is required.')

    serialised = _serialise_for_db(data)
    now = _now()
    action = "create" if row_id is None else "update"

    with _connect() as conn:
        if row_id is None:
            serialised["created_at"] = now
            serialised["updated_at"] = now
            serialised["created_by"] = username
            serialised["updated_by"] = username

            cols = ", ".join(f'"{k}"' for k in serialised)
            placeholders = ", ".join("?" for _ in serialised)
            cur = conn.execute(
                f'INSERT INTO "{table}" ({cols}) VALUES ({placeholders})',
                list(serialised.values())
            )
            row_id = cur.lastrowid
        else:
            serialised["updated_at"] = now
            serialised["updated_by"] = username
            set_clause = ", ".join(f'"{k}" = ?' for k in serialised)
            conn.execute(
                f'UPDATE "{table}" SET {set_clause} WHERE id = ?',
                list(serialised.values()) + [row_id]
            )

        # Fetch updated row for snapshot
        new_row = _row_to_dict(
            conn.execute(f'SELECT * FROM "{table}" WHERE id = ?', (row_id,)).fetchone()
        )

        # Compute diff against previous history snapshot
        prev = get_history(row_id, limit=1)
        old_snapshot = prev[0]["snapshot"] if prev else None
        if old_snapshot and isinstance(old_snapshot, str):
            old_snapshot = json.loads(old_snapshot)
        diff = _diff_summary(old_snapshot, new_row)

        conn.execute(
            f'INSERT INTO "{table}_history" (row_id, saved_at, saved_by, action, snapshot, diff_summary) VALUES (?, ?, ?, ?, ?, ?)',
            (row_id, now, username, action, json.dumps(new_row, ensure_ascii=False), diff)
        )
        conn.commit()

    return row_id


def import_rows(rows, username):
    """Bulk-insert a list of dicts. Skips rows that fail required-field validation.
    Returns (imported_count, skipped_count)."""
    imported = 0
    skipped = 0
    for row in rows:
        try:
            save_row(row, username=username)
            imported += 1
        except ValueError:
            skipped += 1
    return imported, skipped


def get_history(row_id, limit=50):
    table = _s.SCHEMA["table_name"]
    with _connect() as conn:
        rows = conn.execute(
            f'SELECT * FROM "{table}_history" WHERE row_id = ? ORDER BY history_id DESC LIMIT ?',
            (row_id, limit)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        if d.get("snapshot"):
            try:
                d["snapshot"] = json.loads(d["snapshot"])
            except Exception:
                pass
        result.append(d)
    return result


def restore_version(row_id, history_id, username):
    """Restore a row to a specific historical snapshot."""
    table = _s.SCHEMA["table_name"]
    with _connect() as conn:
        h = conn.execute(
            f'SELECT * FROM "{table}_history" WHERE history_id = ? AND row_id = ?',
            (history_id, row_id)
        ).fetchone()
    if not h:
        raise ValueError("History entry not found.")
    snapshot = json.loads(h["snapshot"])
    # Strip metadata fields before re-saving
    for meta in ("id", "created_at", "updated_at", "created_by", "updated_by"):
        snapshot.pop(meta, None)
    return save_row(snapshot, username=f"{username} (restore)", row_id=row_id)


# ── Users ────────────────────────────────────────────────────────────────────

def create_user(username, password, role="editor"):
    import bcrypt
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (username, pw_hash, role, _now())
        )
        conn.commit()


def verify_user(username, password):
    import bcrypt
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    if not row:
        return None
    if bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
        return {"id": row["id"], "username": row["username"], "role": row["role"]}
    return None


def list_users():
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, username, role, created_at FROM users ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]
