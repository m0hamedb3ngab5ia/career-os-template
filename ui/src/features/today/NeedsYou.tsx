import { useEffect, useRef, useState } from "react";
import { Button } from "../../kit/Button";
import { EmptyState } from "../../kit/EmptyState";
import { useToast } from "../../kit/Toast";
import { formatCount } from "../../lib/format";
import { Link } from "react-router";
import { sortTasks } from "./actions";
import { buildSections, type Row, type Section } from "./sections";
import { errorText, useAnswer, useMarkDone, useMeta, useReopen, useToday } from "./api";
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
  const listRef = useRef<HTMLElement>(null);
  /** After Mark done: the row that left and the row whose control takes focus (null = the heading). */
  const [refocus, setRefocus] = useState<{ done: string; next: string | null } | null>(null);

  function onDone(item: ActionItem) {
    // Next row as seen on screen (sections reorder the priority list), else the previous one.
    const ids = [...(listRef.current?.querySelectorAll<HTMLElement>("[data-action-id]") ?? [])].map((e) => e.dataset.actionId ?? "");
    const i = ids.indexOf(String(item.id));
    const next = i < 0 ? undefined : ids[i + 1] ?? ids[i - 1];
    setRefocus({ done: String(item.id), next: next ?? null });
    markDone.mutate(item, {
      onSuccess: (res) =>
        toast.show({
          message: `Marked ${item.company || "task"} done.${res?.queued.length ? " The tracker is open in Excel, so the change is queued." : ""}`,
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

  const sections = buildSections(shown, (today.data?.outreach ?? []).filter((o) => !jobIds || jobIds.includes(o.job_id)));
  const total = sections.reduce((t, x) => t + x.rows.length, 0);

  if (today.isPending) return <div className={styles.skeletonBlock} aria-label="Loading tasks" role="img" />;
  if (today.isError)
    return (
      <EmptyState
        title="Couldn’t load what needs you"
        headingLevel={2}
        action={
          <Button size="small" onClick={() => void today.refetch()}>
            Try again
          </Button>
        }
      >
        {errorText(today.error)}
      </EmptyState>
    );
  return (
    <section ref={listRef} className={styles.sections} aria-labelledby="needs-you-title">
      <h2 id="needs-you-title" ref={headingRef} tabIndex={-1} className="sr-only">
        Needs you, {formatCount(total)}
      </h2>
      {total === 0 ? (
        <p className={styles.allClear}>Nothing needs you. New tasks show up here when a run needs a decision.</p>
      ) : (
        sections.map((sec) => <SectionList key={sec.key} section={sec} onDone={onDone} />)
      )}
    </section>
  );
}

const PREVIEW = 3;

function SectionList({ section, onDone }: { section: Section; onDone: (item: ActionItem) => void }) {
  const [open, setOpen] = useState(false);
  const rows = open ? section.rows : section.rows.slice(0, PREVIEW);
  const id = `sec-${section.key}`;
  return (
    <section className={styles.section} aria-labelledby={id}>
      <header className={styles.sectionHead}>
        <h3 id={id} className={styles.sectionTitle}>
          {section.title} <span className={styles.sectionCount}>{formatCount(section.rows.length)}</span>
        </h3>
        {section.caption ? <p className={styles.sectionCaption}>{section.caption}</p> : null}
      </header>
      <ul className={styles.inset}>
        {rows.map((r) => (
          <RowItem key={r.id} row={r} onDone={onDone} />
        ))}
        {section.rows.length > PREVIEW ? (
          <li>
            <button type="button" className={styles.more} aria-expanded={open} onClick={() => setOpen(!open)}>
              {open ? "Show less" : `Show ${formatCount(section.rows.length - PREVIEW)} more`}
            </button>
          </li>
        ) : null}
      </ul>
    </section>
  );
}

function RowItem({ row: r, onDone }: { row: Row; onDone: (item: ActionItem) => void }) {
  return (
    <li className={styles.cell} data-action-id={r.id}>
      <div className={styles.cellMain}>
        <div className={styles.cellTitle}>
          {r.title}
          {r.sub ? <span className={styles.cellSub}> · {r.sub}</span> : null}
        </div>
        {r.why ? <div className={styles.cellWhy}>{r.why}</div> : null}
      </div>
      <div className={styles.cellSide}>
        {r.detected ? null : (
          <button type="button" className={styles.textButton} data-mark-done aria-label={`Dismiss: ${r.title}`} onClick={() => r.items.forEach(onDone)}>
            Dismiss
          </button>
        )}
        {r.answerable && r.items[0] ? <AnswerControl item={r.items[0]} title={r.title} /> : null}
        {r.href && r.cta && r.external ? (
          <a href={r.href} target="_blank" rel="noopener noreferrer" className={styles.cellLink}>
            {r.cta}
          </a>
        ) : r.href && r.cta ? (
          <Link to={r.href} className={styles.cellLink}>
            {r.cta}
          </Link>
        ) : null}
      </div>
    </li>
  );
}

/** Inline Answer: a button reveals a field and Save; Esc cancels. The item closes once the answer is saved. */
function AnswerControl({ item, title }: { item: ActionItem; title: string }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const answer = useAnswer();
  const toast = useToast();
  const btn = useRef<HTMLButtonElement>(null);
  const cancel = () => {
    setOpen(false);
    setText("");
    queueMicrotask(() => btn.current?.focus());
  };
  if (!open)
    return (
      <button ref={btn} type="button" className={styles.cellLink} aria-label={`Answer: ${title}`} onClick={() => setOpen(true)}>
        Answer
      </button>
    );
  const save = () =>
    answer.mutate(
      { item, answer: text.trim() },
      {
        onSuccess: () => toast.show({ message: `Saved your answer for ${title}.` }),
        onError: (e) => toast.show({ message: `Couldn’t save the answer: ${errorText(e)}` }),
      },
    );
  return (
    <form
      className={styles.answerForm}
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) save();
      }}
      onKeyDown={(e) => e.key === "Escape" && (e.stopPropagation(), cancel())}
    >
      <input autoFocus type="text" className={styles.answerInput} placeholder="Your answer" value={text} onChange={(e) => setText(e.target.value)} aria-label={`Your answer for ${title}`} />
      <Button size="small" variant="primary" type="submit" disabled={!text.trim()} pending={answer.isPending} pendingLabel="Saving…">
        Save
      </Button>
    </form>
  );
}
