import { useId, useState } from "react";
import { Link } from "react-router";
import { Page } from "../../app/PageHeader";
import { Button } from "../../kit/Button";
import { TextInput } from "../../kit/inputs";
import { useToast } from "../../kit/Toast";
import { errorText } from "../today/api";
import { deleteAnswer, editAnswer, useAnswers, useProfileWrite, type SavedAnswer } from "./api";
import { describeAnswer, groupAnswers } from "./answerLabels";
import { DeleteButton, Loaded } from "./ProfilePage";
import styles from "./Profile.module.css";

function AnswerRow({ a }: { a: SavedAnswer }) {
  const [draft, setDraft] = useState<string | null>(null);
  const save = useProfileWrite(editAnswer);
  const del = useProfileWrite(deleteAnswer);
  const toast = useToast();
  const hint = useId();
  const { label } = describeAnswer(a);
  return (
    <li className={styles.row}>
      <span className={styles.grow}>
        <strong>{label}</strong>
        {draft === null ? <> · {a.answer ?? <em>Not set</em>}</> : (
          <TextInput aria-label={`Answer for ${label}`} value={draft} onValueChange={setDraft} />
        )}
        {draft !== null && !draft.trim() ? <span id={hint} className={styles.muted}> Type an answer first</span> : null}
        {save.isError ? <span role="alert"> Couldn’t save: {errorText(save.error)}</span> : null}
      </span>
      {draft === null ? (
        <Button size="small" aria-label={`Edit ${label}`} onClick={() => setDraft(a.answer ?? "")}>Edit</Button>
      ) : (
        <>
          <Button size="small" disabled={!draft.trim()} aria-describedby={draft.trim() ? undefined : hint} pending={save.isPending}
            pendingLabel="Saving…" onClick={() => save.mutate({ a, answer: draft }, { onSuccess: () => setDraft(null) })}>Save</Button>
          <Button size="small" onClick={() => setDraft(null)}>Cancel</Button>
          <DeleteButton label={label} onConfirm={() => del.mutate(a, { onError: (e) => toast.show({ message: `Couldn’t delete ${label}: ${errorText(e)}` }) })} />
        </>
      )}
    </li>
  );
}

/** Application answers: grouped, plain-language labels; delete lives inside a row's edit mode. */
export function AnswersPage() {
  const answers = useAnswers();
  return (
    <Page title="Application answers" subtitle={<>CareerOS uses these answers when filling applications. <Link to="/profile">Back to Profile</Link></>}>
      <Loaded q={answers} empty={(d) => !d.answers.length}>
        {(d) => <div className={styles.col}>{groupAnswers(d.answers).map((g) => (
          <section key={g.group} className={styles.card} aria-labelledby={`g-${g.group}`}>
            <h2 id={`g-${g.group}`} className={styles.h2}>{g.group} · {g.rows.length}</h2>
            <ul className={`${styles.list} ${styles.zebra}`}>
              {g.rows.map((a) => <AnswerRow key={`${a.company ?? ""}/${a.key}`} a={a} />)}
            </ul>
          </section>
        ))}</div>}
      </Loaded>
    </Page>
  );
}
