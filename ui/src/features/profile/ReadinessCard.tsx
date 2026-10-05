import { CheckCircle2, Circle } from "lucide-react";
import { Link } from "react-router";
import { errorText } from "../today/api";
import { Button } from "../../kit/Button";
import { useReadiness } from "./api";
import styles from "./Profile.module.css";

/** REQ-102 readiness checklist (Today + Profile): every open item links to its fix; all must-haves → Ready to apply. */
export function ReadinessCard() {
  const { data, isPending, isError, error, refetch } = useReadiness();
  const open = data?.items.filter((i) => i.must && !i.done).length ?? 0;
  return (
    <section id="readiness" className={styles.card} aria-labelledby="readiness-h">
      <h2 id="readiness-h" className={styles.h2}>
        {data ? (data.ready ? "Ready to apply" : `Before you apply: ${open} must-have${open === 1 ? "" : "s"} left`) : "Readiness"}
      </h2>
      {isPending ? <p className={styles.muted}>Checking your setup…</p> : null}
      {isError ? (
        <p className={styles.muted}>
          Couldn’t check your setup: {errorText(error)}{" "}
          <Button size="small" onClick={() => void refetch()}>
            Try again
          </Button>
        </p>
      ) : null}
      {data ? (
        <ul className={styles.list}>
          {data.items.map((i) => (
            <li key={i.id} className={styles.row}>
              {i.done ? (
                <CheckCircle2 size={16} aria-hidden="true" className={styles.done} />
              ) : (
                <Circle size={16} aria-hidden="true" className={styles.todo} />
              )}
              <span className={styles.grow}>
                {i.label}
                <span className="sr-only">{i.done ? ", done" : ", not done"}</span>
                {i.must ? null : <span className={styles.muted}> · optional</span>}
              </span>
              {i.done ? null : <Link to={i.fix_link}>Fix</Link>}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
