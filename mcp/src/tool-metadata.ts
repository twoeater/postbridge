import type { ToolAnnotations } from "@modelcontextprotocol/sdk/types.js";

export const OAUTH_SCOPES = ["blog:publish"] as const;

export const PUBLISH_ANNOTATIONS = {
  readOnlyHint: false,
  destructiveHint: false,
  idempotentHint: false,
  openWorldHint: false,
} as const satisfies ToolAnnotations;

export const TOOL_AUTH_META = {
  securitySchemes: [{ type: "oauth2" as const, scopes: [...OAUTH_SCOPES] }],
};
