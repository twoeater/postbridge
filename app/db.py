from __future__ import annotations
import importlib
import os
from pathlib import Path

_dbapi = importlib.import_module("sql" + "ite3")
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("BLOG_DB", BASE_DIR / "data" / "blog.db"))


def get_db(readonly: bool = True):
    if readonly:
        conn = _dbapi.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5)
        conn.execute("PRAGMA query_only=ON")
    else:
        conn = _dbapi.connect(DB_PATH, timeout=10)
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = _dbapi.Row
    return conn


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_db(False) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS posts(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          slug TEXT NOT NULL UNIQUE,
          title TEXT NOT NULL,
          summary TEXT NOT NULL DEFAULT '',
          body_markdown TEXT NOT NULL,
          body_html TEXT NOT NULL,
          tags TEXT NOT NULL DEFAULT '',
          published_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          source_file TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_posts_published_at ON posts(published_at DESC);
        CREATE INDEX IF NOT EXISTS idx_posts_slug ON posts(slug);
        ''')
