import { timingSafeEqual } from "node:crypto";
import type { RequestHandler } from "express";
import type { OAuthTokenVerifier } from "@modelcontextprotocol/sdk/server/auth/provider.js";
import type { AppConfig } from "./config.js";

export function tokensEqual(actual: string, expected: string): boolean {
  const a = Buffer.from(actual);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

function resourceMetadataUrl(config: AppConfig): string {
  const resource = new URL(config.oauthResourceUrl);
  return new URL(`/.well-known/oauth-protected-resource${resource.pathname}`, resource).href;
}

export function createBearerAuth(config: AppConfig, verifier: OAuthTokenVerifier): RequestHandler {
  return async (request, response, next) => {
    const match = request.header("authorization")?.match(/^Bearer\s+(.+)$/i);
    const token = match?.[1];
    if (token) {
      try {
        const auth = await verifier.verifyAccessToken(token);
        if (
          auth.expiresAt !== undefined &&
          auth.expiresAt >= Date.now() / 1000 &&
          auth.resource?.href === config.oauthResourceUrl &&
          auth.scopes.includes("blog:publish")
        ) {
          next();
          return;
        }
      } catch {
        // Return the same challenge for every invalid or expired token.
      }
    }

    response
      .status(401)
      .set(
        "WWW-Authenticate",
        `Bearer realm="${config.serverName}", error="invalid_token", scope="blog:publish", resource_metadata="${resourceMetadataUrl(config)}"`,
      )
      .set("Cache-Control", "no-store")
      .json({
        jsonrpc: "2.0",
        error: { code: -32001, message: "Unauthorized" },
        id: null,
      });
  };
}

export function createHostValidation(config: AppConfig): RequestHandler {
  return (request, response, next) => {
    let hostname = "";
    try {
      hostname = new URL(`http://${request.header("host") || ""}`).hostname.toLowerCase();
    } catch {
      // Rejected below.
    }
    if (!config.allowedHosts.includes(hostname)) {
      response.status(403).json({
        jsonrpc: "2.0",
        error: { code: -32002, message: "Host header is not allowed" },
        id: null,
      });
      return;
    }
    next();
  };
}
