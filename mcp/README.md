# Postbridge MCP Publisher

`mcp/` provides an optional remote publisher for Postbridge.

The MCP server is deployment-neutral: the site URL, host validation, display name, executable paths, database path, OAuth state location, and token lifetimes are configured through the shared environment file rather than hardcoded into the source.

## Shared configuration

The MCP service can use the same unified environment file as the web and ntfy services:

```ini
EnvironmentFile=/etc/postbridge/.env
```

Relevant variables:

```ini
BLOG_SITE_NAME="Postbridge"
BLOG_SITE_URL=https://blog.example.com
BLOG_ROOT=/opt/postbridge
BLOG_DB=/var/lib/postbridge/blog.db
BLOG_POSTS_DIR=/var/lib/postbridge/posts
BLOG_TIMEZONE=UTC

MCP_PUBLIC_URL=https://blog.example.com
MCP_ALLOWED_HOSTS=blog.example.com
MCP_SERVER_NAME=postbridge-mcp
MCP_DISPLAY_NAME="Postbridge Publisher"
MCP_PORT=8766
MCP_TRUST_PROXY_HOPS=1
MCP_OAUTH_APPROVAL_KEY=
MCP_OAUTH_ISSUER=https://blog.example.com
MCP_OAUTH_RESOURCE=https://blog.example.com/mcp
MCP_OAUTH_STATE_FILE=/var/lib/postbridge/mcp-oauth-state.json
MCP_OAUTH_ACCESS_TOKEN_TTL_SECONDS=3600
MCP_OAUTH_REFRESH_TOKEN_TTL_SECONDS=2592000
MCP_OAUTH_AUTHORIZATION_CODE_TTL_SECONDS=300
MCP_MAX_REQUEST_BODY=4mb
```

See the repository root [`.env.example`](../.env.example) for the complete configuration.

## Connection

With the example configuration above:

- MCP endpoint: `${MCP_PUBLIC_URL}/mcp`
- OAuth issuer: `MCP_OAUTH_ISSUER` or `MCP_PUBLIC_URL` when omitted
- OAuth protected resource: `MCP_OAUTH_RESOURCE` or `${MCP_PUBLIC_URL}/mcp` when omitted
- OAuth scope: `blog:publish`
- Local listener: `127.0.0.1:${MCP_PORT}`
- Display name: `MCP_DISPLAY_NAME`

`MCP_ALLOWED_HOSTS` defaults to the hostname parsed from `MCP_PUBLIC_URL` when it is not explicitly set.

The public TLS endpoint should normally be provided by nginx, Caddy, Cloudflare Tunnel, or another reverse proxy while the Node.js process remains bound to localhost.

## Build

The MCP project requires Node.js 22 or later.

```bash
cd mcp
npm install
npm run typecheck
npm run build
```

Run the compiled server with the shared environment loaded:

```bash
set -a
. /etc/postbridge/.env
set +a

node dist/server.js
```

## Tool

The server exposes one tool:

```text
publish_blog(title, markdown, slug?, date?, tags?, summary?)
```

Arguments:

- `title`: article title without Markdown `#` markers
- `markdown`: body only; do not repeat the article title as an H1
- `slug`: optional stable lowercase kebab-case slug
- `date`: optional ISO 8601 publication timestamp with timezone
- `tags`: optional small set of article tags
- `summary`: optional short listing/meta summary

When the same explicit slug already exists, the article is updated rather than duplicated.

The publisher invokes the configured `BLOGCTL_PATH`, passes the configured database/site/post paths to the child process, and does not invoke a shell.

## MCP instructions

The MCP server tells connected clients to:

- call `publish_blog` only for explicit publish/update requests
- avoid repeating the article title as Markdown H1
- start body sections at `##`
- use concise summaries and a small tag set
- use stable kebab-case slugs when stable URLs matter
- never place credentials, private tokens, or server configuration in articles

The instructions and tool description use `MCP_PUBLIC_URL`, so they automatically follow the configured deployment URL.

## OAuth

The MCP endpoint is protected with an OAuth 2.1 authorization-code flow using PKCE (`S256`).

The approval page displays `MCP_DISPLAY_NAME` and `MCP_PUBLIC_URL` rather than a hardcoded site name or domain.

`MCP_OAUTH_APPROVAL_KEY` must be at least 32 characters and should be kept only in the root/service-readable environment file. Do not commit it to Git.

Generate a strong approval key with OpenSSL, for example:

```bash
openssl rand -hex 32
```

Then place the generated value in the shared environment file:

```ini
MCP_OAUTH_APPROVAL_KEY=<generated value>
```

This value is the **server-side approval key used on the OAuth authorization page**, not an OAuth access token. Access and refresh tokens are issued by the OAuth flow itself.

The implementation includes:

- authorization code + PKCE (`S256`)
- dynamic client registration for MCP client compatibility
- RFC 9207 `iss` in authorization responses
- short-lived access tokens
- rotating refresh tokens with replay invalidation
- configurable access/refresh/code TTLs
- hashed persisted OAuth token state
- Host header validation
- protected-resource and authorization-server metadata endpoints

## OAuth state

OAuth client/token state is stored at `MCP_OAUTH_STATE_FILE`.

The persisted state stores token hashes rather than raw access or refresh token values. The state path should be writable by the MCP service and should not be located in a public web directory.

## HTTP endpoints

The server exposes:

```text
/mcp
/health
/.well-known/oauth-protected-resource
/.well-known/oauth-protected-resource/mcp
/.well-known/oauth-authorization-server
/authorize
/token
/register
/revoke
```

The MCP transport itself accepts authenticated `POST` requests. Unsupported methods return `405`.

## Security model

The MCP server intentionally has a narrow role:

- it exposes no shell tool
- it exposes no arbitrary file tool
- it exposes no generic HTTP-fetch tool
- it exposes no delete/admin tool
- publication is delegated to one configured `blogctl` executable
- child processes receive only the small environment required for publishing
- the OAuth approval key is not forwarded to the publishing child process
- the Node process binds to localhost by default
- public TLS and request filtering can be handled by a reverse proxy

A hardened systemd deployment can additionally restrict filesystem access to the configured blog data/posts/state paths, drop Linux capabilities, and deny outbound networking except localhost when external network access is not required.

## Reverse proxy notes

When running behind a reverse proxy:

- set `MCP_TRUST_PROXY_HOPS` to match the proxy topology
- set `MCP_ALLOWED_HOSTS` to the public host or allowed host list
- forward the original `Host` and scheme
- keep OAuth/MCP responses uncached (`Cache-Control: no-store`)
- apply appropriate request size and rate limits at the proxy boundary

The exact proxy domain and configuration are deployment-specific and do not need to appear in the source code.
