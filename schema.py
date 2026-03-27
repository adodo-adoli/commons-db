"""
schema.py — edit this file to define the database schema for your archive instance.
If a schema.json file exists alongside this file, it takes precedence and is loaded instead.
Use /admin/setup in the web interface to edit the schema or import a CSV cold-start.

FIELD TYPES:
  text       — single-line text
  longtext   — multi-line textarea
  integer    — whole number
  url        — URL (rendered as link)
  keywords   — comma-separated tags (rendered as pills)
  image      — URL or path to image (rendered as thumbnail)
  file       — file attachment path/URL
  multilingual — dict of {lang_code: value}, rendered as expandable per-language fields

FIELD OPTIONS:
  required   — bool, default False
  searchable — bool, included in full-text search, default True
  width      — 'sm' | 'md' | 'lg' | 'xl', hints for column width in grid view
  primary    — bool, marks this as the human-readable identifier shown in history/diffs
"""

import os
import json

SCHEMA_PATH = os.environ.get("SCHEMA_PATH", "schema.json")

_DEFAULT_SCHEMA = {
    "table_name": "archive",
    "display_name": "Commons Archive",
    "description": "Decentralised archive of grassroots activist works",

    "fields": [
        {
            "name": "unique_id",
            "label": "Unique ID",
            "type": "text",
            "required": True,
            "searchable": True,
            "width": "sm",
            "primary": True,
        },
        {
            "name": "title",
            "label": "Title",
            "type": "text",
            "required": True,
            "searchable": True,
            "width": "lg",
        },
        {
            "name": "title_translations",
            "label": "Title (translations)",
            "type": "multilingual",
            "languages": [
                {"code": "zh", "label": "中文"},
                {"code": "fa", "label": "فارسی"},
                {"code": "ja", "label": "日本語"},
                {"code": "ko", "label": "한국어"},
                {"code": "ar", "label": "العربية"},
                {"code": "es", "label": "Español"},
                {"code": "fr", "label": "Français"},
                {"code": "de", "label": "Deutsch"},
                {"code": "ru", "label": "Русский"},
                {"code": "pt", "label": "Português"},
            ],
            "searchable": True,
            "width": "lg",
        },
        {
            "name": "year",
            "label": "Year",
            "type": "integer",
            "required": False,
            "searchable": False,
            "width": "sm",
        },
        {
            "name": "author",
            "label": "Author",
            "type": "text",
            "required": False,
            "searchable": True,
            "width": "md",
        },
        {
            "name": "press_publisher",
            "label": "Press / Publisher",
            "type": "text",
            "required": False,
            "searchable": True,
            "width": "md",
        },
        {
            "name": "place_of_publication",
            "label": "Place of Publication",
            "type": "text",
            "required": False,
            "searchable": True,
            "width": "md",
        },
        {
            "name": "isbn_issn",
            "label": "ISBN / ISSN",
            "type": "text",
            "required": False,
            "searchable": True,
            "width": "sm",
        },
        {
            "name": "website",
            "label": "Website",
            "type": "url",
            "required": False,
            "searchable": False,
            "width": "md",
        },
        {
            "name": "keywords",
            "label": "Keywords",
            "type": "keywords",
            "required": False,
            "searchable": True,
            "width": "lg",
        },
        {
            "name": "description",
            "label": "Description",
            "type": "longtext",
            "required": False,
            "searchable": True,
            "width": "xl",
        },
        {
            "name": "image",
            "label": "Image",
            "type": "image",
            "required": False,
            "searchable": False,
            "width": "sm",
        },
        {
            "name": "attachment",
            "label": "Attachment",
            "type": "file",
            "required": False,
            "searchable": False,
            "width": "sm",
        },
    ]
}


def load_schema():
    """Load schema from schema.json if it exists, otherwise return the built-in default."""
    if os.path.exists(SCHEMA_PATH):
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            return json.load(f)
    return _DEFAULT_SCHEMA


def save_schema(d):
    """Write schema dict to schema.json and update the in-memory SCHEMA global."""
    global SCHEMA
    with open(SCHEMA_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    SCHEMA = d


SCHEMA = load_schema()
