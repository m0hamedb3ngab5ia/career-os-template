import { Page } from "../../app/PageHeader";
import { EmptyState } from "../../kit/EmptyState";
import { ButtonLink } from "../../kit/Button";

export function NotFoundPage() {
  return (
    <Page title="Page not found" subtitle="This address has no page · pick a section from the sidebar">
      <EmptyState title="Nothing lives at this address" action={<ButtonLink to="/">Go to Today</ButtonLink>}>
        The link may be old or mistyped.
      </EmptyState>
    </Page>
  );
}
