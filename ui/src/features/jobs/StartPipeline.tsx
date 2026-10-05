import { AlertTriangle } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { Button } from "../../kit/Button";
import { UnavailableButton } from "../../kit/UnavailableButton";
import controls from "../../kit/controls.module.css";
import { Pager, usePaged } from "../../kit/Pager";
import { SegmentedControl } from "../../kit/SegmentedControl";
import { useBatchPreview, useStartBatch, type StopAt, type Stops } from "../pipeline/batch/api";
import { COLUMNS, type Column } from "./cells";
import { FilterChips } from "./HeaderFilterMenu";
import { JobsTable } from "./JobsTable";
import styles from "./JobsPage.module.css";
import type { JobListItem } from "./types";
import { FILTERS, toggleSort, type ColumnFilter, type FilterField, type Filters, type SortKey } from "./urlState";

const STOPS: { value: StopAt; label: string }[] = [
  { value: "prepare", label: "Prepare" },
  { value: "fill", label: "Fill" },
  { value: "submit", label: "Submit" },
];
const label = (s: string | null | undefined) => STOPS.find((x) => x.value === s)?.label ?? s ?? "…";
const BASE = COLUMNS.filter((c) => ["company", "role", "tier", "fit"].includes(c.key));

const isTierA = (j: JobListItem) => j.tier?.toUpperCase() === "A";

/** Client-side column filters over the ticked rows (REQ-120): value lists, number and ISO-date ranges. */
function matches(j: JobListItem, filters: Filters) {
  return (Object.entries(filters) as [FilterField, ColumnFilter][]).every(([k, f]) => {
    const v = (j as unknown as Record<string, unknown>)[k];
    if (f.kind === "values") return f.values.includes(String(v ?? ""));
    if (v == null || v === "") return false;
    if (FILTERS[k].kind === "range") return (!f.min || Number(v) >= Number(f.min)) && (!f.max || Number(v) <= Number(f.max));
    const d = String(v).slice(0, 10);
    return (!f.min || d >= f.min) && (!f.max || d <= f.max);
  });
}

/** Flagged posting: left out, with why on hover and keyboard focus (REQ-117). */
function Excluded({ reason }: { reason: string }) {
  const id = useId();
  return (
    <span className={controls.unavailable}>
      <AlertTriangle size={14} role="img" aria-label="Excluded" aria-describedby={id} tabIndex={0} /> Excluded
      <span id={id} role="tooltip" className={controls.unavailableReason}>{reason}</span>
    </span>
  );
}

/**
 * Start pipeline review (REQ-117, UC-013): the ticked jobs on the Jobs table, one "Go as far as" for all (default
 * Fill: you submit), an override per row, and the server's caps with their reasons from a dry-run preview. Start
 * saves one batch with per-job stops (REQ-118) and opens its progress.
 */
export function StartPipeline({ ids, rows, onToggle, onUntick, onClose }: {
  ids: string[];
  rows: JobListItem[];
  onToggle: (id: string) => void;
  /** Untick these jobs (the header checkbox: the rows on this page). */
  onUntick: (ids: string[]) => void;
  onClose: () => void;
}) {
  const headingId = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  const navigate = useNavigate();
  const [stop, setStop] = useState<StopAt>("fill");
  const [overrides, setOverrides] = useState<Stops>({});
  const [sort, setSort] = useState("company");
  const [filters, setFilters] = useState<Filters>({});
  const onFilter = (field: FilterField, f: ColumnFilter | null) =>
    setFilters(({ [field]: _, ...rest }) => (f ? { ...rest, [field]: f } : rest));
  const stops = useMemo(() => {
    const s = Object.fromEntries(Object.entries(overrides).filter(([j]) => ids.includes(j)));
    return Object.keys(s).length ? s : undefined;
  }, [overrides, ids]);
  const preview = useBatchPreview(ids, stop, stops);
  const start = useStartBatch();
  useEffect(() => heading.current?.focus(), []);
  useEffect(() => {
    if (start.data?.id) navigate(`/pipeline/batch/${encodeURIComponent(start.data.id)}`);
  }, [start.data, navigate]);

  const picked = new Map((preview.data?.selected ?? []).map((j) => [j.job_id, j]));
  const excluded = new Map((preview.data?.excluded ?? []).map((x) => [x.job_id, x.reason]));
  const sorted = useMemo(() => {
    const k = sort.replace(/^-/, "") as keyof JobListItem;
    const dir = sort.startsWith("-") ? -1 : 1;
    return rows.filter((j) => matches(j, filters)).sort((a, b) => String(a[k] ?? "").localeCompare(String(b[k] ?? ""), undefined, { numeric: true }) * dir);
  }, [rows, sort, filters]);
  const paged = usePaged(sorted);
  const loaded = new Set(rows.map((r) => r.job_id));
  const unloaded = ids.filter((i) => !loaded.has(i));
  const nCapped = unloaded.filter((i) => picked.get(i)?.cap).length;
  const nExcluded = unloaded.filter((i) => excluded.has(i)).length;
  const blocked = preview.error
    ? `Couldn’t check caps: ${preview.error.message}`
    : !preview.data || preview.isFetching
      ? "Checking caps…"
      : !preview.data.selected.length
        ? "Every ticked job is excluded"
        : null;

  const columns: Column[] = [
    ...BASE,
    {
      key: "go",
      label: "Go as far as",
      width: 140,
      exportField: "",
      cell: (j) => (
        <select
          aria-label={`Go as far as for ${j.company || j.job_id}`}
          value={overrides[j.job_id] ?? ""}
          onChange={(e) => {
            const v = e.target.value as StopAt | "";
            setOverrides(({ [j.job_id]: _, ...rest }) => (v ? { ...rest, [j.job_id]: v } : rest));
          }}
        >
          <option value="">Same as all ({label(stop === "submit" && isTierA(j) ? "fill" : stop)})</option>
          {STOPS.filter((s) => !(s.value === "submit" && isTierA(j))).map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
      ),
    },
    {
      key: "stops",
      label: "Stops at",
      width: 320,
      exportField: "",
      cell: (j) => {
        const why = excluded.get(j.job_id);
        if (why) return <Excluded reason={why} />;
        const p = picked.get(j.job_id);
        if (!p) return "…";
        return (
          <span>
            <strong>{label(p.stop_at)}</strong>
            {p.cap ? ` · ${p.cap}` : ""}
            {p.cap?.startsWith("setup not finished") ? <> · <Link to="/profile">Finish your Profile</Link></> : null}
          </span>
        );
      },
    },
  ];

  return (
    <section aria-labelledby={headingId} className={styles.stack}>
      <h2 id={headingId} ref={heading} tabIndex={-1}>Review pipeline</h2>
      <SegmentedControl label="Go as far as" value={stop} onValueChange={(v) => setStop(v as StopAt)}>
        {STOPS.map((s) => <SegmentedControl.Option key={s.value} value={s.value}>{s.label}</SegmentedControl.Option>)}
      </SegmentedControl>
      <p>Fill stops before submitting, so you submit. Tier A jobs are never submitted, LinkedIn Easy Apply stops at Prepare, flagged postings are left out.</p>
      {preview.error || start.error ? <p role="alert">{(preview.error ?? start.error)?.message}</p> : null}
      <FilterChips filters={filters} onFilter={onFilter} onClearAll={() => setFilters({})} />
      <div className={styles.card}>
        <JobsTable
          rows={paged.pageItems}
          columns={columns}
          sort={sort}
          onSort={(k: SortKey) => setSort(toggleSort(sort, k))}
          onSortTo={setSort}
          selected={new Set(ids)}
          onToggle={onToggle}
          onToggleAll={() => onUntick(paged.pageItems.map((j) => j.job_id))}
          total={sorted.length}
          captionId={`${headingId}-c`}
          filters={filters}
          onFilter={onFilter}
          filterParams={{ tab: "all", q: "", location: "", filters, rows }}
        />
        <div className={styles.footer}>
          <span>
            {unloaded.length > 0
              ? `${unloaded.length} more ticked jobs aren’t in the current list; they run with “Go as far as”` +
                `${nCapped ? `, ${nCapped} capped` : ""}${nExcluded ? `, ${nExcluded} excluded` : ""}.`
              : ""}
          </span>
          <Pager paged={paged} label="Review" />
        </div>
      </div>
      <div className={styles.toolbar}>
        {blocked ? (
          <UnavailableButton variant="primary" reason={blocked}>Start</UnavailableButton>
        ) : (
          <Button variant="primary" pending={start.isPending} pendingLabel="Starting…" onClick={() => start.mutate({ jobIds: ids, stopAt: stop, stops })}>
            Start
          </Button>
        )}
        <Button onClick={onClose}>Back</Button>
      </div>
    </section>
  );
}
