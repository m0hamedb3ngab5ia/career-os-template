import { useVirtualizer } from "@tanstack/react-virtual";
import { useCallback, useRef } from "react";
import { Link, useSearchParams } from "react-router";
import { StopReasonChip } from "../../kit/chips";
import { EmptyState } from "../../kit/EmptyState";
import { Pager, usePaged } from "../../kit/Pager";
import { SegmentedControl } from "../../kit/SegmentedControl";
import { formatDuration, formatNumber, formatWhen } from "../../lib/format";
import { useNow } from "../../lib/useNow";
import { useRunHistory } from "./api";
import { STOP_FIX, kindLabel, needsYou, runChipCode, runTone, triggerLabel } from "./labels";
import styles from "./Runs.module.css";
import type { RunRecord } from "./types";

export const HISTORY_KINDS = ["", "scout", "score", "prepare", "inbox_sync", "tracker", "prune"] as const;

/** One line under the title: what the run did, then the fix when its stop reason needs you. */
export function runSummary(run: Omit<RunRecord, "attempts">): string {
  const c = run.counters ?? {};
  const parts: string[] = [];
  if (run.kind === "score" || run.kind === "prepare") {
    const done = run.kind === "score" ? "scored" : "prepared";
    parts.push(`${formatNumber(c.ok ?? 0)} of ${formatNumber(c.attempted ?? 0)} ${done}`);
  } else if (run.detail) {
    parts.push(run.detail);
  }
  const took = formatDuration(run.duration_s);
  if (took) parts.push(took);
  const code = runChipCode(run);
  if (needsYou(run) && code && STOP_FIX[code]) parts.push(STOP_FIX[code]);
  return parts.join(" · ");
}

function HistoryRow({ run, now }: { run: RunRecord; now: Date }) {
  const trig = triggerLabel(run.trigger);
  return (
    <Link to={`/automation/runs/${encodeURIComponent(run.id)}`} className={styles.historyRow}>
      <span className={styles.dot} data-tone={runTone(run)} aria-hidden="true" />
      <div className={styles.grow}>
        <div className={styles.strong}>
          {kindLabel(run.kind)}
          {trig ? ` · ${trig}` : ""}
        </div>
        <div className={styles.caption}>{runSummary(run)}</div>
      </div>
      <span className={styles.rowMeta}>{formatWhen(run.started_at, now)}</span>
      <StopReasonChip reason={runChipCode(run)} />
    </Link>
  );
}

/** Past and running runs, newest first; the kind filter lives in the URL (?history=score). */
export function HistoryCard() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("history") ?? "";
  const kind = (HISTORY_KINDS as readonly string[]).includes(raw) ? raw : "";
  const q = useRunHistory(kind);
  const now = useNow(60_000);
  const all = q.data?.pages.flatMap((p) => p.runs) ?? [];
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = q;
  const paged = usePaged(all, {
    more: hasNextPage,
    resetKey: kind,
    onNeedMore: useCallback(() => {
      if (hasNextPage && !isFetchingNextPage) void fetchNextPage();
    }, [hasNextPage, isFetchingNextPage, fetchNextPage]),
  });
  const runs = paged.pageItems;
  const ref = useRef<HTMLDivElement>(null);
  const v = useVirtualizer({
    count: runs.length,
    getScrollElement: () => ref.current,
    estimateSize: () => 58,
    overscan: 8,
    initialRect: { width: 520, height: 480 },
    getItemKey: (i) => runs[i]!.id,
  });

  function pick(value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set("history", value);
    else next.delete("history");
    setParams(next, { replace: true });
  }

  return (
    <section className={`${styles.card} ${styles.historyCard}`} aria-labelledby="hist-h">
      <div className={styles.cardHeadInline}>
        <h2 id="hist-h" className={styles.h2Inline}>
          History
        </h2>
        <span className={styles.caption}>Stop reason on every run</span>
      </div>
      <div className={styles.toolbarRow}>
        <SegmentedControl label="Run kind" value={kind} onValueChange={pick}>
          {HISTORY_KINDS.map((k) => (
            <SegmentedControl.Option key={k || "all"} value={k}>
              {k ? kindLabel(k) : "All"}
            </SegmentedControl.Option>
          ))}
        </SegmentedControl>
      </div>
      {q.error ? (
        <p role="alert" className={styles.fix}>
          {q.error.message}
        </p>
      ) : q.isPending ? (
        <p className={styles.sub}>Loading…</p>
      ) : runs.length === 0 ? (
        <EmptyState title="No runs yet" headingLevel={3}>
          {kind ? `No ${kindLabel(kind).toLowerCase()} runs so far.` : "Runs you start here or on a schedule show up here."}
        </EmptyState>
      ) : (
        <div ref={ref} className={styles.historyScroll} role="list" aria-label="Runs">
          <div style={{ height: v.getTotalSize(), position: "relative" }}>
            {v.getVirtualItems().map((item) => (
              <div
                key={item.key}
                role="listitem"
                data-index={item.index}
                ref={v.measureElement}
                className={styles.virtualRow}
                style={{ transform: `translateY(${item.start}px)` }}
              >
                <HistoryRow run={runs[item.index]!} now={now} />
              </div>
            ))}
          </div>
        </div>
      )}
      <Pager paged={paged} label="Runs" />
    </section>
  );
}
