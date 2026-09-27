import { Chip } from "../../kit/chips";
import { formatCount } from "../../lib/format";
import { Card, Muted } from "./Card";
import styles from "./JobDetail.module.css";
import type { Contact, ContactPolicy } from "./types";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");
}

const DEGREE: Record<number, string> = { 2: "2nd", 3: "3rd" };

function Relationship({ contact, policy }: { contact: Contact; policy?: ContactPolicy }) {
  if (policy?.reason === "LINKEDIN_CONNECTED" || contact.linkedin_degree === 1) return <Chip tone="orange">Connected</Chip>;
  const mutuals = contact.mutuals ?? 0;
  if (policy?.reason === "LINKEDIN_MUTUALS" || mutuals > 0) {
    return <Chip tone="orange">{mutuals === 1 ? "1 mutual" : `${formatCount(mutuals)} mutuals`}</Chip>;
  }
  const d = contact.linkedin_degree ? DEGREE[contact.linkedin_degree] : undefined;
  return d ? <Chip tone="gray">{d}</Chip> : null;
}

function draftState(c: Contact, manual: boolean): string {
  if (manual) return "Manual: tailor it";
  if (c.sent) return "Sent";
  return c.draft_message ? "Draft ready · you send" : "No draft yet";
}

function outreachCount(outreach: Record<string, unknown> | null | undefined): number | null {
  if (!outreach) return null;
  for (const k of ["drafts", "contacts", "messages"]) {
    const v = outreach[k];
    if (Array.isArray(v)) return v.length;
  }
  return null;
}

export function ContactsCard({
  contacts,
  policy,
  outreach,
}: {
  contacts: Contact[];
  policy: ContactPolicy[];
  outreach: Record<string, unknown> | null | undefined;
}) {
  const byName = new Map(policy.map((p) => [p.name.trim().toLowerCase(), p]));
  const n = outreachCount(outreach);
  return (
    <Card title="Contacts & outreach">
      {contacts.length === 0 ? (
        <Muted>No contacts yet. find-contacts adds them after the job is prepared.</Muted>
      ) : (
        <ul className={styles.list}>
          {contacts.map((c, i) => {
            const p = byName.get(c.name.trim().toLowerCase());
            return (
              <li key={`${c.name}-${i}`} className={styles.contact}>
                <span aria-hidden="true" className={styles.avatar}>
                  {initials(c.name)}
                </span>
                <div className={styles.grow}>
                  <div className={styles.strong}>{c.name}</div>
                  {c.title || c.role ? <div className={styles.caption}>{c.title || c.role}</div> : null}
                </div>
                <Relationship contact={c} policy={p} />
                <span className={styles.caption}>{draftState(c, !!p?.manual)}</span>
              </li>
            );
          })}
        </ul>
      )}
      <Muted>
        {outreach
          ? n !== null
            ? `Outreach drafted for ${formatCount(n)} ${n === 1 ? "contact" : "contacts"} · you send every message`
            : "Outreach drafted · you send every message"
          : "No outreach drafted yet."}
      </Muted>
    </Card>
  );
}
