import { Page } from "../../app/PageHeader";
import { EmptyState } from "../../kit/EmptyState";
import { useSettings } from "./api";
import { Group } from "./Section";
import styles from "./Lists.module.css";

/** Route `/settings`: the config in plain words, grouped as the files are. Read only; ask in chat to change a value. */
export function SettingsPage() {
  const { data, isError, error, isPending } = useSettings();
  const subtitle = "How the search and applier are set up. To change a value, ask in chat.";
  if (isPending) return <Page title="Settings" subtitle={subtitle} busy />;
  if (isError || !data) {
    return (
      <Page title="Settings" subtitle={subtitle}>
        <EmptyState title="Couldn’t load settings">{error instanceof Error ? error.message : "Try again in a moment."}</EmptyState>
      </Page>
    );
  }
  return (
    <Page title="Settings" subtitle={subtitle}>
      <div className={styles.stack}>
        {data.sections.map((sec) => (
          <div key={sec.id} className={styles.stack} style={{ padding: 0 }}>
            <h2 className={styles.heading} style={{ fontSize: "var(--fs-body)", color: "var(--label)" }}>
              {sec.title}
            </h2>
            {sec.groups.map((g) => (
              <Group key={g.title} title={g.title} empty="" rows={g.rows.map((r) => ({ key: r.label, label: r.label, value: r.value }))} />
            ))}
          </div>
        ))}
      </div>
    </Page>
  );
}
