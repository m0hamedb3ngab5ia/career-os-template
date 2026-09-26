import { useState, type FormEvent } from "react";
import { Button } from "../../kit/Button";
import { STATUSES, describeCode } from "../../kit/labels";
import { Sheet } from "../../kit/Sheet";
import styles from "./Pipeline.module.css";

interface StatusChooserProps {
  company: string;
  target: string;
  statuses: string[];
  onChoose: (status: string) => void;
  onClose: () => void;
}

/** A column holds several statuses (Queued = queued + prepared): ask which one before moving. */
export function StatusChooser({ company, target, statuses, onChoose, onClose }: StatusChooserProps) {
  const [value, setValue] = useState(statuses[0] ?? "");
  function submit(e: FormEvent) {
    e.preventDefault();
    if (value) onChoose(value);
  }
  return (
    <Sheet title={`Move ${company} to ${target}`} description="This column holds more than one status. Which one?" onClose={onClose}>
      <form onSubmit={submit}>
        <fieldset className={styles.choices}>
          <legend className={styles.srOnlyLegend}>Status</legend>
          {statuses.map((s) => (
            <label key={s} className={styles.choice}>
              <input type="radio" name="status" value={s} checked={value === s} onChange={() => setValue(s)} />
              {describeCode(STATUSES, s).label}
            </label>
          ))}
        </fieldset>
        <div className={styles.sheetButtons}>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary">
            Move
          </Button>
        </div>
      </form>
    </Sheet>
  );
}
