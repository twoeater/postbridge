# Postbridge

<p align="center">
  <strong>English</strong> &nbsp;|&nbsp; <a href="README.ko.md">한국어</a>
</p>

---

Postbridge is a lightweight blog that stores Markdown documents in SQLite and renders them with Flask.

The web application treats published data as read-only. Articles are created and updated through a server-side CLI, an ntfy trigger, or the optional MCP publisher. The site name, public URL, data paths, ntfy settings, and MCP settings are all configurable through environment variables.

## Features

- Markdown publishing and HTML rendering
- SQLite-backed article storage
- Tags, search, Atom feed, and sitemap
- Canonical URLs, per-page meta descriptions, and `BlogPosting` JSON-LD
- CLI-based publish/update/delete operations
- Automatic publishing from ntfy messages and Markdown attachments
- Remote MCP publishing with OAuth 2.1 + PKCE
- A single `.env` file shared by the blog, ntfy publisher, and MCP publisher

## Project layout

```text
app/                    Flask web application
bin/blogctl              management CLI launcher
bin/blogctl.py           publish/delete implementation
bin/publish-stdin        stdin publishing helper
bin/ntfy-publisher       ntfy publisher launcher
bin/ntfy-publisher.py    ntfy polling/publishing implementation
bin/configure-ntfy-token ntfy credential setup helper
mcp/                     MCP publisher
scripts/                 deployment/helper scripts
posts/                   default Markdown source directory
data/                    default SQLite database directory
state/                   default runtime state directory
.env.example             unified environment configuration example
```

The actual data directories can be moved with `BLOG_DB`, `BLOG_POSTS_DIR`, and `BLOG_STATE_DIR`, so runtime data does not need to live inside the repository.

## Configuration

All components can share one environment file. Copy the example and adjust it for your deployment.

```bash
cp .env.example /etc/postbridge/.env
chmod 600 /etc/postbridge/.env
```

Important core settings include:

```ini
BLOG_SITE_NAME="Postbridge"
BLOG_SITE_URL=https://blog.example.com
BLOG_TIMEZONE=UTC
BLOG_LANGUAGE=en

BLOG_ROOT=/opt/postbridge
BLOG_DB=/var/lib/postbridge/blog.db
BLOG_POSTS_DIR=/var/lib/postbridge/posts
BLOG_STATE_DIR=/var/lib/postbridge/state
```

`BLOG_SITE_URL` is used as the base URL for published article URLs, canonical URLs, sitemap entries, and robots information. The actual site domain does not need to be hardcoded in the source.

See [`.env.example`](.env.example) for the complete set of supported variables and examples.

## Python environment

Example:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

The CLI launcher uses `${BLOG_ROOT}/.venv/bin/python` by default. Override it with `BLOG_PYTHON` when needed.

## Publishing

Publish from a file:

```bash
bin/blogctl publish --file /path/to/post.md
```

Publish from stdin:

```bash
cat <<'EOF' | bin/publish-stdin
---
title: "Example post"
summary: "Short summary"
tags: [linux, networking]
---

## Section

Markdown body.
EOF
```

You can also provide the title directly:

```bash
printf '%s\n' '## Hello' | \
  bin/blogctl publish --stdin --title 'Hello world' --slug hello-world
```

The CLI prints the resulting URL in the form `${BLOG_SITE_URL}/post/<slug>`.

## Management commands

```bash
bin/blogctl list
bin/blogctl publish --file FILE
bin/blogctl publish --stdin [OPTIONS]
bin/blogctl delete SLUG
```

Publishing again with the same `slug` updates the existing article's title, body, summary, and tags while preserving the original publication timestamp.

## Web application

The Flask application opens SQLite in read-only mode when serving public pages.

Example Gunicorn invocation:

```bash
set -a
. /etc/postbridge/.env
set +a

.venv/bin/gunicorn \
  --workers 2 \
  --bind 127.0.0.1:8765 \
  app:app
```

A typical deployment terminates TLS at nginx or another reverse proxy and forwards requests to `127.0.0.1:8765`.

## systemd and the unified `.env`

When running the web app, MCP publisher, and ntfy publisher as systemd services, all three services can read the same environment file:

```ini
EnvironmentFile=/etc/postbridge/.env
```

For example:

```text
postbridge.service
postbridge-mcp.service
postbridge-ntfy.service
        │
        └── /etc/postbridge/.env
```

Ready-to-use sample units are included under [`scripts/systemd/`](scripts/systemd/):

```text
scripts/systemd/postbridge.service
scripts/systemd/postbridge-mcp.service
scripts/systemd/postbridge-ntfy.service
```

The samples assume:

```text
/opt/postbridge       application source
/etc/postbridge/.env  shared environment file
/var/lib/postbridge   writable DB/posts/state
```

They run under a dedicated `postbridge` system user. Install them with:

```bash
sudo cp scripts/systemd/postbridge*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now postbridge.service
```

After configuring the optional publishers, enable them separately:

```bash
sudo systemctl enable --now postbridge-mcp.service
sudo systemctl enable --now postbridge-ntfy.service
```

See [`scripts/systemd/README.md`](scripts/systemd/README.md) for user, directory, and permission setup. The MCP sample expects Node.js at `/usr/bin/node`; adjust `ExecStart` when Node.js is installed elsewhere.

Service names and installation paths are examples and can be changed for a specific deployment.

## ntfy publisher

The ntfy publisher polls `NTFY_TOPIC` on `NTFY_BASE_URL` and converts new messages into blog posts.

Required settings:

```ini
NTFY_BASE_URL=https://ntfy.example.com
NTFY_TOPIC=blog-publish
NTFY_TOKEN=
```

Create `NTFY_TOKEN` in the ntfy web UI under **Account → Access tokens**, then place the generated access token in the unified `.env` file.

Behavior:

- ntfy `Title` → article title
- message body → Markdown body
- `.md` or `.markdown` attachment → Markdown body
- when both body and attachment are present, the contents are concatenated
- a first `# H1` identical to the ntfy title is removed automatically
- the last processed message ID is stored in `NTFY_STATE_FILE`
- on first startup, the current time is used as the cursor to avoid republishing all cached messages
- attachment URLs are restricted to HTTPS `/file/` URLs on the configured ntfy host

Related settings:

```ini
NTFY_POLL_INTERVAL=5
NTFY_STATE_FILE=/var/lib/postbridge/ntfy-last-id
NTFY_MAX_ATTACHMENT_BYTES=5242880
NTFY_USER_AGENT=postbridge-ntfy-publisher/2.0
NTFY_SERVICE_NAME=postbridge-ntfy.service
```

`bin/configure-ntfy-token` preserves unrelated settings in the unified `.env` file and updates only `NTFY_BASE_URL`, `NTFY_TOPIC`, and `NTFY_TOKEN`.

```bash
sudo bin/configure-ntfy-token /etc/postbridge/.env
```

## MCP publisher

The `mcp/` directory contains an optional publisher that allows remote MCP clients to publish blog articles.

The public MCP URL and display name are configurable:

```ini
MCP_PUBLIC_URL=https://blog.example.com
MCP_ALLOWED_HOSTS=blog.example.com
MCP_SERVER_NAME=postbridge-mcp
MCP_DISPLAY_NAME="Postbridge Publisher"
MCP_OAUTH_APPROVAL_KEY=
```

`MCP_OAUTH_APPROVAL_KEY` is the server-side secret used on the MCP OAuth approval page. It must be at least 32 characters long. You can generate a strong random value with OpenSSL:

```bash
openssl rand -hex 32
```

To generate a complete configuration line that can be pasted into the unified `.env` file, run:

```bash
echo "MCP_OAUTH_APPROVAL_KEY=$(openssl rand -hex 32)"
```

This is **not** an OAuth access token. It is the secret used to approve an OAuth connection, and it must never be committed to Git. OAuth access and refresh tokens are issued by the OAuth flow itself.

The default endpoint is `${MCP_PUBLIC_URL}/mcp`, and the server exposes one MCP tool:

```text
publish_blog(title, markdown, slug?, date?, tags?, summary?)
```

The MCP server does not expose shell, file, delete, or generic HTTP tools. Publishing is delegated only to the configured `BLOGCTL_PATH`.

See [`mcp/README.md`](mcp/README.md) for detailed MCP and OAuth documentation.

## Data and backups

It is recommended to keep these areas separate:

```text
application   BLOG_ROOT
SQLite        BLOG_DB
Markdown      BLOG_POSTS_DIR
runtime state BLOG_STATE_DIR
```

`BLOG_DB`, Markdown sources, and OAuth/ntfy state files can then be backed up independently from the application source.

## Security notes

- A real `.env` may contain an ntfy token and the MCP OAuth approval key. Never commit it to the repository.
- Restrict the `.env` file so that only root or the service account can read it.
- The public web application does not modify articles through HTTP requests.
- When exposing MCP to the internet, use a TLS reverse proxy together with Host validation, rate limits, and systemd sandboxing.

## Configuration example

The included `.env.example` is deployment-neutral and does not depend on a specific domain or installation path. Use it as the starting point for configuring the site identity, URLs, storage paths, ntfy publisher, and MCP publisher for a new installation.
