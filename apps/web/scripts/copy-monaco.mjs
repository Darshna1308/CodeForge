// Serve Monaco's AMD build from /public so the editor works offline and
// never pulls code from a third-party CDN at runtime.
import { cpSync, existsSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "node_modules", "monaco-editor", "min", "vs");
const dest = join(root, "public", "monaco", "vs");
if (!existsSync(src)) {
  console.warn("[copy-monaco] monaco-editor not installed; skipping");
  process.exit(0);
}
rmSync(dest, { recursive: true, force: true });
cpSync(src, dest, { recursive: true });
console.log("[copy-monaco] copied monaco-editor/min/vs -> public/monaco/vs");
