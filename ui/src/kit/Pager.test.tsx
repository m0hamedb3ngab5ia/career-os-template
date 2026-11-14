import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { axeViolations } from "../test/axe";
import { Pager, usePaged } from "./Pager";

const nums = (n: number) => Array.from({ length: n }, (_, i) => i + 1);

function List({ items, resetKey }: { items: number[]; resetKey?: string }) {
  const paged = usePaged(items, { resetKey });
  return (
    <>
      <ul>
        {paged.pageItems.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
      <Pager paged={paged} label="Things" />
    </>
  );
}

function Filtered() {
  const [q, setQ] = useState("");
  return (
    <>
      <button onClick={() => setQ("odd")}>filter</button>
      <List items={nums(57).filter((n) => !q || n % 2)} resetKey={q} />
    </>
  );
}

const shown = () => screen.getAllByRole("listitem").map((li) => Number(li.textContent));

describe("usePaged + Pager", () => {
  it("shows 10 rows, pages with Prev/Next and changes the page size", async () => {
    const { container } = render(<List items={nums(57)} />);
    expect(shown()).toEqual(nums(10));
    expect(screen.getByText(/1–10 of 57/)).toBeInTheDocument();
    const prev = screen.getByRole("button", { name: "Previous Things page" });
    expect(prev).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Next Things page" }));
    expect(shown()[0]).toBe(11);
    expect(screen.getByText(/11–20 of 57/)).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Rows"), "25");
    expect(shown()).toEqual(nums(25));
    await userEvent.selectOptions(screen.getByLabelText("Rows"), "50");
    await userEvent.click(screen.getByRole("button", { name: "Next Things page" }));
    expect(shown()).toEqual(nums(57).slice(50));
    expect(screen.getByRole("button", { name: "Next Things page" })).toBeDisabled();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("goes back to page 1 when the filtered list changes", async () => {
    render(<Filtered />);
    await userEvent.click(screen.getByRole("button", { name: "Next Things page" }));
    expect(shown()[0]).toBe(11);
    await userEvent.click(screen.getByRole("button", { name: "filter" }));
    expect(shown()[0]).toBe(1);
  });

  it("hides the pager when everything fits on one page", () => {
    render(<List items={nums(10)} />);
    expect(shown()).toHaveLength(10);
    expect(screen.queryByRole("navigation")).toBeNull();
  });
});
