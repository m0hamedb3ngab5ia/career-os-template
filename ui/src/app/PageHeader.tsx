import { useEffect, type ReactNode } from "react";
import styles from "./PageHeader.module.css";

interface PageProps {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  /** The title is a placeholder while the page loads: marked aria-busy so the route announcer waits for the real one. */
  busy?: boolean;
}

/** Page frame: large title, optional subtitle and right-aligned actions, then the body. Sets the tab title. */
export function Page({ title, subtitle, actions, children, busy }: PageProps) {
  useEffect(() => {
    document.title = `${title} · career-os`;
  }, [title]);
  return (
    <>
      <header className={styles.header}>
        <div>
          <h1 className={styles.title} aria-busy={busy || undefined}>{title}</h1>
          {subtitle ? <div className={styles.subtitle}>{subtitle}</div> : null}
        </div>
        {actions ? <div className={styles.actions}>{actions}</div> : null}
      </header>
      <div className={styles.body}>{children}</div>
    </>
  );
}
