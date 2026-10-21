// Copies the built embeddable widget (apps/widget/dist/widget.js) into the web app's public folder,
// so the Vercel deployment serves it at /widget/widget.js. The hosted API redirects /widget/* there.
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "apps", "widget", "dist", "widget.js");
if (!existsSync(src)) {
  console.error("✖ apps/widget/dist/widget.js not found. Run `pnpm --filter widget build` first.");
  process.exit(1);
}
const out = join(root, "apps", "web", "public", "widget");
mkdirSync(out, { recursive: true });
copyFileSync(src, join(out, "widget.js"));
console.log("✔ Copied widget.js into apps/web/public/widget/");
