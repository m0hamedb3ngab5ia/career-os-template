import { useParams } from "react-router";
import { useSyncExternalStore } from "react";
import { JobDetailPage } from "../job-detail/JobDetailPage";
import { JobsPage } from "./JobsPage";

const WIDE = "(min-width: 900px)";
const mq = () => (typeof window.matchMedia === "function" ? window.matchMedia(WIDE) : null);
/** Master-detail needs room (REQ-129): under 900px a job opens as a full page. */
function useWide(): boolean {
  return useSyncExternalStore(
    (cb) => (mq()?.addEventListener("change", cb), () => mq()?.removeEventListener("change", cb)),
    () => mq()?.matches ?? false,
  );
}

/** /jobs/:jobId: the Jobs list with the job beside it when wide, else the job's own page. */
export function JobsRoute() {
  const { jobId } = useParams();
  return jobId && !useWide() ? <JobDetailPage /> : <JobsPage jobId={jobId} />;
}
