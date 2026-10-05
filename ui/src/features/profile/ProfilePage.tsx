import { useId, useRef, useState, type ReactNode } from "react";
import { Page } from "../../app/PageHeader";
import { Button } from "../../kit/Button";
import { TextInput } from "../../kit/inputs";
import { useToast } from "../../kit/Toast";
import { errorText } from "../today/api";
import {
  deleteAnswer, deleteLesson, deleteResume, editAnswer, makeMaster, relearn, removeSample, upload, uploadSamples,
  useAnswers, useLearnRun, useLessons, useProfileWrite, useResumes, useSamples, type SampleChange, type SavedAnswer,
} from "./api";
import styles from "./Profile.module.css";
import { ReadinessCard } from "./ReadinessCard";
import { JustReadyNextStep } from "../today/NextStepCard";

/** Loading / error (with Try again) / empty states shared by every section. */
function Loaded<T>({ q, empty, children }: { q: { data?: T; isPending: boolean; isError: boolean; error: unknown; refetch: () => unknown }; empty: (d: T) => boolean; children: (d: T) => ReactNode }) {
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

function Section({ id, title, intro, children }: { id: string; title: string; intro: string; children: ReactNode }) {
  return (
    <section id={id} className={styles.card} aria-labelledby={`${id}-h`}>
      <h2 id={`${id}-h`} className={styles.h2}>{title}</h2>
      <p className={styles.muted}>{intro}</p>
      {children}
    </section>
  );
}

/** Delete with an inline "Delete? Yes / No" step: no accidental loss of profile data. */
function DeleteButton({ label, onConfirm }: { label: string; onConfirm: () => void }) {
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

function AnswerRow({ a }: { a: SavedAnswer }) {
  const [draft, setDraft] = useState<string | null>(null);
  const save = useProfileWrite(editAnswer);
  const del = useProfileWrite(deleteAnswer);
  const toast = useToast();
  const hint = useId();
  const name = `${a.key}${a.company ? ` (${a.company})` : ""}`;
  return (
    <li className={styles.row}>
      <span className={styles.grow}>
        <strong>{name}</strong>
        {draft === null ? <> · {a.answer ?? <em>not set</em>}</> : (
          <TextInput aria-label={`Answer for ${name}`} value={draft} onValueChange={setDraft} />
        )}
        {draft !== null && !draft.trim() ? <span id={hint} className={styles.muted}> Type an answer first</span> : null}
        {save.isError ? <span role="alert"> Couldn’t save: {errorText(save.error)}</span> : null}
      </span>
      {draft === null ? (
        <>
          <Button size="small" aria-label={`Edit ${name}`} onClick={() => setDraft(a.answer ?? "")}>Edit</Button>
          <DeleteButton label={name} onConfirm={() => del.mutate(a, { onError: (e) => toast.show({ message: `Couldn’t delete ${name}: ${errorText(e)}` }) })} />
        </>
      ) : (
        <>
          <Button size="small" disabled={!draft.trim()} aria-describedby={draft.trim() ? undefined : hint} pending={save.isPending}
            pendingLabel="Saving…" onClick={() => save.mutate({ a, answer: draft }, { onSuccess: () => setDraft(null) })}>Save</Button>
          <Button size="small" onClick={() => setDraft(null)}>Cancel</Button>
        </>
      )}
    </li>
  );
}

const SCOPES: { scope: SavedAnswer["scope"]; title: string }[] = [
  { scope: "general", title: "General" },
  { scope: "company", title: "Per company" },
  { scope: "eeo", title: "EEO (voluntary)" },
];

/** REQ-107 Profile page: Readiness, Résumés, Writing samples, Saved answers, Learned. */
export function ProfilePage() {
  const resumes = useResumes();
  const samples = useSamples();
  const answers = useAnswers();
  const lessons = useLessons();
  const toast = useToast();
  const [learn, setLearn] = useState<Partial<SampleChange>>({});
  const onSamples = { onSuccess: (r: SampleChange) => setLearn(r) };
  const run = useLearnRun(learn.learn_run).data;
  const ended = run && run.state !== "running";
  // UC-005 Fail: a run that started and then failed keeps the samples and offers Retry like a start failure.
  const learnError = learn.learn_error ?? (ended && run.stop_reason !== "completed"
    ? `Voice update failed: ${run.detail || run.stop_reason || run.state}` : null);
  const learnInfo = learn.learn_info ?? (run && !ended ? "Updating your writing style from the samples…" : null);
  const addResume = useProfileWrite((f: File) => upload("/api/profile/resumes", f));
  const master = useProfileWrite(makeMaster);
  const delResume = useProfileWrite(deleteResume);
  const addSample = useProfileWrite(uploadSamples);
  const delSample = useProfileWrite(removeSample);
  const retry = useProfileWrite(relearn);
  const delLesson = useProfileWrite(deleteLesson);
  const failed = [addResume, master, delResume, addSample, delSample, delLesson].find((m) => m.isError);

  return (
    <Page
      title="Profile"
      subtitle="What the applier knows about you. Finish the checklist, then apply."
      actions={<FilePick primary label="Upload résumé" accept=".pdf,.docx,.txt,.md" pending={addResume.isPending} onFiles={(f) => f[0] && addResume.mutate(f[0])} />}
    >
      <div className={styles.stack}>
        {failed ? <p role="alert" className={styles.banner}>{errorText(failed.error)}</p> : null}
        <ReadinessCard />
        <JustReadyNextStep />
        <Section id="resumes" title="Résumés" intro="The master résumé is the source for profile/master.yaml.">
          <Loaded q={resumes} empty={(d) => !d.resumes.length}>
            {(d) => (
              <ul className={styles.list}>
                {d.resumes.map((r) => (
                  <li key={r.rid} className={styles.row}>
                    <span className={styles.grow}><strong>{r.name}</strong> · {r.type} · v{r.latest}</span>
                    {r.type === "master" ? <span className={styles.muted}>Master</span> : (
                      <Button size="small" onClick={() => master.mutate(r.rid)}>Make master</Button>
                    )}
                    <DeleteButton label={r.name} onConfirm={() => delResume.mutate(r.rid)} />
                  </li>
                ))}
              </ul>
            )}
          </Loaded>
        </Section>
        <Section id="samples" title="Writing samples" intro="Letters or emails you wrote (txt, md or eml, up to 5 MB). Cover letters copy your style from them.">
          {learnInfo && !learnError ? <p role="status" className={styles.muted}>{learnInfo}</p> : null}
          {learnError ? (
            <p role="alert" className={styles.banner}>
              {learnError}{" "}
              <Button size="small" pending={retry.isPending} pendingLabel="Retrying…"
                onClick={() => retry.mutate(undefined, { ...onSamples, onError: (e) => toast.show({ message: `Retry failed: ${errorText(e)}` }) })}>Retry</Button>
            </p>
          ) : null}
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
          <FilePick multiple label="Add samples" accept=".txt,.md,.eml" pending={addSample.isPending} onFiles={(f) => addSample.mutate(f, onSamples)} />
        </Section>
        <Section id="answers" title="Saved answers" intro="The only answers the applier types without asking you.">
          <Loaded q={answers} empty={(d) => !d.answers.length}>
            {(d) =>
              SCOPES.filter((s) => d.answers.some((a) => a.scope === s.scope)).map((s) => (
                <div key={s.scope}>
                  <h3 className={styles.h3}>{s.title}</h3>
                  <ul className={styles.list}>
                    {d.answers.filter((a) => a.scope === s.scope).map((a) => (
                      <AnswerRow key={`${a.company ?? ""}/${a.key}`} a={a} />
                    ))}
                  </ul>
                </div>
              ))
            }
          </Loaded>
        </Section>
        <Section id="learned" title="Learned" intro="Lessons from past applications and the writing style taken from your samples.">
          <h3 className={styles.h3}>Apply lessons</h3>
          <Loaded q={lessons} empty={(d) => !d.lessons.length}>
            {(d) => (
              <ul className={styles.list}>
                {d.lessons.map((l) => (
                  <li key={l.id} className={styles.row}>
                    <span className={styles.grow}>{l.text}{l.ats || l.company ? <span className={styles.muted}> · {[l.ats, l.company].filter(Boolean).join(", ")}</span> : null}</span>
                    <DeleteButton label={`lesson ${l.id}`} onConfirm={() => delLesson.mutate(l.id)} />
                  </li>
                ))}
              </ul>
            )}
          </Loaded>
          <h3 className={styles.h3}>Voice style</h3>
          <Loaded q={samples} empty={(d) => !d.learned}>{(d) => <pre className={styles.learned}>{d.learned}</pre>}</Loaded>
        </Section>
      </div>
    </Page>
  );
}
