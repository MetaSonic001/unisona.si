// Copies the variables the web app needs from the root .env into apps/web/.env.local.
// Runs automatically before `pnpm dev` / `pnpm build`. One .env for the whole repo.
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, ".env");
if (!existsSync(src)) {
  console.error("✖ No .env at repo root. Copy .env.example to .env and fill it in.");
  process.exit(1);
}
const wanted = /^(NEXT_PUBLIC_|CLERK_|DEV_MODE|DEV_TOKEN|DEV_AUTH_BYPASS|API_URL|APP_URL|UNISONA_ENV)/;
const lines = readFileSync(src, "utf8").split(/\r?\n/).filter((l) => wanted.test(l.trim()));
const env = Object.fromEntries(lines.map((l) => [l.split("=")[0], l.slice(l.indexOf("=") + 1)]));
if (!env.NEXT_PUBLIC_API_URL) lines.push(`NEXT_PUBLIC_API_URL=${env.API_URL || "http://127.0.0.1:8000"}`);
writeFileSync(join(root, "apps", "web", ".env.local"), `# Generated from ../../.env by scripts/sync-env.mjs — edit the root .env instead\n${lines.join("\n")}\n`);
console.log(`✔ Synced ${lines.length} web env vars from root .env`);
