import { SlidersHorizontal } from "lucide-react";
import type { Ref } from "react";
import { useMeta } from "../../api/meta";
import { Button } from "../../kit/Button";
import { Menu } from "../../kit/Menu";
import { STATUSES, describeCode } from "../../kit/labels";
import { useToast } from "../../kit/Toast";
import { help } from "./actionHelp";
import { errorText, useSetOverride, useSetStatus } from "./api";
import { OVERRIDE_LABELS, OVERRIDES } from "./labels";

export function StatusMenu({ jobId, status }: { jobId: string; status: string | null }) {
  const toast = useToast();
  const meta = useMeta();
  const set = useSetStatus(jobId);
  // "applied" is reached only through the confirmed Mark submitted path, never this menu.
  const statuses = (meta.data?.statuses ?? []).filter((s) => s !== "applied");
  const seconds = meta.data?.ui?.undo_seconds;
  function pick(next: string) {
    if (next === status) return;
    set.mutate(
      { status: next },
      {
        onSuccess: (r) =>
          toast.show({
            message: `Status set to ${describeCode(STATUSES, r.status).label}`,
            seconds,
            onUndo: r.previous
              ? () =>
                  set.mutate(
                    { status: r.previous!, note: "undo status change" },
                    { onError: (e) => toast.show({ message: errorText(e) }) },
                  )
              : undefined,
          }),
        onError: (e) => toast.show({ message: errorText(e) }),
      },
    );
  }
  return (
    <Menu label="Set status">
      <Menu.Trigger {...help("setStatus")} pending={set.isPending} pendingLabel="Saving…" disabled={statuses.length === 0}>
        Set status
      </Menu.Trigger>
      <Menu.Content align="end">
        {statuses.map((s) => (
          <Menu.RadioItem key={s} checked={s === status} onSelect={() => pick(s)}>
            {describeCode(STATUSES, s).label}
          </Menu.RadioItem>
        ))}
      </Menu.Content>
    </Menu>
  );
}

export function OverrideMenu({ jobId, override }: { jobId: string; override: string | null | undefined }) {
  const toast = useToast();
  const set = useSetOverride(jobId);
  const current = override ?? "";
  return (
    <Menu label="Status override">
      <Menu.Trigger
        {...help("override")}
        pending={set.isPending}
        pendingLabel="Saving…"
        icon={<SlidersHorizontal size={14} strokeWidth={1.7} aria-hidden="true" />}
      >
        Status override: {current || "none"}
      </Menu.Trigger>
      <Menu.Content align="end">
        {OVERRIDES.map((v) => (
          <Menu.RadioItem
            key={v || "none"}
            checked={v === current}
            onSelect={() =>
              v !== current &&
              set.mutate(
                { value: v },
                {
                  onSuccess: (r) =>
                    toast.show({
                      message:
                        `Override set to ${OVERRIDE_LABELS[v]!.toLowerCase()}` +
                        (r?.queued
                          ? ". Excel has the tracker open, so it's saved to a queue; it's written on the next change, or close Excel and it saves then. Applying reads the old value until then."
                          : ""),
                    }),
                  onError: (e) => toast.show({ message: errorText(e) }),
                },
              )
            }
          >
            {OVERRIDE_LABELS[v]}
          </Menu.RadioItem>
        ))}
      </Menu.Content>
    </Menu>
  );
}

export function WithdrawButton({
  expanded,
  onClick,
  ref,
}: {
  expanded: boolean;
  onClick: () => void;
  ref?: Ref<HTMLButtonElement>;
}) {
  return (
    <Button ref={ref} {...help("withdraw")} variant="destructive" aria-expanded={expanded} onClick={onClick}>
      Withdraw…
    </Button>
  );
}
