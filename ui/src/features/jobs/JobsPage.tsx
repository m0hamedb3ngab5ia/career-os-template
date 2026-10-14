import { Download, FileSearch, RotateCw, FolderOpen, MapPin, RefreshCw, Search, Table2 } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { Page } from "../../app/PageHeader";
import { useMeta } from "../../api/meta";
import { Button } from "../../kit/Button";
import { CheckJobDialog } from "./CheckJobDialog";
import { EmptyState } from "../../kit/EmptyState";
import { Menu } from "../../kit/Menu";
import { Pager, usePaged } from "../../kit/Pager";
import { SegmentedControl } from "../../kit/SegmentedControl";
import { Tabs } from "../../kit/Tabs";
import { useToast } from "../../kit/Toast";
import { formatCount } from "../../lib/format";
import { useJobFacets, useExportJobs, useSelectJobs, useJobsList, useJobsTabs, useMoveJob, useOpenTracker, useRememberView, useUiState, useSyncTracker, exportFilters } from "./api";
import { COLUMNS } from "./cells";
import { JobsBoard } from "./JobsBoard";
import { JobDetailPage } from "../job-detail/JobDetailPage";
import { JobsList } from "./JobsCards";
import { JobsTable } from "./JobsTable";
import { StartPipeline } from "./StartPipeline";
import { useStepRun } from "../runs/useStepRun";
import { UnavailableButton } from "../../kit/UnavailableButton";
import { FilterChips } from "./HeaderFilterMenu";
import styles from "./JobsPage.module.css";
import { STAGES, TABS, VIEWS, effectiveView, toggleSort, useJobsView, type SortKey, type ColumnFilter, type FilterField } from "./urlState";
import type { StageKey, TabKey, ViewKey } from "./types";

const DEFAULT_PAGE_SIZE = 100;
const SEARCH_DEBOUNCE_MS = 250;

// Fallback labels until GET /api/jobs/tabs answers (the server's labels win).
const TAB_LABELS: Record<TabKey, string> = { recommended: "Recommended", saved: "Saved", applied: "Applied" };
// Footer noun: "Showing 12 of 59 recommended jobs".
const TAB_NOUNS: Record<TabKey, string> = { recommended: "recommended jobs", saved: "saved jobs", applied: "applied jobs" };
const VIEW_LABELS: Record<ViewKey, string> = { list: "List", table: "Table", board: "Board" };

function errorText(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong";
}

function basename(path: string): string {
  return path.split(/[\\/]/).pop() || path;
}

function HeaderActions() {
  const toast = useToast();
  const sync = useSyncTracker();
  const open = useOpenTracker();
  const [checking, setChecking] = useState(false);
  const scout = useStepRun("scout", undefined, (run) => {
    if (run.stop_reason !== "cancelled") toast.show({ message: run.stop_reason === "completed" ? "Finished looking for jobs." : `Job search stopped: ${run.detail || run.stop_reason}` });
  });
  return (
    <>
      <Button
        icon={<RotateCw size={14} strokeWidth={1.7} aria-hidden="true" />}
        pending={scout.start.isPending || scout.running}
        pendingLabel="Finding jobs…"
        onClick={() => scout.start.mutate(undefined, { onError: (e) => toast.show({ message: `Couldn’t start the job search: ${errorText(e)}` }) })}
      >
        Find jobs now
      </Button>
      <Button variant="primary" icon={<FileSearch size={14} strokeWidth={1.7} aria-hidden="true" />} onClick={() => setChecking(true)}>
        Check a job
      </Button>
      <CheckJobDialog open={checking} onClose={() => setChecking(false)} />
      <Button
        icon={<RefreshCw size={14} strokeWidth={1.7} aria-hidden="true" />}
        pending={sync.isPending}
        pendingLabel="Syncing…"
        onClick={() =>
          sync.mutate(undefined, {
            onSuccess: (r) =>
              toast.show({
                message: r.pending
                  ? `Synced ${formatCount(r.synced)} jobs. Excel has the tracker open, so they're saved to a queue; they're written on the next change, or close Excel and they save then.`
                  : `Synced ${formatCount(r.synced)} jobs`,
              }),
            onError: (e) => toast.show({ message: errorText(e) }),
          })
        }
      >
        Sync tracker
      </Button>
      <Button
        icon={<FolderOpen size={14} strokeWidth={1.7} aria-hidden="true" />}
        pending={open.isPending}
        pendingLabel="Opening…"
        onClick={() =>
          open.mutate(undefined, {
            onSuccess: (r) => toast.show({ message: `Opened ${basename(r.path)}` }),
            onError: (e) => toast.show({ message: errorText(e) }),
          })
        }
      >
        Open JobTracker.xlsx
      </Button>
    </>
  );
}

interface FilterFieldProps {
  value: string;
  onCommit: (value: string) => void;
  name: string;
  label: string;
  placeholder: string;
  icon: ReactNode;
}

/** A text filter that commits to the URL after a short pause; it follows the URL when something else sets it (the
 * sidebar search, a deep link). */
function FilterField({ value: q, onCommit, name, label, placeholder, icon }: FilterFieldProps) {
  const [text, setText] = useState(q);
  const committed = useRef(q);
  useEffect(() => {
    if (q !== committed.current) {
      committed.current = q;
      setText(q);
    }
  }, [q]);
  useEffect(() => {
    if (text.trim() === committed.current) return;
    const t = setTimeout(() => {
      committed.current = text.trim();
      onCommit(text);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [text, onCommit]);
  return (
    <label className={styles.search}>
      {icon}
      <span className="sr-only">{label}</span>
      <input
        type="search"
        name={name}
        autoComplete="off"
        spellCheck={false}
        placeholder={placeholder}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
    </label>
  );
}

export function JobsPage({ jobId }: { jobId?: string } = {}) {
  const toast = useToast();
  const [view, update] = useJobsView();
  const { tab, q, location, sort, stage } = view;
  const columnFilters = view.filters;
  const meta = useMeta();
  const uiState = useUiState();
  const remember = useRememberView();
  const move = useMoveJob();
  const mode = effectiveView(view.view, uiState.data?.jobs_view, tab);
  const chooseView = (v: ViewKey) => {
    update({ view: v }, true);
    remember.mutate(v);
  };
  const pageSize = meta.data?.ui?.page_size ?? DEFAULT_PAGE_SIZE;
  const filters = columnFilters;
  const stageStatuses = STAGES.find((x) => x.key === stage)?.statuses;
  // A stage is a status filter on the Applied tab (REQ-128); Board shows every stage as a column.
  const requestFilters = useMemo(
    () => (stageStatuses && mode !== "board" ? { ...filters, status: { kind: "values" as const, values: stageStatuses } } : filters),
    [filters, stageStatuses, mode],
  );
  const filterParams = useMemo(() => ({ tab, q, location, filters: requestFilters }), [tab, q, location, requestFilters]);
  const stageFacets = useJobFacets("status", { tab, q, location, filters: { ...filters, status: undefined } }, tab === "applied");
  const stageCount = (statuses: string[]) =>
    stageFacets.data ? (stageFacets.data.values ?? []).filter((v) => statuses.includes(String(v.value))).reduce((n, v) => n + v.count, 0) : null;
  const list = useJobsList({ ...filterParams, sort, limit: pageSize }, !meta.isPending);
  const tabs = useJobsTabs(filterParams);
  const exporter = useExportJobs();
  const pick = useSelectJobs();
  const bulkPick = (on: boolean) =>
    pick.mutate(
      { ids: [...selected], selected: on },
      {
        onSuccess: () => toast.show({ message: `${on ? "Ticked" : "Unticked"} ${formatCount(nSel)} for pipeline` }),
        onError: (e) => toast.show({ message: errorText(e) }),
      },
    );
  const captionId = useId();
  const panelId = useId();

  const rows = useMemo(() => list.data?.pages.flatMap((p) => p.items ?? []) ?? [], [list.data]);
  const total = list.data?.pages[0]?.total ?? rows.length;
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = list;
  const paged = usePaged(rows, {
    total,
    resetKey: JSON.stringify([filterParams, sort]),
    onNeedMore: useCallback(() => {
      if (hasNextPage && !isFetchingNextPage) void fetchNextPage();
    }, [hasNextPage, isFetchingNextPage, fetchNextPage]),
  });
  const hidden = useMemo(() => new Set(view.hidden), [view.hidden]);
  const columns = useMemo(() => COLUMNS.filter((c) => !hidden.has(c.key)), [hidden]);
  const selectedKey = view.selected.join(",");
  const selected = useMemo(() => new Set(selectedKey ? selectedKey.split(",") : []), [selectedKey]);

  const setSelected = useCallback((ids: Iterable<string>) => update({ selected: [...ids] }, true), [update]);
  const onToggle = useCallback(
    (id: string) => {
      const next = new Set(selected);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      setSelected(next);
    },
    [selected, setSelected],
  );
  const onToggleAll = () => {
    const next = new Set(selected);
    const shown = paged.pageItems;
    const allOn = shown.length > 0 && shown.every((r) => next.has(r.job_id));
    for (const r of shown) {
      if (allOn) next.delete(r.job_id);
      else next.add(r.job_id);
    }
    setSelected(next);
  };
  const onSort = useCallback((key: SortKey) => update({ sort: toggleSort(sort, key) }), [update, sort]);
  const onSortTo = useCallback((s: string) => update({ sort: s }), [update]);
  const onFilter = useCallback(
    (field: FilterField, f: ColumnFilter | null) => {
      const next = { ...filters };
      if (f) next[field] = f;
      else delete next[field];
      update({ filters: next });
    },
    [update, filters],
  );
  const onSearch = useCallback((text: string) => update({ q: text }, true), [update]);
  const onLocation = useCallback((text: string) => update({ location: text }, true), [update]);

  const serverTabs = new Map((tabs.data?.tabs ?? []).map((t) => [t.key, t]));
  const nSel = selected.size;
  const [reviewing, setReviewing] = useState(false);
  const startRef = useRef<HTMLButtonElement>(null);
  const wasReviewing = useRef(false);
  // Unticking every job ends the review, so ticking the next one doesn't reopen it; Back refocuses Start pipeline.
  useEffect(() => {
    if (!nSel) setReviewing(false);
  }, [nSel]);
  useEffect(() => {
    if (wasReviewing.current && !reviewing) startRef.current?.focus();
    wasReviewing.current = reviewing;
  }, [reviewing]);

  function onExport() {
    const cols = ["job_id", ...columns.map((c) => c.exportField)];
    const body =
      nSel > 0
        ? { job_ids: [...selected], columns: cols }
        : { tab, q: q || undefined, location: location || undefined, sort, columns: cols, ...exportFilters(filters) };
    exporter.mutate(body, {
      onSuccess: (name) => toast.show({ message: `Downloaded ${name}` }),
      onError: (e) => toast.show({ message: errorText(e) }),
    });
  }

  let body;
  if (list.isError && rows.length === 0) {
    body = (
      <EmptyState
        title="Couldn’t load jobs"
        action={
          <Button size="small" onClick={() => void list.refetch()}>
            Try again
          </Button>
        }
      >
        {errorText(list.error)}
      </EmptyState>
    );
  } else if (list.isPending) {
    body = <p className={styles.loading}>Loading jobs…</p>;
  } else if (rows.length === 0) {
    body = q || location ? (
      <EmptyState
        title={q ? `No jobs match “${q}”` : `No jobs in “${location}”`}
        action={
          <Button size="small" onClick={() => update({ q: "", location: "" }, true)}>
            Clear search
          </Button>
        }
      >
        Try a company, role or location, or another tab.
      </EmptyState>
    ) : (
      <EmptyState
        title="No jobs here yet"
        action={
          tab === "recommended" ? (
            <Link to="/automation">Open Automation</Link>
          ) : (
            <Button size="small" onClick={() => update({ tab: "recommended" }, true)}>
              Show recommended jobs
            </Button>
          )
        }
      >
        {tab === "recommended"
          ? "Scout adds postings here. Run scout from Automation or the command line."
          : "Nothing in this tab right now. Other tabs may have jobs."}
      </EmptyState>
    );
  } else if (mode === "list") {
    body = <JobsList rows={paged.pageItems} tab={tab} selected={selected} onToggle={onToggle} current={jobId} />;
  } else if (mode === "board") {
    body = (
      <JobsBoard
        rows={paged.pageItems}
        onMove={(job, status) =>
          move.mutateAsync({ jobId: job.job_id, status }).catch((e) => {
            toast.show({ message: `Couldn’t move ${job.company || job.job_id} to ${status}: ${errorText(e)}` });
            throw e;
          })
        }
      />
    );
  } else {
    body = (
      <JobsTable
        filters={filters}
        onFilter={onFilter}
        filterParams={filterParams}
        onSortTo={onSortTo}
        rows={paged.pageItems}
        columns={columns}
        sort={sort}
        onSort={onSort}
        selected={selected}
        onToggle={onToggle}
        onToggleAll={onToggleAll}
        total={total}
        captionId={captionId}
      />
    );
  }

  if (jobId && mode !== "list") return <JobDetailPage />;
  return (
    <Page
      title="Jobs"
      subtitle="Every tracked posting · same columns as the Jobs tab in JobTracker.xlsx"
      actions={<HeaderActions />}
    >
      {reviewing && nSel > 0 ? (
        <StartPipeline
          ids={[...selected]}
          rows={rows.filter((r) => selected.has(r.job_id))}
          onToggle={onToggle}
          onUntick={(drop) => setSelected([...selected].filter((id) => !drop.includes(id)))}
          onClose={() => setReviewing(false)}
        />
      ) : (
      <div className={styles.stack}>
        <div className={styles.toolbar}>
          <Tabs label="Filter jobs" value={tab} onValueChange={(v) => update({ tab: v as TabKey })} controls={panelId}>
            {TABS.map((k) => (
              <Tabs.Tab key={k} value={k} count={serverTabs.get(k)?.count}>
                {serverTabs.get(k)?.label ?? TAB_LABELS[k]}
              </Tabs.Tab>
            ))}
          </Tabs>
          <FilterField
            value={q}
            onCommit={onSearch}
            name="jobs-q"
            label="Search jobs"
            placeholder="Company, role or location…"
            icon={<Search size={14} strokeWidth={1.7} aria-hidden="true" />}
          />
          <FilterField
            value={location}
            onCommit={onLocation}
            name="jobs-loc"
            label="Filter by location"
            placeholder="Location…"
            icon={<MapPin size={14} strokeWidth={1.7} aria-hidden="true" />}
          />
          <span className={styles.grow} />
          <div role="status" aria-live="polite" className={styles.bulk}>
            {nSel > 0 ? (
              <>
                <span className="tabular">{formatCount(nSel)} selected</span>
                <Button size="small" disabled={pick.isPending} onClick={() => bulkPick(true)}>
                  Tick for pipeline
                </Button>
                <Button size="small" disabled={pick.isPending} onClick={() => bulkPick(false)}>
                  Untick
                </Button>
                <Button size="small" onClick={() => setSelected([])}>
                  Clear selection
                </Button>
              </>
            ) : null}
          </div>
          <span data-tour="start-pipeline" hidden={tab !== "saved"}>
            {nSel > 0 ? (
              <Button ref={startRef} size="small" variant="primary" onClick={() => setReviewing(true)}>
                Start pipeline
              </Button>
            ) : (
              <UnavailableButton size="small" variant="primary" reason="Tick jobs first">
                Start pipeline
              </UnavailableButton>
            )}
          </span>
          <SegmentedControl label="View" value={mode} onValueChange={(v) => chooseView(v as ViewKey)}>
            {VIEWS.filter((v) => v !== "board" || tab === "applied").map((v) => (
              <SegmentedControl.Option key={v} value={v}>
                {VIEW_LABELS[v]}
              </SegmentedControl.Option>
            ))}
          </SegmentedControl>
          <Menu label="Columns">
            <Menu.Trigger size="small" icon={<Table2 size={14} strokeWidth={1.7} aria-hidden="true" />}>
              Columns
            </Menu.Trigger>
            <Menu.Content align="end">
              {COLUMNS.filter((c) => c.key !== "company").map((c) => (
                <Menu.CheckboxItem
                  key={c.key}
                  checked={!hidden.has(c.key)}
                  onCheckedChange={(on) =>
                    update({ hidden: on ? view.hidden.filter((k) => k !== c.key) : [...view.hidden, c.key] })
                  }
                >
                  {c.label}
                </Menu.CheckboxItem>
              ))}
            </Menu.Content>
          </Menu>
          <Button
            size="small"
            icon={<Download size={14} strokeWidth={1.7} aria-hidden="true" />}
            pending={exporter.isPending}
            pendingLabel="Exporting…"
            onClick={onExport}
          >
            {nSel > 0 ? `Export ${formatCount(nSel)} to xlsx` : "Export xlsx"}
          </Button>
        </div>
        {tab === "applied" && mode !== "board" ? (
          <Tabs label="Stage" value={stage || "all"} onValueChange={(v) => update({ stage: v === "all" ? "" : (v as StageKey) })} controls={panelId}>
            <Tabs.Tab value="all" count={stageCount(STAGES.flatMap((x) => x.statuses))}>All</Tabs.Tab>
            {STAGES.map((x) => (
              <Tabs.Tab key={x.key} value={x.key} count={stageCount(x.statuses)}>
                {x.label}
              </Tabs.Tab>
            ))}
          </Tabs>
        ) : null}
        <FilterChips filters={filters} onFilter={onFilter} onClearAll={() => update({ filters: {} })} />
        <div className={jobId ? styles.split : undefined}>
        <section
          id={panelId}
          role="tabpanel"
          aria-labelledby={rows.length ? captionId : undefined}
          aria-label={rows.length ? undefined : "Jobs"}
          aria-busy={list.isFetching || undefined}
          className={styles.card}
        >
          {body}
          {rows.length > 0 ? (
            <div className={styles.footer}>
              <span className="tabular">
                {formatCount(total)} {TAB_NOUNS[tab]} · live from data/careeros.db
              </span>
              <span>Open a job to change its status or add notes</span>
              <Pager paged={paged} label="Jobs" />
            </div>
          ) : null}
        </section>
        {jobId ? (
          <aside aria-label="Job detail" className={styles.detail}>
            <JobDetailPage embedded />
          </aside>
        ) : null}
        </div>
      </div>
      )}
    </Page>
  );
}
