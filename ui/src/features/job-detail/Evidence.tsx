import { ExternalLink } from "../../kit/ExternalLink";
import styles from "./JobDetail.module.css";

const URL_RE = /^https?:\/\//i;

/** Evidence entries are URLs (links) or short notes (text). */
export function EvidenceList({ items }: { items: string[] }) {
  if (items.length === 0) return <p className={styles.muted}>No evidence recorded.</p>;
  return (
    <ul className={styles.evidence}>
      {items.map((e, i) => (
        <li key={`${i}-${e}`}>{URL_RE.test(e) ? <ExternalLink href={e}>{e}</ExternalLink> : e}</li>
      ))}
    </ul>
  );
}

/** One per line; blank lines dropped. */
export function lines(text: string): string[] {
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
}
