import { useEffect, useState } from "react";
import { useBlocker } from "react-router";
import { ApiError } from "../../api/client";
import { Button } from "../../kit/Button";
import { ConfirmPanel } from "../../kit/ConfirmPanel";
import { Sheet } from "../../kit/Sheet";
import { useToast } from "../../kit/Toast";
import { useDiff, useSave } from "./api";
import { clientErrors, useSettingsForm } from "./form";
import { joinFiles, plural } from "./format";
import styles from "./settings.module.css";
import type { SaveErrorBody } from "./types";

const FOCUSABLE = "input:not([disabled]),select:not([disabled]),textarea,button:not([disabled])";

/** Move focus to the first field (in page order) that has an error; its message is under it. */
export function focusFirstInvalid(order: string[], errors: Record<string, string>): boolean {
  for (const id of order) {
    if (!(id in errors)) continue;
    const row = document.querySelector(`[data-field="${CSS.escape(id)}"]`);
    const target = row?.querySelector<HTMLElement>(`[aria-invalid="true"]`) ?? row?.querySelector<HTMLElement>(FOCUSABLE);
    if (target) {
      target.focus();
      return true;
    }
  }
  return false;
}

function errorBody(e: unknown): SaveErrorBody | null {
  if (e instanceof ApiError && e.status === 422 && e.body && typeof e.body === "object" && "fields" in e.body) {
    return e.body as SaveErrorBody;
  }
  return null;
}

function DiffView({ diffs, files }: { diffs: Record<string, string>; files: Record<string, string> }) {
  const entries = Object.entries(diffs);
  if (!entries.length) return <p className={styles.hint}>Nothing would change in the files.</p>;
  return (
    <>
      {entries.map(([file, text]) => (
        <section key={file} aria-label={files[file] ?? file}>
          <h3 className={styles.diffFile}>
            <code translate="no">{files[file] ?? file}</code>
          </h3>
          <pre className={styles.diff} translate="no">
            {text.split("\n").map((line, i) => (
              <span
                key={i}
                className={
                  line.startsWith("+++") || line.startsWith("---") || line.startsWith("@@")
                    ? styles.diffMeta
                    : line.startsWith("+")
                      ? styles.diffAdd
                      : line.startsWith("-")
                        ? styles.diffDel
                        : undefined
                }
              >
                {line}
                {"\n"}
              </span>
            ))}
          </pre>
        </section>
      ))}
    </>
  );
}

/** Sticky save bar: unsaved count, the files a save writes, Show diff, Discard (confirmed) and Save. Also guards
 * leaving the page (router + beforeunload) while there are unsaved changes. */
export function SaveBar() {
  const form = useSettingsForm();
  const toast = useToast();
  const section = form.data.section.id;
  const save = useSave(section);
  const diff = useDiff(section);
  const [askDiscard, setAskDiscard] = useState(false);
  const [diffs, setDiffs] = useState<Record<string, string> | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);
  const n = form.dirtyCount;
  const dirty = n > 0;
  const nErrors = Object.keys(form.errors).length + form.general.length;
  const files = form.data.section.files.map((f) => form.data.files[f] ?? `config/${f}.yaml`);
  const order = form.fields.map((f) => f.id);

  // Unsaved changes: warn before closing the tab and before leaving for another route.
  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname);

  function showErrors(fields: Record<string, string>, general: string[] = []) {
    form.setErrors(fields, general);
    setTimeout(() => {
      if (!focusFirstInvalid(order, fields)) document.getElementById("settings-general-error")?.focus();
    }, 0);
  }

  function checkLocally(): boolean {
    const local = clientErrors(form.fields, form.changes);
    if (Object.keys(local).length) {
      showErrors(local);
      return false;
    }
    return true;
  }

  function onSave() {
    setAskDiscard(false);
    setConflict(null);
    if (!checkLocally()) return;
    save.mutate(
      { changes: form.changes, version: form.data.version },
      {
        onSuccess: () => {
          form.discard();
          toast.show({ message: `Saved ${joinFiles(files)}.` });
        },
        onError: (e) => {
          const body = errorBody(e);
          if (body) return showErrors(body.fields, body.general);
          if (e instanceof ApiError && e.status === 409) return setConflict(e.message);
          showErrors({}, [e instanceof ApiError ? e.message : "Couldn't save. Check that careeros ui is running."]);
        },
      },
    );
  }

  function onShowDiff() {
    if (!checkLocally()) return;
    diff.mutate(form.changes, {
      onSuccess: (r) => setDiffs(r.diffs),
      onError: (e) => {
        const body = errorBody(e);
        if (body) return showErrors(body.fields, body.general);
        showErrors({}, [e instanceof ApiError ? e.message : "Couldn't build the diff."]);
      },
    });
  }

  const status = dirty ? plural(n, "unsaved change") : "No unsaved changes";

  return (
    <>
      {form.general.length ? (
        <div id="settings-general-error" tabIndex={-1} role="alert" className={styles.generalError}>
          {form.general.map((g) => (
            <div key={g}>{g}</div>
          ))}
        </div>
      ) : null}
      {conflict ? (
        <div role="alert" className={styles.generalError}>
          {conflict}{" "}
          <Button size="small" onClick={() => window.location.reload()}>
            Reload
          </Button>
        </div>
      ) : null}
      <div className={styles.saveBar}>
        <div className={styles.saveLine}>
          <span className={styles.saveDot} data-dirty={dirty} aria-hidden="true" />
          <span role="status" className={styles.saveText}>
            {status}
            {nErrors ? <span className={styles.saveErrors}> · fix {plural(nErrors, "error")} to save</span> : null} · writes{" "}
            {files.map((f, i) => (
              <span key={f}>
                {i ? (i === files.length - 1 ? " and " : ", ") : null}
                <code translate="no">{f}</code>
              </span>
            ))}
            , comments kept
          </span>
          <Button size="small" disabled={!dirty} pending={diff.isPending} pendingLabel="Building diff…" onClick={onShowDiff}>
            Show diff
          </Button>
          <Button size="small" disabled={!dirty || save.isPending} onClick={() => setAskDiscard(true)}>
            Discard changes
          </Button>
          <Button size="small" variant="primary" disabled={!dirty} pending={save.isPending} pendingLabel="Saving…" onClick={onSave}>
            Save changes
          </Button>
        </div>
        {askDiscard && dirty ? (
          <ConfirmPanel
            question={`Discard ${status}? This can’t be undone.`}
            cancelLabel="Keep editing"
            confirmLabel="Discard"
            onCancel={() => setAskDiscard(false)}
            onConfirm={() => {
              setAskDiscard(false);
              form.discard();
            }}
          />
        ) : null}
      </div>
      {diffs ? (
        <Sheet title="Changes a save writes" onClose={() => setDiffs(null)}>
          <DiffView diffs={diffs} files={form.data.files} />
        </Sheet>
      ) : null}
      {blocker.state === "blocked" ? (
        <div className={styles.guard}>
          <ConfirmPanel
            question={`Leave without saving? ${status} will be lost.`}
            cancelLabel="Keep editing"
            confirmLabel="Leave"
            onCancel={() => blocker.reset?.()}
            onConfirm={() => blocker.proceed?.()}
          />
        </div>
      ) : null}
    </>
  );
}
