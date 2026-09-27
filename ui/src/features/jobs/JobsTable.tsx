import { useWindowVirtualizer } from "@tanstack/react-virtual";
import { ArrowDown, ArrowUp } from "lucide-react";
import { memo, useLayoutEffect, useRef, useState } from "react";
import type { Column } from "./cells";
import styles from "./JobsPage.module.css";
import type { JobListItem } from "./types";
import { sortCaption, sortDirection, type SortKey } from "./urlState";

const ROW_H = 44;

interface JobsTableProps {
  rows: JobListItem[];
  columns: Column[];
  sort: string;
  onSort: (key: SortKey) => void;
  selected: ReadonlySet<string>;
  onToggle: (jobId: string) => void;
  onToggleAll: () => void;
  /** All rows the filter matches (loaded or not), for aria-rowcount. */
  total: number;
  captionId: string;
}

function SortHeader({ col, sort, onSort }: { col: Column; sort: string; onSort: (k: SortKey) => void }) {
  const key = col.sort!;
  const active = sort.replace(/^-/, "") === key;
  const desc = sort.startsWith("-");
  const Icon = desc ? ArrowDown : ArrowUp;
  return (
    <th scope="col" aria-sort={active ? (desc ? "descending" : "ascending") : "none"} className={styles.th}>
      <button type="button" className={styles.sortButton} data-active={active} onClick={() => onSort(key)}>
        {col.label}
        {active ? <Icon size={10} strokeWidth={2.4} aria-hidden="true" /> : null}
        {active ? <span className="sr-only">, sorted {sortDirection(sort)}</span> : null}
      </button>
    </th>
  );
}

const Row = memo(function Row({
  job,
  index,
  columns,
  checked,
  onToggle,
}: {
  job: JobListItem;
  index: number;
  columns: Column[];
  checked: boolean;
  onToggle: (id: string) => void;
}) {
  const name = job.company || job.job_id;
  return (
    <tr className={styles.row} aria-rowindex={index + 2} data-selected={checked || undefined}>
      <td className={styles.td}>
        <label className={styles.check}>
          <input type="checkbox" checked={checked} onChange={() => onToggle(job.job_id)} />
          <span className="sr-only">Select {name}</span>
        </label>
      </td>
      {columns.map((c, i) => {
        const Cell = i === 0 ? "th" : "td";
        return (
          <Cell
            key={c.key}
            scope={i === 0 ? "row" : undefined}
            className={c.className ? `${styles.td} ${c.className}` : styles.td}
            title={c.title?.(job)}
          >
            {c.cell(job)}
          </Cell>
        );
      })}
    </tr>
  );
});

/**
 * The live table: a real <table> (caption, column headers, row headers) whose body is windowed with TanStack
 * Virtual against the page scroll, so thousands of rows cost only what is on screen. Spacer rows keep the
 * scroll height; aria-rowcount / aria-rowindex tell assistive tech where each row sits.
 */
export function JobsTable({ rows, columns, sort, onSort, selected, onToggle, onToggleAll, total, captionId }: JobsTableProps) {
  const bodyRef = useRef<HTMLTableSectionElement>(null);
  const [margin, setMargin] = useState(0);
  useLayoutEffect(() => {
    const top = bodyRef.current?.getBoundingClientRect().top ?? 0;
    setMargin(top + window.scrollY);
  }, []);

  const v = useWindowVirtualizer({
    count: rows.length,
    estimateSize: () => ROW_H,
    overscan: 8,
    scrollMargin: margin,
  });
  const items = v.getVirtualItems();
  const before = items.length ? items[0]!.start - margin : 0;
  const after = items.length ? v.getTotalSize() - (items[items.length - 1]!.end - margin) : 0;

  const shownSel = rows.reduce((n, r) => n + (selected.has(r.job_id) ? 1 : 0), 0);
  const allOn = rows.length > 0 && shownSel === rows.length;
  const colSpan = columns.length + 1;

  return (
    <table className={styles.table} aria-rowcount={total + 1}>
      <caption id={captionId} className="sr-only">
        Tracked jobs, {sortCaption(sort)}
      </caption>
      <colgroup>
        <col style={{ width: 40 }} />
        {columns.map((c) => (
          <col key={c.key} style={c.width ? { width: c.width } : undefined} />
        ))}
      </colgroup>
      <thead>
        <tr aria-rowindex={1}>
          <th scope="col" className={styles.th}>
            <label className={styles.check}>
              <input
                type="checkbox"
                checked={allOn}
                ref={(el) => {
                  if (el) el.indeterminate = shownSel > 0 && !allOn;
                }}
                onChange={onToggleAll}
                disabled={rows.length === 0}
              />
              <span className="sr-only">Select all shown jobs</span>
            </label>
          </th>
          {columns.map((c) =>
            c.sort ? (
              <SortHeader key={c.key} col={c} sort={sort} onSort={onSort} />
            ) : (
              <th key={c.key} scope="col" className={styles.th}>
                {c.label}
              </th>
            ),
          )}
        </tr>
      </thead>
      <tbody ref={bodyRef}>
        {before > 0 ? (
          <tr aria-hidden="true" className={styles.spacer}>
            <td colSpan={colSpan} style={{ height: before }} />
          </tr>
        ) : null}
        {items.map((it) => {
          const job = rows[it.index]!;
          return (
            <Row
              key={job.job_id}
              job={job}
              index={it.index}
              columns={columns}
              checked={selected.has(job.job_id)}
              onToggle={onToggle}
            />
          );
        })}
        {after > 0 ? (
          <tr aria-hidden="true" className={styles.spacer}>
            <td colSpan={colSpan} style={{ height: after }} />
          </tr>
        ) : null}
      </tbody>
    </table>
  );
}
