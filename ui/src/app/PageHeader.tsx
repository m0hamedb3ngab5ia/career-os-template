import { useEffect, type ReactNode } from "react";
import styles from "./PageHeader.module.css";

interface PageProps {
  title: string;
  /** REQ-119 guidance line: what the page is for and the next thing to do. */
  subtitle: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  /** The title is a placeholder while the page loads: marked aria-busy so the route announcer waits for the real one. */
  busy?: boolean;
  /** Inside another page (the Jobs detail pane): a level-2 heading, and the tab title is left to the host. */
  embedded?: boolean;
}

/** Page frame: large title, guidance line and right-aligned actions, then the body. Sets the tab title. */
export function Page({ title, subtitle, actions, children, busy, embedded }: PageProps) {
  useEffect(() => {
    if (!embedded) document.title = `${title} · career-os`;
  }, [title, embedded]);
  const H = embedded ? "h2" : "h1";
  return (
    <>
      <header className={styles.header}>
        <div>
          <H className={styles.title} aria-busy={busy || undefined}>{title}</H>
          {subtitle ? <div className={styles.subtitle}>{subtitle}</div> : null}
        </div>
        {actions ? <div className={styles.actions}>{actions}</div> : null}
      </header>
      <div className={styles.body}>{children}</div>
    </>
  );
}
