// Pure check behind scripts/check-node.mjs, kept separate so it can be unit-tested.

/**
 * @param {string} nvmrcText contents of .nvmrc ("22", "v22", "22.22.0")
 * @param {string} nodeVersion process.versions.node
 * @param {Record<string, string | undefined>} env
 * @returns {{ ok: boolean, message: string | null }}
 */
export function checkNode(nvmrcText, nodeVersion, env) {
  const want = nvmrcText.trim().replace(/^v/, "").split(".")[0];
  if (!want) return { ok: false, message: "careeros-ui: .nvmrc is empty; it should hold a Node major such as 22." };
  const have = nodeVersion.split(".")[0];
  if (have === want) return { ok: true, message: null };
  const msg = `careeros-ui: Node ${want} is required (from .nvmrc); this is Node ${nodeVersion}.`;
  if (env.CAREEROS_NODE_ANY === "1") return { ok: true, message: `${msg} Continuing because CAREEROS_NODE_ANY=1.` };
  return {
    ok: false,
    message: `${msg}\nUse Node ${want} (e.g. \`npx -p node@${want} npm run build\`) or set CAREEROS_NODE_ANY=1.`,
  };
}
