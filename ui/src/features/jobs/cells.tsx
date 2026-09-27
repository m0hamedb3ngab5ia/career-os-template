import type { ReactNode } from "react";
import { Link } from "react-router";
import { SafetyChip, StatusChip, TierBadge } from "../../kit/chips";
import { humanize } from "../../kit/labels";
import { formatDate, formatDecimal } from "../../lib/format";
import styles from "./JobsPage.module.css";
import type { JobListItem } from "./types";
import type { SortKey } from "./urlState";

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
    exportField: "company",
    title: (j) => j.company ?? undefined,
    cell: (j) => (
      <Link to={`/jobs/${encodeURIComponent(j.job_id)}`} className={styles.company} translate="no">
        {j.company || j.job_id}
      </Link>
    ),
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
    exportField: "location",
    className: styles.sec,
    title: (j) => j.location ?? undefined,
    cell: (j) => j.location || <Empty sr="No location" />,
  },
  { key: "tier", label: "Tier", width: 48, sort: "tier", exportField: "tier", cell: (j) => <TierBadge tier={j.tier} /> },
  {
    key: "fit",
    label: "Fit",
    width: 56,
    sort: "fit",
    exportField: "fit",
    className: styles.fit,
    cell: (j) => (j.fit === null || j.fit === undefined ? <Empty sr="No fit score" /> : j.fit),
  },
  {
    key: "status",
    label: "Status",
    width: 118,
    sort: "status",
    exportField: "status",
    cell: (j) => (j.status ? <StatusChip status={j.status} /> : <Empty sr="No status" />),
  },
  {
    key: "safety",
    label: "Safety",
    width: 84,
    exportField: "safety",
    cell: (j) => (j.safety ? <SafetyChip verdict={j.safety} /> : <Empty sr="Not checked" />),
  },
  {
    key: "qa",
    label: "QA",
    width: 44,
    exportField: "qa_score",
    className: styles.num,
    cell: (j) => (typeof j.qa_score === "number" ? formatDecimal(j.qa_score) : <Empty sr="No QA score" />),
  },
  {
    key: "ats",
    label: "ATS",
    width: 92,
    exportField: "ats",
    className: styles.sec,
    cell: (j) => (j.ats ? humanize(j.ats) : <Empty sr="Unknown ATS" />),
  },
  {
    key: "found",
    label: "Found",
    width: 72,
    sort: "found_at",
    exportField: "found_at",
    className: styles.num,
    cell: (j) => formatDate(j.found_at) ?? <Empty sr="Unknown" />,
  },
  {
    key: "applied",
    label: "Applied",
    width: 76,
    sort: "applied_at",
    exportField: "applied_at",
    className: styles.num,
    cell: (j) => formatDate(j.applied_at) ?? <Empty sr="Not applied" />,
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
