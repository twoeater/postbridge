from __future__ import annotations

import math
import os
import secrets
from datetime import datetime, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from flask import Flask, abort, g, make_response, render_template, request

from .db import get_db

app = Flask(__name__)
site_name = os.environ.get("BLOG_SITE_NAME", "Postbridge").strip() or "Postbridge"
site_url = os.environ.get("BLOG_SITE_URL", "http://127.0.0.1:8765").strip().rstrip("/")
app.config.update(
    SITE_NAME=site_name,
    SITE_DESCRIPTION=os.environ.get("BLOG_SITE_DESCRIPTION", "notes."),
    SITE_META_DESCRIPTION=os.environ.get(
        "BLOG_SITE_META_DESCRIPTION", f"Articles and notes from {site_name}."
    ),
    SITE_URL=site_url,
    SITE_LANGUAGE=os.environ.get("BLOG_LANGUAGE", "en").strip() or "en",
    POSTS_PER_PAGE=int(os.environ.get("BLOG_POSTS_PER_PAGE", "10")),
)

LOCAL_TZ = ZoneInfo(os.environ.get("BLOG_TIMEZONE", "UTC"))


@app.before_request
def prepare_security_context():
    # A fresh nonce lets the JSON-LD block remain inline without enabling
    # unsafe-inline for executable JavaScript.
    g.csp_nonce = secrets.token_urlsafe(24)


@app.after_request
def add_security_headers(response):
    nonce = getattr(g, "csp_nonce", "")
    response.headers["Content-Security-Policy"] = "; ".join(
        [
            "default-src 'self'",
            "base-uri 'self'",
            "object-src 'none'",
            "frame-ancestors 'none'",
            "form-action 'self'",
            f"script-src 'self' 'nonce-{nonce}'",
            "style-src 'self'",
            "img-src 'self' data:",
            "font-src 'self'",
            "connect-src 'self'",
            "media-src 'self'",
            "manifest-src 'self'",
        ]
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


def parse_tags(value: str):
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_iso(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def local_date(value: str) -> str:
    return parse_iso(value).astimezone(LOCAL_TZ).strftime("%Y-%m-%d")


def add_display_fields(row):
    data = dict(row)
    data["tag_list"] = parse_tags(data.get("tags", ""))
    if data.get("published_at"):
        data["published_date"] = local_date(data["published_at"])
    if data.get("updated_at"):
        data["updated_date"] = local_date(data["updated_at"])
    return data


@app.get("/healthz")
def healthz():
    with get_db() as db:
        db.execute("SELECT 1").fetchone()
    return {"status": "ok"}


@app.get("/")
def index():
    page = max(1, request.args.get("page", 1, type=int))
    per_page = app.config["POSTS_PER_PAGE"]
    offset = (page - 1) * per_page
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        rows = db.execute(
            """
            SELECT slug,title,summary,tags,published_at,updated_at
            FROM posts
            ORDER BY published_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (per_page, offset),
        ).fetchall()
    pages = max(1, math.ceil(total / per_page))
    if page > pages and total:
        abort(404)
    canonical_url = app.config["SITE_URL"] + "/"
    if page > 1:
        canonical_url += f"?page={page}"
    return render_template(
        "index.html",
        posts=[add_display_fields(row) for row in rows],
        page=page,
        pages=pages,
        meta_description=app.config["SITE_META_DESCRIPTION"],
        canonical_url=canonical_url,
    )


@app.get("/post/<slug>")
def post(slug):
    with get_db() as db:
        row = db.execute("SELECT * FROM posts WHERE slug = ?", (slug,)).fetchone()
    if not row:
        abort(404)
    post_data = add_display_fields(row)
    canonical_url = f'{app.config["SITE_URL"]}/post/{post_data["slug"]}'
    structured_data = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": post_data["title"],
        "datePublished": post_data["published_at"],
        "dateModified": post_data["updated_at"],
        "url": canonical_url,
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical_url},
        "inLanguage": app.config["SITE_LANGUAGE"],
        "isPartOf": {
            "@type": "Blog",
            "name": app.config["SITE_NAME"],
            "url": app.config["SITE_URL"] + "/",
        },
    }
    if post_data.get("summary"):
        structured_data["description"] = post_data["summary"]
    return render_template(
        "post.html",
        post=post_data,
        meta_description=post_data.get("summary") or app.config["SITE_META_DESCRIPTION"],
        canonical_url=canonical_url,
        structured_data=structured_data,
    )


@app.get("/tag/<tag>")
def tag(tag):
    with get_db() as db:
        rows = db.execute(
            """
            SELECT slug,title,summary,tags,published_at,updated_at
            FROM posts
            WHERE ',' || replace(tags, ', ', ',') || ',' LIKE ?
            ORDER BY published_at DESC, id DESC
            """,
            (f"%,{tag},%",),
        ).fetchall()
    return render_template(
        "tag.html",
        tag=tag,
        posts=[add_display_fields(row) for row in rows],
        meta_description=f"{app.config['SITE_NAME']}의 #{tag} 관련 게시글 모음.",
        canonical_url=f"{app.config['SITE_URL']}{request.path}",
    )


@app.get("/search")
def search():
    q = request.args.get("q", "").strip()
    posts = []
    if q:
        like = f"%{q}%"
        with get_db() as db:
            rows = db.execute(
                """
                SELECT slug,title,summary,tags,published_at,updated_at
                FROM posts
                WHERE title LIKE ? OR summary LIKE ? OR body_markdown LIKE ?
                ORDER BY published_at DESC, id DESC
                LIMIT 50
                """,
                (like, like, like),
            ).fetchall()
        posts = [add_display_fields(row) for row in rows]
    response = make_response(
        render_template(
            "search.html",
            q=q,
            posts=posts,
            meta_description=f"{app.config['SITE_NAME']} 게시글 검색.",
            robots_meta="noindex,follow",
        )
    )
    response.headers["X-Robots-Tag"] = "noindex, follow"
    return response


@app.get("/feed.xml")
def feed():
    with get_db() as db:
        rows = db.execute(
            """
            SELECT slug,title,summary,published_at,updated_at
            FROM posts
            ORDER BY published_at DESC, id DESC
            LIMIT 20
            """
        ).fetchall()
    response = make_response(render_template("feed.xml", posts=rows))
    response.headers["Content-Type"] = "application/atom+xml; charset=utf-8"
    return response


@app.get("/robots.txt")
def robots():
    body = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            f'Sitemap: {app.config["SITE_URL"]}/sitemap.xml',
            "",
        ]
    )
    response = make_response(body)
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    return response


@app.get("/sitemap.xml")
def sitemap():
    with get_db() as db:
        rows = db.execute(
            "SELECT slug,updated_at FROM posts ORDER BY updated_at DESC, id DESC"
        ).fetchall()
    home_lastmod = rows[0]["updated_at"] if rows else None
    response = make_response(
        render_template("sitemap.xml", posts=rows, home_lastmod=home_lastmod)
    )
    response.headers["Content-Type"] = "application/xml; charset=utf-8"
    return response


@app.context_processor
def common():
    return {
        "site_name": app.config["SITE_NAME"],
        "site_description": app.config["SITE_DESCRIPTION"],
        "site_meta_description": app.config["SITE_META_DESCRIPTION"],
        "site_url": app.config["SITE_URL"],
        "site_host": urlparse(app.config["SITE_URL"]).netloc or app.config["SITE_URL"],
        "site_language": app.config["SITE_LANGUAGE"],
        "current_year": datetime.now(LOCAL_TZ).year,
        "csp_nonce": getattr(g, "csp_nonce", ""),
    }
