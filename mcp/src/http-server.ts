import type { Server as HttpServer } from "node:http";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import {
  createOAuthMetadata,
  mcpAuthRouter,
  type AuthRouterOptions,
} from "@modelcontextprotocol/sdk/server/auth/router.js";
import express, { type Request, type Response } from "express";
import { createBearerAuth, createHostValidation } from "./auth.js";
import type { AppConfig } from "./config.js";
import { createMcpServer } from "./mcp-server.js";
import { OAUTH_SCOPES, BlogOAuthProvider } from "./oauth.js";

function rpcError(response: Response, status: number, message: string): void {
  response
    .status(status)
    .set("Cache-Control", "no-store")
    .json({ jsonrpc: "2.0", error: { code: -32000, message }, id: null });
}

export async function startHttpServer(
  config: AppConfig,
): Promise<{ httpServer: HttpServer; close: () => Promise<void> }> {
  const app = express();
  app.disable("x-powered-by");
  app.set("trust proxy", config.trustProxyHops);
  app.use((_request, response, next) => {
    response.set({
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
      "Cache-Control": "no-store",
    });
    next();
  });
  app.use(createHostValidation(config));

  const oauth = new BlogOAuthProvider(config);
  const resourceMetadata = {
    resource: oauth.resourceUrl.href,
    authorization_servers: [oauth.issuerUrl.href],
    scopes_supported: [...OAUTH_SCOPES],
    bearer_methods_supported: ["header"],
    resource_name: config.displayName,
  };

  app.get("/.well-known/oauth-protected-resource", (_request, response) => {
    response.set("Access-Control-Allow-Origin", "*").json(resourceMetadata);
  });
  app.get("/.well-known/oauth-protected-resource/mcp", (_request, response) => {
    response.set("Access-Control-Allow-Origin", "*").json(resourceMetadata);
  });

  const oauthOptions = {
    provider: oauth,
    issuerUrl: oauth.issuerUrl,
    resourceServerUrl: oauth.resourceUrl,
    scopesSupported: [...OAUTH_SCOPES],
    resourceName: config.displayName,
  } satisfies AuthRouterOptions;

  const oauthMetadata = {
    ...createOAuthMetadata(oauthOptions),
    revocation_endpoint_auth_methods_supported: ["client_secret_post", "none"],
  };
  app.get("/.well-known/oauth-authorization-server", (_request, response) => {
    response.set("Access-Control-Allow-Origin", "*").json(oauthMetadata);
  });
  app.use(mcpAuthRouter(oauthOptions));

  const authenticate = createBearerAuth(config, oauth);
  const parseJson = express.json({ limit: config.maxRequestBody, strict: true });

  app.get("/health", (_request, response) => {
    response.json({
      status: "ok",
      service: config.serverName,
      oauth: true,
      tools: ["publish_blog"],
    });
  });

  app.post(
    config.endpoint,
    authenticate,
    parseJson,
    async (request: Request, response: Response) => {
      const transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: undefined,
        enableJsonResponse: true,
      });
      const server = createMcpServer(config);
      try {
        await server.connect(transport);
        await transport.handleRequest(request, response, request.body);
      } catch (error) {
        console.error(
          "MCP request failed",
          error instanceof Error ? error.message : String(error),
        );
        if (!response.headersSent) rpcError(response, 500, "Internal MCP server error");
      } finally {
        await server.close().catch(() => undefined);
      }
    },
  );

  const methodNotAllowed = (_request: Request, response: Response) => {
    response.set("Allow", "POST");
    rpcError(response, 405, "Stateless MCP accepts POST only");
  };
  app.get(config.endpoint, authenticate, methodNotAllowed);
  app.delete(config.endpoint, authenticate, methodNotAllowed);

  app.use(
    (
      error: unknown,
      _request: Request,
      response: Response,
      _next: express.NextFunction,
    ) => {
      if (!response.headersSent) {
        rpcError(
          response,
          400,
          `Invalid request: ${error instanceof Error ? error.message : String(error)}`,
        );
      }
    },
  );

  const httpServer = await new Promise<HttpServer>((resolve, reject) => {
    const server = app.listen(config.port, config.host, () => resolve(server));
    server.once("error", reject);
  });

  return {
    httpServer,
    close: () =>
      new Promise<void>((resolve, reject) =>
        httpServer.close((error) => (error ? reject(error) : resolve())),
      ),
  };
}
