import { ChevronDown, X } from "lucide-react";
import { useId, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { describeCode, PRIORITIES, STATUSES } from "../../kit/labels";
import { Popover } from "../../kit/Popover";
import { formatDay, formatPercent } from "../../lib/dates";
import { formatCount } from "../../lib/format";
import type { Tiles } from "./types";
import styles from "./Today.module.css";

type TileKey = "applied" | "needs" | "interviews" | "response";

interface PopRow {
  key: string;
  company: string;
  role?: string;
  detail?: string;
  when?: string | null;
}

interface TileSpec {
  key: TileKey;
  label: string;
  value: string;
  tone?: "orange" | "purple";
  sub: string;
  pop: { sub: string; rows: PopRow[]; more: number; foot?: string; href: string; linkText: string };
}

const plural = (n: number, one: string, many: string) => `${formatCount(n)} ${n === 1 ? one : many}`;

function uniq(xs: string[]): string[] {
  return [...new Set(xs.filter(Boolean))];
}

function capitalize(s: string): string {
  return s ? s[0]!.toUpperCase() + s.slice(1) : s;
}

function specs(t: Partial<Tiles>, now: Date): TileSpec[] {
  const applied = t.applied_week ?? { value: 0, since: "", daily_cap: null, rows: [] };
  const needs = t.needs_you ?? { value: 0, high: 0, rows: [] };
  const interviews = t.interviews ?? { value: 0, rows: [] };
  const rr = t.response_rate ?? { rate: null, responded: 0, applied: 0, days: 30, definition: "", breakdown: [], rows: [] };
  const aRows = applied.rows ?? [];
  const nRows = needs.rows ?? [];
  const iRows = interviews.rows ?? [];
  const since = formatDay(applied.since, now);
  const names = uniq(iRows.flatMap((r) => (r.company ? [r.company] : [])));
  const cap = applied.daily_cap;
  return [
    {
      key: "applied",
      label: "Applied this week",
      value: formatCount(applied.value),
      sub: typeof cap === "number" ? `Limit: ${formatCount(cap)} a day` : "",
      pop: {
        sub: `${plural(applied.value, "application", "applications")}${since ? ` since ${since}` : " this week"}`,
        rows: aRows.map((r) => ({
          key: r.job_id,
          company: r.company ?? "",
          role: r.role ?? undefined,
          detail: describeCode(STATUSES, r.detail).label,
          when: formatDay(r.when, now),
        })),
        more: Math.max(0, applied.value - aRows.length),
        foot: typeof cap === "number" ? `Limit: ${formatCount(cap)} a day` : undefined,
        href: "/jobs",
        linkText: "All jobs",
      },
    },
    {
      key: "needs",
      label: "Needs you",
      value: formatCount(needs.value),
      tone: "orange",
      sub: `${formatCount(needs.high ?? 0)} high priority`,
      pop: {
        sub: `${plural(needs.value, "item", "items")} · ${formatCount(needs.high ?? 0)} high priority`,
        rows: nRows.map((r) => ({
          key: String(r.id),
          company: r.company ?? "",
          role: r.role ?? undefined,
          detail: r.what ?? undefined,
          when: r.priority ? describeCode(PRIORITIES, r.priority).label : null,
        })),
        more: Math.max(0, needs.value - nRows.length),
        foot: "Sorted by priority",
        href: "/actions",
        linkText: "Action Items",
      },
    },
    {
      key: "interviews",
      label: "Interviews",
      value: formatCount(interviews.value),
      tone: "purple",
      sub: names.length ? names.slice(0, 3).join(", ") + (names.length > 3 ? ` +${names.length - 3}` : "") : "None yet",
      pop: {
        sub: `${formatCount(interviews.value)} active`,
        rows: iRows.map((r) => ({
          key: r.job_id,
          company: r.company ?? "",
          role: r.role ?? undefined,
          detail: describeCode(STATUSES, r.detail).label,
          when: formatDay(r.when, now),
        })),
        more: Math.max(0, interviews.value - iRows.length),
        href: "/inbox",
        linkText: "Inbox",
      },
    },
    {
      key: "response",
      label: "Response rate",
      value: rr.rate === null || rr.rate === undefined ? "—" : formatPercent(rr.rate),
      sub: `${plural(rr.responded, "reply", "replies")} from ${formatCount(rr.applied)} · ${formatCount(rr.days)} days`,
      pop: {
        sub: `${plural(rr.responded, "reply", "replies")} from ${plural(rr.applied, "application", "applications")} in the last ${formatCount(rr.days)} days`,
        rows: (rr.breakdown ?? []).map((b) => ({
          key: b.status,
          company: b.status === "no_reply" ? "No reply yet" : describeCode(STATUSES, b.status).label,
          detail: (b.companies ?? []).join(", ") || undefined,
          when: formatCount(b.count),
        })),
        more: 0,
        foot: rr.definition ? capitalize(rr.definition) : undefined,
        href: "/pipeline",
        linkText: "Pipeline",
      },
    },
  ];
}

/** `tiles` is missing only while /api/status has not answered with a full reply (then every tile reads zero). */
export function StatTiles({ tiles, now }: { tiles: Tiles | undefined; now: Date }) {
  const [open, setOpen] = useState<TileKey | null>(null);
  const anchor = useRef<HTMLElement | null>(null);
  const popId = useId();
  const list = specs(tiles ?? {}, now);
  const current = list.find((s) => s.key === open);

  function close() {
    setOpen(null);
  }

  return (
    <div className={styles.tilesWrap}>
      <div className={styles.tiles}>
        {list.map((s) => {
          const on = open === s.key;
          return (
            <button
              key={s.key}
              type="button"
              className={styles.tile}
              aria-expanded={on}
              aria-controls={on ? popId : undefined}
              onClick={(e) => {
                anchor.current = e.currentTarget;
                setOpen((o) => (o === s.key ? null : s.key));
              }}
            >
              <span className={styles.tileLabel}>
                {s.label}
                <ChevronDown size={14} strokeWidth={1.7} aria-hidden="true" className={styles.tileChevron} />
              </span>
              <span className={`${styles.tileValue} tabular`} data-tone={s.tone}>
                {s.value}
              </span>
              {s.sub ? <span className={styles.tileSub}>{s.sub}</span> : null}
            </button>
          );
        })}
      </div>
      <Popover
        id={popId}
        open={current !== undefined}
        onClose={close}
        anchorRef={anchor}
        label={current?.label ?? ""}
        className={`${styles.pop} ${styles[`pop_${current?.key ?? "applied"}`] ?? ""}`}
      >
        {current ? (
          <TilePopover
            title={current.label}
            {...current.pop}
            onClose={() => {
              close();
              anchor.current?.focus();
            }}
          />
        ) : null}
      </Popover>
    </div>
  );
}

function TilePopover({
  title,
  sub,
  rows,
  more,
  foot,
  href,
  linkText,
  onClose,
}: TileSpec["pop"] & { title: string; onClose: () => void }) {
  return (
    <>
      <div className={styles.popHead}>
        <h2 className={styles.popTitle}>{title}</h2>
        <button type="button" className={styles.iconButton} aria-label="Close" onClick={onClose}>
          <X size={14} strokeWidth={1.8} aria-hidden="true" />
        </button>
      </div>
      <p className={styles.popSub}>{sub}</p>
      {rows.length ? (
        <ul className={styles.popRows}>
          {rows.map((r) => (
            <PopRowItem key={r.key} company={r.company} role={r.role} detail={r.detail} when={r.when} />
          ))}
          {more > 0 ? (
            <li className={styles.popRow}>
              <span className={styles.popMore}>+{formatCount(more)} more</span>
            </li>
          ) : null}
        </ul>
      ) : (
        <p className={styles.popEmpty}>Nothing here yet.</p>
      )}
      <div className={styles.popFoot}>
        <span>{foot}</span>
        <Link to={href} className={styles.popLink}>
          {linkText}
        </Link>
      </div>
    </>
  );
}

function PopRowItem({ company, role, detail, when }: Omit<PopRow, "key">): ReactNode {
  return (
    <li className={styles.popRow}>
      <div className={styles.popRowMain}>
        <div>
          <span className={styles.strong}>{company}</span>
          {role ? <span className={styles.sec}> {role}</span> : null}
        </div>
        {detail ? <div className={styles.caption}>{detail}</div> : null}
      </div>
      {when ? <span className={`${styles.popWhen} tabular`}>{when}</span> : null}
    </li>
  );
}
