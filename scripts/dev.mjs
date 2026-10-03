// `pnpm dev`: one terminal, everything. Starts the API (FastAPI + worker + scheduler) and the web app
// with labelled, coloured output. Ctrl+C stops both. Prefer separate terminals? See README → "Running".
import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { createServer } from "node:net";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const c = { api: "\x1b[35m", web: "\x1b[36m", widget: "\x1b[33m", dim: "\x1b[2m", reset: "\x1b[0m", red: "\x1b[31m", green: "\x1b[32m" };
const log = (tag, msg) => console.log(`${c[tag] || ""}[${tag.padEnd(6)}]${c.reset} ${msg}`);

console.log(`\n${c.api}  ◆ unisona${c.reset}  dev runner\n`);
if (!existsSync(join(root, ".env"))) {
  console.error(`${c.red}✖ No .env found. Run: cp .env.example .env  (then add GROQ_API_KEY, DATABASE_URL, Clerk keys)${c.reset}`);
  process.exit(1);
}
spawnSync(process.execPath, [join(root, "scripts", "sync-env.mjs")], { stdio: "inherit" });

// Call the workspace's local binaries directly so this works from pnpm, npm, bun or plain node,
// even when pnpm itself isn't on PATH.
const bin = (app, name) => `"${join(root, "apps", app, "node_modules", ".bin", process.platform === "win32" ? `${name}.CMD` : name)}"`;
for (const [app, name] of [["web", "next"], ["widget", "vite"]]) {
  if (!existsSync(join(root, "apps", app, "node_modules", ".bin", name))) {
    console.error(`${c.red}✖ apps/${app} dependencies are missing. Run: pnpm install  (or: npx pnpm install)${c.reset}`);
    process.exit(1);
  }
}

if (!existsSync(join(root, "apps", "widget", "dist", "widget.js"))) {
  log("widget", "building embeddable widget (first run only)…");
  spawnSync(`${bin("widget", "vite")} build`, { cwd: join(root, "apps", "widget"), stdio: "inherit", shell: true });
}

const portBusy = (port, host) =>
  new Promise((res) => {
    const s = createServer().once("error", () => res(true)).once("listening", () => s.close(() => res(false)));
    s.listen(port, host);
  });
for (const [port, host, what] of [[8000, "127.0.0.1", "API"], [3000, "::", "web app"]]) {
  if (await portBusy(port, host)) {
    console.error(`${c.red}✖ Port ${port} (${what}) is already in use, probably a previous run that didn't exit.${c.reset}`);
    console.error(process.platform === "win32"
      ? `  Find it:  netstat -ano | findstr :${port}     Stop it:  taskkill /PID <pid> /T /F`
      : `  Stop it:  lsof -ti :${port} | xargs kill`);
    process.exit(1);
  }
}

const procs = [];
function run(tag, command, cwd) {
  log(tag, `${c.dim}starting: ${command}${c.reset}`);
  const p = spawn(command, { cwd, shell: true, env: { ...process.env, FORCE_COLOR: "1", PYTHONUNBUFFERED: "1" } });
  const pipe = (stream) => {
    let buf = "";
    stream.on("data", (d) => {
      buf += d.toString();
      const lines = buf.split(/\r?\n/);
      buf = lines.pop();
      for (const l of lines) if (l.trim()) log(tag, l);
    });
  };
  pipe(p.stdout);
  pipe(p.stderr);
  p.on("exit", (code) => {
    log(tag, code === 0 ? "stopped" : `${c.red}exited with code ${code}${c.reset}`);
    if (!shuttingDown) {
      console.log(`${c.red}✖ ${tag} stopped, shutting down the rest. Fix the error above (port busy? run the ${tag} alone to see it).${c.reset}`);
      shutdown(code ?? 1);
    }
  });
  procs.push(p);
}

let shuttingDown = false;
function shutdown(code = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const p of procs) {
    if (p.exitCode !== null) continue;
    if (process.platform === "win32") spawnSync("taskkill", ["/pid", String(p.pid), "/T", "/F"], { stdio: "ignore" });
    else p.kill("SIGTERM");
  }
  setTimeout(() => process.exit(code), 300);
}
process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

run("api", "uv run python -m unisona.main --reload", join(root, "services", "api"));
run("web", `${bin("web", "next")} dev`, join(root, "apps", "web"));

setTimeout(() => {
  console.log(`\n${c.green}  ➜ App      http://localhost:3000${c.reset}`);
  console.log(`${c.green}  ➜ API      http://127.0.0.1:8000  (docs: /docs)${c.reset}`);
  console.log(`${c.green}  ➜ Dev mode http://localhost:3000/app/dev  (local only)${c.reset}\n`);
}, 4000);
