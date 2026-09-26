import type { ReactNode } from "react";
import styles from "./controls.module.css";

interface EmptyStateProps {
  title: string;
  children?: ReactNode;
  /** A single next step, e.g. a "Clear filter" button. */
  action?: ReactNode;
  headingLevel?: 2 | 3;
}

export function EmptyState({ title, children, action, headingLevel = 2 }: EmptyStateProps) {
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <div className={styles.empty}>
      <Heading className={styles.emptyTitle}>{title}</Heading>
      {children ? <p className={styles.emptyBody}>{children}</p> : null}
      {action}
    </div>
  );
}
