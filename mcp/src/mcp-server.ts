import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import * as z from "zod/v4";
import { publishBlog } from "./publisher.js";
import { PUBLISH_ANNOTATIONS, TOOL_AUTH_META } from "./tool-metadata.js";
import type { AppConfig } from "./config.js";

function instructions(config: AppConfig): string {
  return `This MCP server publishes Markdown articles to ${config.publicUrl}.
Use publish_blog only when the user explicitly asks to publish or update an article.
The title is rendered separately by the blog, so do not repeat it as a Markdown H1. Start body sections at ##.
Use a concise summary and a small set of relevant tags; prefer existing broad tags over near-duplicates.
Use an explicit lowercase kebab-case slug when stable URLs matter. The same slug updates the existing article.
Never put credentials, secrets, private tokens, or internal server configuration into an article.`;
}


export function createMcpServer(config: AppConfig): McpServer {
  const server = new McpServer(
    { name: config.serverName, version: "0.1.0" },
    { instructions: instructions(config) },
  );

  server.registerTool(
    "publish_blog",
    {
      title: "Publish blog article",
      description:
        `Publish a Markdown article to ${config.publicUrl}. Call only when the user explicitly requests publication or an update. The blog renders title separately; markdown must not repeat the same title as H1. The same slug updates the existing article.`,
      inputSchema: {
        title: z
          .string()
          .trim()
          .min(1)
          .max(200)
          .describe("Article title, without Markdown # markers."),
        slug: z
          .string()
          .trim()
          .min(1)
          .max(150)
          .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/)
          .optional()
          .describe("Optional stable URL slug using lowercase ASCII letters, digits, and hyphens."),
        date: z
          .string()
          .trim()
          .max(64)
          .optional()
          .refine((value) => value === undefined || !Number.isNaN(Date.parse(value)), "date must be parseable ISO 8601")
          .describe("Optional ISO 8601 publication timestamp including timezone offset."),
        tags: z
          .array(z.string().trim().min(1).max(40))
          .max(10)
          .optional()
          .describe("0-10 concise tags. Prefer existing broad tags over synonyms or near-duplicates."),
        summary: z
          .string()
          .trim()
          .max(500)
          .optional()
          .describe("Short article summary used in listings."),
        markdown: z
          .string()
          .min(1)
          .max(1_000_000)
          .describe("Markdown article body. Do not include YAML front matter or repeat the title as a # H1. Start top-level body sections at ##."),
      },
      annotations: PUBLISH_ANNOTATIONS,
      _meta: TOOL_AUTH_META,
    },
    async (input) => {
      try {
        const result = await publishBlog(input, config);
        const payload = { success: true, slug: result.slug, url: result.url };
        return {
          content: [{ type: "text", text: JSON.stringify(payload) }],
          structuredContent: payload,
        };
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        return {
          isError: true,
          content: [{ type: "text", text: `Publish failed: ${message}` }],
        };
      }
    },
  );

  return server;
}
