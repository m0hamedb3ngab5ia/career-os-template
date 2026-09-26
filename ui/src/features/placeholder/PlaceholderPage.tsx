import { Page } from "../../app/PageHeader";
import { EmptyState } from "../../kit/EmptyState";

export function PlaceholderPage({ title }: { title: string }) {
  return (
    <Page title={title}>
      <EmptyState title="Coming in a later slice">This screen is part of the UI build plan in docs/UI.md.</EmptyState>
    </Page>
  );
}

export function NotFoundPage() {
  return (
    <Page title="Page not found">
      <EmptyState title="Nothing lives at this address">Pick a section from the sidebar.</EmptyState>
    </Page>
  );
}
