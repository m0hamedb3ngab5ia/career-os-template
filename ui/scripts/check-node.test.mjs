import { describe, expect, it } from "vitest";
import { checkNode } from "./check-node-lib.mjs";

describe("checkNode", () => {
  it("accepts the pinned major", () => {
    expect(checkNode("22\n", "22.22.0", {})).toEqual({ ok: true, message: null });
    expect(checkNode("v22", "22.23.3", {})).toMatchObject({ ok: true });
    expect(checkNode("22.22.0", "22.1.0", {})).toMatchObject({ ok: true });
  });

  it("rejects another major with a fix in the message", () => {
    const r = checkNode("22", "26.4.0", {});
    expect(r.ok).toBe(false);
    expect(r.message).toContain("Node 22 is required");
    expect(r.message).toContain("26.4.0");
    expect(r.message).toContain("CAREEROS_NODE_ANY=1");
  });

  it("CAREEROS_NODE_ANY=1 lets another major through with a warning", () => {
    const r = checkNode("22", "26.4.0", { CAREEROS_NODE_ANY: "1" });
    expect(r.ok).toBe(true);
    expect(r.message).toContain("Continuing because CAREEROS_NODE_ANY=1");
  });

  it("an empty .nvmrc is an error, not a pass", () => {
    expect(checkNode("", "22.22.0", {}).ok).toBe(false);
  });
});
