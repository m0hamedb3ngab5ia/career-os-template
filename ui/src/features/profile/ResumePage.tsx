import { Link, useParams } from "react-router";
import { Page } from "../../app/PageHeader";
import { errorText } from "../today/api";
import { useResumeMeta } from "./api";
import { NotCarriedOver } from "./ImportPanels";
import styles from "./Profile.module.css";
import { ResumeFeedback } from "./ResumePanels";

/** /profile/resumes/:rid — one résumé: View, review suggestions, version history. */
export function ResumePage() {
  const rid = useParams().rid ?? "";
  const q = useResumeMeta(rid);
  const r = q.data;
  const back = <Link to="/profile#resumes">Back to Profile</Link>;
  if (q.isError) return <Page title="Résumé" subtitle={back}><p role="alert" className={styles.banner}>Couldn’t load: {errorText(q.error)}</p></Page>;
  if (!r) return <Page title="Résumé" subtitle={back} busy><p className={styles.muted}>Loading…</p></Page>;
  const latest = r.versions[r.versions.length - 1]?.n ?? 1;
  return (
    <Page title={r.name} subtitle={<>{r.type === "master" ? "Master résumé. " : ""}{back}</>}
      actions={<a href={`/api/profile/resumes/${encodeURIComponent(rid)}/file`} target="_blank" rel="noreferrer">View PDF</a>}>
      <div className={styles.col}>
        <section className={styles.card} aria-labelledby="sugg-h">
          <h2 id="sugg-h" className={styles.h2}>Suggestions</h2>
          <ResumeFeedback rid={rid} />
        </section>
        <NotCarriedOver rid={rid} />
        <section id="versions" className={styles.card} aria-labelledby="ver-h">
          <h2 id="ver-h" className={styles.h2}>Versions</h2>
          {/* Every version is kept; the newest is the one in use. */}
          <ul className={styles.list}>
            {[...r.versions].reverse().map((v) => {
              const name = `${String(v.n).padStart(2, "0")} · ${v.label || `Version ${v.n}`}`;
              return (
                <li key={v.n} className={styles.row}>
                  <span className={styles.grow}>
                    <strong>{name}</strong>
                    {v.n === latest ? <> · {r.type === "master" ? "Used for tailored résumés" : "Current version"}</> : null}
                  </span>
                  <span className={styles.muted}>{new Date(v.at).toLocaleDateString()}</span>
                  {/* Published versions keep only JSON; only the latest has a PDF (DEC-020). */}
                  {v.source === "publish" && v.n !== latest ? null : (
                    <a href={`/api/profile/resumes/${encodeURIComponent(rid)}/file?v=${v.n}&download=true`} download
                      aria-label={`Download ${name}`}>Download</a>
                  )}
                </li>
              );
            })}
          </ul>
          {r.versions.length > 1 ? <p className={styles.muted}>Older versions are kept. Uploaded files can still be downloaded.</p> : null}
        </section>
      </div>
    </Page>
  );
}
