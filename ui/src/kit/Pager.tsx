import { useEffect, useId, useState } from "react";
import { Button } from "./Button";
import { SelectInput } from "./inputs";
import styles from "./Pager.module.css";

export const PAGE_SIZES = [10, 25, 50, 100];
const SIZE_OPTIONS = PAGE_SIZES.map((n) => ({ value: String(n), label: String(n) }));

interface PagedOptions {
  /** Rows in the whole list when the server knows more than it sent (defaults to items.length). */
  total?: number;
  /** The server has more rows past `total` (cursor lists without a count). */
  more?: boolean;
  /** Called when the page reaches past the loaded items and `more` is set. */
  onNeedMore?: () => void;
  /** Back to page 1 whenever this changes (filters, search, sort). */
  resetKey?: string;
}

export interface Paged<T> {
  pageItems: T[];
  page: number;
  setPage: (p: number) => void;
  size: number;
  setSize: (s: number) => void;
  pages: number;
  total: number;
  more: boolean;
}

/** Client-side paging after filter/sort: 10 rows by default, page 1 again when the size or resetKey changes. */
export function usePaged<T>(items: T[], { total = items.length, more = false, onNeedMore, resetKey = "" }: PagedOptions = {}): Paged<T> {
  const [raw, setPage] = useState(1);
  const [size, setSizeState] = useState(PAGE_SIZES[0]!);
  const [key, setKey] = useState(resetKey);
  if (key !== resetKey) {
    setKey(resetKey);
    setPage(1);
  }
  const pages = Math.max(1, Math.ceil(total / size));
  const page = more ? raw : Math.min(raw, pages);
  const start = (page - 1) * size;
  const needMore = (more || items.length < total) && start + size > items.length;
  useEffect(() => {
    if (needMore) onNeedMore?.();
  }, [needMore, onNeedMore]);
  return {
    pageItems: items.slice(start, start + size),
    page,
    setPage,
    size,
    setSize: (s) => {
      setSizeState(s);
      setPage(1);
    },
    pages,
    total,
    more,
  };
}

/** "1–10 of 57", Prev/Next and a rows-per-page select. Hidden while everything fits on one 10-row page. */
export function Pager<T>({ paged, label }: { paged: Paged<T>; label: string }) {
  const id = useId();
  const { page, setPage, size, setSize, pages, total, more } = paged;
  if (total <= PAGE_SIZES[0]! && !more) return null;
  const start = (page - 1) * size;
  return (
    <nav className={styles.pager} aria-label={`${label} pages`}>
      <span className="tabular" aria-live="polite">
        {total ? start + 1 : 0}–{Math.min(start + size, total)} of {total}
        {more ? "+" : ""}
      </span>
      <label htmlFor={id} className={styles.size}>
        Rows
        <SelectInput id={id} value={String(size)} options={SIZE_OPTIONS} onValueChange={(v) => setSize(Number(v))} />
      </label>
      <Button size="small" aria-label={`Previous ${label} page`} disabled={page <= 1} onClick={() => setPage(page - 1)}>
        Prev
      </Button>
      <Button size="small" aria-label={`Next ${label} page`} disabled={page >= pages && !more} onClick={() => setPage(page + 1)}>
        Next
      </Button>
    </nav>
  );
}
