import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../../api/client";
import type { components } from "../../api/schema.gen";
import { Chip } from "../../kit/chips";
import { Card, Muted } from "./Card";
import styles from "./JobDetail.module.css";

type Matches = components["schemas"]["Matches"];

/** REQ-115: every résumé's match for this job (REQ-111), best first, best marked, threshold, missing skills. */
export function MatchesCard({ jobId }: { jobId: string }) {
  const q = useQuery({
    queryKey: ["job", jobId, "matches"],
    queryFn: () => apiFetch<Matches>(`/api/jobs/${encodeURIComponent(jobId)}/matches`),
  });
  const m = q.data;
  return (
    <Card title="Résumé match" aside={m?.scored ? <Muted>Threshold {m.threshold}</Muted> : null}>
      {!m ? (
        <Muted>{q.isError ? "Could not load résumé matches." : "Loading…"}</Muted>
      ) : !m.scored ? (
        <Muted>Not scored yet. {m.hint ?? ""}</Muted>
      ) : m.resumes.length === 0 ? (
        <Muted>No résumés yet. Add one on the Profile page.</Muted>
      ) : (
        <MatchesTable m={m} />
      )}
      {m?.scored && m.hint ? <Muted>{m.hint}</Muted> : null}
    </Card>
  );
}

/** The match table itself (also used by the Check a job dialog). */
export function MatchesTable({ m }: { m: Matches }) {
  return (
    <table className={styles.matches}>
      <thead>
        <tr>
          <th scope="col">Résumé</th>
          <th scope="col">Match</th>
          <th scope="col">Missing skills</th>
        </tr>
      </thead>
      <tbody>
        {m.resumes.map((r) => (
          <tr key={r.rid} data-best={r.rid === m.best || undefined}>
            <th scope="row">
              {r.name} {r.rid === m.best ? <Chip tone="green">Best</Chip> : null}
            </th>
            <td className="tabular">
              {r.score}
              {r.score < m.threshold ? <span className="sr-only"> (below threshold)</span> : null}
            </td>
            <td>{r.missing.length ? r.missing.join(", ") : "None"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
