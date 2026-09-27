import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { Button } from "../../kit/Button";
import { ConfirmPanel } from "../../kit/ConfirmPanel";
import { useToast } from "../../kit/Toast";
import { QUEUED_NOTE } from "./queued";
import { useBlockCompany, useMarkSafe, useUndoMarkSafe, useUnblockCompany } from "./api";
import styles from "./ActionItems.module.css";
import type { ActionItem } from "./types";
import { useUndoSeconds } from "./useUndoSeconds";

type Ask = "idle" | "block" | "safe";

function message(e: unknown): string {
  return e instanceof ApiError ? e.message : "Couldn't reach careeros ui. Is it still running?";
}

/** A possible-scam item's two ways out, each confirmed first and undoable from the toast. */
export function ScamControls({ item }: { item: ActionItem }) {
  const [ask, setAsk] = useState<Ask>("idle");
  const toast = useToast();
  const seconds = useUndoSeconds();
  const block = useBlockCompany();
  const unblock = useUnblockCompany();
  const safe = useMarkSafe();
  const undoSafe = useUndoMarkSafe();
  const company = item.company || "this company";
  // Cancel puts focus back on the button that opened the confirm (Escape included).
  const returnTo = useRef<"block" | "safe" | null>(null);
  const blockRef = useRef<HTMLButtonElement>(null);
  const safeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (ask !== "idle" || !returnTo.current) return;
    (returnTo.current === "block" ? blockRef : safeRef).current?.focus();
    returnTo.current = null;
  }, [ask]);
  function cancel() {
    returnTo.current = ask === "idle" ? null : ask;
    setAsk("idle");
  }

  function doBlock() {
    block.mutate(item.id, {
      onSuccess: (r) => {
        setAsk("idle");
        toast.show({
          message: (r.added ? `Blocked ${r.company}` : `${r.company} was already blocked; item marked done`) +
            (r.queued ? QUEUED_NOTE : ""),
          seconds,
          onUndo: () =>
            unblock.mutate(
              // already blocked before: Undo only reopens the item and leaves the user's own entry
              { id: item.id, company: r.company, remove: r.added },
              { onError: (e) => toast.show({ message: `Undo failed: ${message(e)}` }) },
            ),
        });
      },
      onError: (e) => toast.show({ message: `Couldn't block ${company}: ${message(e)}` }),
    });
  }

  function doSafe() {
    safe.mutate(item.id, {
      onSuccess: (r) => {
        setAsk("idle");
        toast.show({
          message: `Marked ${r.company} posting safe${r.queued ? QUEUED_NOTE : ""}`,
          seconds,
          onUndo: () =>
            undoSafe.mutate(
              { id: item.id, previous_status: r.previous_status, registry_before: r.registry_before },
              { onError: (e) => toast.show({ message: `Undo failed: ${message(e)}` }) },
            ),
        });
      },
      onError: (e) => toast.show({ message: `Couldn't mark the posting safe: ${message(e)}` }),
    });
  }

  if (ask === "block")
    return (
      <ConfirmPanel
        question={`Block ${company}?`}
        detail="career-os skips its postings from now on. You can unblock it in Settings › Companies."
        cancelLabel="Cancel"
        confirmLabel="Block company"
        pending={block.isPending}
        onCancel={cancel}
        onConfirm={doBlock}
      />
    );
  if (ask === "safe")
    return (
      <ConfirmPanel
        question="Mark this posting safe?"
        detail="It goes back to Queued and can be prepared tonight. Only do this if you checked the company yourself."
        cancelLabel="Cancel"
        confirmLabel="Mark posting safe"
        confirmVariant="primary"
        pending={safe.isPending}
        onCancel={cancel}
        onConfirm={doSafe}
      />
    );
  return (
    <div className={styles.scam}>
      <Button ref={blockRef} size="small" onClick={() => setAsk("block")}>
        Block company
      </Button>
      <Button ref={safeRef} size="small" onClick={() => setAsk("safe")}>
        Mark posting safe
      </Button>
    </div>
  );
}
