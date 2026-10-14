import { useState } from "react";
import { ButtonLink } from "../../kit/Button";
import { useReadiness } from "../profile/api";
import styles from "./Today.module.css";

/** True while a must-have is still open (REQ-131); false while loading, so Top picks never flashes first. */
export function useSetupOpen(): boolean | undefined {
  const r = useReadiness().data;
  return r ? r.items.some((i) => i.must && !i.done) : undefined;
}

/** REQ-131: setup card at the top of Today, only while a must-have is open. Data: REQ-102 readiness. */
export function SetupCard() {
  const [all, setAll] = useState(false);
  const musts = (useReadiness().data?.items ?? []).filter((i) => i.must);
  const open = musts.filter((i) => !i.done);
  if (!open.length) return null;
  const done = musts.length - open.length;
  return (
    <section className={`${styles.panel} ${styles.setup}`} aria-labelledby="setup-title">
      <div className={styles.oneLine}>
        <span className={styles.ring} role="img" aria-label={`${done} of ${musts.length} required items done`}
          style={{ "--pct": `${(done / musts.length) * 100}%` } as React.CSSProperties}>
          <span aria-hidden="true">{done}/{musts.length}</span>
        </span>
        <div className={styles.grow}>
          <h2 id="setup-title" className={styles.h2}>Finish setup</h2>
          <p className={styles.caption}>Finish setup so CareerOS can fill applications for you.</p>
        </div>
        <ButtonLink to={open[0]!.fix_link || "/profile"} variant="primary">Finish setup</ButtonLink>
      </div>
      <button type="button" className={styles.linkBtn} aria-expanded={all} onClick={() => setAll(!all)}>
        {all ? "Hide items" : `Show all (${musts.length})`}
      </button>
      {all ? (
        <ul className={styles.plainList}>
          {musts.map((i) => (
            <li key={i.id}>{i.done ? "Done" : "To do"}: {i.label}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
