import { CircleAlert, CircleCheck, Clock3, ShieldAlert, UserRoundCheck } from "lucide-react";
import type { DragEvent } from "react";
import { Link } from "react-router";
import { ActionTypeLabel, Chip, SafetyChip, TierBadge } from "../../kit/chips";
import { Menu, type MenuItem } from "../../kit/Menu";
import { formatMonthDay } from "../../lib/format";
import styles from "./Pipeline.module.css";
import type { Card, Hint } from "./types";

function capitalize(s: string): string {
  return s ? s[0]!.toUpperCase() + s.slice(1) : s;
}

export function HintLine({ hint }: { hint: Hint | null }) {
  if (!hint) return null;
  if (hint.kind === "action") {
    const day = formatMonthDay(hint.due);
    return (
      <div className={styles.hint} title={hint.due_reason ?? undefined}>
        <ActionTypeLabel type={hint.type} />
        {day ? <span className={styles.hintDue}>· due {day}</span> : null}
      </div>
    );
  }
  const [Icon, text] =
    hint.kind === "safety"
      ? [ShieldAlert, capitalize(hint.text)]
      : hint.kind === "not_scored"
        ? [Clock3, "Not scored yet"]
        : hint.kind === "tier_a"
          ? [UserRoundCheck, "Tier A · you submit"]
          : [CircleAlert, "QA failed"];
  return (
    <div className={styles.hint}>
      <Icon size={13} strokeWidth={1.7} aria-hidden="true" />
      {text}
    </div>
  );
}

interface JobCardProps {
  card: Card;
  moveItems: MenuItem[];
  dragging: boolean;
  pending: boolean;
  onDragStart: (card: Card) => void;
  onDragEnd: () => void;
}

/** A job on the board: tier, company, fit, role, safety, QA, override, "Move to…", and what's next. Draggable. */
export function JobCard({ card, moveItems, dragging, pending, onDragStart, onDragEnd }: JobCardProps) {
  const company = card.company || card.job_id;
  return (
    <div
      className={styles.card}
      data-job-id={card.job_id}
      draggable
      data-dragging={dragging || undefined}
      data-pending={pending || undefined}
      onDragStart={(e: DragEvent) => {
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", card.job_id);
        onDragStart(card);
      }}
      onDragEnd={onDragEnd}
    >
      <Link to={`/jobs/${encodeURIComponent(card.job_id)}`} className={styles.cardLink} draggable={false}>
        <span className={styles.cardTop}>
          <TierBadge tier={card.tier} />
          <span className={styles.company}>{company}</span>
          <span className={styles.fit}>
            {card.fit === null ? (
              <>
                <span aria-hidden="true">—</span>
                <span className="sr-only">Not scored yet</span>
              </>
            ) : (
              <>
                <span className="sr-only">Fit </span>
                {card.fit}
              </>
            )}
          </span>
        </span>
        {card.title ? <span className={styles.role}>{card.title}</span> : null}
      </Link>
      <div className={styles.cardMeta}>
        {card.safety ? (
          <span>
            <span className="sr-only">Safety </span>
            <SafetyChip verdict={card.safety} />
          </span>
        ) : null}
        {card.qa_passed === true ? (
          <Chip tone="green">
            <CircleCheck size={12} strokeWidth={2} aria-hidden="true" />
            QA
          </Chip>
        ) : card.qa_passed === false ? (
          <Chip tone="red">QA failed</Chip>
        ) : null}
        {card.override ? <Chip tone="gray">Override: {card.override}</Chip> : null}
        <span className={styles.move} data-move>
          <Menu size="small" label={`Move ${company} to`} items={moveItems}>
            Move to… <span className="sr-only">({company})</span>
          </Menu>
        </span>
      </div>
      <HintLine hint={card.hint} />
    </div>
  );
}
