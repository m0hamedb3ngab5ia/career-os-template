import { Page } from "../../app/PageHeader";
import { EmptyState } from "../../kit/EmptyState";
import { formatRelative } from "../../lib/format";
import { useProfile } from "./api";
import { Group } from "./Section";
import { MasterPreview } from "./MasterPreview";
import styles from "./Lists.module.css";

const kb = (n: number) => (n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${Math.round(n / 1024)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`);
const TYPE = (t: string) => (t === "master" ? "Master" : "Variant");

/** Route `/profile`: what the applier knows about you. Read only; ask in chat to change anything. */
export function ProfilePage() {
  const { data, isError, error, isPending } = useProfile();
  const subtitle = "What the applier uses to fill forms. To change anything, ask in chat.";
  if (isPending) return <Page title="Profile" subtitle={subtitle} busy />;
  if (isError || !data) {
    return (
      <Page title="Profile" subtitle={subtitle}>
        <EmptyState title="Couldn’t load your profile">{error instanceof Error ? error.message : "Try again in a moment."}</EmptyState>
      </Page>
    );
  }
  const master = data.resumes.find((r) => r.type === "master");
  return (
    <Page title="Profile" subtitle={subtitle}>
      <div className={styles.stack}>
        {master && <MasterPreview rid={master.rid} version={master.version} />}
        <Group
          title="Résumés"
          empty="No résumés yet. Ask in chat to add one."
          note="The master résumé is the source for tailored versions."
          rows={data.resumes.map((r) => ({ key: r.rid, label: r.name, value: `${TYPE(r.type)} · v${r.version} · ${formatRelative(r.at, new Date()) ?? ""}` }))}
        />
        <Group
          title="Documents"
          empty="No documents. Put files such as a transcript in profile/documents."
          rows={data.documents.map((d) => ({ key: d.name, label: d.name, value: kb(d.size) }))}
        />
        <Group
          title="Standard answers"
          empty="No standard answers yet."
          note="Typed into forms as written. A question with no match becomes an Action Item."
          rows={data.answers.map((a) => ({ key: a.key, label: a.key.replace(/_/g, " "), value: a.answer }))}
        />
      </div>
    </Page>
  );
}
