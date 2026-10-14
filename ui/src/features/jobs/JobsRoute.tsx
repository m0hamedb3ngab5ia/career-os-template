import { useParams } from "react-router";
import { JobDetailPage } from "../job-detail/JobDetailPage";
import { JobsPage } from "./JobsPage";
import { useWide } from "./useWide";

/** /jobs/:jobId: the Jobs list with the job beside it when wide, else the job's own page. */
export function JobsRoute() {
  const { jobId } = useParams();
  return jobId && !useWide() ? <JobDetailPage /> : <JobsPage jobId={jobId} />;
}
