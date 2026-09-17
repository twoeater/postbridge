#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.content import render_markdown
from app.db import get_db, init_db

POSTS_DIR = Path(os.environ.get("BLOG_POSTS_DIR", ROOT / "posts"))
SITE_URL = os.environ.get("BLOG_SITE_URL", "http://127.0.0.1:8765").rstrip("/")
LOCAL_TZ = ZoneInfo(os.environ.get("BLOG_TIMEZONE", "UTC"))


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_iso_utc(value: object) -> str:
    """Normalize an ISO-8601 value to a UTC timestamp ending in Z.

    Date-only or timezone-naive values are interpreted as Korea Standard Time,
    because this blog's configured publication timezone is used for human-entered dates.
    """
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, time.min)
    else:
        text = str(value).strip()
        if not text:
            raise ValueError("publication date is empty")
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"invalid ISO 8601 publication date: {value}") from exc

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)

    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9가-힣]+", "-", value.strip().lower(), flags=re.UNICODE).strip("-")
    return value or datetime.now(LOCAL_TZ).strftime("post-%Y%m%d-%H%M%S")


def parse_md(text: str) -> tuple[dict, str]:
    if text.startswith("---\n"):
        parts = text.split("---\n", 2)
        if len(parts) == 3:
            return yaml.safe_load(parts[1]) or {}, parts[2].lstrip("\n")
    return {}, text


def publish(args) -> None:
    if args.stdin:
        text = sys.stdin.read()
        source = "stdin"
    else:
        src = Path(args.file).resolve()
        text = src.read_text(encoding="utf-8")
        source = str(src)

    meta, body = parse_md(text)
    title = args.title or meta.get("title")
    if not title:
        raise SystemExit("title is required (--title or YAML front matter)")

    slug = slugify(args.slug or meta.get("slug") or title)
    summary = args.summary if args.summary is not None else str(meta.get("summary", ""))

    tag_value = args.tags if args.tags is not None else meta.get("tags", [])
    if isinstance(tag_value, list):
        tags = ",".join(str(item).strip() for item in tag_value if str(item).strip())
    else:
        tags = ",".join(item.strip() for item in str(tag_value).split(",") if item.strip())

    try:
        published = normalize_iso_utc(meta.get("date") or args.date or now_iso())
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    updated = now_iso()

    init_db()
    with get_db(False) as db:
        existing = db.execute("SELECT published_at FROM posts WHERE slug = ?", (slug,)).fetchone()
        original_published = normalize_iso_utc(existing[0]) if existing else published
        db.execute(
            """
            INSERT INTO posts(
                slug,title,summary,body_markdown,body_html,tags,
                published_at,updated_at,source_file
            ) VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(slug) DO UPDATE SET
                title=excluded.title,
                summary=excluded.summary,
                body_markdown=excluded.body_markdown,
                body_html=excluded.body_html,
                tags=excluded.tags,
                updated_at=excluded.updated_at,
                source_file=excluded.source_file
            """,
            (
                slug,
                title,
                summary,
                body,
                render_markdown(body),
                tags,
                original_published,
                updated,
                source,
            ),
        )

    POSTS_DIR.mkdir(exist_ok=True)
    target = POSTS_DIR / f"{slug}.md"
    front = {
        "title": title,
        "slug": slug,
        "date": original_published,
        "summary": summary,
        "tags": [item for item in tags.split(",") if item],
    }
    target.write_text(
        "---\n"
        + yaml.safe_dump(front, allow_unicode=True, sort_keys=False)
        + "---\n\n"
        + body.rstrip()
        + "\n",
        encoding="utf-8",
    )
    print(f"published: {slug} -> {SITE_URL}/post/{slug}")


def list_posts(_args) -> None:
    init_db()
    with get_db(False) as db:
        rows = db.execute(
            "SELECT slug,title,published_at FROM posts ORDER BY published_at DESC, id DESC"
        ).fetchall()
    for row in rows:
        print(f"{row['published_at']}\t{row['slug']}\t{row['title']}")


def rebuild_html(_args) -> None:
    """Re-render and sanitize HTML for all existing posts."""
    init_db()
    with get_db(False) as db:
        rows = db.execute("SELECT id, body_markdown FROM posts").fetchall()
        for row in rows:
            db.execute(
                "UPDATE posts SET body_html = ? WHERE id = ?",
                (render_markdown(row["body_markdown"]), row["id"]),
            )
    print(f"rebuilt html: {len(rows)} post(s)")


def delete(args) -> None:
    init_db()
    with get_db(False) as db:
        cur = db.execute("DELETE FROM posts WHERE slug = ?", (args.slug,))
    path = POSTS_DIR / f"{args.slug}.md"
    path.unlink(missing_ok=True)
    print(("deleted" if cur.rowcount else "not found"), args.slug)


def main() -> None:
    parser = argparse.ArgumentParser(description="Postbridge Markdown publisher")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")

    pub = sub.add_parser("publish")
    source = pub.add_mutually_exclusive_group(required=True)
    source.add_argument("--file")
    source.add_argument("--stdin", action="store_true")
    pub.add_argument("--title")
    pub.add_argument("--slug")
    pub.add_argument("--summary")
    pub.add_argument("--tags")
    pub.add_argument("--date")

    sub.add_parser("list")
    sub.add_parser("rebuild-html")
    remove = sub.add_parser("delete")
    remove.add_argument("slug")

    args = parser.parse_args()
    if args.cmd == "init":
        init_db()
        print("initialized")
    elif args.cmd == "publish":
        publish(args)
    elif args.cmd == "list":
        list_posts(args)
    elif args.cmd == "rebuild-html":
        rebuild_html(args)
    elif args.cmd == "delete":
        delete(args)


if __name__ == "__main__":
    main()
