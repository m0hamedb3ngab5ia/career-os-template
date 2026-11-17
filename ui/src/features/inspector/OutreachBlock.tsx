import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fileUrl } from "./api";
import styles from "./JobInspector.module.css";

// The drafts find-contacts / draft-outreach wrote (contacts.json, outreach.json). Read-only: copy the text and send it
// yourself. Nothing here sends, schedules or opens LinkedIn.

interface Draft {
  contact?: string;
  role?: string;
  linkedin_note?: string;
  linkedin_message?: string;
  email?: { subject?: string; body?: string } | null;
}

const ROLE: Record<string, string> = { recruiter: "Recruiter", hiring_manager: "Hiring manager", team_lead: "Team lead" };
const linkedinOnly = (u: unknown) => (typeof u === "string" && u.startsWith("https://www.linkedin.com/search/") ? u : null);

function useJobJson<T>(id: string, name: string | undefined) {
  return useQuery({
    queryKey: ["jobs", "json", id, name],
    enabled: !!name,
    queryFn: async () => {
      const res = await fetch(fileUrl(id, name!));
      if (!res.ok) throw new Error(`Couldn’t load ${name}`);
      return (await res.json()) as T;
    },
  });
}

export function OutreachBlock({ id, files }: { id: string; files: string[] }) {
  const hasOut = files.includes("outreach.json");
  const hasCon = files.includes("contacts.json");
  const out = useJobJson<{ drafts?: Draft[] }>(id, hasOut ? "outreach.json" : undefined);
  const con = useJobJson<{ search_urls?: Record<string, unknown> }>(id, hasCon ? "contacts.json" : undefined);
  if (!hasOut && !hasCon) return null;
  const drafts = (out.data?.drafts ?? []).filter((d) => d.email || d.linkedin_note || d.linkedin_message);
  const search = linkedinOnly(con.data?.search_urls?.recruiter);
  return (
    <section aria-label="Reach out">
      <h3 className={styles.h3}>Reach out</h3>
      <p className={styles.muted}>{drafts.length ? "You send these yourself. Nothing is sent from here." : "No draft written yet."}</p>
      {drafts.map((d, i) => (
        <div key={`${d.contact}-${i}`} className={styles.draft}>
          <h4 className={styles.h4}>{[ROLE[d.role ?? ""], d.contact].filter(Boolean).join(" ") || "Contact"}</h4>
          {d.email?.body ? (
            <Piece label="Email" copyLabel="Copy email" title={d.email.subject} text={d.email.body}
              copy={`${d.email.subject ? `Subject: ${d.email.subject}\n\n` : ""}${d.email.body}`} />
          ) : null}
          {d.linkedin_note ? <Piece label="LinkedIn note" copyLabel="Copy note" text={d.linkedin_note} copy={d.linkedin_note} /> : null}
          {d.linkedin_message ? <Piece label="LinkedIn message" copyLabel="Copy message" text={d.linkedin_message} copy={d.linkedin_message} /> : null}
        </div>
      ))}
      {search ? <a className={styles.posting} href={search} target="_blank" rel="noopener noreferrer">Search LinkedIn</a> : null}
    </section>
  );
}

function Piece({ label, copyLabel, title, text, copy }: { label: string; copyLabel: string; title?: string; text: string; copy: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  async function onCopy() {
    try {
      await navigator.clipboard.writeText(copy);
      setState("copied");
    } catch {
      setState("failed");
    }
    setTimeout(() => setState("idle"), 2000);
  }
  return (
    <div className={styles.piece}>
      <div className={styles.pieceHead}>
        <span className={styles.pieceLabel}>{label}</span>
        <button type="button" className={styles.copy} onClick={() => void onCopy()} aria-label={copyLabel}>
          {state === "copied" ? "Copied" : state === "failed" ? "Couldn’t copy" : "Copy"}
        </button>
      </div>
      {title ? <p className={styles.pieceTitle}>{title}</p> : null}
      <pre className={styles.text}>{text}</pre>
    </div>
  );
}
