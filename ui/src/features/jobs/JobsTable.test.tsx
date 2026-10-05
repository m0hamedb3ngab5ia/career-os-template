import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { ToastProvider } from "../../kit/Toast";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { axeViolations } from "../../test/axe";
import { COLUMNS } from "./cells";
import { job } from "./fixtures";
import { JobsTable } from "./JobsTable";

const qc = new QueryClient();
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={qc}><ToastProvider>{children}</ToastProvider></QueryClientProvider>
);

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
    { wrapper }
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

  it("select all on the page is checked, mixed or off from the shown rows", () => {
    const rows = MANY.slice(0, 3);
    const all = () => screen.getByRole("checkbox", { name: "Select all shown jobs" }) as HTMLInputElement;
    const { rerender } = renderTable({ rows, total: 3, selected: new Set(["j0", "j1", "j2", "elsewhere"]) });
    expect(all()).toBeChecked();
    expect(all().indeterminate).toBe(false);
    const props = { columns: COLUMNS, sort: "-fit", onSort: vi.fn(), onToggle: vi.fn(), onToggleAll: vi.fn(), total: 3,
      captionId: "cap", filters: {}, onFilter: vi.fn(), filterParams: { tab: "active" as const, q: "", location: "", filters: {} },
      onSortTo: vi.fn() };
    rerender(<MemoryRouter><JobsTable {...props} rows={rows} selected={new Set(["j1"])} /></MemoryRouter>);
    expect(all()).not.toBeChecked();
    expect(all().indeterminate).toBe(true);
    rerender(<MemoryRouter><JobsTable {...props} rows={rows} selected={new Set()} /></MemoryRouter>);
    expect(all().indeterminate).toBe(false);
    rerender(<MemoryRouter><JobsTable {...props} rows={[]} total={0} selected={new Set()} /></MemoryRouter>);
    expect(all()).toBeDisabled();
  });

  it("has no axe violations", async () => {
    const { container } = renderTable({ rows: MANY.slice(0, 5), total: 5 });
    expect(await axeViolations(container)).toEqual([]);
  });
});
