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
              <Why groups={r.groups} />
            </td>
            <td>{r.missing.length ? r.missing.join(", ") : "None"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const GROUPS = [["required", "Required"], ["preferred", "Preferred"], ["title", "Title"]] as const;

/** REQ-114 "Why this score": matched (✓) and missing keywords per group, from match.py `groups`. */
function Why({ groups }: { groups: Matches["resumes"][number]["groups"] }) {
  const lines = GROUPS.flatMap(([k, label]) => {
    const g = groups[k];
    const hit = g?.hit ?? [];
    const miss = g?.missing ?? [];
    if (!hit.length && !miss.length) return [];
    const parts = [hit.length ? `✓ ${hit.join(", ")}` : "", miss.length ? `missing ${miss.join(", ")}` : ""];
    return [`${label}: ${parts.filter(Boolean).join(" · ")}`];
  });
  if (!lines.length) return null;
  return (
    <details>
      <summary>Why this score</summary>
      {lines.map((l) => (
        <div key={l}>{l}</div>
      ))}
    </details>
  );
}
