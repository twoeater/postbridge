import { spawn } from "node:child_process";
import type { AppConfig } from "./config.js";

export interface PublishInput {
  title: string;
  markdown: string;
  slug?: string;
  summary?: string;
  tags?: string[];
  date?: string;
}

function stripFrontMatter(text: string): string {
  const normalized = text.replace(/\r\n/g, "\n");
  if (!normalized.startsWith("---\n")) return normalized;
  const end = normalized.indexOf("\n---\n", 4);
  return end === -1 ? normalized : normalized.slice(end + 5).replace(/^\n+/, "");
}

function stripDuplicateH1(title: string, text: string): string {
  const body = stripFrontMatter(text).replace(/^\n+/, "");
  const [first = "", ...rest] = body.split("\n");
  if (first.startsWith("# ") && first.slice(2).trim() === title.trim()) {
    return rest.join("\n").replace(/^\n+/, "");
  }
  return body;
}

export async function publishBlog(
  input: PublishInput,
  config: AppConfig,
): Promise<{ slug: string; url: string }> {
  const body = stripDuplicateH1(input.title, input.markdown).trimEnd() + "\n";
  if (!body.trim()) throw new Error("markdown body is empty");

  const args = ["publish", "--stdin", "--title", input.title];
  if (input.slug) args.push("--slug", input.slug);
  if (input.summary !== undefined) args.push("--summary", input.summary);
  if (input.tags?.length) args.push("--tags", input.tags.join(","));
  if (input.date) args.push("--date", input.date);

  const output = await new Promise<string>((resolve, reject) => {
    const child = spawn(config.blogCtl, args, {
      cwd: config.blogRoot,
      stdio: ["pipe", "pipe", "pipe"],
      env: {
        PATH: "/usr/bin:/bin",
        LANG: "C.UTF-8",
        BLOG_DB: config.blogDb,
        BLOG_SITE_URL: config.publicUrl,
        BLOG_SITE_NAME: config.siteName,
        BLOG_POSTS_DIR: config.blogPostsDir,
        BLOG_TIMEZONE: config.blogTimezone,
      },
      timeout: 60_000,
    });

    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
      if (stdout.length > 16_384) child.kill("SIGKILL");
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
      if (stderr.length > 16_384) child.kill("SIGKILL");
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) resolve(stdout.trim());
      else reject(new Error((stderr || stdout || `blogctl exited with ${code}`).trim().slice(0, 2000)));
    });
    child.stdin.end(body, "utf8");
  });

  const match = output.match(/^published:\s+([^\s]+)\s+->\s+(https:\/\/[^\s]+)$/m);
  if (!match) throw new Error("blogctl returned an unexpected success response");
  return { slug: match[1], url: match[2] };
}
