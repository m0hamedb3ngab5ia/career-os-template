import type { LucideIcon } from "lucide-react";
import { Activity, Inbox, KanbanSquare, ListChecks, Search, Settings, Sun, Table2, Users, Zap } from "lucide-react";
import { NavLink, Outlet } from "react-router";
import { useLiveEvents, type Connection } from "../api/events";
import { useStatus } from "../api/queries";
import type { StatusSummary } from "../api/types";
import { formatCount, formatRelative } from "../lib/format";
import { useNow } from "../lib/useNow";
import styles from "./AppShell.module.css";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  count?: (s: StatusSummary) => number | undefined;
  end?: boolean;
}

// Sidebar order and groups from the mockup (Today artboard).
const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "Overview",
    items: [
      { to: "/", label: "Today", icon: Sun, end: true },
      { to: "/pipeline", label: "Pipeline", icon: KanbanSquare },
      { to: "/jobs", label: "Jobs", icon: Table2, count: (s) => s.counts?.jobs },
    ],
  },
  {
    group: "Work",
    items: [
      { to: "/actions", label: "Action Items", icon: ListChecks, count: (s) => s.counts?.action_items_open },
      { to: "/inbox", label: "Inbox & Follow-ups", icon: Inbox, count: (s) => s.counts?.inbox },
      { to: "/contacts", label: "Contacts", icon: Users },
    ],
  },
  {
    group: "System",
    items: [
      { to: "/runs", label: "Runs", icon: Activity },
      { to: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

const LIVE_TEXT: Record<Connection, string> = {
  connecting: "Connecting…",
  open: "Live",
  reconnecting: "Reconnecting…",
};

function Freshness({ status, connection }: { status: StatusSummary | undefined; connection: Connection }) {
  const now = useNow();
  const synced = formatRelative(status?.index?.synced_at, now);
  const exported = formatRelative(status?.tracker?.exported_at, now);
  return (
    <div className={styles.footer} aria-live="polite">
      <span className={styles.live}>
        <span className={styles.dot} data-state={connection} aria-hidden="true" />
        {LIVE_TEXT[connection]}
        {synced ? ` · index synced ${synced}` : null}
      </span>
      {exported ? <span>JobTracker.xlsx exported {exported}</span> : null}
    </div>
  );
}

export function AppShell() {
  const connection = useLiveEvents();
  const { data: status } = useStatus();

  return (
    <div className={styles.shell}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <nav aria-label="Sections" className={styles.sidebar}>
        <div className={styles.brand}>
          <span className={styles.brandMark} aria-hidden="true">
            <Zap size={15} strokeWidth={2} />
          </span>
          <span translate="no">career-os</span>
        </div>
        <label className={styles.search}>
          <Search size={14} strokeWidth={1.7} aria-hidden="true" />
          <span className="sr-only">Search jobs and companies (coming soon)</span>
          <input
            type="search"
            name="q"
            autoComplete="off"
            placeholder="Search jobs and companies…"
            disabled
            title="Search arrives with the Jobs screen"
          />
        </label>
        {NAV.map(({ group, items }) => (
          <div key={group}>
            <h2 className={styles.group}>{group}</h2>
            <ul className={styles.list}>
              {items.map(({ to, label, icon: Icon, count, end }) => {
                const n = status && count ? (count(status) ?? 0) : undefined;
                return (
                  <li key={to}>
                    <NavLink to={to} end={end} className={styles.item}>
                      <span className={styles.icon}>
                        <Icon size={16} strokeWidth={1.7} aria-hidden="true" />
                      </span>
                      <span className={styles.itemLabel}>{label}</span>
                      {n !== undefined ? <span className={styles.count}>{formatCount(n)}</span> : null}
                    </NavLink>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
        <Freshness status={status} connection={connection} />
      </nav>
      <main id="main" tabIndex={-1} className={styles.main}>
        <Outlet />
      </main>
    </div>
  );
}
