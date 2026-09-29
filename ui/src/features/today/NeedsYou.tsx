import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { Button } from "../../kit/Button";
import { ActionTypeLabel, NeedsLabel, PriorityChip } from "../../kit/chips";
import { Details } from "../../kit/Details";
import { EmptyState } from "../../kit/EmptyState";
import { ExternalLink } from "../../kit/ExternalLink";
import { MarkDoneCircle } from "../../kit/MarkDoneCircle";
import { useToast } from "../../kit/Toast";
import { dueInfo, type DueLevel } from "../../lib/dates";
import { formatDue } from "../../lib/format";
import { formatCount } from "../../lib/format";
import { useNow } from "../../lib/useNow";
import { groupByJob, jobCta, linkInfo, type JobGroup } from "./actions";
import { errorText, useMarkDone, useMeta, useReopen, useToday } from "./api";
import type { ActionItem } from "./types";
import styles from "./Today.module.css";

/** The "Needs you" list: every open Action Item, grouped by job with one next step each (design doc 3 "Today"). */
export function NeedsYou() {
  const today = useToday();
  const meta = useMeta();
  const now = useNow(60_000);
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

  const all = today.data?.actions ?? [];
  const groups = groupByJob(all);
  const shown = groups.flatMap((g) => g.items);
  useEffect(() => {
    if (!refocus || shown.some((a) => String(a.id) === refocus.done)) return;
    setRefocus(null);
    const target =
      refocus.next === null
        ? null
        : listRef.current?.querySelector<HTMLElement>(`[data-action-id="${CSS.escape(refocus.next)}"] [role="checkbox"]`);
    (target ?? headingRef.current)?.focus();
  });

  return (
    <section className={styles.list} aria-labelledby="needs-you-title" aria-busy={today.isPending || undefined}>
      <div className={styles.listHead}>
        <h2 id="needs-you-title" ref={headingRef} tabIndex={-1} className={styles.h2}>
          Needs you {today.data ? <span className={`${styles.count} tabular`}>{formatCount(all.length)}</span> : null}
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
      ) : all.length === 0 ? (
        <EmptyState title="Nothing needs you" headingLevel={3}>
          New tasks appear here when a run needs a decision from you.
        </EmptyState>
      ) : (
        <ul ref={listRef} className={styles.groups}>
          {groups.map((g) => (
            <JobTasks key={g.jobId ?? ""} group={g} now={now} onDone={onDone} />
          ))}
        </ul>
      )}
    </section>
  );
}

function JobTasks({ group, now, onDone }: { group: JobGroup; now: Date; onDone: (item: ActionItem) => void }) {
  const n = group.items.length;
  return (
    <li className={styles.group}>
      <div className={styles.groupHead}>
        <div className={styles.rowMain}>
          {group.jobId ? (
            <h3 className={styles.rowTitle}>
              <span className={styles.strong} data-company translate="no">
                {group.company}
              </span>
              {group.role ? <span className={styles.rowRole}>{group.role}</span> : null}
            </h3>
          ) : (
            <h3 className={`${styles.rowTitle} ${styles.strong}`}>Other tasks</h3>
          )}
          <div className={styles.rowWhat}>{n === 1 ? "1 thing needs attention" : `${formatCount(n)} things need attention`}</div>
        </div>
        {group.jobId ? (
          <Link to={`/jobs/${encodeURIComponent(group.jobId)}`} className={styles.headLink}>
            {jobCta(group.items)}
          </Link>
        ) : null}
      </div>
      <ul className={styles.rows}>
        {group.items.map((item) => (
          <ActionRow key={item.id} item={item} now={now} onDone={onDone} showCompany={!group.jobId} />
        ))}
      </ul>
    </li>
  );
}

function ActionRow({ item, now, onDone, showCompany }: { item: ActionItem; now: Date; onDone: (item: ActionItem) => void; showCompany: boolean }) {
  const info = dueInfo(item.due, now);
  // Same fields as /api/actions: a date-only deadline has no time of day; the server's level wins when present.
  const due = info && {
    text: item.due_date_only ? (formatDue(item.due, true, now) ?? info.text) : info.text,
    level: (item.level as DueLevel | undefined) ?? info.level,
  };
  const link = linkInfo(item.link);
  return (
    <li className={styles.row} data-action-id={String(item.id)}>
      <span className={styles.rowDone}>
        <MarkDoneCircle done={false} onDoneChange={() => onDone(item)} itemName={item.company ? `${item.company}: ${item.what}` : item.what} />
      </span>
      <div className={styles.rowMain}>
        {showCompany && item.company ? (
          <div className={styles.rowTitle}>
            <span className={styles.strong} translate="no">
              {item.company}
            </span>
          </div>
        ) : null}
        <div className={styles.rowWhat}>{item.what}</div>
        {item.detail ? <Details summary="Details">{item.detail}</Details> : null}
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
