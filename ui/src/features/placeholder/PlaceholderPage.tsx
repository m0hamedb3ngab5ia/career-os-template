import { Page } from "../../app/PageHeader";
import { EmptyState } from "../../kit/EmptyState";

export function NotFoundPage() {
  return (
    <Page title="Page not found">
      <EmptyState title="Nothing lives at this address">Pick a section from the sidebar.</EmptyState>
    </Page>
  );
}
