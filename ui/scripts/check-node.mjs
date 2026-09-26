// Build guard: the committed bundle in src/careeros/ui/static must be reproducible, so builds run on the Node
// major pinned in ../.nvmrc (CI uses the same). Set CAREEROS_NODE_ANY=1 to build on another major locally;
// CI's bundle-freshness check still catches any difference.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { checkNode } from "./check-node-lib.mjs";

const nvmrc = readFileSync(fileURLToPath(new URL("../../.nvmrc", import.meta.url)), "utf8");
const { ok, message } = checkNode(nvmrc, process.versions.node, process.env);
if (message) (ok ? console.warn : console.error)(message);
if (!ok) process.exit(1);
