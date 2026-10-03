// `pnpm setup`: first-time setup. Checks tools, installs deps, runs DB migrations, builds the widget.
import { spawnSync } from "node:child_process";
import { copyFileSync, existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const api = join(root, "services", "api");
const ok = (m) => console.log(`\x1b[32m✔\x1b[0m ${m}`);
const bad = (m) => console.log(`\x1b[31m✖\x1b[0m ${m}`);
const step = (m) => console.log(`\n\x1b[35m▸ ${m}\x1b[0m`);
const sh = (cmd, args, cwd = root) => spawnSync(cmd, args, { cwd, stdio: "inherit", shell: true }).status === 0;
const has = (cmd) => spawnSync(cmd, ["--version"], { shell: true, stdio: "ignore" }).status === 0;

step("Checking tools");
let missing = false;
for (const [cmd, hint] of [["node", "https://nodejs.org (v20+)"], ["pnpm", "npm i -g pnpm"], ["uv", "https://docs.astral.sh/uv/ (installs Python 3.12 for you)"]]) {
  if (has(cmd)) ok(cmd);
  else { bad(`${cmd} not found → ${hint}`); missing = true; }
}
if (missing) process.exit(1);

step("Environment");
if (!existsSync(join(root, ".env"))) {
  copyFileSync(join(root, ".env.example"), join(root, ".env"));
  ok("Created .env from .env.example. Fill in DATABASE_URL, GROQ_API_KEY and the Clerk keys, then re-run `pnpm setup`.");
}
const env = readFileSync(join(root, ".env"), "utf8");
const val = (k) => (env.match(new RegExp(`^${k}=(.*)$`, "m"))?.[1] || "").trim();
for (const k of ["DATABASE_URL", "UNISONA_MASTER_KEY", "GROQ_API_KEY", "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "CLERK_SECRET_KEY"]) {
  val(k) ? ok(k) : bad(`${k} is empty${k === "UNISONA_MASTER_KEY" ? " (generate: uv run python -c \"import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())\")" : ""}`);
}

step("Installing JS dependencies (pnpm)");
if (!sh("pnpm", ["install"])) process.exit(1);
step("Installing Python dependencies (uv)");
if (!sh("uv", ["sync", "--all-extras"], api)) process.exit(1);
step("Syncing web env");
sh("node", [join("scripts", "sync-env.mjs")]);
step("Running database migrations");
if (!val("DATABASE_URL")) bad("Skipped: DATABASE_URL not set");
else if (!sh("uv", ["run", "alembic", "upgrade", "head"], api)) bad("Migration failed. Check DATABASE_URL (use the Supabase *session* pooler, port 5432).");
step("Building the embeddable widget");
sh("pnpm", ["--filter", "widget", "build"]);

console.log("\n\x1b[32mSetup complete.\x1b[0m Start everything with \x1b[1mpnpm dev\x1b[0m (or see README for separate terminals).\n");
