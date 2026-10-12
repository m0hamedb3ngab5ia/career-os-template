import { CheckCircle2, Circle } from "lucide-react";
import { Link } from "react-router";
import { errorText } from "../today/api";
import { Button } from "../../kit/Button";
import { Details } from "../../kit/Details";
import { useState } from "react";
import { useReadiness, type ReadinessItem } from "./api";
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
        <>
          <ul className={styles.list}>{data.items.filter((i) => !i.done).map((i) => <Item key={i.id} i={i} />)}</ul>
          {/* Done items are reference only: tucked away so the open ones stand out. */}
          {data.items.some((i) => i.done) ? (
            <Details summary={`Done · ${data.items.filter((i) => i.done).length}`}>
              <ul className={styles.list}>{data.items.filter((i) => i.done).map((i) => <Item key={i.id} i={i} />)}</ul>
            </Details>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

function Item({ i }: { i: ReadinessItem }) {
  return (
    <li className={styles.row}>
      {i.done ? <CheckCircle2 size={16} aria-hidden="true" className={styles.done} /> : <Circle size={16} aria-hidden="true" className={styles.todo} />}
      <span className={styles.grow}>
        {i.label}
        <span className="sr-only">{i.done ? ", done" : ", not done"}</span>
        {i.must ? null : <span className={styles.muted}> · optional</span>}
      </span>
      {i.done ? null : <Link to={i.fix_link}>Fix it</Link>}
    </li>
  );
}

/** Profile header line: "Ready to auto-fill applications" or "N setup items remaining" + Review → the full checklist. */
export function ReadinessSummary() {
  const { data } = useReadiness();
  const [open, setOpen] = useState(false);
  const left = data?.items.filter((i) => i.must && !i.done).length ?? 0;
  if (open || !data) return <ReadinessCard />;
  return (
    <section id="readiness" className={`${styles.card} ${styles.summary}`} aria-label="Application readiness">
      <span className={styles.grow}>{data.ready ? "Ready to auto-fill applications" : `${left} setup item${left === 1 ? "" : "s"} remaining`}</span>
      <Button size="small" onClick={() => setOpen(true)}>Review</Button>
    </section>
  );
}
