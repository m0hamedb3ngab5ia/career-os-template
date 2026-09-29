import { ArrowLeft, Mail, RefreshCw, Settings, TriangleAlert } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";
import { Page } from "../../app/PageHeader";
import { Button } from "../../kit/Button";
import { Chip, StatusChip } from "../../kit/chips";
import { EmptyState } from "../../kit/EmptyState";
import { ExternalLink } from "../../kit/ExternalLink";
import { Pager, usePaged } from "../../kit/Pager";
import { UnavailableButton } from "../../kit/UnavailableButton";
import { formatDate, formatDateTime, formatRelative } from "../../lib/format";
import { useNow } from "../../lib/useNow";
import { DraftSheet } from "../drafts/DraftSheet";
import { DraftText } from "../drafts/DraftText";
import { kindLabel, modeLabel } from "../drafts/labels";
import type { Draft } from "../drafts/types";
import { useInbox, useInboxThread } from "./api";
import styles from "./InboxPage.module.css";
import { emailClass, nextTone } from "./labels";
import type { InboxDetailResponse, InboxRow, ThreadEvent } from "./types";

export const EDIT_REASON = "Editing drafts here isn't built yet";
export const SKIP_REASON = "Skipping notes isn't built yet";

function rowMeta(r: InboxRow, now: Date): string {
  if (r.last_email) {
    const when = formatDate(r.last_email.at);
    return when ? `${emailClass(r.last_email.class).label} · ${when}` : emailClass(r.last_email.class).label;
  }
  if (r.status === "applied" && r.applied_at) return `Applied ${formatRelative(r.applied_at, now) ?? ""}`.trim();
  return "";
}

function nextChipText(r: InboxRow): string {
  const due = formatDate(r.next.due);
  return due ? `${kindLabel(r.next.kind)} · due ${due}` : kindLabel(r.next.kind);
}

export function InboxPage() {
  const { jobId } = useParams();
  const now = useNow(60_000);
  const { data, isPending, isError, error } = useInbox();
  const items = data?.items ?? [];
  const paged = usePaged(items);
  const selectedId = jobId ?? items[0]?.job_id;
  const syncReason = data?.sync.reason ?? "Inbox sync isn't set up yet";
  const lastSync = data?.last_sync ? formatDateTime(data.last_sync) : null;

  const actions = (
    <>
      <UnavailableButton reason={syncReason} icon={<RefreshCw size={14} aria-hidden="true" />}>
        Sync inbox
      </UnavailableButton>
      <Link to="/settings/outreach" className={styles.linkButton}>
        <Settings size={14} strokeWidth={1.7} aria-hidden="true" />
        Follow-up rules
      </Link>
    </>
  );

  return (
    <Page
      title="Inbox & Follow-ups"
      subtitle="After you apply · Gmail sync classifies replies, follow-ups wait here for you"
      actions={actions}
    >
      {isError ? (
        <div role="alert" className={styles.card}>
          <EmptyState title="Couldn't load the inbox">{error instanceof Error ? `${error.message}. ` : ""}Check that Career OS is still running, then reload.</EmptyState>
        </div>
      ) : isPending ? (
        <div className={styles.card} aria-busy="true">
          <p className={styles.loading}>Loading…</p>
        </div>
      ) : items.length === 0 ? (
        <div className={styles.card}>
          <EmptyState title="Nothing after applying yet">
            Jobs show up here once they are applied, with replies from inbox sync and the follow-ups due.
          </EmptyState>
        </div>
      ) : (
        <div className={styles.layout} data-selected={jobId ? "true" : undefined}>
          <section aria-labelledby="postapply-h" className={`${styles.card} ${styles.list}`}>
            <div className={styles.listHead}>
              <h2 id="postapply-h" className={styles.h2small}>
                Post-apply
              </h2>
              <span className={styles.sec}>
                {lastSync ? (
                  <>
                    Last inbox sync <span className="tabular">{lastSync}</span>
                  </>
                ) : (
                  "Inbox sync hasn't run yet"
                )}
              </span>
            </div>
            <ul className={styles.rows}>
              {paged.pageItems.map((r) => (
                <li key={r.job_id}>
                  <Link
                    to={`/inbox/${encodeURIComponent(r.job_id)}`}
                    className={styles.row}
                    aria-current={r.job_id === selectedId ? "true" : undefined}
                  >
                    <span className={styles.rowTop}>
                      <span className={styles.company}>{r.company ?? "Unknown company"}</span>
                      <span className={styles.meta}>{rowMeta(r, now)}</span>
                    </span>
                    <span className={styles.role}>{r.title}</span>
                    <span className={styles.rowBottom}>
                      <Chip tone={nextTone(r.next.kind)}>{nextChipText(r)}</Chip>
                      <span className={styles.meta}>{modeLabel(r.next.mode).label}</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
            <Pager paged={paged} label="Follow-ups" />
          </section>
          <div className={styles.pane}>
            {jobId ? (
              <Link to="/inbox" className={styles.back}>
                <ArrowLeft size={14} aria-hidden="true" />
                All follow-ups
              </Link>
            ) : null}
            {selectedId ? <ThreadPane jobId={selectedId} sendingReason={data.sending.reason} /> : null}
          </div>
        </div>
      )}
    </Page>
  );
}

function ThreadPane({ jobId, sendingReason }: { jobId: string; sendingReason: string }) {
  const { data, isPending, isError, error } = useInboxThread(jobId);
  if (isError)
    return (
      <div role="alert" className={styles.card}>
        <EmptyState title="Couldn't load this job">{error instanceof Error ? `${error.message}. ` : ""}Check that Career OS is still running, then reload.</EmptyState>
      </div>
    );
  if (isPending || !data)
    return (
      <div className={styles.card} aria-busy="true">
        <p className={styles.loading}>Loading…</p>
      </div>
    );
  return (
    <>
      <NotePane key={jobId} d={data} sendingReason={sendingReason} />
      <Thread events={data.thread} />
    </>
  );
}

function noDraftText(kind: string): string {
  switch (kind) {
    case "post_interview_thanks":
      return "Thank-you notes are always written by you after the interview, with a detail only you know.";
    case "reply_with_slot":
      return "Reply to the interview invite yourself with a time that works.";
    case "offer_reply":
      return "Reply to the offer yourself.";
    default:
      return "Drafts appear after /draft-outreach runs for this job in Claude Code.";
  }
}

function policyText(mode: string): string {
  switch (mode) {
    case "sent":
      return "Already sent";
    case "always_manual":
      return "Thank-you notes are always manual: you send them yourself";
    case "manual":
      return "You know this person: tailor the note and send it yourself";
    case "verified_email":
      return "Auto-send will only ever go to a verified email; otherwise it becomes a LinkedIn draft";
    case "email_manual":
      return "Follow-ups are never sent automatically: copy it and send it yourself";
    default:
      return "LinkedIn is draft-only: copy it and send it yourself";
  }
}

function NotePane({ d, sendingReason }: { d: InboxDetailResponse; sendingReason: string }) {
  const [sheet, setSheet] = useState<number | null>(null);
  const draft: Draft | null = d.primary !== null ? (d.drafts[d.primary] ?? null) : null;
  const others = d.drafts.map((x, i) => ({ x, i })).filter(({ i }) => i !== d.primary);
  const heading = `${d.company ?? "Unknown company"} · ${kindLabel(draft?.kind ?? d.next.kind).toLowerCase()}`;
  // Send now / Pause auto-send only ever apply to a verified email; LinkedIn is draft-only, never automated
  const autoSendable = draft?.mode === "verified_email";
  const count = draft?.placeholders.length ?? 0;
  const opened = sheet !== null ? d.drafts[sheet] : undefined;

  let badge: { text: string; tone: "green" | "orange" | "purple" | "gray" };
  if (!draft) badge = { text: modeLabel(d.next.mode).label, tone: d.next.mode === "always_manual" ? "purple" : "gray" };
  else if (draft.sent) badge = { text: "Sent", tone: "green" };
  else if (draft.mode === "always_manual") badge = { text: "Always manual", tone: "purple" };
  else if (draft.mode === "manual") badge = { text: "Manual: you tailor it", tone: "orange" };
  else if (count > 0) badge = { text: "Fill placeholders first", tone: "orange" };
  else badge = { text: "Draft · not sent", tone: "gray" };

  return (
    <section aria-labelledby="note-h" className={`${styles.card} ${styles.note}`}>
      <div className={styles.noteHead}>
        <div className={styles.min0}>
          <h2 id="note-h" className={styles.h2}>
            {heading}
          </h2>
          {draft ? (
            <div className={styles.noteMeta}>
              {draft.to ? (
                <>
                  To <span translate="no">{draft.to}</span>
                </>
              ) : draft.contact ? (
                <>To {draft.contact}</>
              ) : null}
              {draft.to && draft.verified ? <Chip tone="green">Verified</Chip> : null}
              <span className="tabular">· {draft.words} words</span>
            </div>
          ) : (
            <div className={styles.noteMeta}>
              <StatusChip status={d.status} />
            </div>
          )}
        </div>
        <Chip tone={badge.tone}>{badge.text}</Chip>
      </div>

      {!draft ? (
        <EmptyState title="No draft for this job" headingLevel={3}>
          {noDraftText(d.next.kind)}
        </EmptyState>
      ) : (
        <>
          {count > 0 ? (
            <div className={styles.alert} role="note">
              <TriangleAlert size={16} strokeWidth={1.7} aria-hidden="true" className={styles.alertIcon} />
              <span className={styles.grow}>
                <strong>
                  {count} {count === 1 ? "placeholder" : "placeholders"} to fill before this can go out.
                </strong>
              </span>
              <UnavailableButton size="small" reason={EDIT_REASON}>
                Fill in placeholders
              </UnavailableButton>
            </div>
          ) : null}
          <div className={styles.letter} tabIndex={0} role="region" aria-label="Draft text">
            <DraftText text={draft.body} />
          </div>
          <div className={styles.noteActions}>
            {!autoSendable ? null : (
              <UnavailableButton variant="primary" reason={sendingReason} icon={<Mail size={14} aria-hidden="true" />}>
                Send now
              </UnavailableButton>
            )}
            <Button onClick={() => setSheet(d.primary)}>Edit note</Button>
            {!autoSendable ? null : <UnavailableButton reason={sendingReason}>Pause auto-send</UnavailableButton>}
            <UnavailableButton reason={SKIP_REASON}>Skip this note</UnavailableButton>
            <span className={styles.policy}>
              {policyText(draft.mode)}
            </span>
          </div>
        </>
      )}

      {others.length > 0 ? (
        <div className={styles.others}>
          <h3 className={styles.h3}>Other drafts for this job</h3>
          <ul className={styles.otherList}>
            {others.map(({ x, i }) => (
              <li key={i}>
                <Button size="small" onClick={() => setSheet(i)}>
                  {kindLabel(x.kind)}
                  {x.contact ? ` · ${x.contact}` : ""}
                  {formatDate(x.due) ? ` · due ${formatDate(x.due)}` : ""}
                </Button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {opened ? (
        <DraftSheet
          key={sheet}
          open
          onClose={() => setSheet(null)}
          draft={opened}
          company={d.company}
          jobTitle={d.title}
          tier={d.tier}
          edit={{ unavailable: EDIT_REASON }}
          approve={opened.mode === "verified_email" ? { unavailable: sendingReason } : undefined}
          discard={{ unavailable: "Discarding drafts isn't built yet" }}
        />
      ) : null}
    </section>
  );
}

function eventText(e: ThreadEvent): { text: string; chip: ReactNode; link?: string | null } {
  switch (e.type) {
    case "status":
      return {
        text: e.status === "applied" ? "You applied" : e.note ? `Status changed: ${e.note}` : "Status changed",
        chip: <StatusChip status={e.status} />,
      };
    case "email": {
      const c = emailClass(e.class);
      return { text: `${c.label} from ${e.from}`, chip: <Chip tone={c.tone}>{c.label}</Chip>, link: e.link };
    }
    case "pending_update":
      return {
        text: `Inbox sync found a change it couldn't apply${e.note ? `: ${e.note}` : ""}`,
        chip: <Chip tone="orange">Pending</Chip>,
      };
    case "sent":
      return { text: `${kindLabel(e.kind)} sent to ${e.contact}`, chip: <Chip tone="green">Sent</Chip> };
    default:
      return { text: "Event", chip: null };
  }
}

function Thread({ events }: { events: ThreadEvent[] }) {
  return (
    <section aria-labelledby="thread-h" className={`${styles.card} ${styles.thread}`}>
      <h2 id="thread-h" className={styles.h2thread}>
        Thread
      </h2>
      {events.length === 0 ? (
        <p className={styles.sec}>No emails synced for this job yet.</p>
      ) : (
        <ol className={styles.events}>
          {events.map((e, i) => {
            const t = eventText(e);
            return (
              <li key={`${e.at}-${i}`} className={styles.event}>
                <time dateTime={e.at} className={styles.when}>
                  {formatDateTime(e.at)}
                </time>
                <span className={styles.grow}>
                  {t.text}
                  {t.link ? (
                    <>
                      {" "}
                      <ExternalLink href={t.link}>Open in Gmail</ExternalLink>
                    </>
                  ) : null}
                </span>
                {t.chip}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
