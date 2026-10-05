import { TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { SafetyChip, StatusChip, TierBadge } from "../../kit/chips";
import { humanize } from "../../kit/labels";
import { useToast } from "../../kit/Toast";
import { formatDate, formatDecimal } from "../../lib/format";
import { useSelectJobs } from "./api";
import styles from "./JobsPage.module.css";
import type { JobListItem } from "./types";
import type { FilterField, SortKey } from "./urlState";

/** An empty cell: a dash for the eye, words for screen readers. */
export function Empty({ sr }: { sr: string }) {
  return (
    <>
      <span aria-hidden="true" className={styles.dash}>
        —
      </span>
      <span className="sr-only">{sr}</span>
    </>
  );
}

export interface Column {
  key: string;
  label: string;
  width?: number;
  sort?: SortKey;
  /** Column filter (header menu); the field names the URL `f.<field>` key and the facet. */
  filter?: FilterField;
  /** Field name sent to POST /api/jobs/export. */
  exportField: string;
  className?: string;
  title?: (j: JobListItem) => string | undefined;
  cell: (j: JobListItem) => ReactNode;
}

// Mockup order and widths (Jobs artboard). The first data column (Company) is the row header.
export const COLUMNS: Column[] = [
  {
    key: "company",
    label: "Company",
    width: 170,
    sort: "company",
    filter: "company",
    exportField: "company",
    title: (j) => j.company ?? undefined,
    cell: (j) => (
      <>
        <Link to={`/jobs/${encodeURIComponent(j.job_id)}`} className={styles.company} translate="no">
          {j.company || j.job_id}
        </Link>
        {j.injection ? <InjectionBadge reasons={j.injection} /> : null}
      </>
    ),
  },
  {
    key: "pick",
    label: "Pipeline",
    width: 80,
    exportField: "selected",
    title: () => "Ticked jobs are the only ones prepared or applied",
    cell: (j) => <PickCell job={j} />,
  },
  {
    key: "role",
    label: "Role",
    exportField: "title",
    title: (j) => j.title ?? undefined,
    cell: (j) => j.title || <Empty sr="No role" />,
  },
  {
    key: "location",
    label: "Location",
    width: 130,
    sort: "location",
    filter: "location",
    exportField: "location",
    className: styles.sec,
    title: (j) => j.location ?? undefined,
    cell: (j) => j.location || <Empty sr="No location" />,
  },
  { key: "tier", label: "Tier", width: 48, sort: "tier", filter: "tier", exportField: "tier", cell: (j) => <TierBadge tier={j.tier} /> },
  {
    key: "fit",
    label: "Fit",
    width: 56,
    sort: "fit",
    filter: "fit",
    exportField: "fit",
    className: styles.fit,
    cell: (j) => (j.fit === null || j.fit === undefined ? <Empty sr="No fit score" /> : j.fit),
  },
  {
    key: "status",
    label: "Status",
    width: 118,
    sort: "status",
    filter: "status",
    exportField: "status",
    cell: (j) => (j.status ? <StatusChip status={j.status} /> : <Empty sr="No status" />),
  },
  {
    key: "category",
    label: "Category",
    width: 92,
    filter: "category",
    exportField: "category",
    className: styles.sec,
    cell: (j) => (j.category ? humanize(j.category) : <Empty sr="No category" />),
  },
  {
    key: "safety",
    label: "Safety",
    width: 84,
    filter: "safety",
    exportField: "safety",
    cell: (j) => (j.safety ? <SafetyChip verdict={j.safety} /> : <Empty sr="Not checked" />),
  },
  {
    key: "qa",
    label: "QA",
    width: 44,
    filter: "qa_score",
    exportField: "qa_score",
    className: styles.num,
    cell: (j) => (typeof j.qa_score === "number" ? formatDecimal(j.qa_score) : <Empty sr="No QA score" />),
  },
  {
    key: "qa_passed",
    label: "QA passed",
    width: 84,
    filter: "qa_passed",
    exportField: "qa_passed",
    cell: (j) => (j.qa_passed === null || j.qa_passed === undefined ? <Empty sr="No QA verdict" /> : j.qa_passed ? "Passed" : "Failed"),
  },
  {
    key: "ats",
    label: "ATS",
    width: 92,
    filter: "ats",
    exportField: "ats",
    className: styles.sec,
    cell: (j) => (j.ats ? humanize(j.ats) : <Empty sr="Unknown ATS" />),
  },
  {
    key: "found",
    label: "Found",
    width: 72,
    sort: "found_at",
    filter: "found_at",
    exportField: "found_at",
    className: styles.num,
    cell: (j) => formatDate(j.found_at) ?? <Empty sr="Unknown" />,
  },
  {
    key: "applied",
    label: "Applied",
    width: 76,
    sort: "applied_at",
    filter: "applied_at",
    exportField: "applied_at",
    className: styles.num,
    cell: (j) => formatDate(j.applied_at) ?? <Empty sr="Not applied" />,
  },
  {
    key: "closes_at",
    label: "Closes",
    width: 72,
    filter: "closes_at",
    exportField: "closes_at",
    className: styles.num,
    cell: (j) => formatDate(j.closes_at) ?? <Empty sr="No closing date" />,
  },
  {
    key: "next",
    label: "Next action",
    width: 150,
    exportField: "next_action",
    title: (j) => j.next_action ?? undefined,
    cell: (j) => j.next_action || <Empty sr="None" />,
  },
];

/** REQ-104: tick/untick one job for prepare/apply. A missing flag (old job) counts as ticked. */
function PickCell({ job }: { job: JobListItem }) {
  const pick = useSelectJobs();
  const toast = useToast();
  // Optimistic while the POST and the list refetch run (useSelectJobs waits for it); then server state wins.
  const checked = pick.isPending ? pick.variables.selected : job.selected !== 0;
  const toggle = () =>
    pick.mutate(
      { ids: [job.job_id], selected: !checked },
      { onError: (e) => toast.show({ message: e instanceof Error ? e.message : "Could not save the tick" }) },
    );
  return (
    <label className={styles.check}>
      <input type="checkbox" checked={checked} onChange={toggle} />
      <span className="sr-only">Tick {job.company || job.job_id} for pipeline</span>
    </label>
  );
}

/** REQ-109: flagged posting; the reasons show on hover and to screen readers. */
function InjectionBadge({ reasons }: { reasons: string }) {
  return (
    <span className={styles.flag} title={`Possible prompt injection: ${reasons}`}>
      <TriangleAlert size={14} strokeWidth={1.7} aria-hidden="true" />
      <span className="sr-only">Possible prompt injection: {reasons}</span>
    </span>
  );
}
