import type { LucideIcon } from "lucide-react";
import {
  Bell,
  CircleCheckBig,
  Clock3,
  Database,
  Filter,
  Folder,
  Search,
  Settings,
  Shield,
  SlidersHorizontal,
  Users,
  Zap,
} from "lucide-react";
import { Link, Navigate, useParams } from "react-router";
import { Page } from "../../app/PageHeader";
import { EmptyState } from "../../kit/EmptyState";
import { useSection, useSectionList } from "./api";
import { BudgetGroup } from "./custom/BudgetGroup";
import { RankingGroup } from "./custom/RankingGroup";
import { TierCards } from "./custom/TierCards";
import { SettingsFormProvider } from "./form";
import { GroupCard } from "./GroupCard";
import { SaveBar } from "./SaveBar";
import styles from "./settings.module.css";
import { StorageOverview } from "./storage/StorageOverview";
import type { GroupSchema, SectionData } from "./types";

export const DEFAULT_SECTION = "general";

const ICONS: Record<string, LucideIcon> = {
  general: Settings,
  targets: Filter,
  autonomy: Zap,
  safety: Shield,
  scout: Search,
  companies: Folder,
  outreach: Users,
  notifications: Bell,
  runs: Clock3,
  storage: Database,
  qa: CircleCheckBig,
};

// Page subtitles from the mockup; sections without an artboard say what they hold.
const SUBTITLES: Record<string, string> = {
  general: "General · files, the app, Claude and résumé builds",
  targets: "Targets · who you are and which roles to look for",
  autonomy: "Autonomy and outreach · how much career-os does without asking",
  safety: "Safety · what stops an auto-submit",
  scout: "Scout · where new postings come from and what gets filtered out",
  companies: "Companies · dream list, never-apply list, domains and job boards",
  outreach: "Outreach · who gets a message and who you contact yourself",
  notifications: "Notifications · what reaches you and how",
  runs: "Runs & schedule · when career-os works on its own, and how much",
  storage: "Storage & efficiency · is retention too tight or too loose, and are runs using Claude well",
  qa: "Quality checks · what a résumé and cover letter must pass",
};

function SectionNav({ current }: { current: string }) {
  const list = useSectionList();
  const sections = list.data?.sections ?? [];
  return (
    <nav aria-label="Settings sections" className={styles.nav}>
      <ul className={styles.navList}>
        {sections.map((s) => {
          const Icon = ICONS[s.id] ?? SlidersHorizontal;
          return (
            <li key={s.id}>
              <Link
                to={`/settings/${s.id}`}
                className={styles.navItem}
                aria-current={s.id === current ? "page" : undefined}
              >
                <span className={styles.navIcon}>
                  <Icon size={15} strokeWidth={1.7} aria-hidden="true" />
                </span>
                {s.title}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function Groups({ data }: { data: SectionData }) {
  const id = data.section.id;
  const groups = data.section.groups;
  const tiers = id === "autonomy" ? groups.filter((g) => /^tier_[a-z]$/.test(g.id)) : [];
  const render = (g: GroupSchema) => {
    if (id === "runs" && g.id === "budget") return <BudgetGroup key={g.id} group={g} />;
    if (id === "runs" && g.id === "ranking") return <RankingGroup key={g.id} group={g} />;
    return <GroupCard key={g.id} group={g} />;
  };
  return (
    <>
      {tiers.length ? <TierCards groups={tiers} /> : null}
      {groups.filter((g) => !tiers.includes(g)).map(render)}
    </>
  );
}

function SectionBody({ id }: { id: string }) {
  const q = useSection(id);
  if (q.isPending) return <p className={styles.hint}>Loading settings…</p>;
  if (q.isError) {
    const status = (q.error as { status?: number }).status;
    return status === 404 ? (
      <EmptyState title="No settings page here" action={<Link to={`/settings/${DEFAULT_SECTION}`}>Open General</Link>}>
        Pick a section from the list.
      </EmptyState>
    ) : (
      <EmptyState title="Couldn't load these settings">
        {q.error instanceof Error ? q.error.message : "Check that careeros ui is running."}
      </EmptyState>
    );
  }
  return (
    <SettingsFormProvider key={id} data={q.data}>
      {id === "storage" ? <StorageOverview /> : null}
      <Groups data={q.data} />
      <SaveBar />
    </SettingsFormProvider>
  );
}

export function SettingsPage() {
  const { section } = useParams();
  if (!section) return <Navigate to={`/settings/${DEFAULT_SECTION}`} replace />;
  return (
    <Page title="Settings" subtitle={SUBTITLES[section] ?? "Settings"}>
      <div className={styles.layout}>
        <SectionNav current={section} />
        <div className={styles.content}>
          <SectionBody id={section} />
        </div>
      </div>
    </Page>
  );
}
