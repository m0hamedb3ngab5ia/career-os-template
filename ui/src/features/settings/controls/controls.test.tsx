import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { axeViolations } from "../../../test/axe";
import { equal, formatBytes, formatValue, humanize, reasonLabel } from "../format";
import { field } from "../testing";
import type { FieldSchema } from "../types";
import { KeyValueControl, RecordsControl, RuleListControl } from "./editors";

function Harness({ f, initial }: { f: FieldSchema; initial: unknown }) {
  const [v, setV] = useState(initial);
  const Control = f.control === "records" ? RecordsControl : f.control === "key_value" ? KeyValueControl : RuleListControl;
  return (
    <>
      <Control field={f} value={v} onChange={setV} inputId="x" invalid={false} disabled={false} />
      <output data-testid="value">{JSON.stringify(v)}</output>
    </>
  );
}
const value = () => JSON.parse(screen.getByTestId("value").textContent!);

describe("format helpers", () => {
  it("humanize, reason labels, equal, formatValue, formatBytes", () => {
    expect(humanize("if_contact_found")).toBe("If contact found");
    expect(reasonLabel("GHOST_OLD_POST")).toBe("Posting is old");
    expect(reasonLabel("NEW_CODE_X")).toBe("New code x");
    expect(equal({ a: [1, { b: 2 }] }, { a: [1, { b: 2 }] })).toBe(true);
    expect(equal({ a: 1 }, { a: 1, b: 2 })).toBe(false);
    const days = field({ file: "p", key: "k", control: "number", label: "L", unit: "days" });
    expect(formatValue(days, 30)).toBe("30 days");
    expect(formatValue({ ...days, control: "switch" }, false)).toBe("Off");
    expect(formatValue({ ...days, control: "time_range" }, { start: "09:00", end: "18:00" })).toBe("09:00–18:00");
    expect(formatBytes(34 * 1024 * 1024, "en-US")).toBe("34 MB");
    expect(formatBytes(1536 * 1024 * 1024, "en-US")).toBe("1.5 GB");
  });
});

describe("tier rules", () => {
  const f = field({
    file: "targets",
    key: "tier_rules",
    control: "rule_list",
    label: "Rules",
    default: [{ if: "fit >= 85", tier: "B" }],
  });

  it("edits, reorders, removes and adds rows", async () => {
    const user = userEvent.setup();
    render(<Harness f={f} initial={[{ if: "company_in dream_list", tier: "A" }, { if: "fit >= 85", tier: "B" }]} />);
    await user.click(screen.getByRole("button", { name: "Move rule 2 up" }));
    expect(value()[0]).toEqual({ if: "fit >= 85", tier: "B" });
    await user.selectOptions(screen.getByRole("combobox", { name: "Rule 1 tier" }), "C");
    expect(value()[0].tier).toBe("C");
    await user.click(screen.getByRole("button", { name: "Remove rule 2" }));
    await user.click(screen.getByRole("button", { name: "Add tier rule" }));
    expect(value()).toEqual([{ if: "fit >= 85", tier: "C" }, { if: "fit >= 70", tier: "C" }]);
  });

  it("token rule lists are chips", async () => {
    const user = userEvent.setup();
    const tokens = field({ file: "pipeline", key: "runs.auto_submit.manual", control: "rule_list", label: "Always manual", default: ["tier_a"] });
    render(<Harness f={tokens} initial={["tier_a"]} />);
    await user.type(screen.getByRole("textbox", { name: "Add to Always manual" }), "fit_gte_90{Enter}");
    expect(value()).toEqual(["tier_a", "fit_gte_90"]);
  });
});

describe("key/value and records", () => {
  it("season multipliers stay numbers", async () => {
    const user = userEvent.setup();
    const f = field({ file: "targets", key: "volume.season_multiplier", control: "key_value", label: "Busy months", default: { "9": 2 } });
    render(<Harness f={f} initial={{ "9": 2 }} />);
    const v = screen.getByRole("textbox", { name: "Value for 9" });
    await user.clear(v);
    await user.type(v, "1.5");
    expect(value()).toEqual({ "9": 1.5 });
    await user.click(screen.getByRole("button", { name: "Remove 9" }));
    expect(value()).toEqual({});
  });

  it("records edit list cells as comma-separated text", async () => {
    const user = userEvent.setup();
    const f = field({
      file: "pipeline",
      key: "ui.pipeline.columns",
      control: "records",
      label: "Pipeline columns",
      default: [{ name: "Found", statuses: ["found", "scored"] }],
    });
    const { container } = render(<Harness f={f} initial={[{ name: "Found", statuses: ["found", "scored"] }]} />);
    const table = screen.getByRole("table", { name: "Pipeline columns" });
    const statuses = within(table).getByRole("textbox", { name: "Statuses, row 1" });
    await user.clear(statuses);
    await user.type(statuses, "found, queued");
    expect(value()).toEqual([{ name: "Found", statuses: ["found", "queued"] }]);
    await user.click(screen.getByRole("button", { name: "Add row" }));
    expect(value()).toHaveLength(2);
    expect(await axeViolations(container)).toEqual([]);
  });
});
