import { useEffect, type ReactNode } from "react";
import styles from "./PageHeader.module.css";

interface PageProps {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}

/** Page frame: large title, optional subtitle and right-aligned actions, then the body. Sets the tab title. */
export function Page({ title, subtitle, actions, children }: PageProps) {
  useEffect(() => {
    document.title = `${title} · career-os`;
  }, [title]);
  return (
    <>
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>{title}</h1>
          {subtitle ? <p className={styles.subtitle}>{subtitle}</p> : null}
        </div>
        {actions ? <div className={styles.actions}>{actions}</div> : null}
      </header>
      <div className={styles.body}>{children}</div>
    </>
  );
}
