// Build guard: the committed bundle in src/careeros/ui/static must be reproducible, so builds run on the Node
// major pinned in ../.nvmrc (CI uses the same). Set CAREEROS_NODE_ANY=1 to build on another major locally;
// CI's bundle-freshness check still catches any difference.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const nvmrc = fileURLToPath(new URL("../../.nvmrc", import.meta.url));
const want = readFileSync(nvmrc, "utf8").trim().replace(/^v/, "").split(".")[0];
const have = process.versions.node.split(".")[0];

if (have !== want) {
  const msg = `careeros-ui: Node ${want} is required (from .nvmrc); this is Node ${process.versions.node}.`;
  if (process.env.CAREEROS_NODE_ANY === "1") {
    console.warn(`${msg} Continuing because CAREEROS_NODE_ANY=1.`);
  } else {
    console.error(`${msg}\nUse Node ${want} (e.g. \`npx -p node@${want} npm run build\`) or set CAREEROS_NODE_ANY=1.`);
    process.exit(1);
  }
}
