# Commons Archive — POC

A self-hostable, open-source database editing platform for grassroots activist archives.

## What this is

A lightweight web application that gives any group a structured, versioned, searchable database with a browser-based editing interface. No cloud dependency. No proprietary formats. The entire database is a single SQLite file you can copy, back up, or migrate anywhere.

## Stack

| Layer | Technology | Why |
|---|---|---|
| Database | SQLite (WAL mode) | Single portable file, ACID, runs everywhere |
| Version history | Append-only `_history` table | Full row snapshots + diffs, no external tool |
| Backend | Python 3 + Flask | Minimal, auditable, no build step |
| Auth | bcrypt password hashing | No third-party identity provider |
| Frontend | Vanilla HTML/CSS/JS | No framework, easy to audit, works without JS for basic reads |
| Schema | `schema.py` | One file to edit at setup time |

## Quick start

```bash
# 1. Clone / copy the project
git clone <repo> && cd commons-db

# 2. Install dependencies (Python 3.8+)
pip install flask bcrypt

# 3. Run
python app.py
```

Open http://localhost:5050

Default login: **admin / admin** — change this immediately via /admin/users.

## Customising the schema

Edit `schema.py` before first run. The `SCHEMA` dict defines:

- `table_name` — SQLite table name (no spaces)
- `display_name` — shown in the UI
- `fields` — list of field definitions

### Field types

| Type | Storage | UI |
|---|---|---|
| `text` | TEXT | Single-line input |
| `longtext` | TEXT | Textarea |
| `integer` | INTEGER | Number input |
| `url` | TEXT | Text input + open link button |
| `keywords` | TEXT (JSON array) | Tag pill input |
| `image` | TEXT | URL input + thumbnail preview |
| `file` | TEXT | URL/path input |
| `multilingual` | TEXT (JSON object) | Per-language inputs, collapsible |

### Adding a new language to multilingual fields

In `schema.py`, add an entry to the `languages` list of any `multilingual` field:

```python
{"code": "tr", "label": "Türkçe"},
```

No migration needed — the JSON column stores whatever keys are present.

### Adding a new field

Add a dict to the `fields` list. On the next startup, run:

```bash
python -c "import db; db.init_db()"
```

This is safe to re-run — it uses `CREATE TABLE IF NOT EXISTS`. **Note: adding columns to an existing table requires a SQLite migration** (ALTER TABLE ADD COLUMN) — see Migration section below.

## Data portability

**Export to CSV/JSON:**
```bash
sqlite3 -csv archive.db "SELECT * FROM archive;" > export.csv
sqlite3 archive.db ".mode json" ".output export.json" "SELECT * FROM archive;"
```

**Move to another host:** copy `archive.db`. That's it.

**Import to PostgreSQL:**
```bash
pgloader sqlite://./archive.db postgresql://user:pass@host/dbname
```

## Version history

Every save writes a full row snapshot to `archive_history`. To browse history for a row, click "edit →" then see the history sidebar. To restore, click "restore ↩" on any version.

The history table is append-only — rows are never deleted. It is safe to truncate if it grows large, though this loses the audit trail.

## Authentication & roles

Three roles:

- **viewer** — read-only browse and search
- **editor** — create and edit rows
- **admin** — everything including user management

Manage users at `/admin/users` (admin only).

**Passwords** are hashed with bcrypt. The application never stores plaintext passwords.

**Production note:** run behind a reverse proxy (nginx, Caddy) with TLS. Set `SECRET_KEY` as an environment variable:

```bash
SECRET_KEY=your-random-secret python app.py
```

Or use gunicorn:
```bash
gunicorn -w 2 -b 0.0.0.0:5050 app:app
```

## SQLite migrations

When adding columns to an existing database:

```sql
ALTER TABLE archive ADD COLUMN new_field TEXT;
```

Run via:
```bash
sqlite3 archive.db "ALTER TABLE archive ADD COLUMN new_field TEXT;"
```

## Roadmap (not in this POC)

- [ ] CSV import
- [ ] Per-row access control (public/private)
- [ ] Tor-accessible .onion deployment guide
- [ ] E2E encryption layer (client-side key derivation)
- [ ] Multi-node replication (cr-sqlite or manual sync)
- [ ] Configurable export templates

## License

MIT. Copy, fork, adapt, redistribute freely.
