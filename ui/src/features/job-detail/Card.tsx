import { useId, type ReactNode } from "react";
import styles from "./JobDetail.module.css";

/** A titled card: <section> named by its <h2>, with an optional right-hand item (chip, number, button). */
export function Card({
  title,
  icon,
  aside,
  wide,
  id: anchor,
  nested,
  children,
}: {
  title: string;
  icon?: ReactNode;
  aside?: ReactNode;
  /** Spans the full row of the Job detail grid. */
  wide?: boolean;
  /** Page anchor (e.g. `qa`) so other cards can link here. */
  id?: string;
  /** A section inside another card (e.g. QA and Safety in Checks): no border, h3. */
  nested?: boolean;
  children: ReactNode;
}) {
  const id = useId();
  const H = nested ? "h3" : "h2";
  return (
    <section
      id={anchor}
      aria-labelledby={id}
      className={nested ? styles.subCard : styles.card}
      data-wide={wide || undefined}
    >
      <div className={styles.cardHead}>
        <H id={id} className={styles.h2}>
          {icon}
          {title}
        </H>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function Muted({ children }: { children: ReactNode }) {
  return <p className={styles.muted}>{children}</p>;
}
