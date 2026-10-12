import { useRef, useState } from "react";
import { Button } from "../../kit/Button";
import { Chip } from "../../kit/chips";
import { Details } from "../../kit/Details";
import { SelectInput, TextInput } from "../../kit/inputs";
import { useToast } from "../../kit/Toast";
import { optionLabel } from "../settings/format";
import { errorText, useApproveFillField, useEditFillField, useFillPlan, useMakeFillPlan, type FillField } from "./api";
import { Card } from "./Card";
import styles from "./JobDetail.module.css";

// Where each value came from, in plain words (REQ-105: saved answer | résumé | default | yours).
export function sourceLabel(f: FillField): string {
  const s = f.source ?? "";
  if (f.skipped) return "Skipped";
  if (s.startsWith("standard:") || s === "eeo") return "Saved answer";
  if (s === "profile" || s === "file") return "Résumé / profile";
  if (s === "user") return "Edited by you";
  if (s === "ai_draft") return f.reviewed ? "AI draft, approved" : "AI draft";
  if (s === "pause:sensitive") return "Never filled (sensitive)";
  if (s.startsWith("pause:")) return `Your answer needed (${s.slice(6)})`;
  if (s === "unanswered") return "Needs input";
  return f.value == null ? "Empty" : "Default";
}

// Fill preview sections, in form order (information architecture: who you are → documents → background → this role → self-ID).
const SECTIONS = [
  "Contact & identity",
  "Documents",
  "Education",
  "Work & eligibility",
  "Role preferences",
  "Other questions",
  "Voluntary self-identification",
] as const;
type Section = (typeof SECTIONS)[number];

// ponytail: label regexes, good enough for Greenhouse forms; move to the server if plans gain a section field.
export function sectionOf(f: FillField): Section {
  const l = f.label;
  if (f.kind === "eeo" || f.source === "eeo" || /veteran|race|gender|ethnic|disabilit|hispanic/i.test(l)) return "Voluntary self-identification";
  if (f.type === "file") return "Documents";
  if (/school|degree|discipline|gpa|universit|academic|graduat|major|education|date year/i.test(l)) return "Education";
  if (/preference|engineer/i.test(l)) return "Role preferences";
  if (["salary", "legal"].includes(f.kind ?? "") || /sponsor|authori[sz]|eligib|visa|employer|job title|start|notice|offer|salary|compensation/i.test(l))
    return "Work & eligibility";
  if (/name|email|phone|pronoun|linkedin|github|website|portfolio|address|city|country|location|zip|postal/i.test(l)) return "Contact & identity";
  return "Other questions";
}

const shown = (v: unknown) => (Array.isArray(v) ? v.join(", ") : v == null ? "" : String(v));
const isEmpty = (f: FillField) => f.value == null || shown(f.value) === "";

function FieldRow({ jobId, f }: { jobId: string; f: FillField }) {
  const edit = useEditFillField(jobId, f.field_id);
  const approve = useApproveFillField(jobId, f.field_id);
  const draft = f.source === "ai_draft" && !f.reviewed;
  const toast = useToast();
  const [value, setValue] = useState(shown(f.value));
  // EEO stays on this job only (judged from the field, so a re-edit can't save it); salary is per job unless ticked.
  const eeo = f.kind === "eeo";
  // Drafts are AI text for this job: off by default (DEC-010).
  const [save, setSave] = useState(f.kind !== "salary" && f.source !== "ai_draft");
  const editable = !["file", "hidden"].includes(f.type) && f.source !== "pause:sensitive";
  const empty = isEmpty(f);
  function send(body: { value?: string; skip?: boolean; save?: boolean }) {
    edit.mutate(body, {
      onSuccess: (r) =>
        toast.show({ message: body.skip ? `Skipped: ${f.label}` : `Saved: ${f.label}${r.saved ? ", also saved to your profile" : ""}` }),
      onError: (e) => toast.show({ message: errorText(e) }),
    });
  }
  return (
    <tr data-needs={empty && !f.skipped ? "" : undefined}>
      <th scope="row">{f.label}</th>
      <td>
        {!editable ? (
          shown(f.value) || "—"
        ) : f.options?.length ? (
          <SelectInput
            aria-label={f.label}
            value={value}
            onValueChange={setValue}
            options={[{ value: "", label: "Choose…" }, ...f.options.map((o) => ({ value: o, label: o }))]}
          />
        ) : (
          <TextInput aria-label={f.label} value={value} onValueChange={setValue} />
        )}
      </td>
      <td>{draft ? <Chip tone="orange">AI draft</Chip> : sourceLabel(f)}</td>
      <td>{f.required ? <Chip tone="orange">Required</Chip> : "Optional"}</td>
      <td>
        {editable ? (
          <>
            {!eeo ? (
              <label>
                <input type="checkbox" checked={save} onChange={(e) => setSave(e.target.checked)} /> Save to profile
              </label>
            ) : null}{" "}
            <Button
              size="small"
              disabled={edit.isPending || !value.trim() || value === shown(f.value)}
              onClick={() => send({ value, save: save && !eeo })}
            >
              Save
            </Button>
            {draft && value === shown(f.value) ? (
              <Button
                size="small"
                disabled={approve.isPending}
                onClick={() =>
                  approve.mutate(undefined, {
                    onSuccess: () => toast.show({ message: `Approved: ${f.label}` }),
                    onError: (e) => toast.show({ message: errorText(e) }),
                  })
                }
              >
                Approve
              </Button>
            ) : null}
            {!f.required && !f.skipped && (empty || draft) ? (
              <Button size="small" disabled={edit.isPending} onClick={() => send({ skip: true })}>
                Skip
              </Button>
            ) : null}
          </>
        ) : null}
      </td>
    </tr>
  );
}

/** Preview fill: every field career-os will type, editable; unknown ones asked; Fill waits for required answers. */
export function FillPlanCard({ jobId, ats, canPlan = true }: { jobId: string; ats?: string; canPlan?: boolean }) {
  const q = useFillPlan(jobId);
  const make = useMakeFillPlan(jobId);
  const toast = useToast();
  const plan = q.data?.plan;
  const sectionsRef = useRef<HTMLDivElement>(null);
  // Native <details>: toggle the DOM attribute directly, no per-section state.
  const setAll = (open: boolean) => sectionsRef.current?.querySelectorAll("details").forEach((d) => (d.open = open));
  const problems = q.data?.problems ?? [];
  const preview = (
    <Button disabled={make.isPending || !canPlan} onClick={() => make.mutate(undefined, { onError: (e) => toast.show({ message: errorText(e) }) })}>
      {make.isPending ? "Building preview…" : plan ? "Rebuild preview" : "Preview fill"}
    </Button>
  );
  return (
    <Card title="Fill preview" wide aside={plan ? (
      <span className={styles.planBar}>
        <Button size="small" onClick={() => setAll(true)}>Expand all</Button>
        <Button size="small" onClick={() => setAll(false)}>Collapse all</Button>
        {problems.length ? <Chip tone="orange">{problems.length} to answer</Chip> : <Chip tone="green">Ready to fill</Chip>}
      </span>
    ) : null}>
      {!plan && ats && ats !== "greenhouse" ? (
        <p>career-os can preview and fill only Greenhouse postings; this one is on {optionLabel(ats)}. Apply on the posting's own page.</p>
      ) : !plan ? (
        <p>See what career-os will type into the application, and answer anything it doesn't know, before it fills. {preview}{!canPlan ? <> This posting is missing its board or job id, so a preview isn't possible. Apply on the posting's own page.</> : null}</p>
      ) : (
        <>
          <div role="status" aria-live="polite">
            {problems.length ? (
              <p className={styles.alert}>Fill application waits until you answer: {problems.map((p) => p.replace(/^[^)]*\): /, "")).join("; ")}</p>
            ) : null}
          </div>
          <div ref={sectionsRef}>
          {SECTIONS.map((name) => {
            const fields = plan.fields.filter((f) => f.type !== "hidden" && sectionOf(f) === name);
            if (!fields.length) return null;
            const need = fields.filter((f) => isEmpty(f) && !f.skipped).length;
            return (
              <Details
                key={name}
                summary={`${name} · ${fields.length}${need ? ` · ${need} to answer` : ""}`}
              >
                <div className={styles.planWrap}>
                  <table className={styles.planTable}>
                    <caption className="sr-only">{name}: fields career-os will fill</caption>
                    <thead className="sr-only">
                      <tr>
                        <th scope="col">Field</th>
                        <th scope="col">Value</th>
                        <th scope="col">Source</th>
                        <th scope="col">Required</th>
                        <th scope="col">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {fields.map((f) => (
                        <FieldRow key={`${f.field_id}:${shown(f.value)}:${f.skipped ? 1 : 0}:${f.reviewed ? 1 : 0}`} jobId={jobId} f={f} />
                      ))}
                    </tbody>
                  </table>
                </div>
              </Details>
            );
          })}
          </div>
          {preview}
        </>
      )}
    </Card>
  );
}
