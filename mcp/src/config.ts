import path from "node:path";
import { fileURLToPath } from "node:url";

export interface AppConfig {
  host: string;
  port: number;
  endpoint: string;
  publicUrl: string;
  siteName: string;
  serverName: string;
  displayName: string;
  allowedHosts: string[];
  trustProxyHops: number;
  oauthEnabled: boolean;
  oauthApprovalKey: string;
  oauthIssuerUrl: string;
  oauthResourceUrl: string;
  oauthStateFile: string;
  oauthAccessTokenTtlSeconds: number;
  oauthRefreshTokenTtlSeconds: number;
  oauthAuthorizationCodeTtlSeconds: number;
  maxRequestBody: string;
  blogRoot: string;
  blogCtl: string;
  blogDb: string;
  blogPostsDir: string;
  blogTimezone: string;
}

function intEnv(name: string, fallback: number, min: number, max = Number.MAX_SAFE_INTEGER): number {
  const raw = process.env[name]?.trim();
  if (!raw) return fallback;
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < min || value > max) {
    throw new Error(`${name} must be an integer between ${min} and ${max}`);
  }
  return value;
}

function secureUrl(value: string, name: string): string {
  const url = new URL(value);
  if (url.protocol !== "https:") throw new Error(`${name} must use HTTPS`);
  if (url.username || url.password || url.search || url.hash) {
    throw new Error(`${name} must not contain credentials, query, or fragment`);
  }
  return url.href;
}

export function loadConfig(): AppConfig {
  const defaultBlogRoot = fileURLToPath(new URL("../../", import.meta.url));
  const blogRoot = path.resolve(process.env.BLOG_ROOT?.trim() || defaultBlogRoot);
  const siteName = process.env.BLOG_SITE_NAME?.trim() || "Postbridge";
  const publicUrl = secureUrl(
    process.env.MCP_PUBLIC_URL?.trim() || process.env.BLOG_SITE_URL?.trim() || "https://example.com",
    "MCP_PUBLIC_URL",
  ).replace(/\/$/, "");
  const endpoint = "/mcp";
  const approvalKey = process.env.MCP_OAUTH_APPROVAL_KEY?.trim();
  if (!approvalKey || approvalKey.length < 32) {
    throw new Error("MCP_OAUTH_APPROVAL_KEY must be set and at least 32 characters");
  }

  const defaultStateDir = path.resolve(process.env.BLOG_STATE_DIR?.trim() || path.join(blogRoot, "state"));
  const publicHostname = new URL(publicUrl).hostname.toLowerCase();

  return {
    host: "127.0.0.1",
    port: intEnv("MCP_PORT", 8766, 1, 65535),
    endpoint,
    publicUrl,
    siteName,
    serverName: process.env.MCP_SERVER_NAME?.trim() || "postbridge-mcp",
    displayName: process.env.MCP_DISPLAY_NAME?.trim() || `${siteName} Publisher`,
    allowedHosts: (process.env.MCP_ALLOWED_HOSTS || publicHostname)
      .split(",")
      .map((v) => v.trim().toLowerCase())
      .filter(Boolean),
    trustProxyHops: intEnv("MCP_TRUST_PROXY_HOPS", 1, 0, 4),
    oauthEnabled: true,
    oauthApprovalKey: approvalKey,
    oauthIssuerUrl: secureUrl(
      process.env.MCP_OAUTH_ISSUER?.trim() || publicUrl,
      "MCP_OAUTH_ISSUER",
    ),
    oauthResourceUrl: secureUrl(
      process.env.MCP_OAUTH_RESOURCE?.trim() || `${publicUrl}${endpoint}`,
      "MCP_OAUTH_RESOURCE",
    ),
    oauthStateFile: path.resolve(
      process.env.MCP_OAUTH_STATE_FILE?.trim() || path.join(defaultStateDir, "mcp-oauth-state.json"),
    ),
    oauthAccessTokenTtlSeconds: intEnv("MCP_OAUTH_ACCESS_TOKEN_TTL_SECONDS", 3600, 300),
    oauthRefreshTokenTtlSeconds: intEnv(
      "MCP_OAUTH_REFRESH_TOKEN_TTL_SECONDS",
      30 * 24 * 3600,
      3600,
    ),
    oauthAuthorizationCodeTtlSeconds: intEnv(
      "MCP_OAUTH_AUTHORIZATION_CODE_TTL_SECONDS",
      300,
      60,
      900,
    ),
    maxRequestBody: process.env.MCP_MAX_REQUEST_BODY?.trim() || "4mb",
    blogRoot,
    blogCtl: path.resolve(process.env.BLOGCTL_PATH?.trim() || path.join(blogRoot, "bin", "blogctl")),
    blogDb: path.resolve(process.env.BLOG_DB?.trim() || path.join(blogRoot, "data", "blog.db")),
    blogPostsDir: path.resolve(
      process.env.BLOG_POSTS_DIR?.trim() || path.join(blogRoot, "posts"),
    ),
    blogTimezone: process.env.BLOG_TIMEZONE?.trim() || "UTC",
  };
}
