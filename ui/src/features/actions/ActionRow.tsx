import { Clock3 } from "lucide-react";
import { Link } from "react-router";
import { ActionTypeLabel, NeedsLabel, PriorityChip } from "../../kit/chips";
import { Details } from "../../kit/Details";
import { ExternalLink } from "../../kit/ExternalLink";
import { MarkDoneCircle } from "../../kit/MarkDoneCircle";
import { taskText } from "../../kit/labels";
import { formatDue } from "../../lib/format";
import styles from "./ActionItems.module.css";
import { isWebLink, linkLabel, shortLink } from "./links";
import { ScamControls } from "./ScamControls";
import type { ActionItem } from "./types";

interface ActionRowProps {
  item: ActionItem;
  now: Date;
  selected: boolean;
  pending: boolean;
  onSelectChange: (id: string, on: boolean) => void;
  onDone: (item: ActionItem) => void;
  onAddDate: (item: ActionItem) => void;
}

function titleOf(item: ActionItem): string {
  return item.company || item.what;
}

/** Skimmable task text: one plain headline, the rest as short bullets. Drops the company/role (the row title
 * shows them), local paths and "question:" labels. */
export function brief(item: { type?: string | null; what: string; company?: string | null; role?: string | null }): { head: string; more: string[] } {
  let t = taskText(item.type, item.what);
  if (item.company) t = t.replaceAll(item.role ? `${item.company} ${item.role}` : item.company, "");
  t = t.replace(/(Screenshot:\s*)?\S*data\/jobs\/\S*\.?/g, "").replace(/\(\s*\)/g, "").replace(/question:\s*/gi, "").replace(/\s+([.,;:])/g, "$1").replace(/\s{2,}/g, " ").trim();
  const [head = "", ...rest] = t.split(/(?<=\.)\s+/);
  const more = rest.join(" ").split(/;\s*|(?<=\.)\s+/).map((x) => x.replace(/\.$/, "").trim()).filter((x) => x && !x.endsWith(":"));
  return { head: head.replace(/\.$/, ""), more };
}

/** One open Action Item: select, Mark done, what to do, its deadline (or Add date), the link, priority, needs. */
export function ActionRow({ item, now, selected, pending, onSelectChange, onDone, onAddDate }: ActionRowProps) {
  const name = titleOf(item);
  const b = brief(item);
  const due = formatDue(item.due, item.due_date_only, now);
  return (
    <li className={styles.row} data-action-id={item.id} data-selected={selected || undefined} data-pending={pending || undefined}>
      <label className={styles.select}>
        <input type="checkbox" checked={selected} onChange={(e) => onSelectChange(item.id, e.target.checked)} />
        <span className="sr-only">Select {name}</span>
      </label>
      <span className={styles.doneSlot} data-row-focus>
        <MarkDoneCircle done={false} itemName={name} onDoneChange={() => onDone(item)} />
      </span>
      <div className={styles.body}>
        <h3 className={styles.title}>
          {item.company ? <span>{item.company}</span> : null}
          {item.role ? (
            <span className={styles.role} title={item.role}>
              {item.role}
            </span>
          ) : null}
        </h3>
        <div className={styles.what} title={item.what}>{b.head}</div>
        {b.more.length ? (
          <Details summary={`${b.more.length} more detail${b.more.length === 1 ? "" : "s"}`}>
            <ul className={styles.bullets}>{b.more.map((m) => <li key={m}>{m}</li>)}</ul>
          </Details>
        ) : null}
        {due ? (
          <div className={styles.due} data-level={item.level}>
            <Clock3 size={13} strokeWidth={1.7} aria-hidden="true" />
            <span>
              {due}
              {item.due_reason ? ` · ${item.due_reason}` : null}
            </span>
          </div>
        ) : (
          <button type="button" data-add-date className={styles.dateButton} onClick={() => onAddDate(item)}>
            <Clock3 size={13} strokeWidth={1.7} aria-hidden="true" />
            Add date <span className="sr-only">for {name}</span>
          </button>
        )}
        <div className={styles.linkRow}>
          {isWebLink(item.link) ? (
            <>
              <ExternalLink href={item.link}>{linkLabel(item.link)}</ExternalLink>
              <span className={styles.host} translate="no">
                {shortLink(item.link)}
              </span>
            </>
          ) : item.job_id ? (
            <Link to={`/jobs/${encodeURIComponent(item.job_id)}`}>Open job</Link>
          ) : item.link ? (
            <span className={styles.host} translate="no">
              {item.link}
            </span>
          ) : null}
          <ActionTypeLabel type={item.type} />
        </div>
        {item.scam_actions ? <ScamControls item={item} /> : null}
      </div>
      <div className={styles.side}>
        <PriorityChip priority={item.priority} />
        <NeedsLabel needs={item.needs} />
      </div>
    </li>
  );
}
