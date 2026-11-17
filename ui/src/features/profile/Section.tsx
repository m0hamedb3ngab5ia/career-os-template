import { useId, type ReactNode } from "react";
import styles from "./Lists.module.css";

/** One grouped inset list: a small heading, then rows of label + value. */
export function Group({ title, note, empty, rows }: { title: string; note?: ReactNode; empty: string; rows: { label: string; value: ReactNode; key: string }[] }) {
  const id = useId();
  return (
    <section aria-labelledby={id}>
      <h2 id={id} className={styles.heading}>
        {title}
      </h2>
      {rows.length ? (
        <ul className={styles.list}>
          {rows.map((r) => (
            <li key={r.key} className={styles.row}>
              <span className={styles.name}>{r.label}</span>
              <span className={styles.value}>{r.value}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className={`${styles.list} ${styles.empty}`}>{empty}</p>
      )}
      {note ? <p className={styles.note}>{note}</p> : null}
    </section>
  );
}
