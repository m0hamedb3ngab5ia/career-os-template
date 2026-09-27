import { useId, type ReactNode } from "react";
import styles from "./JobDetail.module.css";

/** A titled card: <section> named by its <h2>, with an optional right-hand item (chip, number, button). */
export function Card({
  title,
  icon,
  aside,
  children,
}: {
  title: string;
  icon?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <section aria-labelledby={id} className={styles.card}>
      <div className={styles.cardHead}>
        <h2 id={id} className={styles.h2}>
          {icon}
          {title}
        </h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function Muted({ children }: { children: ReactNode }) {
  return <p className={styles.muted}>{children}</p>;
}
