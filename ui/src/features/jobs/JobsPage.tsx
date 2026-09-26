import { Download, FolderOpen, RefreshCw, Search, Table2 } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { Page } from "../../app/PageHeader";
import { useMeta } from "../../api/meta";
import { Button } from "../../kit/Button";
import { EmptyState } from "../../kit/EmptyState";
import { Menu } from "../../kit/Menu";
import { Tabs } from "../../kit/Tabs";
import { useToast } from "../../kit/Toast";
import { formatCount } from "../../lib/format";
import { useExportJobs, useJobsList, useJobsTabs, useOpenTracker, useSyncTracker } from "./api";
import { COLUMNS } from "./cells";
import { JobsTable } from "./JobsTable";
import styles from "./JobsPage.module.css";
import { TABS, toggleSort, useJobsView, type SortKey } from "./urlState";
import type { TabKey } from "./types";

const DEFAULT_PAGE_SIZE = 100;
const SEARCH_DEBOUNCE_MS = 250;

// Fallback labels until GET /api/jobs/tabs answers (the server's labels win).
const TAB_LABELS: Record<TabKey, string> = {
  active: "Active",
  review: "Needs review",
  applied: "Applied",
  tier_a: "Tier A",
  all: "All",
};
// Footer noun: "Showing 12 of 59 active jobs".
const TAB_NOUNS: Record<string, string> = {
  active: "active jobs",
  review: "jobs needing review",
  applied: "applied jobs",
  tier_a: "Tier A jobs",
  all: "jobs",
};

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
  return (
    <>
      <Button
        icon={<RefreshCw size={14} strokeWidth={1.7} aria-hidden="true" />}
        pending={sync.isPending}
        pendingLabel="Syncing…"
        onClick={() =>
          sync.mutate(undefined, {
            onSuccess: (r) =>
              toast.show({
                message: r.pending
                  ? `Synced ${formatCount(r.synced)} jobs. Excel has the tracker open, so the changes are queued until you close it.`
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

/** The search box commits to the URL after a short pause; it follows the URL when the sidebar search sets it. */
function SearchField({ q, onCommit }: { q: string; onCommit: (q: string) => void }) {
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
      <Search size={14} strokeWidth={1.7} aria-hidden="true" />
      <span className="sr-only">Search jobs</span>
      <input
        type="search"
        name="jobs-q"
        autoComplete="off"
        spellCheck={false}
        placeholder="Company, role or location…"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
    </label>
  );
}

export function JobsPage() {
  const toast = useToast();
  const [view, update] = useJobsView();
  const { tab, q, sort } = view;
  const meta = useMeta();
  const pageSize = meta.data?.ui?.page_size ?? DEFAULT_PAGE_SIZE;
  const list = useJobsList({ tab, q, sort, limit: pageSize }, !meta.isPending);
  const tabs = useJobsTabs(q);
  const exporter = useExportJobs();
  const captionId = useId();
  const panelId = useId();

  const rows = useMemo(() => list.data?.pages.flatMap((p) => p.items ?? []) ?? [], [list.data]);
  const total = list.data?.pages[0]?.total ?? rows.length;
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
    const allOn = rows.length > 0 && rows.every((r) => next.has(r.job_id));
    for (const r of rows) {
      if (allOn) next.delete(r.job_id);
      else next.add(r.job_id);
    }
    setSelected(next);
  };
  const onSort = useCallback((key: SortKey) => update({ sort: toggleSort(sort, key) }), [update, sort]);
  const onSearch = useCallback((text: string) => update({ q: text }, true), [update]);

  const serverTabs = new Map((tabs.data?.tabs ?? []).map((t) => [t.key, t]));
  const nSel = selected.size;

  function onExport() {
    const cols = ["job_id", ...columns.map((c) => c.exportField)];
    const body =
      nSel > 0 ? { job_ids: [...selected], columns: cols } : { tab, q: q || undefined, sort, columns: cols };
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
    body = q ? (
      <EmptyState
        title={`No jobs match “${q}”`}
        action={
          <Button size="small" onClick={() => update({ q: "" }, true)}>
            Clear search
          </Button>
        }
      >
        Try a company, role or location, or another tab.
      </EmptyState>
    ) : (
      <EmptyState title="No jobs here yet">
        {tab === "all"
          ? "Scout adds postings to this table. Run scout from Runs or the command line."
          : "Nothing in this tab right now. Other tabs may have jobs."}
      </EmptyState>
    );
  } else {
    body = (
      <JobsTable
        rows={rows}
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

  return (
    <Page
      title="Jobs"
      subtitle="Every tracked posting · same columns as the Jobs tab in JobTracker.xlsx"
      actions={<HeaderActions />}
    >
      <div className={styles.stack}>
        <div className={styles.toolbar}>
          <Tabs label="Filter jobs" value={tab} onValueChange={(v) => update({ tab: v as TabKey })} controls={panelId}>
            {TABS.map((k) => (
              <Tabs.Tab key={k} value={k} count={serverTabs.get(k)?.count}>
                {serverTabs.get(k)?.label ?? TAB_LABELS[k]}
              </Tabs.Tab>
            ))}
          </Tabs>
          <SearchField q={q} onCommit={onSearch} />
          <span className={styles.grow} />
          <div role="status" aria-live="polite" className={styles.bulk}>
            {nSel > 0 ? (
              <>
                <span className="tabular">{formatCount(nSel)} selected</span>
                <Button size="small" onClick={() => setSelected([])}>
                  Clear selection
                </Button>
              </>
            ) : null}
          </div>
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
                Showing {formatCount(rows.length)} of {formatCount(total)} {TAB_NOUNS[tab] ?? "jobs"} · live from
                data/careeros.db
              </span>
              <span>Open a job to change its status or add notes</span>
              {list.hasNextPage ? (
                <Button
                  size="small"
                  pending={list.isFetchingNextPage}
                  pendingLabel="Loading…"
                  onClick={() => void list.fetchNextPage()}
                >
                  Show more
                </Button>
              ) : (
                <span />
              )}
            </div>
          ) : null}
        </section>
      </div>
    </Page>
  );
}
