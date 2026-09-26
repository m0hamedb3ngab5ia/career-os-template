import { Lock, Search, Users } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { Page } from "../../app/PageHeader";
import { Button } from "../../kit/Button";
import { Chip } from "../../kit/chips";
import { EmptyState } from "../../kit/EmptyState";
import { UnavailableButton } from "../../kit/UnavailableButton";
import type { Tone } from "../../kit/labels";
import { formatCount } from "../../lib/format";
import { DraftSheet } from "../drafts/DraftSheet";
import { useContacts } from "./api";
import styles from "./ContactsPage.module.css";
import { MarkConnectionSheet } from "./MarkConnectionSheet";
import type { ContactRow } from "./types";

export const FIND_CONTACTS_REASON = "Finding contacts runs from Claude Code for now: /find-contacts";

const MODE_TEXT: Record<string, string> = {
  manual: "Manual: you tailor it",
  linkedin_draft: "LinkedIn draft ready · you send",
  email_draft: "Email draft · verified address",
  no_draft: "No draft yet",
  sent: "Sent",
  replied: "Replied",
};

const AVATAR_TONES: Tone[] = ["purple", "blue", "teal", "green", "gray"];
const ORDINAL: Record<number, string> = { 1: "1st", 2: "2nd", 3: "3rd" };

function initials(name: string): string {
  const parts = name.replace(/[^\p{L}\p{N}\s]/gu, "").split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1]![0] : "")).toUpperCase() || "?";
}

function toneFor(name: string): Tone {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return AVATAR_TONES[h % AVATAR_TONES.length]!;
}

function None({ label = "None" }: { label?: string }) {
  return (
    <>
      <span aria-hidden="true" className={styles.dash}>
        —
      </span>
      <span className="sr-only">{label}</span>
    </>
  );
}

function Connection({ degree }: { degree: number | null }) {
  if (degree === null) return <None label="Not marked" />;
  if (degree === 1)
    return (
      <span className={styles.badges}>
        <Chip tone="purple">1st</Chip>
        <Chip tone="orange">Connected</Chip>
      </span>
    );
  return <span className={styles.sec}>{ORDINAL[degree] ?? String(degree)}</span>;
}

function Mutuals({ n }: { n: number | null }) {
  if (n === null) return <None label="Not marked" />;
  if (n === 0) return <span className={styles.sec}>{formatCount(0)}</span>;
  return <Chip tone="orange">{`${formatCount(n)} ${n === 1 ? "mutual" : "mutuals"}`}</Chip>;
}

interface Selected {
  drafts: ContactRow[];
  index: number;
}

export function ContactsPage() {
  const { data, isPending, isError, error } = useContacts();
  const [marking, setMarking] = useState<ContactRow | null>(null);
  const [open, setOpen] = useState<Selected | null>(null);
  const items = data?.items ?? [];
  const linkedin = items.filter((c) => c.mode === "linkedin_draft" && c.draft);
  const policy = data?.policy;
  const gateOn = !policy || policy.manual_if_connected || policy.manual_if_mutuals;
  const current = open ? open.drafts[open.index] : undefined;

  const actions = (
    <>
      <UnavailableButton reason={FIND_CONTACTS_REASON} icon={<Search size={14} aria-hidden="true" />}>
        Find contacts
      </UnavailableButton>
      {linkedin.length > 0 ? (
        <Button
          variant="primary"
          icon={<Users size={14} aria-hidden="true" />}
          onClick={() => setOpen({ drafts: linkedin, index: 0 })}
        >
          Open LinkedIn drafts ({formatCount(linkedin.length)})
        </Button>
      ) : (
        <UnavailableButton variant="primary" reason="No LinkedIn drafts yet" icon={<Users size={14} aria-hidden="true" />}>
          Open LinkedIn drafts (0)
        </UnavailableButton>
      )}
    </>
  );

  return (
    <Page
      title="Contacts"
      subtitle="People at companies you applied to · LinkedIn is draft-only, you always send"
      actions={actions}
    >
      <div className={styles.stack}>
        <div className={styles.banner}>
          <Users size={18} strokeWidth={1.7} aria-hidden="true" className={styles.bannerIcon} />
          <p className={styles.bannerText}>
            {gateOn ? (
              <>
                <strong>No automated messages to people you know.</strong> If you are connected on LinkedIn or share
                mutuals, career-os writes nothing send-ready and adds an Action Item so you tailor the note yourself.
              </>
            ) : (
              <>
                <strong>Drafts go to people you know too.</strong> Your Outreach settings turn the connected and
                mutuals rules off.
              </>
            )}{" "}
            Degree and mutuals come from what you mark here (or <code translate="no">careeros outreach mark</code>).
          </p>
          <Link to="/settings/outreach" className={styles.bannerLink}>
            Outreach settings
          </Link>
        </div>

        {isError ? (
          <div role="alert" className={styles.card}>
            <EmptyState title="Couldn't load contacts">{error instanceof Error ? `${error.message}. ` : ""}Check that careeros ui is still running, then reload.</EmptyState>
          </div>
        ) : isPending ? (
          <div className={styles.card} aria-busy="true">
            <p className={styles.loading}>Loading contacts…</p>
          </div>
        ) : items.length === 0 ? (
          <div className={styles.card}>
            <EmptyState title="No contacts yet">
              People appear here after /find-contacts runs for a job in Claude Code. Nothing is ever sent from this
              list.
            </EmptyState>
          </div>
        ) : (
          <section aria-labelledby="contacts-caption" className={styles.card}>
            <div className={styles.scroll}>
              <table className={styles.table}>
                <caption id="contacts-caption" className="sr-only">
                  Contacts at companies you applied to
                </caption>
                <colgroup>
                  <col className={styles.colName} />
                  <col className={styles.colCompany} />
                  <col className={styles.colConn} />
                  <col className={styles.colMutuals} />
                  <col />
                  <col className={styles.colActions} />
                </colgroup>
                <thead>
                  <tr>
                    <th scope="col">Name</th>
                    <th scope="col">Company</th>
                    <th scope="col">Connection</th>
                    <th scope="col">Mutuals</th>
                    <th scope="col">Outreach</th>
                    <th scope="col">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((c) => (
                    <ContactRowView
                      key={`${c.job_id}/${c.name}`}
                      c={c}
                      onMark={() => setMarking(c)}
                      onOpen={() => setOpen({ drafts: [c], index: 0 })}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>

      <MarkConnectionSheet contact={marking} onClose={() => setMarking(null)} />
      {current ? (
        <DraftSheet
          key={`${current.job_id}/${current.name}`}
          open
          onClose={() => setOpen(null)}
          draft={current.draft}
          company={current.company}
          jobTitle={current.job_title}
          edit={{ unavailable: "Editing drafts here isn't built yet" }}
          pager={
            open && open.drafts.length > 1
              ? {
                  index: open.index,
                  count: open.drafts.length,
                  onPrev: () => setOpen((s) => (s ? { ...s, index: Math.max(0, s.index - 1) } : s)),
                  onNext: () => setOpen((s) => (s ? { ...s, index: Math.min(s.drafts.length - 1, s.index + 1) } : s)),
                }
              : undefined
          }
        />
      ) : null}
    </Page>
  );
}

function ContactRowView({ c, onMark, onOpen }: { c: ContactRow; onMark: () => void; onOpen: () => void }) {
  const tone = toneFor(c.name);
  return (
    <tr>
      <th scope="row">
        <div className={styles.person}>
          <span aria-hidden="true" className={styles.avatar} data-tone={tone}>
            {initials(c.name)}
          </span>
          <div className={styles.min0}>
            <div className={styles.name} title={c.name}>
              {c.linkedin ? (
                <a href={c.linkedin} target="_blank" rel="noopener noreferrer">
                  {c.name}
                  <span className="sr-only"> on LinkedIn (opens in a new tab)</span>
                </a>
              ) : (
                c.name
              )}
            </div>
            {c.title ? (
              <div className={styles.title} title={c.title}>
                {c.title}
              </div>
            ) : null}
          </div>
        </div>
      </th>
      <td className={styles.truncate} title={c.company ?? undefined}>
        {c.company ?? <None label="Unknown" />}
      </td>
      <td>
        <Connection degree={c.linkedin_degree} />
      </td>
      <td>
        <Mutuals n={c.mutuals} />
      </td>
      <td>
        <span className={styles.mode}>
          {c.mode === "manual" ? <Lock size={13} strokeWidth={1.7} aria-hidden="true" className={styles.lock} /> : null}
          <span>{MODE_TEXT[c.mode] ?? c.mode}</span>
        </span>
        {c.manual_detail ? <span className="sr-only">{`: ${c.manual_detail}`}</span> : null}
      </td>
      <td className={styles.actionsCell}>
        <span className={styles.rowActions}>
          <Button size="small" onClick={onMark} aria-label={`Mark connection for ${c.name}`}>
            Mark
          </Button>
          {c.mode === "manual" && c.draft ? (
            <Button size="small" variant="primary" onClick={onOpen} aria-label={`Tailor manually: ${c.name}`}>
              Tailor manually
            </Button>
          ) : c.draft && (c.mode === "linkedin_draft" || c.mode === "email_draft") ? (
            <Button size="small" onClick={onOpen} aria-label={`Open draft for ${c.name}`}>
              Open draft
            </Button>
          ) : null}
        </span>
      </td>
    </tr>
  );
}
