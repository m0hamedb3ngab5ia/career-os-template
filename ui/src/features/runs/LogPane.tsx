import { useVirtualizer } from "@tanstack/react-virtual";
import { useEffect, useRef } from "react";
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
}

const LINE_H = 18;

/**
 * A run's output: virtualized (a long run writes thousands of lines), follows the tail while you're at the
 * bottom, and stops following when you scroll up to read. A focusable log region so the keyboard can scroll it.
 */
export function LogPane({ label, lines, empty }: LogPaneProps) {
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

  return (
    <div
      ref={ref}
      role="log"
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
  );
}
