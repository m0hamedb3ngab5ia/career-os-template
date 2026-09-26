import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { axeViolations } from "../test/axe";
import { NumberInput, SelectInput, TagEditor, TextInput } from "./inputs";
import { Switch } from "./Switch";

describe("NumberInput", () => {
  it("reports numbers, null when empty and NaN for text", async () => {
    const user = userEvent.setup();
    const seen: (number | null)[] = [];
    function Demo() {
      const [v, setV] = useState<number | null>(15);
      return (
        <label>
          Applications per day
          <NumberInput
            value={v}
            onValueChange={(n) => {
              seen.push(n);
              setV(n);
            }}
          />
        </label>
      );
    }
    render(<Demo />);
    const input = screen.getByRole("textbox", { name: "Applications per day" });
    expect(input).toHaveValue("15");
    await user.clear(input);
    expect(seen.at(-1)).toBeNull();
    await user.type(input, "2,5");
    expect(seen.at(-1)).toBe(2.5);
    await user.type(input, "x");
    expect(Number.isNaN(seen.at(-1))).toBe(true);
    expect(input).toHaveValue("2,5x");
    await user.clear(input);
    await user.type(input, "15x");
    expect(input).toHaveValue("15x");
  });

  it("sets aria-invalid when invalid", () => {
    render(<NumberInput aria-label="Old post" value={3} onValueChange={() => undefined} invalid />);
    expect(screen.getByRole("textbox", { name: "Old post" })).toHaveAttribute("aria-invalid", "true");
  });
});

describe("TagEditor", () => {
  function Demo({ strict = false, options = [] as string[] }) {
    const [v, setV] = useState(["greenhouse"]);
    return <TagEditor label="Allowed ATS" values={v} onValuesChange={setV} options={options} strict={strict} />;
  }

  it("adds with Enter, removes by button and Backspace", async () => {
    const user = userEvent.setup();
    render(<Demo />);
    const add = screen.getByRole("textbox", { name: "Add to Allowed ATS" });
    await user.type(add, "lever{Enter}");
    expect(screen.getByRole("list", { name: "Allowed ATS" })).toHaveTextContent("greenhouselever");
    await user.click(screen.getByRole("button", { name: "Remove greenhouse" }));
    expect(screen.queryByText("greenhouse")).not.toBeInTheDocument();
    await user.type(add, "{Backspace}");
    expect(screen.getByText("None")).toBeInTheDocument();
  });

  it("strict lists add from a select of the remaining options", async () => {
    const user = userEvent.setup();
    render(<Demo strict options={["greenhouse", "lever", "ashby"]} />);
    const select = screen.getByRole("combobox", { name: "Add to Allowed ATS" });
    expect(screen.queryByRole("option", { name: "greenhouse" })).not.toBeInTheDocument();
    await user.selectOptions(select, "ashby");
    expect(screen.getByRole("list", { name: "Allowed ATS" })).toHaveTextContent("ashby");
  });

  it("has no axe violations", async () => {
    const { container } = render(<Demo />);
    expect(await axeViolations(container)).toEqual([]);
  });
});

describe("SelectInput and TextInput", () => {
  it("are controlled", async () => {
    const user = userEvent.setup();
    const onSel = vi.fn();
    const onText = vi.fn();
    render(
      <>
        <SelectInput
          aria-label="Cover letter"
          value="always"
          onValueChange={onSel}
          options={[
            { value: "always", label: "Always (Recommended)" },
            { value: "if_required", label: "If required" },
          ]}
        />
        <TextInput aria-label="Time zone" value="local" onValueChange={onText} />
      </>,
    );
    await user.selectOptions(screen.getByRole("combobox", { name: "Cover letter" }), "if_required");
    expect(onSel).toHaveBeenCalledWith("if_required");
    await user.type(screen.getByRole("textbox", { name: "Time zone" }), "x");
    expect(onText).toHaveBeenCalledWith("localx");
  });
});

describe("Switch describedBy", () => {
  it("points at its hint", () => {
    render(
      <>
        <Switch checked onCheckedChange={() => undefined} label="Daily digest" describedBy="hint" />
        <span id="hint">Once a day</span>
      </>,
    );
    expect(screen.getByRole("switch", { name: "Daily digest" })).toHaveAccessibleDescription("Once a day");
  });
});
