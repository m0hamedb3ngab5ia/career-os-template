import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { Button, ButtonLink } from "../../kit/Button";
import { EmptyState } from "../../kit/EmptyState";
import { useToast } from "../../kit/Toast";
import { formatCount } from "../../lib/format";
import { sortTasks, taskRow } from "./actions";
import { errorText, useMarkDone, useMeta, useReopen, useToday } from "./api";
import type { ActionItem } from "./types";
import styles from "./Today.module.css";

/** "Needs your attention": every open Action Item in priority order, one plain row and one CTA each (Today, locked). */
export function NeedsYou({ jobIds }: { jobIds?: readonly string[] } = {}) {
  const today = useToday();
  const meta = useMeta();
  const toast = useToast();
  const markDone = useMarkDone();
  const reopen = useReopen();
  const undoSeconds = meta.data?.ui?.undo_seconds;
  const headingRef = useRef<HTMLHeadingElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  /** After Mark done: the row that left and the row whose control takes focus (null = the heading). */
  const [refocus, setRefocus] = useState<{ done: string; next: string | null } | null>(null);

  function onDone(item: ActionItem) {
    const i = shown.findIndex((a) => a.id === item.id);
    const next = shown[i + 1] ?? shown[i - 1];
    setRefocus({ done: String(item.id), next: next ? String(next.id) : null });
    markDone.mutate(item, {
      onSuccess: (res) =>
        toast.show({
          message: `Marked ${item.company} done.${res?.queued.length ? " The tracker is open in Excel, so the change is queued." : ""}`,
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

  // `jobIds`: only these jobs' tasks (Today filtered by batch, docs/design/ui-redesign.md §4.2 Review queue).
  const shown = sortTasks((today.data?.actions ?? []).filter((a) => !jobIds || jobIds.includes(a.job_id ?? "")));
  useEffect(() => {
    if (!refocus || shown.some((a) => String(a.id) === refocus.done)) return;
    setRefocus(null);
    const row = refocus.next === null ? null : listRef.current?.querySelector(`[data-action-id="${CSS.escape(refocus.next)}"]`);
    const target = row?.querySelector<HTMLElement>("[data-mark-done]") ?? row?.querySelector<HTMLElement>("a");
    (target ?? headingRef.current)?.focus();
  });

  return (
    <section className={styles.list} aria-labelledby="needs-you-title" aria-busy={today.isPending || undefined}>
      <div className={styles.listHead}>
        <h2 id="needs-you-title" ref={headingRef} tabIndex={-1} className={styles.h2}>
          Needs your attention {today.data ? <span className={`${styles.count} tabular`}>{formatCount(shown.length)}</span> : null}
        </h2>
        <Link to="/actions" className={styles.headLink}>
          View all tasks
        </Link>
      </div>
      {today.isPending ? (
        <div className={styles.skeletonBlock} aria-label="Loading tasks" role="img" />
      ) : today.isError ? (
        <EmptyState
          title="Couldn’t load tasks"
          headingLevel={3}
          action={
            <Button size="small" onClick={() => void today.refetch()}>
              Retry
            </Button>
          }
        >
          {errorText(today.error)}
        </EmptyState>
      ) : shown.length === 0 ? (
        <EmptyState title="Nothing needs you" headingLevel={3}>
          New tasks appear here when a run needs a decision from you.
        </EmptyState>
      ) : (
        <ul ref={listRef} className={styles.rows}>
          {shown.map((item) => (
            <TaskRowItem key={item.id} item={item} onDone={onDone} />
          ))}
        </ul>
      )}
    </section>
  );
}

function TaskRowItem({ item, onDone }: { item: ActionItem; onDone: (item: ActionItem) => void }) {
  const r = taskRow(item);
  return (
    <li className={styles.row} data-action-id={String(item.id)}>
      <div className={styles.rowMain}>
        <div className={`${styles.rowTitle} ${styles.strong}`}>{r.title}</div>
        {r.why ? <div className={styles.rowWhat}>{r.why}</div> : null}
      </div>
      <div className={styles.rowSide}>
        {r.detected ? null : (
          <button type="button" className={styles.textButton} data-mark-done aria-label={`Mark done: ${item.company || r.title}`} onClick={() => onDone(item)}>
            Mark done
          </button>
        )}
        <ButtonLink to={r.href}>{r.cta}</ButtonLink>
      </div>
    </li>
  );
}
