import { useRef, useState, type KeyboardEvent } from "react";
import { useSearchParams } from "react-router";
import { formatNumber } from "../format";
import type { Snapshot, StorageCategory } from "../types";
import styles from "./storage.module.css";

// Weekly stacked bars of what career-os stores, from data/runs/storage.jsonl (one snapshot per prune, plus
// `careeros storage --snapshot`). Colour follows the category, in a fixed order; tracker and other fold into a
// neutral "Other". Every bar is focusable (one tab stop, arrow keys move) and shows the same tooltip as hover;
// "Show as table" (kept in the URL) has every number.

export const SERIES: { key: string; label: string; color: string; cats: StorageCategory[] }[] = [
  { key: "screenshots", label: "Screenshots", color: "var(--cat-1)", cats: ["screenshots"] },
  { key: "postings", label: "Postings", color: "var(--cat-2)", cats: ["postings"] },
  { key: "resumes_pdfs", label: "Résumés and PDFs", color: "var(--cat-3)", cats: ["resumes_pdfs"] },
  { key: "run_logs", label: "Run logs", color: "var(--cat-4)", cats: ["run_logs"] },
  { key: "other", label: "Other", color: "var(--cat-other)", cats: ["tracker", "other"] },
];

const MB = 1024 * 1024;
const WEEKS = 8;

export interface Week {
  key: string;
  label: string;
  values: number[]; // MB per SERIES entry
  total: number;
}

function weekStart(d: Date): Date {
  const s = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  s.setDate(s.getDate() - ((s.getDay() + 6) % 7)); // Monday
  return s;
}

/** The last snapshot of each week, oldest first, at most the last 8 weeks. */
export function weeklySnapshots(snaps: Snapshot[], locale?: string): Week[] {
  const fmt = new Intl.DateTimeFormat(locale, { month: "short", day: "numeric" });
  const byWeek = new Map<string, { start: Date; snap: Snapshot }>();
  const dated = snaps.filter((s): s is Snapshot & { at: string } => typeof s.at === "string");
  for (const s of dated.sort((a, b) => a.at.localeCompare(b.at))) {
    const t = new Date(s.at);
    if (Number.isNaN(t.getTime())) continue;
    const start = weekStart(t);
    byWeek.set(start.toISOString(), { start, snap: s });
  }
  return [...byWeek.values()].slice(-WEEKS).map(({ start, snap }) => {
    const values = SERIES.map((sr) => sr.cats.reduce((a, c) => a + (snap.bytes?.[c] ?? 0), 0) / MB);
    return { key: start.toISOString(), label: fmt.format(start), values, total: values.reduce((a, b) => a + b, 0) };
  });
}

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  const n = v / p;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 4 ? 4 : n <= 5 ? 5 : 10;
  return step * p;
}

const mb = (v: number) => formatNumber(v, { maximumFractionDigits: 1, minimumFractionDigits: v < 10 ? 1 : 0 });

export function StorageChart({ weeks }: { weeks: Week[] }) {
  const [active, setActive] = useState<number | null>(null);
  const [focusIdx, setFocusIdx] = useState(weeks.length - 1);
  const [params, setParams] = useSearchParams();
  const plot = useRef<HTMLDivElement>(null);
  const max = niceMax(Math.max(...weeks.map((w) => w.total)));
  const ticks = [4, 3, 2, 1, 0].map((i) => (max * i) / 4);
  const H = 190;
  const tableOpen = params.get("table") === "storage";
  const shown = active !== null ? weeks[active] : null;

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const last = weeks.length - 1;
    const i = focusIdx;
    const next =
      e.key === "ArrowRight" ? Math.min(last, i + 1) : e.key === "ArrowLeft" ? Math.max(0, i - 1)
        : e.key === "Home" ? 0 : e.key === "End" ? last : null;
    if (next === null) {
      if (e.key === "Escape") setActive(null);
      return;
    }
    e.preventDefault();
    setFocusIdx(next);
    plot.current?.querySelectorAll<HTMLButtonElement>("button")[next]?.focus();
  }

  return (
    <>
      <ul className={styles.legend} aria-label="Categories">
        {SERIES.map((s) => (
          <li key={s.key} className={styles.legendItem}>
            <span className={styles.swatch} style={{ background: s.color }} aria-hidden="true" />
            {s.label}
          </li>
        ))}
      </ul>
      <div className={styles.chart}>
        <div className={styles.yAxis} aria-hidden="true">
          {ticks.map((t) => (
            <span key={t}>{formatNumber(t, { maximumFractionDigits: 1 })}</span>
          ))}
        </div>
        <div
          ref={plot}
          className={styles.plot}
          role="group"
          aria-label="Storage by week, in MB. Use the arrow keys to move between weeks."
          data-hover={active !== null}
          style={{ gridTemplateColumns: `repeat(${weeks.length}, minmax(0, 1fr))` }}
          onKeyDown={onKeyDown}
          onMouseLeave={() => setActive(null)}
        >
          <div className={styles.grid} aria-hidden="true">
            {ticks.map((t) => (
              <span key={t} />
            ))}
          </div>
          {weeks.map((w, i) => (
            <button
              key={w.key}
              type="button"
              className={styles.bar}
              data-active={active === i}
              tabIndex={i === focusIdx ? 0 : -1}
              aria-label={`Week of ${w.label}: ${mb(w.total)} MB. ${SERIES.map((s, k) => `${s.label} ${mb(w.values[k]!)}`).join(", ")}`}
              onMouseEnter={() => setActive(i)}
              onFocus={() => {
                setActive(i);
                setFocusIdx(i);
              }}
              onBlur={() => setActive(null)}
            >
              <span className={styles.barTotal} aria-hidden="true">
                {mb(w.total)}
              </span>
              <span className={styles.stack} aria-hidden="true">
                {w.values.map((v, k) =>
                  v > 0 ? (
                    <span
                      key={SERIES[k]!.key}
                      className={styles.seg}
                      style={{ height: Math.max(2, Math.round((v / max) * H)), background: SERIES[k]!.color }}
                    />
                  ) : null,
                )}
              </span>
              <span className={styles.barLabel} aria-hidden="true">
                {w.label}
              </span>
            </button>
          ))}
          {shown ? (
            <div
              className={styles.tip}
              aria-hidden="true"
              style={{ left: `${Math.min(70, (active! / Math.max(1, weeks.length)) * 100 + 4)}%` }}
            >
              <div className={styles.tipTitle}>
                Week of {shown.label} · {mb(shown.total)} MB
              </div>
              {SERIES.map((s, k) => (
                <div key={s.key} className={styles.tipRow}>
                  <span className={styles.tipName}>
                    <span className={styles.swatch} style={{ background: s.color }} />
                    {s.label}
                  </span>
                  <span>{mb(shown.values[k]!)}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </div>
      <details
        className={styles.details}
        open={tableOpen}
        onToggle={(e) => {
          const open = (e.currentTarget as HTMLDetailsElement).open;
          if (open === tableOpen) return;
          setParams(
            (p) => {
              const n = new URLSearchParams(p);
              if (open) n.set("table", "storage");
              else n.delete("table");
              return n;
            },
            { replace: true },
          );
        }}
      >
        <summary>Show as table</summary>
        <table className={styles.table}>
          <caption className="sr-only">Storage by week, in MB</caption>
          <thead>
            <tr>
              <th scope="col">Week</th>
              {SERIES.map((s) => (
                <th key={s.key} scope="col">
                  {s.label}
                </th>
              ))}
              <th scope="col">Total</th>
            </tr>
          </thead>
          <tbody>
            {weeks.map((w) => (
              <tr key={w.key}>
                <th scope="row">{w.label}</th>
                {w.values.map((v, k) => (
                  <td key={SERIES[k]!.key}>{mb(v)}</td>
                ))}
                <td>{mb(w.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </>
  );
}
