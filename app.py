"""
app.py — Flask application for the Commons Archive editing interface.

Routes:
  GET  /                        → grid view (browse + search)
  GET  /row/<id>                → detail/edit view
  POST /row/<id>                → save edits
  GET  /row/new                 → new row form
  POST /row/new                 → create row
  GET  /row/<id>/history        → version history
  POST /row/<id>/restore/<hid>  → restore version
  GET  /login                   → login form
  POST /login                   → authenticate
  GET  /logout                  → clear session
  GET  /api/schema              → schema JSON (for client-side rendering)
  GET  /api/rows                → rows JSON (search/page)
  GET  /admin/users             → user management (admin only)
  POST /admin/users             → create user
  GET  /admin/setup             → schema editor + CSV import (admin only)
  POST /admin/setup/schema      → save edited schema
  POST /admin/setup/csv         → upload CSV and preview inferred schema
  POST /admin/setup/csv/import  → confirm CSV import
"""

import os
import re
import csv
import io
import json
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, abort, flash
)
import db
import schema as _schema

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-in-production-please")


# ── Auth helpers ─────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated


def editor_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login", next=request.path))
        if session["user"]["role"] not in ("editor", "admin"):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session or session["user"]["role"] != "admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ── Context processor: pass schema + user to all templates ───────────────────

@app.context_processor
def inject_globals():
    return {
        "schema": _schema.SCHEMA,
        "current_user": session.get("user"),
    }


# ── Auth routes ──────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.verify_user(username, password)
        if user:
            session["user"] = user
            return redirect(request.args.get("next") or url_for("index"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Main grid view ────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    search = request.args.get("q", "").strip()
    page = max(1, int(request.args.get("page", 1)))
    per_page = 50
    offset = (page - 1) * per_page
    rows, total = db.list_rows(search=search or None, limit=per_page, offset=offset)
    total_pages = max(1, (total + per_page - 1) // per_page)
    cold_start = (total == 0 and session.get("user", {}).get("role") == "admin")
    return render_template(
        "index.html",
        rows=rows,
        total=total,
        page=page,
        total_pages=total_pages,
        search=search,
        cold_start=cold_start,
    )


# ── Row detail / edit ────────────────────────────────────────────────────────

@app.route("/row/new", methods=["GET", "POST"])
@editor_required
def new_row():
    if request.method == "POST":
        data = _parse_form(request.form)
        try:
            row_id = db.save_row(data, username=session["user"]["username"])
            flash("Row created.", "success")
            return redirect(url_for("edit_row", row_id=row_id))
        except ValueError as e:
            flash(str(e), "error")
    return render_template("edit.html", row=None, history=[])


@app.route("/row/<int:row_id>", methods=["GET", "POST"])
@login_required
def edit_row(row_id):
    row = db.get_row(row_id)
    if row is None:
        abort(404)
    history = db.get_history(row_id, limit=30)

    if request.method == "POST":
        if session["user"]["role"] not in ("editor", "admin"):
            abort(403)
        data = _parse_form(request.form)
        try:
            db.save_row(data, username=session["user"]["username"], row_id=row_id)
            flash("Saved.", "success")
            return redirect(url_for("edit_row", row_id=row_id))
        except ValueError as e:
            flash(str(e), "error")

    return render_template("edit.html", row=row, history=history)


@app.route("/row/<int:row_id>/restore/<int:history_id>", methods=["POST"])
@editor_required
def restore_version(row_id, history_id):
    try:
        db.restore_version(row_id, history_id, username=session["user"]["username"])
        flash("Version restored.", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("edit_row", row_id=row_id))


# ── Admin: user management ────────────────────────────────────────────────────

@app.route("/admin/users", methods=["GET", "POST"])
@admin_required
def admin_users():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "editor")
        if not username or not password:
            flash("Username and password required.", "error")
        else:
            try:
                db.create_user(username, password, role)
                flash(f"User '{username}' created.", "success")
            except Exception as e:
                flash(f"Error: {e}", "error")
    users = db.list_users()
    return render_template("admin_users.html", users=users)


# ── Admin: setup (schema editor + CSV import) ─────────────────────────────────

@app.route("/admin/setup")
@admin_required
def admin_setup():
    row_count = db.table_row_count()
    return render_template("admin_setup.html",
                           active_tab="schema",
                           row_count=row_count,
                           csv_preview=None,
                           csv_raw=None,
                           inferred_schema=None)


@app.route("/admin/setup/schema", methods=["POST"])
@admin_required
def setup_save_schema():
    new_schema = _parse_schema_form(request.form)
    if not new_schema["fields"]:
        flash("Schema must have at least one field.", "error")
        return redirect(url_for("admin_setup"))

    row_count = db.table_row_count()
    if row_count > 0 and request.form.get("confirm_wipe") != "yes":
        flash(f"Table has {row_count} existing rows. Check the confirmation box to wipe and re-initialise.", "error")
        return redirect(url_for("admin_setup"))

    _schema.save_schema(new_schema)
    db.reset_db()
    flash("Schema saved and database re-initialised.", "success")
    return redirect(url_for("index"))


@app.route("/admin/setup/csv", methods=["POST"])
@admin_required
def setup_csv_preview():
    f = request.files.get("csvfile")
    if not f or not f.filename:
        flash("No file selected.", "error")
        return redirect(url_for("admin_setup"))

    try:
        csv_text = f.read().decode("utf-8-sig")  # strip BOM if present
    except UnicodeDecodeError:
        flash("File must be UTF-8 encoded.", "error")
        return redirect(url_for("admin_setup"))

    inferred_schema, preview_rows = _infer_schema_from_csv(csv_text)
    if inferred_schema is None:
        flash("CSV appears to be empty or has no header row.", "error")
        return redirect(url_for("admin_setup"))

    row_count = db.table_row_count()
    return render_template("admin_setup.html",
                           active_tab="csv",
                           row_count=row_count,
                           csv_preview=preview_rows[:5],
                           csv_raw=csv_text,
                           inferred_schema=inferred_schema)


@app.route("/admin/setup/csv/import", methods=["POST"])
@admin_required
def setup_csv_import():
    csv_raw = request.form.get("csv_raw", "")
    new_schema = _parse_schema_form(request.form)
    if not new_schema["fields"]:
        flash("Schema must have at least one field.", "error")
        return redirect(url_for("admin_setup"))

    row_count = db.table_row_count()
    if row_count > 0 and request.form.get("confirm_wipe") != "yes":
        flash(f"Table has {row_count} existing rows. Check the confirmation box to proceed.", "error")
        return redirect(url_for("admin_setup"))

    # Extract col-index → field-name mapping, then strip _csv_col from schema
    col_to_field = {}
    clean_fields = []
    for field in new_schema["fields"]:
        csv_col = field.pop("_csv_col", None)
        if csv_col is not None:
            col_to_field[csv_col] = field["name"]
        clean_fields.append(field)
    new_schema["fields"] = clean_fields

    # Build type lookup for conversion
    type_map = {f["name"]: f["type"] for f in new_schema["fields"]}

    # Re-parse raw CSV and convert using user-edited schema
    reader = csv.reader(io.StringIO(csv_raw))
    all_rows = list(reader)
    data_rows = all_rows[1:] if len(all_rows) > 1 else []

    converted = []
    for row in data_rows:
        d = {}
        for col_idx, field_name in col_to_field.items():
            raw = row[col_idx].strip() if col_idx < len(row) else ""
            d[field_name] = _convert_csv_value(raw, type_map.get(field_name, "text"))
        converted.append(d)

    _schema.save_schema(new_schema)
    db.reset_db()
    imported, skipped = db.import_rows(converted, username=session["user"]["username"])

    msg = f"Schema saved. {imported} row(s) imported."
    if skipped:
        msg += f" {skipped} row(s) skipped (missing required fields)."
    flash(msg, "success")
    return redirect(url_for("index"))


# ── API ───────────────────────────────────────────────────────────────────────

@app.route("/api/schema")
@login_required
def api_schema():
    return jsonify(_schema.SCHEMA)


@app.route("/api/rows")
@login_required
def api_rows():
    search = request.args.get("q", "").strip() or None
    rows, total = db.list_rows(search=search, limit=100)
    return jsonify({"rows": rows, "total": total})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_form(form):
    """Convert flat HTML form submission back into typed Python values."""
    data = {}
    for f in _schema.SCHEMA["fields"]:
        name = f["name"]
        if f["type"] == "multilingual":
            langs = {l["code"]: l["label"] for l in f.get("languages", [])}
            translations = {}
            for code in langs:
                val = form.get(f"{name}__{code}", "").strip()
                if val:
                    translations[code] = val
            data[name] = translations
        elif f["type"] == "keywords":
            raw = form.get(name, "")
            try:
                data[name] = json.loads(raw)
            except Exception:
                data[name] = [k.strip() for k in raw.split(",") if k.strip()]
        elif f["type"] == "integer":
            val = form.get(name, "").strip()
            data[name] = int(val) if val else None
        else:
            data[name] = form.get(name, "").strip() or None
    return data


def _parse_schema_form(form):
    """Parse the setup form into a schema dict."""
    count = int(form.get("field_count", 0))
    fields = []
    for i in range(count):
        name = form.get(f"field_name_{i}", "").strip()
        if not name:
            continue
        # Sanitise: only lowercase letters, digits, underscores
        name = re.sub(r"[^a-z0-9_]", "_", name.lower()).strip("_") or f"field_{i}"
        field = {
            "name": name,
            "label": form.get(f"field_label_{i}", name).strip() or name,
            "type": form.get(f"field_type_{i}", "text"),
            "required": form.get(f"field_required_{i}") == "on",
            "searchable": form.get(f"field_searchable_{i}") == "on",
            "width": form.get(f"field_width_{i}", "md"),
        }
        if form.get(f"field_primary_{i}") == "on":
            field["primary"] = True
        if field["type"] == "multilingual":
            try:
                field["languages"] = json.loads(form.get(f"field_languages_{i}", "[]"))
            except Exception:
                field["languages"] = []
        csv_col_raw = form.get(f"field_csv_col_{i}", "")
        if csv_col_raw != "":
            try:
                field["_csv_col"] = int(csv_col_raw)
            except ValueError:
                pass
        fields.append(field)

    table_name = re.sub(r"[^a-z0-9_]", "_", form.get("table_name", "data").strip().lower()).strip("_") or "data"
    return {
        "table_name": table_name,
        "display_name": form.get("display_name", "My Archive").strip() or "My Archive",
        "description": form.get("description", "").strip(),
        "fields": fields,
    }


def _infer_field_type(values):
    non_empty = [v.strip() for v in values if v.strip()]
    if not non_empty:
        return "text"
    if all(v.lstrip("-").isdigit() for v in non_empty):
        return "integer"
    url_frac = sum(1 for v in non_empty if v.startswith(("http://", "https://"))) / len(non_empty)
    if url_frac > 0.8:
        return "url"
    avg_len = sum(len(v) for v in non_empty) / len(non_empty)
    if avg_len > 150:
        return "longtext"
    return "text"


def _convert_csv_value(raw, field_type):
    if not raw:
        return None
    if field_type == "integer":
        return int(raw) if raw.lstrip("-").isdigit() else None
    return raw


def _infer_schema_from_csv(csv_text):
    """Parse CSV text, infer field types, return (schema_dict, preview_rows_as_dicts).
    Returns (None, []) if CSV is empty."""
    reader = csv.reader(io.StringIO(csv_text))
    all_rows = list(reader)
    if len(all_rows) < 1 or not any(all_rows[0]):
        return None, []

    headers = all_rows[0]
    data_rows = all_rows[1:]

    fields = []
    for col_idx, h in enumerate(headers):
        col_values = [r[col_idx] if col_idx < len(r) else "" for r in data_rows]
        field_type = _infer_field_type(col_values)
        field_name = re.sub(r"[^a-z0-9]+", "_", h.lower().strip()).strip("_") or f"field_{col_idx}"
        fields.append({
            "name": field_name,
            "label": h.strip(),
            "type": field_type,
            "required": False,
            "searchable": field_type in ("text", "longtext"),
            "width": "xl" if field_type == "longtext" else ("sm" if field_type == "integer" else "md"),
            "_csv_col": col_idx,
        })

    inferred_schema = {
        "table_name": "data",
        "display_name": "My Archive",
        "description": "",
        "fields": fields,
    }

    # Build preview rows as dicts keyed by inferred field name
    preview = []
    for row in data_rows:
        d = {}
        for f in fields:
            col_idx = f["_csv_col"]
            d[f["name"]] = row[col_idx].strip() if col_idx < len(row) else ""
        preview.append(d)

    return inferred_schema, preview


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    db.init_db()
    # Create default admin if no users exist
    users = db.list_users()
    if not users:
        db.create_user("admin", "admin", role="admin")
        print("Created default user: admin / admin  ← change this immediately")
    app.run(debug=True, host="0.0.0.0", port=5050)
