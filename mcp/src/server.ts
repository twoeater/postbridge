import { loadConfig } from "./config.js";
import { startHttpServer } from "./http-server.js";

const config = loadConfig();
const running = await startHttpServer(config);

console.log(`${config.serverName} listening on ${config.host}:${config.port}${config.endpoint}`);
console.log(`public resource: ${config.oauthResourceUrl}`);
console.log("authentication: OAuth 2.1 authorization code + PKCE, rotating refresh tokens");
console.log("tools: publish_blog");

let stopping = false;
async function stop(signal: string): Promise<void> {
  if (stopping) return;
  stopping = true;
  console.log(`received ${signal}; shutting down`);
  await running.close();
}

process.on("SIGINT", () => void stop("SIGINT"));
process.on("SIGTERM", () => void stop("SIGTERM"));
