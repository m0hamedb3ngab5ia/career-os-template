import type { LucideIcon } from "lucide-react";
import {
  Bot,
  CircleDollarSign,
  CircleHelp,
  Clock3,
  Eye,
  Ghost,
  Laptop,
  MessageSquareText,
  Mail,
  MoreHorizontal,
  Puzzle,
  ShieldAlert,
  Smartphone,
  UserRoundSearch,
  XCircle,
} from "lucide-react";
import type { ReactNode } from "react";
import styles from "./chips.module.css";
import {
  ACTION_TYPES,
  NEEDS,
  PRIORITIES,
  SAFETY,
  STATUSES,
  STOP_REASONS,
  TIERS,
  describeCode,
  type Tone,
} from "./labels";

type Code = string | null | undefined;

export function Chip({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={styles.chip} data-tone={tone}>
      {children}
    </span>
  );
}

export function StatusChip({ status }: { status: Code }) {
  const { label, tone } = describeCode(STATUSES, status);
  return <Chip tone={tone}>{label}</Chip>;
}

export function SafetyChip({ verdict }: { verdict: Code }) {
  const { label, tone } = describeCode(SAFETY, verdict);
  return (
    <Chip tone={tone}>
      <span className={styles.dot} data-dot aria-hidden="true" />
      {label}
    </Chip>
  );
}

export function PriorityChip({ priority }: { priority: Code }) {
  const { label, tone } = describeCode(PRIORITIES, priority);
  return <Chip tone={tone}>{label}</Chip>;
}

export function StopReasonChip({ reason }: { reason: Code }) {
  const { label, tone } = describeCode(STOP_REASONS, reason);
  return <Chip tone={tone}>{label}</Chip>;
}

export function TierBadge({ tier }: { tier: Code }) {
  if (!tier) {
    return (
      <span className={styles.none}>
        <span aria-hidden="true">—</span>
        <span className="sr-only">No tier</span>
      </span>
    );
  }
  const { label, tone } = describeCode(TIERS, tier);
  return (
    <span className={styles.tier} data-tone={tone}>
      <span className="sr-only">Tier </span>
      {label}
    </span>
  );
}

const NEEDS_ICONS: Record<string, LucideIcon> = { laptop: Laptop, phone: Smartphone, anytime: Clock3 };

export function NeedsLabel({ needs }: { needs: Code }) {
  const Icon = (needs && NEEDS_ICONS[needs]) || Clock3;
  return (
    <span className={styles.label}>
      <Icon size={13} strokeWidth={1.7} aria-hidden="true" />
      {describeCode(NEEDS, needs).label}
    </span>
  );
}

const ACTION_ICONS: Record<string, LucideIcon> = {
  review: Eye,
  scam_suspected: ShieldAlert,
  captcha: Puzzle,
  question: CircleHelp,
  send_linkedin: MessageSquareText,
  profile_gap: UserRoundSearch,
  bot_detection: Bot,
  qa_fail: XCircle,
  salary: CircleDollarSign,
  send_email: Mail,
  laptop_required: Laptop,
  ghost_job: Ghost,
  other: MoreHorizontal,
};

export function ActionTypeLabel({ type }: { type: Code }) {
  const Icon = (type && ACTION_ICONS[type]) || MoreHorizontal;
  return (
    <span className={styles.label}>
      <Icon size={13} strokeWidth={1.7} aria-hidden="true" />
      {describeCode(ACTION_TYPES, type).label}
    </span>
  );
}
