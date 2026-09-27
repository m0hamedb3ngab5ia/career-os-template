import { useVirtualizer } from "@tanstack/react-virtual";
import { useEffect, useRef, useState } from "react";
import styles from "./Runs.module.css";

export interface LogLine {
  key: number | string;
  text: string;
  /** Short left column ("job 2"), muted. */
  prefix?: string;
  error?: boolean;
}

interface LogPaneProps {
  label: string;
  lines: LogLine[];
  empty: string;
  /** A live run: new lines are summarised in a polite status at most every LOG_ANNOUNCE_MS. */
  live?: boolean;
}

const LINE_H = 18;

/** How often a live log may speak: a screen reader hears "12 new log lines" at most this often, never each line. */
export const LOG_ANNOUNCE_MS = 5000;

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** Counts the lines added since the last announcement and turns them into one throttled summary. */
function useLogSummary(lines: LogLine[], live: boolean): string {
  const [message, setMessage] = useState("");
  const lastKey = lines.at(-1)?.key;
  const seen = useRef(lastKey);
  const pending = useRef({ lines: 0, errors: 0 });
  const spokeAt = useRef(Number.NEGATIVE_INFINITY);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    if (lastKey === seen.current) return;
    const at = seen.current === undefined ? -1 : lines.findIndex((l) => l.key === seen.current);
    const fresh = lines.slice(at + 1);
    seen.current = lastKey;
    if (!live || fresh.length === 0) return;
    pending.current.lines += fresh.length;
    pending.current.errors += fresh.filter((l) => l.error).length;
    if (timer.current !== undefined) return;
    const flush = () => {
      timer.current = undefined;
      const { lines: n, errors } = pending.current;
      pending.current = { lines: 0, errors: 0 };
      spokeAt.current = Date.now();
      setMessage(plural(n, "new log line") + (errors ? `, ${plural(errors, "error")}` : ""));
    };
    const wait = spokeAt.current + LOG_ANNOUNCE_MS - Date.now();
    if (wait <= 0) flush();
    else timer.current = setTimeout(flush, wait);
  }, [lastKey, lines, live]);

  useEffect(() => () => clearTimeout(timer.current), []);
  return message;
}

/**
 * A run's output: virtualized (a long run writes thousands of lines), follows the tail while you're at the
 * bottom, and stops following when you scroll up to read. A focusable log region so the keyboard can scroll it.
 */
export function LogPane({ label, lines, empty, live = false }: LogPaneProps) {
  const summary = useLogSummary(lines, live);
  const ref = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const v = useVirtualizer({
    count: lines.length,
    getScrollElement: () => ref.current,
    estimateSize: () => LINE_H,
    overscan: 20,
    initialRect: { width: 600, height: 240 },
    getItemKey: (i) => lines[i]!.key,
  });

  // Follow on every new last line, not on the count: once the buffer is full the count stops changing.
  const lastKey = lines.at(-1)?.key;
  useEffect(() => {
    if (stick.current && lastKey !== undefined) v.scrollToIndex(lines.length - 1, { align: "end" });
  }, [lastKey, lines.length, v]);

  // role="log" is polite by default and would read every line; the summary below speaks for it instead.
  return (
    <>
      <div
        ref={ref}
        role="log"
        aria-live="off"
        aria-label={label}
        tabIndex={0}
        translate="no"
        className={styles.log}
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < LINE_H * 2;
        }}
      >
        {lines.length === 0 ? (
          <span className={styles.logEmpty}>{empty}</span>
        ) : (
          <div style={{ height: v.getTotalSize(), position: "relative" }}>
            {v.getVirtualItems().map((item) => {
              const line = lines[item.index]!;
              return (
                <div
                  key={item.key}
                  data-index={item.index}
                  ref={v.measureElement}
                  className={styles.logLine}
                  data-error={line.error || undefined}
                  style={{ transform: `translateY(${item.start}px)` }}
                >
                  {line.prefix ? <span className={styles.logPrefix}>{line.prefix}</span> : null}
                  <span>{line.text}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>
      <div role="status" className="sr-only" data-testid="log-announcer">
        {summary}
      </div>
    </>
  );
}
