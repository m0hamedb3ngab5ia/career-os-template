import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { axeViolations } from "../../test/axe";
import { COLUMNS } from "./cells";
import { job } from "./fixtures";
import { JobsTable } from "./JobsTable";

const MANY = Array.from({ length: 1000 }, (_, i) => job({ job_id: `j${i}`, company: `Company ${i}`, fit: 99 - (i % 99) }));

function renderTable(props: Partial<Parameters<typeof JobsTable>[0]> = {}) {
  const onSort = vi.fn();
  const onToggle = vi.fn();
  const onToggleAll = vi.fn();
  const utils = render(
    <MemoryRouter>
      <JobsTable
        rows={MANY}
        columns={COLUMNS}
        sort="-fit"
        onSort={onSort}
        selected={new Set(["j1"])}
        onToggle={onToggle}
        onToggleAll={onToggleAll}
        total={1200}
        captionId="cap"
        filters={{}}
        onFilter={vi.fn()}
        filterParams={{ tab: "active", q: "", location: "", filters: {} }}
        onSortTo={vi.fn()}
        {...props}
      />
    </MemoryRouter>,
  );
  return { ...utils, onSort, onToggle, onToggleAll };
}

describe("JobsTable", () => {
  it("renders only a window of rows, with row counts for assistive tech", () => {
    renderTable();
    const table = screen.getByRole("table", { name: "Tracked jobs, sorted by fit, highest first" });
    expect(table).toHaveAttribute("aria-rowcount", "1201");
    const rows = within(table).getAllByRole("rowheader");
    expect(rows.length).toBeGreaterThan(5);
    expect(rows.length).toBeLessThan(60);
    expect(rows[0]!.closest("tr")).toHaveAttribute("aria-rowindex", "2");
  });

  it("marks the sorted column and calls onSort from the header button", async () => {
    const { onSort } = renderTable();
    expect(screen.getByRole("columnheader", { name: /Fit/ })).toHaveAttribute("aria-sort", "descending");
    expect(screen.getByRole("button", { name: "Fit, sorted highest first" })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Found" }));
    expect(onSort).toHaveBeenCalledWith("found_at");
  });

  it("row checkboxes are named after the company and reflect the selection", async () => {
    const { onToggle, onToggleAll } = renderTable();
    expect(screen.getByRole("checkbox", { name: "Select Company 1" })).toBeChecked();
    await userEvent.setup().click(screen.getByRole("checkbox", { name: "Select Company 0" }));
    expect(onToggle).toHaveBeenCalledWith("j0");
    await userEvent.setup().click(screen.getByRole("checkbox", { name: "Select all shown jobs" }));
    expect(onToggleAll).toHaveBeenCalled();
  });

  it("has no axe violations", async () => {
    const { container } = renderTable({ rows: MANY.slice(0, 5), total: 5 });
    expect(await axeViolations(container)).toEqual([]);
  });
});
