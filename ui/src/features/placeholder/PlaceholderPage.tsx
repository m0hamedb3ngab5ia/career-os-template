import { Link } from "react-router";
import { Page } from "../../app/PageHeader";
import { EmptyState } from "../../kit/EmptyState";

export function NotFoundPage() {
  return (
    <Page title="Page not found" subtitle="This address has no page · pick a section from the sidebar">
      <EmptyState title="Nothing lives at this address" action={<Link to="/">Go to Today</Link>}>
        The link may be old or mistyped.
      </EmptyState>
    </Page>
  );
}
