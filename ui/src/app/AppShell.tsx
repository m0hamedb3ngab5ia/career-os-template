import type { LucideIcon } from "lucide-react";
import { ChevronRight, CircleHelp, Search, Settings, Sun, Table2, UserRound, Zap } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type RefObject } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { useLiveEvents, type Connection } from "../api/events";
import { useMeta } from "../api/meta";
import { useStatus } from "../api/queries";
import type { StatusSummary } from "../api/types";
import { formatCount, formatRelative } from "../lib/format";
import { useNow } from "../lib/useNow";
import { JobInspector } from "../features/inspector/JobInspector";
import styles from "./AppShell.module.css";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  count?: (s: StatusSummary) => number | undefined;
  end?: boolean;
}

const NAV_TOP: NavItem[] = [{ to: "/", label: "Today", icon: Sun, end: true, count: (s) => s.counts?.action_items_open }];

// Jobs tabs as sub-items (same ids as the Jobs page ?tab=). No tab in the URL means the page's first tab.
const JOB_TABS = [
  { tab: "recommended", label: "Recommended" },
  { tab: "inprogress", label: "In progress" },
  { tab: "applied", label: "Applied" },
  { tab: "saved", label: "Saved" },
  { tab: "notscored", label: "Not scored" },
];
const JOBS_OPEN_KEY = "careeros.sidebar.jobs";

function readOpen(): boolean {
  try {
    return localStorage.getItem(JOBS_OPEN_KEY) !== "closed";
  } catch {
    return true;
  }
}

function JobsGroup() {
  const { pathname, search } = useLocation();
  const [open, setOpen] = useState(readOpen);
  const onJobs = pathname === "/jobs";
  const tab = new URLSearchParams(search).get("tab") ?? "";
  const current = onJobs ? (JOB_TABS.some((t) => t.tab === tab) ? tab : "recommended") : null;
  function toggle() {
    const next = !open;
    setOpen(next);
    try {
      localStorage.setItem(JOBS_OPEN_KEY, next ? "open" : "closed");
    } catch {
      /* storage blocked: the group just opens again next visit */
    }
  }
  return (
    <li>
      <div className={styles.parent}>
        <Link to="/jobs" className={styles.item} aria-current={!current && pathname.startsWith("/jobs/") ? "page" : undefined}>
          <span className={styles.icon}>
            <Table2 size={16} strokeWidth={1.7} aria-hidden="true" />
          </span>
          <span className={styles.itemLabel}>Jobs</span>
        </Link>
        <button
          type="button"
          className={styles.chevron}
          aria-expanded={open}
          aria-controls="jobs-subnav"
          aria-label="Jobs sections"
          onClick={toggle}
        >
          <ChevronRight size={14} strokeWidth={2} aria-hidden="true" data-open={open} />
        </button>
      </div>
      {open ? (
        <ul id="jobs-subnav" className={styles.sub}>
          {JOB_TABS.map(({ tab, label }) => (
            <li key={tab}>
              <Link
                to={`/jobs?tab=${tab}`}
                className={styles.item}
                aria-current={current === tab ? "page" : undefined}
              >
                <span className={styles.itemLabel}>{label}</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

const LIVE_TEXT: Record<Connection, string> = {
  connecting: "Connecting…",
  open: "Live",
  reconnecting: "Reconnecting…",
};

function Freshness({ status, connection }: { status: StatusSummary | undefined; connection: Connection }) {
  const now = useNow();
  const synced = formatRelative(status?.index?.indexed_at, now);
  // Only the connection state is announced; the relative time ticks and would be noise in a live region.
  return (
    <div className={styles.footer}>
      <span className={styles.live}>
        <span className={styles.dot} data-state={connection} aria-hidden="true" />
        <span data-testid="connection" aria-live="polite">
          {LIVE_TEXT[connection]}
        </span>
      </span>
      {synced ? <span>Index synced {synced}</span> : null}
    </div>
  );
}

const isMac = () => /Mac|iPhone|iPad|iPod/.test(navigator.platform);

/**
 * Sidebar search: Enter opens Jobs filtered by the text (?q=). On the Jobs screen it shows the current q and keeps
 * the rest of the view (tab, sort, columns) and follows the page's own search box.
 */
function SidebarSearch() {
  const location = useLocation();
  const navigate = useNavigate();
  const onJobs = location.pathname === "/jobs";
  const q = onJobs ? (new URLSearchParams(location.search).get("q") ?? "") : "";
  const [text, setText] = useState(q);
  useEffect(() => setText(q), [q]);
  const input = useRef<HTMLInputElement>(null);

  // Cmd+K (Mac) / Ctrl+K (elsewhere) jumps to the search from anywhere but an open modal. Only one modifier per
  // platform: on a Mac Ctrl+K is the text fields' delete-to-end-of-line and must reach them.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.defaultPrevented || e.altKey || e.shiftKey || e.key.toLowerCase() !== "k") return;
      if (isMac() ? !e.metaKey || e.ctrlKey : !e.ctrlKey || e.metaKey) return;
      if (document.querySelector('[aria-modal="true"]')) return;
      e.preventDefault();
      input.current?.focus();
      input.current?.select();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const value = text.trim();
    const params = new URLSearchParams(onJobs ? location.search : "");
    if (value) params.set("q", value);
    else params.delete("q");
    params.delete("sel");
    const search = params.toString();
    navigate({ pathname: "/jobs", search: search ? `?${search}` : "" });
  }

  return (
    <form role="search" className={styles.search} onSubmit={onSubmit}>
      <Search size={14} strokeWidth={1.7} aria-hidden="true" />
      <input
        ref={input}
        type="search"
        aria-keyshortcuts={isMac() ? "Meta+K" : "Control+K"}
        name="q"
        autoComplete="off"
        spellCheck={false}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Search jobs and companies…"
        aria-label="Search jobs and companies"
      />
    </form>
  );
}

/** Cmd+, (Mac) / Ctrl+, opens Settings from anywhere but an open modal. */
function useSettingsShortcut() {
  const navigate = useNavigate();
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.defaultPrevented || e.altKey || e.shiftKey || e.key !== ",") return;
      if (isMac() ? !e.metaKey || e.ctrlKey : !e.ctrlKey || e.metaKey) return;
      if (document.querySelector('[aria-modal="true"]')) return;
      e.preventDefault();
      navigate("/settings");
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [navigate]);
}

/**
 * On a route change (a new path, not just a new query string such as ?sel=, so a sheet's focus return is left
 * alone) move focus to the main region and announce the new page's title. Skipped on the first load. Focus that
 * the new page already put inside main (or kept there, e.g. a section tab) stays where it is.
 */
function useRouteFocus(main: RefObject<HTMLElement | null>): string {
  const { pathname } = useLocation();
  const [message, setMessage] = useState("");
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    const el = main.current;
    if (!el) return;
    const active = document.activeElement;
    if (!active || active === document.body || !el.contains(active)) el.focus({ preventScroll: true });
    // A page still loading shows a placeholder title (aria-busy); announce the real one once it arrives.
    const announce = () => {
      const h1 = el.querySelector("h1");
      const title = h1?.textContent?.trim();
      if (!h1 || h1.getAttribute("aria-busy") === "true" || !title) return false;
      // A zero-width toggle makes an identical title (same h1 on two routes) still count as a change and be re-read.
      setMessage((prev) => (prev === title ? `${title}\u200B` : title));
      return true;
    };
    if (announce()) return;
    const watch = new MutationObserver(() => announce() && watch.disconnect());
    watch.observe(el, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["aria-busy"] });
    return () => watch.disconnect();
  }, [pathname, main]);
  return message;
}

export function AppShell() {
  const connection = useLiveEvents();
  const { data: status } = useStatus();
  const main = useRef<HTMLElement>(null);
  const routeMessage = useRouteFocus(main);
  useSettingsShortcut();
  // Settings > ui.theme: light/dark force a palette on <html>; system (or unknown) drops it so tokens.css follows the OS.
  const theme = useMeta().data?.ui.theme;
  useEffect(() => {
    if (!theme) return; // meta not loaded yet: keep what index.html applied before first paint
    if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
    try { localStorage.setItem("careeros.theme", theme); } catch { /* storage blocked: only the early paint is lost */ }
  }, [theme]);

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
        <SidebarSearch />
        <ul className={styles.list}>
          {NAV_TOP.map(({ to, label, icon: Icon, count, end }) => {
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
          <JobsGroup />
          <li>
            <NavLink to="/profile" className={styles.item}>
              <span className={styles.icon}>
                <UserRound size={16} strokeWidth={1.7} aria-hidden="true" />
              </span>
              <span className={styles.itemLabel}>Profile</span>
            </NavLink>
          </li>
        </ul>
        <div className={styles.bottom}>
          <NavLink to="/catalogue" className={styles.item}>
            <span className={styles.icon}>
              <CircleHelp size={16} strokeWidth={1.7} aria-hidden="true" />
            </span>
            <span className={styles.itemLabel}>What can I do?</span>
          </NavLink>
          <NavLink to="/settings" className={styles.item} aria-keyshortcuts={isMac() ? "Meta+," : "Control+,"}>
            <span className={styles.icon}>
              <Settings size={16} strokeWidth={1.7} aria-hidden="true" />
            </span>
            <span className={styles.itemLabel}>Settings</span>
          </NavLink>
        </div>
        <Freshness status={status} connection={connection} />
      </nav>
      <div role="status" aria-live="polite" className="sr-only" data-testid="route-announcer">
        {routeMessage}
      </div>
      <main ref={main} id="main" tabIndex={-1} className={styles.main}>
        <Outlet />
      </main>
      <JobInspector />
    </div>
  );
}
