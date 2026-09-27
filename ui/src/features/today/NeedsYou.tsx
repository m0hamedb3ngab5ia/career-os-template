import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { Button } from "../../kit/Button";
import { ActionTypeLabel, NeedsLabel, PriorityChip } from "../../kit/chips";
import { EmptyState } from "../../kit/EmptyState";
import { ExternalLink } from "../../kit/ExternalLink";
import { MarkDoneCircle } from "../../kit/MarkDoneCircle";
import { PillGroup } from "../../kit/PillGroup";
import { SegmentedControl } from "../../kit/SegmentedControl";
import { useToast } from "../../kit/Toast";
import { dueInfo } from "../../lib/dates";
import { formatCount } from "../../lib/format";
import { useNow } from "../../lib/useNow";
import {
  DEFAULT_FILTER,
  DEFAULT_SORT,
  FILTERS,
  SORTS,
  filterActions,
  linkInfo,
  parseFilter,
  parseSort,
  sortActions,
} from "./actions";
import { errorText, useMarkDone, useMeta, useReopen, useToday } from "./api";
import type { ActionItem } from "./types";
import styles from "./Today.module.css";

/** The "Needs you" list: every open Action Item, sortable and filterable (both kept in the query string). */
export function NeedsYou() {
  const today = useToday();
  const meta = useMeta();
  const now = useNow(60_000);
  const [params, setParams] = useSearchParams();
  const sort = parseSort(params.get("sort"));
  const filter = parseFilter(params.get("filter"));
  const toast = useToast();
  const markDone = useMarkDone();
  const reopen = useReopen();
  const undoSeconds = meta.data?.ui?.undo_seconds;
  const headingRef = useRef<HTMLHeadingElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  /** After Mark done: the row that left and the row whose control takes focus (null = the heading). */
  const [refocus, setRefocus] = useState<{ done: string; next: string | null } | null>(null);

  function setParam(key: "sort" | "filter", value: string, fallback: string) {
    setParams(
      (p) => {
        const next = new URLSearchParams(p);
        if (value === fallback) next.delete(key);
        else next.set(key, value);
        return next;
      },
      { replace: true },
    );
  }

  function onDone(item: ActionItem) {
    const i = shown.findIndex((a) => a.id === item.id);
    const next = shown[i + 1] ?? shown[i - 1];
    setRefocus({ done: String(item.id), next: next ? String(next.id) : null });
    markDone.mutate(item, {
      onSuccess: (res) =>
        toast.show({
          message: `Marked ${item.company} done.${res?.queued ? " The tracker is open in Excel, so the change is queued." : ""}`,
          seconds: undoSeconds,
          onUndo: () =>
            reopen.mutate(item, {
              onError: (e) => toast.show({ message: `Couldn’t reopen ${item.company}: ${errorText(e)}` }),
            }),
        }),
      onError: (e) => {
        setRefocus(null); // the row comes back: nothing to move focus to
        toast.show({ message: `Couldn’t mark ${item.company} done: ${errorText(e)}` });
      },
    });
  }

  const all = today.data?.actions ?? [];
  const shown = sortActions(filterActions(all, filter, now), sort);
  useEffect(() => {
    if (!refocus || shown.some((a) => String(a.id) === refocus.done)) return;
    setRefocus(null);
    const target =
      refocus.next === null
        ? null
        : listRef.current?.querySelector<HTMLElement>(`[data-action-id="${CSS.escape(refocus.next)}"] [role="checkbox"]`);
    (target ?? headingRef.current)?.focus();
  });
  const countLabel = shown.length === all.length ? formatCount(all.length) : `${formatCount(shown.length)} of ${formatCount(all.length)}`;

  return (
    <section className={styles.list} aria-labelledby="needs-you-title" aria-busy={today.isPending || undefined}>
      <div className={styles.listHead}>
        <h2 id="needs-you-title" ref={headingRef} tabIndex={-1} className={styles.h2}>
          Needs you {today.data ? <span className={`${styles.count} tabular`}>{countLabel}</span> : null}
        </h2>
        <Link to="/actions" className={styles.headLink}>
          All action items
        </Link>
      </div>
      {today.isPending ? (
        <div className={styles.skeletonBlock} aria-label="Loading action items" role="img" />
      ) : today.isError ? (
        <EmptyState
          title="Couldn’t load action items"
          headingLevel={3}
          action={
            <Button size="small" onClick={() => void today.refetch()}>
              Retry
            </Button>
          }
        >
          {errorText(today.error)}
        </EmptyState>
      ) : all.length === 0 ? (
        <EmptyState title="Nothing needs you" headingLevel={3}>
          New action items appear here when a run needs a decision from you.
        </EmptyState>
      ) : (
        <>
          <div className={styles.controls}>
            <SegmentedControl label="Sort" value={sort} onValueChange={(v) => setParam("sort", v, DEFAULT_SORT)}>
              {SORTS.map((s) => (
                <SegmentedControl.Option key={s.value} value={s.value}>
                  {s.label}
                </SegmentedControl.Option>
              ))}
            </SegmentedControl>
            <PillGroup label="Filter" value={filter} onValueChange={(v) => setParam("filter", v, DEFAULT_FILTER)}>
              {FILTERS.map((f) => (
                <PillGroup.Pill key={f.value} value={f.value}>
                  {f.label}
                </PillGroup.Pill>
              ))}
            </PillGroup>
          </div>
          {shown.length === 0 ? (
            <p className={styles.emptyLine}>
              Nothing matches this filter.{" "}
              <button type="button" className={styles.textButton} onClick={() => setParam("filter", DEFAULT_FILTER, DEFAULT_FILTER)}>
                Clear filter
              </button>
            </p>
          ) : (
            <ul ref={listRef} className={styles.rows}>
              {shown.map((item) => (
                <ActionRow key={item.id} item={item} now={now} onDone={onDone} />
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

function ActionRow({ item, now, onDone }: { item: ActionItem; now: Date; onDone: (item: ActionItem) => void }) {
  const due = dueInfo(item.due, now);
  const link = linkInfo(item.link);
  return (
    <li className={styles.row} data-action-id={String(item.id)}>
      <span className={styles.rowDone}>
        <MarkDoneCircle done={false} onDoneChange={() => onDone(item)} itemName={`${item.company}: ${item.what}`} />
      </span>
      <div className={styles.rowMain}>
        <div className={styles.rowTitle}>
          <span className={styles.strong} data-company translate="no">
            {item.company}
          </span>
          {item.role ? <span className={styles.rowRole}>{item.role}</span> : null}
        </div>
        <div className={styles.rowWhat}>{item.what}</div>
        {due ? (
          <div className={styles.due} data-level={due.level}>
            {item.due_reason ? `${due.text} · ${item.due_reason}` : due.text}
          </div>
        ) : (
          <div className={styles.due} data-level="none">
            No date
          </div>
        )}
        <div className={styles.rowMeta}>
          {link?.kind === "web" ? (
            <ExternalLink href={link.href}>{link.label}</ExternalLink>
          ) : link?.kind === "text" ? (
            <span className={styles.linkText} translate="no">
              {link.text}
            </span>
          ) : null}
          <ActionTypeLabel type={item.type} />
        </div>
      </div>
      <div className={styles.rowSide}>
        <PriorityChip priority={item.priority} />
        <NeedsLabel needs={item.needs} />
      </div>
    </li>
  );
}
