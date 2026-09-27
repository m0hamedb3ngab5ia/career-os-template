import { Check, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { ApiError } from "../../api/client";
import { useMeta } from "../../api/queries";
import { Page } from "../../app/PageHeader";
import { Button } from "../../kit/Button";
import { EmptyState } from "../../kit/EmptyState";
import { Listbox } from "../../kit/Listbox";
import { NEEDS, PRIORITIES, describeCode } from "../../kit/labels";
import { SegmentedControl } from "../../kit/SegmentedControl";
import { useToast } from "../../kit/Toast";
import { formatCount } from "../../lib/format";
import { useNow } from "../../lib/useNow";
import styles from "./ActionItems.module.css";
import { ActionRow } from "./ActionRow";
import { AddItemSheet } from "./AddItemSheet";
import { useActions, useMarkDone, useReopen } from "./api";
import { DueSheet } from "./DueSheet";
import { QUEUED_NOTE } from "./queued";
import type { ActionGroup, ActionItem, GroupBy, SortBy, Tab, WriteResult } from "./types";
import { useUndoSeconds } from "./useUndoSeconds";

const TABS: { value: Tab; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "today", label: "Today" },
  { value: "done", label: "Done" },
];
const GROUP_OPTIONS: { value: GroupBy; label: string }[] = [
  { value: "due", label: "Due date" },
  { value: "priority", label: "Priority" },
  { value: "needs", label: "Needs" },
];
const SORT_OPTIONS: { value: SortBy; label: string }[] = [
  { value: "soonest", label: "Soonest, then priority" },
  { value: "priority", label: "Priority, then soonest" },
  { value: "newest", label: "Newest first" },
];
const DUE_GROUPS: Record<string, { label: string; tone?: "red" | "orange" }> = {
  overdue: { label: "Overdue", tone: "red" },
  today: { label: "Today", tone: "orange" },
  tomorrow: { label: "Tomorrow", tone: "orange" },
  week: { label: "Next 7 days" },
  later: { label: "Later" },
  nodate: { label: "No date" },
  done: { label: "Done" },
};

function pick<T extends string>(v: string | null, options: { value: T }[]): T {
  return (options.find((o) => o.value === v) ?? options[0]!).value;
}

function groupHeading(group: GroupBy, key: string): { label: string; tone?: "red" | "orange" } {
  if (group === "priority") return { label: `${describeCode(PRIORITIES, key).label} priority` };
  if (group === "needs") return { label: describeCode(NEEDS, key).label };
  return DUE_GROUPS[key] ?? { label: key };
}

function problem(e: unknown): string {
  return e instanceof ApiError ? e.message : "Couldn't reach careeros ui. Is it still running?";
}

function queuedNote(r: WriteResult): string {
  return r.queued.length ? QUEUED_NOTE : "";
}

export function ActionItemsPage() {
  const [params, setParams] = useSearchParams();
  const tab = pick(params.get("tab"), TABS);
  const group = pick(params.get("group"), GROUP_OPTIONS);
  const sort = pick(params.get("sort"), SORT_OPTIONS);
  const selected = new Set((params.get("sel") ?? "").split(",").filter(Boolean));
  const { data, isPending, error } = useActions({ tab, group, sort });
  const soonHours = useMeta().data?.ui.due_soon_hours ?? 48;
  const now = useNow(60_000);
  const toast = useToast();
  const seconds = useUndoSeconds();
  const markDone = useMarkDone();
  const reopen = useReopen();
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());
  const [dateFor, setDateFor] = useState<ActionItem | null>(null);
  const [adding, setAdding] = useState(false);
  // After Add date the row re-renders without its Add date button: put focus on that row's Mark done instead.
  const [refocusRow, setRefocusRow] = useState<string | null>(null);
  useEffect(() => {
    if (!refocusRow) return;
    const li = [...document.querySelectorAll<HTMLElement>("[data-action-id]")].find((n) => n.dataset.actionId === refocusRow);
    if (li?.querySelector("[data-add-date]")) return; // still the old row: wait for the refetch
    li?.querySelector<HTMLElement>("[data-row-focus] button")?.focus();
    setRefocusRow(null);
  }, [data, refocusRow]);

  function update(changes: Record<string, string | null>) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [k, v] of Object.entries(changes)) {
          if (v) next.set(k, v);
          else next.delete(k);
        }
        return next;
      },
      { replace: true },
    );
  }

  const openIds = new Set(data?.groups.flatMap((g) => g.items.filter((i) => !i.done).map((i) => i.id)) ?? []);
  const selectedOpen = [...selected].filter((id) => openIds.has(id));

  function setSelected(id: string, on: boolean) {
    const next = new Set(selected);
    if (on) next.add(id);
    else next.delete(id);
    update({ sel: [...next].join(",") || null });
  }

  function complete(ids: string[], text: string) {
    setPendingIds((p) => new Set([...p, ...ids]));
    markDone.mutate(ids, {
      onSuccess: (r) => {
        const left = [...selected].filter((id) => !ids.includes(id));
        update({ sel: left.join(",") || null });
        toast.show({
          message: text + queuedNote(r),
          seconds,
          onUndo: () => reopen.mutate(ids, { onError: (e) => toast.show({ message: `Undo failed: ${problem(e)}` }) }),
        });
      },
      onError: (e) => toast.show({ message: `Couldn't mark done: ${problem(e)}` }),
      onSettled: () => setPendingIds((p) => new Set([...p].filter((id) => !ids.includes(id)))),
    });
  }

  function reopenOne(item: ActionItem) {
    reopen.mutate([item.id], {
      onSuccess: (r) => toast.show({ message: `Reopened ${item.company || item.what}${queuedNote(r)}` }),
      onError: (e) => toast.show({ message: `Couldn't reopen: ${problem(e)}` }),
    });
  }

  const head = data?.head;
  const subtitle = (
    <>
      Things only you can do ·{" "}
      <span className={head?.overdue ? styles.overdue : undefined}>
        {head?.overdue ? `${formatCount(head.overdue)} overdue` : "none overdue"}
      </span>{" "}
      ·{" "}
      <span className={head?.soon ? styles.soon : undefined}>
        {head?.soon
          ? `${formatCount(head.soon)} due within ${formatCount(soonHours)} hours`
          : `nothing due within ${formatCount(soonHours)} hours`}
      </span>{" "}
      · every link opens the exact page
    </>
  );

  const n = selectedOpen.length;
  return (
    <Page
      title="Action Items"
      subtitle={subtitle}
      actions={
        <>
          <Button icon={<Plus size={14} strokeWidth={1.7} aria-hidden="true" />} onClick={() => setAdding(true)}>
            Add item
          </Button>
          <Button
            variant="primary"
            icon={<Check size={14} strokeWidth={1.7} aria-hidden="true" />}
            disabled={n === 0 || tab === "done"}
            pending={markDone.isPending && n > 1}
            pendingLabel="Marking…"
            onClick={() => complete(selectedOpen, `Marked ${formatCount(n)} done`)}
          >
            {n === 0 ? "Mark selected done" : `Mark ${formatCount(n)} selected done`}
          </Button>
        </>
      }
    >
      <div className={styles.toolbar}>
        <SegmentedControl label="Show" value={tab} onValueChange={(v) => update({ tab: v === "open" ? null : v })}>
          {TABS.map((t) => (
            <SegmentedControl.Option key={t.value} value={t.value}>
              {t.label}{" "}
              <span className={styles.tabCount}>{formatCount(data?.counts[t.value] ?? 0)}</span>
            </SegmentedControl.Option>
          ))}
        </SegmentedControl>
        {tab !== "done" ? (
          <div className={styles.pickers}>
            <Listbox label="Group by" value={group} options={GROUP_OPTIONS}
              onValueChange={(v) => update({ group: v === "due" ? null : v })} />
            <Listbox label="Sort" value={sort} options={SORT_OPTIONS}
              onValueChange={(v) => update({ sort: v === "soonest" ? null : v })} />
          </div>
        ) : null}
      </div>

      <div className={styles.list}>
        {error ? (
          <EmptyState title="Couldn't load Action Items">{problem(error)}</EmptyState>
        ) : isPending ? null : tab === "done" ? (
          <DoneList groups={data?.groups ?? []} more={data?.more_done ?? 0} onReopen={reopenOne} />
        ) : data && data.groups.length ? (
          data.groups.map((g) => {
            const h = groupHeading(group, g.key);
            const id = `grp-${g.key}`;
            return (
              <section key={g.key} aria-labelledby={id} className={styles.group}>
                <h2 id={id} className={styles.groupTitle} data-heading={h.tone}>
                  {h.label}{" "}
                  <span className={styles.groupCount}>{formatCount(g.count)}</span>
                </h2>
                <ul className={styles.rows}>
                  {g.items.map((item) => (
                    <ActionRow
                      key={item.id}
                      item={item}
                      now={now}
                      selected={selected.has(item.id)}
                      pending={pendingIds.has(item.id)}
                      onSelectChange={setSelected}
                      onDone={(it) => complete([it.id], `Marked done: ${it.company || it.what}`)}
                      onAddDate={setDateFor}
                    />
                  ))}
                </ul>
              </section>
            );
          })
        ) : (
          <div className={styles.empty}>Nothing needs you right now. New items appear after the next run.</div>
        )}
      </div>
      {dateFor ? <DueSheet item={dateFor} onClose={() => setDateFor(null)} onSaved={setRefocusRow} /> : null}
      {adding ? <AddItemSheet onClose={() => setAdding(false)} /> : null}
    </Page>
  );
}

function DoneList({ groups, more, onReopen }: { groups: ActionGroup[]; more: number; onReopen: (i: ActionItem) => void }) {
  const items = groups.flatMap((g) => g.items);
  if (!items.length) return <div className={styles.empty}>Nothing done yet.</div>;
  return (
    <section aria-labelledby="grp-done" className={styles.group}>
      <h2 id="grp-done" className={styles.groupTitle}>
        Done
      </h2>
      <ul className={styles.rows}>
        {items.map((it) => (
          <li key={it.id} className={styles.doneRow}>
            <span className={styles.doneMark} aria-hidden="true">
              <Check size={13} strokeWidth={2.4} />
            </span>
            <div className={styles.doneText}>
              <div className={styles.title}>{it.company || it.what}</div>
              <div className={styles.doneWhat}>{it.what}</div>
            </div>
            <Button size="small" aria-label={`Reopen: ${it.company || it.what}`} onClick={() => onReopen(it)}>
              Reopen
            </Button>
          </li>
        ))}
      </ul>
      {more > 0 ? <div className={styles.more}>{formatCount(more)} more done earlier</div> : null}
    </section>
  );
}
