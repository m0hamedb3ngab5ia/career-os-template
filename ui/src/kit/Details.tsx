import type { ReactNode } from "react";
import styles from "./details.module.css";

// Collapsed-by-default disclosure for Advanced/debug content (design doc 2.3). Native <details>: keyboard and
// screen-reader behaviour come free.
export function Details({ summary, children, defaultOpen = false }: { summary: string; children: ReactNode; defaultOpen?: boolean }) {
  return (
    <details className={styles.details} open={defaultOpen || undefined}>
      <summary className={styles.summary}>{summary}</summary>
      <div className={styles.body}>{children}</div>
    </details>
  );
}
