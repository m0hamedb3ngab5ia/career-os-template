import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { apiFetch, apiSend } from "../../api/client";
import type { components } from "../../api/schema.gen";
import { Button } from "../../kit/Button";
import { Dialog } from "../../kit/Dialog";
import { TextField } from "../../kit/FormField";
import { useToast } from "../../kit/Toast";
import detail from "../job-detail/JobDetail.module.css";
import { MatchesTable } from "../job-detail/MatchesCard";

type Created = components["schemas"]["CheckCreated"];
type CheckState = components["schemas"]["CheckState"];

const MAX_BYTES = 5 * 1024 * 1024; // same cap as the server (check.MAX_BYTES)
const BUSY = new Set(["scoring", "tailoring"]);

function errorText(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong";
}

/** Raw body (DEC-006): pasted text as text/plain, or the file with its name as a query parameter. */
function postCheck(text: string, file: File | null, title: string, company: string): Promise<Created> {
  const p = new URLSearchParams();
  if (file) p.set("filename", file.name);
  if (title) p.set("title", title);
  if (company) p.set("company", company);
  return apiFetch<Created>(`/api/jobs/check?${p}`, {
    method: "POST",
    headers: { "X-CareerOS": "1", "Content-Type": file ? "application/octet-stream" : "text/plain" },
    body: file ?? text,
  });
}

/** REQ-114 / UC-010 / FLOW-003: paste or upload a JD, see the scan, fit and résumé match, then use, tailor or keep. */
export function CheckJobDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [created, setCreated] = useState<Created | null>(null);
  const close = () => {
    setCreated(null);
    onClose();
  };
  return (
    <Dialog
      open={open}
      onClose={close}
      title="Check a job"
      description="Paste a job description or upload it. It's stored as a manual job, scanned, scored and matched to your résumés."
    >
      {created ? <Result created={created} onDone={close} /> : <CheckForm onCreated={setCreated} onCancel={close} />}
    </Dialog>
  );
}

function CheckForm({ onCreated, onCancel }: { onCreated: (c: Created) => void; onCancel: () => void }) {
  const qc = useQueryClient();
  const id = useId();
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [error, setError] = useState<string | null>(null);
  const send = useMutation({
    mutationFn: () => postCheck(text, file, title.trim(), company.trim()),
    onSuccess: (c) => {
      void qc.invalidateQueries({ queryKey: ["jobs"] });
      onCreated(c);
    },
    onError: (e) => setError(errorText(e)),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!file && !text.trim()) return setError("Paste the job description or choose a file.");
    if (file && file.size > MAX_BYTES) return setError(`${file.name} is larger than 5 MB.`);
    setError(null);
    send.mutate();
  }

  return (
    <form onSubmit={submit} noValidate>
      <label htmlFor={`${id}-jd`}>Job description</label>
      <textarea
        id={`${id}-jd`}
        name="jd"
        rows={8}
        className={detail.input}
        value={text}
        disabled={!!file}
        aria-invalid={error && !file ? true : undefined}
        aria-describedby={error ? `${id}-err` : undefined}
        onChange={(e) => setText(e.target.value)}
      />
      <label htmlFor={`${id}-file`}>Or upload a file (PDF, DOCX, TXT or MD, up to 5 MB)</label>
      <input
        id={`${id}-file`}
        type="file"
        name="file"
        accept=".pdf,.docx,.txt,.md"
        aria-invalid={error && file ? true : undefined}
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      <TextField label="Title (optional)" name="title" value={title} onChange={(e) => setTitle(e.target.value)} />
      <TextField label="Company (optional)" name="company" value={company} onChange={(e) => setCompany(e.target.value)} />
      {error ? (
        <p id={`${id}-err`} role="alert">
          {error}
        </p>
      ) : null}
      <div>
        <Button type="button" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" pending={send.isPending} pendingLabel="Checking…">
          Check job
        </Button>
      </div>
    </form>
  );
}

function Result({ created, onDone }: { created: Created; onDone: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const jobId = created.job_id;
  const path = `/api/jobs/${encodeURIComponent(jobId)}/check`;
  const q = useQuery({
    queryKey: ["job", jobId, "check"],
    queryFn: () => apiFetch<CheckState>(path),
    refetchInterval: (s) => (!s.state.data || BUSY.has(s.state.data.stage) ? 2000 : false),
  });
  const refresh = (s?: CheckState) => {
    if (s) qc.setQueryData(["job", jobId, "check"], s);
    else void qc.invalidateQueries({ queryKey: ["job", jobId, "check"] });
    void qc.invalidateQueries({ queryKey: ["jobs"] });
  };
  const fail = (e: unknown) => toast.show({ message: errorText(e) });
  const tailor = useMutation({ mutationFn: () => apiSend("POST", `${path}/tailor`), onSuccess: () => refresh(), onError: fail });
  const decide = useMutation({
    mutationFn: (keep: boolean) => apiSend<CheckState>("POST", `${path}/decision`, { keep }),
    onSuccess: refresh,
    onError: fail,
  });
  const use = useMutation({
    mutationFn: () => apiSend("POST", "/api/jobs/select", { ids: [jobId], selected: true }),
    onSuccess: () => {
      refresh();
      toast.show({ message: "Job ticked; the next prepare run uses its best résumé." });
      onDone();
    },
    onError: fail,
  });

  const s = q.data;
  const best = s?.resumes[0]?.score;
  return (
    <div aria-live="polite">
      {created.flagged ? (
        <p role="alert">
          Possible prompt injection: {created.reasons.join("; ")}. Scoring continues; prepare waits until you mark it
          checked on the job page.
        </p>
      ) : null}
      {created.score_error ? <p>Scoring could not start: {created.score_error}</p> : null}
      {!s ? (
        <p>{q.isError ? errorText(q.error) : "Loading…"}</p>
      ) : (
        <>
          {s.stage === "scoring" ? <p>Scoring… {s.hint ?? ""}</p> : null}
          {s.scored && s.resumes.length ? <MatchesTable m={s} /> : null}
          {s.scored && !s.resumes.length ? <p>No résumés yet. Add one on the Profile page.</p> : null}
          {s.notice ? <p>{s.notice}</p> : null}
          {s.stage === "ready" || s.stage === "ready_tailored" ? (
            <p>
              {s.stage === "ready_tailored" ? `The tailored résumé scores ${s.attempt?.score}` : `Best match ${best}`},
              threshold {s.threshold}.{" "}
              <Button variant="primary" pending={use.isPending} onClick={() => use.mutate()}>
                Use this résumé
              </Button>
            </p>
          ) : null}
          {s.stage === "offer_tailor" || s.stage === "tailor_failed" ? (
            <p>
              {s.stage === "tailor_failed"
                ? "The tailor run ended without a résumé. You can try once more."
                : `No résumé reaches the threshold (best ${best ?? "none"}, needed ${s.threshold}).`}{" "}
              <Button variant="primary" pending={tailor.isPending} onClick={() => tailor.mutate()}>
                Tailor from master
              </Button>{" "}
              <Button onClick={onDone}>Keep job, no résumé</Button>
            </p>
          ) : null}
          {s.stage === "tailoring" ? <p>Tailoring from your master résumé…</p> : null}
          {s.stage === "confirm" ? (
            <p>
              <Button variant="primary" pending={decide.isPending} onClick={() => decide.mutate(true)}>
                Create closest match
              </Button>{" "}
              <Button disabled={decide.isPending} onClick={() => decide.mutate(false)}>
                Discard attempt
              </Button>
            </p>
          ) : null}
          {s.stage === "below_threshold" ? <p>Kept, flagged below threshold.</p> : null}
          {s.stage === "discarded" ? <p>Attempt discarded. The job is kept with no résumé chosen.</p> : null}
        </>
      )}
      <p>
        <Link to={`/jobs/${encodeURIComponent(jobId)}`} onClick={onDone}>
          Open job
        </Link>
      </p>
    </div>
  );
}
