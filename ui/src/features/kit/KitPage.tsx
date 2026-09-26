import { useRef, useState } from "react";
import { Page } from "../../app/PageHeader";
import { Button } from "../../kit/Button";
import {
  ActionTypeLabel,
  NeedsLabel,
  PriorityChip,
  SafetyChip,
  StatusChip,
  StopReasonChip,
  TierBadge,
} from "../../kit/chips";
import { ConfirmPanel } from "../../kit/ConfirmPanel";
import { EmptyState } from "../../kit/EmptyState";
import { ExternalLink } from "../../kit/ExternalLink";
import { ACTION_TYPES, NEEDS, PRIORITIES, SAFETY, STATUSES, STOP_REASONS, TIERS } from "../../kit/labels";
import { MarkDoneCircle } from "../../kit/MarkDoneCircle";
import { Popover } from "../../kit/Popover";
import { SegmentedControl } from "../../kit/SegmentedControl";
import { Switch } from "../../kit/Switch";
import { useToast } from "../../kit/Toast";
import styles from "./KitPage.module.css";

// Developer page for visual checks against the mockup's Components artboard, in both themes side by side.

const TOKENS = [
  "--bg", "--group", "--card", "--sidebar", "--fill", "--sep", "--label", "--sec", "--ter",
  "--accent", "--link", "--selected", "--hover",
];

function Codes({ table, render }: { table: Record<string, unknown>; render: (code: string) => React.ReactNode }) {
  return (
    <div className={styles.row}>
      {Object.keys(table).map((code) => (
        <div key={code} className={styles.cell}>
          {render(code)}
          <code className={styles.code} translate="no">
            {code}
          </code>
        </div>
      ))}
    </div>
  );
}

function Interactive() {
  const toast = useToast();
  const [on, setOn] = useState(true);
  const [off, setOff] = useState(false);
  const [sort, setSort] = useState("priority");
  const [done, setDone] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);
  const [open, setOpen] = useState(false);
  const tile = useRef<HTMLButtonElement>(null);

  return (
    <>
      <section>
        <h3 className={styles.h3}>Buttons and states</h3>
        <div className={styles.stack}>
          {(["primary", "secondary", "destructive"] as const).map((v) => (
            <div key={v} className={styles.row}>
              <Button variant={v}>{v[0]!.toUpperCase() + v.slice(1)}</Button>
              <Button variant={v} disabled>
                Disabled
              </Button>
              <Button variant={v} pending pendingLabel="Saving…">
                Save
              </Button>
            </div>
          ))}
          <div className={styles.row}>
            <Button
              variant="primary"
              pending={pending}
              pendingLabel="Starting…"
              onClick={() => {
                setPending(true);
                setTimeout(() => setPending(false), 1500);
              }}
            >
              Start score run
            </Button>
          </div>
          <p className={styles.note}>Loading: keep the label, add “…” and a spinner. Destructive actions get a confirm or an undo.</p>
        </div>
      </section>

      <section className={styles.row}>
        <div className={styles.stack}>
          <h3 className={styles.h3}>Switches</h3>
          <Switch checked={on} onCheckedChange={setOn} label="Scout schedule" />
          <Switch checked={off} onCheckedChange={setOff} label="Inbox sync schedule" />
        </div>
        <div className={styles.stack}>
          <h3 className={styles.h3}>Mark done</h3>
          <span className={styles.row}>
            <MarkDoneCircle done={done} onDoneChange={setDone} itemName="Ramp LinkedIn note" />
            {done ? "Done" : "Not done"}
          </span>
        </div>
        <div className={styles.stack}>
          <h3 className={styles.h3}>Link</h3>
          <ExternalLink href="https://example.com/jobs">Open posting</ExternalLink>
        </div>
      </section>

      <section className={styles.stack}>
        <h3 className={styles.h3}>Segmented control</h3>
        <SegmentedControl label="Sort" value={sort} onValueChange={setSort}>
          <SegmentedControl.Option value="priority">Priority</SegmentedControl.Option>
          <SegmentedControl.Option value="due">Due date</SegmentedControl.Option>
          <SegmentedControl.Option value="az">A–Z</SegmentedControl.Option>
          <SegmentedControl.Option value="new">Newest</SegmentedControl.Option>
        </SegmentedControl>
      </section>

      <section className={styles.stack}>
        <h3 className={styles.h3}>Stat tile and popover</h3>
        <div className={styles.anchor}>
          <button
            ref={tile}
            type="button"
            className={styles.statTile}
            aria-expanded={open}
            onClick={() => setOpen((o) => !o)}
          >
            <span className={styles.statLabel}>Applied this week</span>
            <span className={styles.statValue}>0</span>
            <span className={styles.statLabel}>Limit 15 a day</span>
          </button>
          <Popover
            open={open}
            onClose={() => setOpen(false)}
            anchorRef={tile}
            label="Applied this week"
            className={styles.pop}
          >
            <EmptyState title="No applications this week" headingLevel={3} />
          </Popover>
        </div>
      </section>

      <section className={styles.stack}>
        <h3 className={styles.h3}>Undo and confirm</h3>
        <div className={styles.row}>
          <Button onClick={() => toast.show({ message: "Marked Ramp done.", onUndo: () => undefined })}>
            Show undo toast
          </Button>
          <Button variant="destructive" onClick={() => setConfirming(true)}>
            Withdraw…
          </Button>
        </div>
        {confirming ? (
          <ConfirmPanel
            question="Withdraw from Acme? You can’t undo this."
            cancelLabel="Keep application"
            confirmLabel="Withdraw"
            onCancel={() => setConfirming(false)}
            onConfirm={() => setConfirming(false)}
          />
        ) : null}
        <p className={styles.note}>Reversible: act now, show Undo for 8 s. Irreversible: confirm first, name the outcome on the button.</p>
      </section>
    </>
  );
}

function Board({ theme }: { theme: "light" | "dark" }) {
  const title = theme === "light" ? "Light" : "Dark";
  const id = `kit-${theme}`;
  return (
    <section data-theme={theme} aria-labelledby={id} className={styles.board}>
      <h2 id={id} className={styles.boardTitle}>
        {title}
      </h2>
      <section>
        <h3 className={styles.h3}>Job status</h3>
        <Codes table={STATUSES} render={(c) => <StatusChip status={c} />} />
      </section>
      <section className={styles.row}>
        <div>
          <h3 className={styles.h3}>Safety verdict</h3>
          <Codes table={SAFETY} render={(c) => <SafetyChip verdict={c} />} />
        </div>
        <div>
          <h3 className={styles.h3}>Tier</h3>
          <Codes table={TIERS} render={(c) => <TierBadge tier={c} />} />
        </div>
        <div>
          <h3 className={styles.h3}>Priority</h3>
          <Codes table={PRIORITIES} render={(c) => <PriorityChip priority={c} />} />
        </div>
        <div>
          <h3 className={styles.h3}>Needs</h3>
          <Codes table={NEEDS} render={(c) => <NeedsLabel needs={c} />} />
        </div>
      </section>
      <section>
        <h3 className={styles.h3}>Run stop reasons</h3>
        <Codes table={STOP_REASONS} render={(c) => <StopReasonChip reason={c} />} />
      </section>
      <section>
        <h3 className={styles.h3}>Action item types</h3>
        <div className={styles.grid}>
          {Object.keys(ACTION_TYPES).map((c) => (
            <span key={c} className={styles.cell}>
              <ActionTypeLabel type={c} />
              <code className={styles.code} translate="no">
                {c}
              </code>
            </span>
          ))}
        </div>
      </section>
      <Interactive />
      <section>
        <h3 className={styles.h3}>Tokens</h3>
        <div className={styles.row}>
          {TOKENS.map((t) => (
            <span key={t} className={styles.cell}>
              <span className={styles.swatch} style={{ background: `var(${t})` }} />
              <code className={styles.code}>{t}</code>
            </span>
          ))}
        </div>
      </section>
    </section>
  );
}

export function KitPage() {
  return (
    <Page title="Components" subtitle="Every kit component in both themes, for checking against the mockup.">
      <div className={styles.boards}>
        <Board theme="light" />
        <Board theme="dark" />
      </div>
    </Page>
  );
}
