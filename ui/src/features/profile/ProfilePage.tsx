import { useRef, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";
import { Page } from "../../app/PageHeader";
import { Button } from "../../kit/Button";
import { ConfirmPanel } from "../../kit/ConfirmPanel";
import { Dialog } from "../../kit/Dialog";
import { Menu } from "../../kit/Menu";
import { useToast } from "../../kit/Toast";
import { errorText } from "../today/api";
import {
  deleteResume, makeMaster, relearn, removeSample, upload, uploadSamples,
  useAnswers, useLearnRun, useProfileWrite, useResumes, useSamples, type SampleChange,
} from "./api";
import { groupAnswers } from "./answerLabels";
import styles from "./Profile.module.css";
import { ReadinessSummary } from "./ReadinessCard";
import { MasterSyncPanel, ResumeFeedback } from "./ResumePanels";
import { JustReadyNextStep } from "../today/NextStepCard";

/** Loading / error (with Try again) / empty states shared by every section. */
export function Loaded<T>({ q, empty, children }: { q: { data?: T; isPending: boolean; isError: boolean; error: unknown; refetch: () => unknown }; empty: (d: T) => boolean; children: (d: T) => ReactNode }) {
  if (q.isPending) return <p className={styles.muted}>Loading…</p>;
  if (q.isError)
    return (
      <p className={styles.muted}>
        Couldn’t load: {errorText(q.error)}{" "}
        <Button size="small" onClick={() => void q.refetch()}>
          Try again
        </Button>
      </p>
    );
  return <>{empty(q.data as T) ? <p className={styles.muted}>Nothing here yet.</p> : children(q.data as T)}</>;
}

function Section({ id, title, intro, aside, children }: { id: string; title: string; intro: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className={styles.card} aria-labelledby={`${id}-h`}>
      <div className={styles.head}>
        <h2 id={`${id}-h`} className={styles.h2}>{title}</h2>
        {aside}
      </div>
      <p className={styles.muted}>{intro}</p>
      {children}
    </section>
  );
}

/** Delete with an inline "Delete? Yes / No" step: no accidental loss of profile data. */
export function DeleteButton({ label, onConfirm }: { label: string; onConfirm: () => void }) {
  const [asking, setAsking] = useState(false);
  if (!asking) return <Button size="small" aria-label={`Delete ${label}`} onClick={() => setAsking(true)}>Delete</Button>;
  return (
    <span role="group" aria-label={`Delete ${label}?`}>
      <Button size="small" variant="destructive" onClick={() => { setAsking(false); onConfirm(); }}>Yes, delete</Button>{" "}
      <Button size="small" onClick={() => setAsking(false)}>Keep</Button>
    </span>
  );
}

function FilePick({ label, accept, onFiles, primary, multiple, pending }: { label: string; accept: string; onFiles: (f: File[]) => void; primary?: boolean; multiple?: boolean; pending?: boolean }) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <>
      <input ref={ref} type="file" accept={accept} multiple={multiple} className={styles.file} aria-label={label} tabIndex={-1}
        onChange={(e) => { const f = [...(e.target.files ?? [])]; if (f.length) onFiles(f); e.target.value = ""; }} />
      <Button size="small" variant={primary ? "primary" : "secondary"} pending={pending} pendingLabel="Uploading…"
        onClick={() => ref.current?.click()}>{label}</Button>
    </>
  );
}

const ago = (at: string) => `Updated ${new Date(at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;

type Row = NonNullable<ReturnType<typeof useResumes>["data"]>["resumes"][number];

/** One résumé: name, short blurb, View, and a ••• menu (Make master, Version history, Delete with confirm). */
function ResumeCard({ r, blurb }: { r: Row; blurb: string }) {
  const nav = useNavigate();
  const master = useProfileWrite(makeMaster);
  const del = useProfileWrite(deleteResume);
  const [asking, setAsking] = useState(false);
  const items = [
    ...(r.type === "master" ? [] : [{ key: "master", label: "Make master", onSelect: () => master.mutate(r.rid) }]),
    { key: "versions", label: "Version history", onSelect: () => void nav(`/profile/resumes/${encodeURIComponent(r.rid)}`) },
    { key: "delete", label: "Delete", onSelect: () => setAsking(true) },
  ];
  const failed = [master, del].find((m) => m.isError);
  return (
    <li className={styles.row}>
      <span className={styles.grow}>
        <strong>{r.type === "master" ? "Master résumé" : r.name}</strong>
        <span className={styles.muted}> · {r.type === "master" ? "" : `${blurb} · `}{ago(r.at)}</span>
      </span>
      <a href={`/api/profile/resumes/${encodeURIComponent(r.rid)}/file`} target="_blank" rel="noreferrer">View</a>
      <Menu size="small" label={`More for ${r.name}`} items={items}>•••</Menu>
      {failed ? <p role="alert" className={styles.banner}>{errorText(failed.error)}</p> : null}
      {asking ? (
        <div className={styles.full}>
          <ConfirmPanel question={`Delete ${r.name}? You can’t undo this.`} cancelLabel="Keep" confirmLabel="Delete" pending={del.isPending}
            onCancel={() => setAsking(false)} onConfirm={() => del.mutate(r.rid, { onSettled: () => setAsking(false) })} />
        </div>
      ) : null}
      <ResumeFeedback rid={r.rid} latest={r.latest} master={r.type === "master"} />
      {r.type === "master" ? <MasterSyncPanel rid={r.rid} /> : null}
    </li>
  );
}

/** REQ-107 Profile page: readiness, résumés, application answers summary, writing style. */
export function ProfilePage() {
  const resumes = useResumes();
  const samples = useSamples();
  const answers = useAnswers();
  const toast = useToast();
  const [learn, setLearn] = useState<Partial<SampleChange>>({});
  const [managing, setManaging] = useState(false);
  const onSamples = { onSuccess: (r: SampleChange) => setLearn(r) };
  const run = useLearnRun(learn.learn_run).data;
  const ended = run && run.state !== "running";
  // UC-005 Fail: a run that started and then failed keeps the samples and offers Retry like a start failure.
  const learnError = learn.learn_error ?? (ended && run.stop_reason !== "completed"
    ? `Voice update failed: ${run.detail || run.stop_reason || run.state}` : null);
  const learnInfo = learn.learn_info ?? (run && !ended ? "Updating your writing style from the samples…" : null);
  const addResume = useProfileWrite((f: File) => upload("/api/profile/resumes", f));
  const addSample = useProfileWrite(uploadSamples);
  const delSample = useProfileWrite(removeSample);
  const retry = useProfileWrite(relearn);
  const failed = [addResume, addSample, delSample].find((m) => m.isError);
  const rows = resumes.data?.resumes ?? [];
  const masters = rows.filter((r) => r.type === "master");
  const others = rows.filter((r) => r.type !== "master" && r.type !== "tailored");
  const banners = (
    <>
      {learnInfo && !learnError ? <p role="status" className={styles.muted}>{learnInfo}</p> : null}
      {learnError ? (
        <p role="alert" className={styles.banner}>
          {learnError}{" "}
          <Button size="small" pending={retry.isPending} pendingLabel="Retrying…"
            onClick={() => retry.mutate(undefined, { ...onSamples, onError: (e) => toast.show({ message: `Retry failed: ${errorText(e)}` }) })}>Retry</Button>
        </p>
      ) : null}
    </>
  );

  return (
    <Page title="Profile" subtitle="Information CareerOS uses when applying for jobs.">
      {failed ? <p role="alert" className={styles.banner}>{errorText(failed.error)}</p> : null}
      <div className={styles.col}>
        <JustReadyNextStep />
        <ReadinessSummary />
        <Section id="resumes" title="Résumés" intro="Source of truth for tailored résumés." aside={<FilePick primary label="Add résumé" accept=".pdf,.docx,.txt,.md" pending={addResume.isPending} onFiles={(f) => f[0] && addResume.mutate(f[0])} />}>
          <Loaded q={resumes} empty={(d) => !d.resumes.length}>
            {() => (
              <>
                <ul className={styles.list}>{masters.map((r) => <ResumeCard key={r.rid} r={r} blurb="Master" />)}</ul>
                {others.length ? (
                  <>
                    <h3 className={styles.h3}>Other résumés</h3>
                    <p className={styles.muted}>Matched to jobs when they fit better.</p>
                    <ul className={styles.list}>{others.map((r) => <ResumeCard key={r.rid} r={r} blurb="Alternate" />)}</ul>
                  </>
                ) : null}
              </>
            )}
          </Loaded>
        </Section>
        <Section id="answers" title="Application answers" intro="CareerOS uses these answers when filling applications."
          aside={<Link to="/profile/answers">Manage answers</Link>}>
          <Loaded q={answers} empty={(d) => !d.answers.length}>
            {(d) => (
              <ul className={styles.list}>
                {groupAnswers(d.answers).map((g) => <li key={g.group} className={styles.row}>{g.group} · {g.rows.length}</li>)}
              </ul>
            )}
          </Loaded>
        </Section>
        <Section id="samples" title="Writing style" intro="CareerOS learns your tone from examples you’ve written."
          aside={<Button size="small" onClick={() => setManaging(true)}>Manage samples</Button>}>
          <p className={styles.muted}>{samples.data ? `${samples.data.samples.length} sample${samples.data.samples.length === 1 ? "" : "s"}` : "Loading…"}</p>
          {managing ? null : banners}
        </Section>
        <Dialog open={managing} onClose={() => setManaging(false)} title="Writing samples"
          description="Letters or emails you wrote (txt, md, eml, pdf or docx, up to 5 MB). Cover letters copy your style from them.">
          {banners}
          <Loaded q={samples} empty={(d) => !d.samples.length}>
            {(d) => (
              <ul className={styles.list}>
                {d.samples.map((s) => (
                  <li key={s.name} className={styles.row}>
                    <span className={styles.grow}>{s.name}</span>
                    <DeleteButton label={s.name} onConfirm={() => delSample.mutate(s.name, onSamples)} />
                  </li>
                ))}
              </ul>
            )}
          </Loaded>
          <FilePick multiple label="Add samples" accept=".txt,.md,.eml,.pdf,.docx" pending={addSample.isPending} onFiles={(f) => addSample.mutate(f, onSamples)} />
        </Dialog>
      </div>
    </Page>
  );
}
