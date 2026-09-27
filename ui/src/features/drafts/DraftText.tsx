import { Fragment } from "react";
import styles from "./DraftSheet.module.css";

const PLACEHOLDER = /(\[[^[\]\n]{1,120}\])/;

/** Draft text with every `[VARIABLE]` still to fill highlighted (the server's placeholder rule). */
export function DraftText({ text }: { text: string }) {
  const parts = text.split(PLACEHOLDER);
  return (
    <>
      {parts.map((p, i) =>
        i % 2 === 1 ? (
          <mark key={i} className={styles.placeholder}>
            {p}
          </mark>
        ) : (
          <Fragment key={i}>{p}</Fragment>
        ),
      )}
    </>
  );
}
