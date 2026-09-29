import { useState } from "react";
import { Button } from "../../kit/Button";
import { Chip } from "../../kit/chips";
import { Details } from "../../kit/Details";
import { useToast } from "../../kit/Toast";
import { errorText, useApplicationTab, useOpenApplication, type ApplicationTab } from "./api";
import styles from "./JobDetail.module.css";

// The browser behind the fill is not reachable (refused up front, or the detached fill could not attach).
const CHROME_DOWN = /^chrome not connected|connect_over_cdp|ECONNREFUSED/i;
const CONNECT = "Connect Chrome extension, then retry";

// Offered once there is something to fill or reopen: saved answers, a recorded tab, a failed fill, or a job at
// review/apply (the fill plans first when it has no answers yet).
function offered(tab: ApplicationTab | undefined, stage: string): tab is ApplicationTab {
  return !!tab && (tab.can_fill || tab.tab !== "none" || !!tab.fill_error || stage === "review" || stage === "apply");
}

/** Fill / Open / Refill / Retry the staged application, beside the pipeline's next-step button. */
export function FillApplicationButton({ jobId, stage }: { jobId: string; stage: string }) {
  const tab = useApplicationTab(jobId).data;
  const openApp = useOpenApplication(jobId);
  const toast = useToast();
  // Chrome (paths.apply_cdp) didn't answer: a plain connect-and-retry state; the recorded tab is kept for the retry.
  const [notConnected, setNotConnected] = useState<{ refill?: boolean } | null>(null);
  if (!offered(tab, stage)) return null;
  const live = tab.tab === "open";
  const label = live ? "Open application" : tab.fill_error ? "Retry fill" : tab.tab === "needs_refill" ? "Refill application" : "Fill application";
  const left = tab.fields_left?.length ?? 0;
  function onOpen(refill?: boolean) {
    openApp.mutate(refill ? { refill: true } : undefined, {
      onSuccess: (r) => {
        setNotConnected(null);
        toast.show({
          message: r.action === "focused" ? "Switched to the filled tab" : "Filling the form in a new browser tab; it stops before submit",
        });
      },
      onError: (e) => {
        if (CHROME_DOWN.test(errorText(e))) setNotConnected({ refill });
        else toast.show({ message: errorText(e) });
      },
    });
  }
  if (notConnected) {
    return (
      <>
        <span className={styles.alert} role="status">
          {CONNECT}
        </span>
        <Button variant="primary" disabled={openApp.isPending} onClick={() => onOpen(notConnected.refill)}>
          Retry
        </Button>
      </>
    );
  }
  return (
    <>
      <Button
        variant={live ? "primary" : undefined}
        disabled={openApp.isPending}
        title={live ? "Focus the tab with the filled form" : "Open a visible tab and fill the form from your saved answers (stops before submit)"}
        onClick={() => onOpen()}
      >
        {label}
      </Button>
      {live ? (
        <Button disabled={openApp.isPending} title="Fill the form again in a new tab from your saved answers" onClick={() => onOpen(true)}>
          Refill
        </Button>
      ) : null}
      {left > 0 && !tab.fill_error ? <Chip tone="orange">{left} field{left === 1 ? "" : "s"} left for you</Chip> : null}
      {tab.fill_error ? <Chip tone="red">Fill failed</Chip> : tab.tab !== "none" ? (
        <Chip tone={live ? "green" : "orange"}>{live ? "Tab open" : "Needs refill"}</Chip>
      ) : null}
    </>
  );
}

/** The last fill's error in plain words, the raw output behind a disclosure. */
export function FillApplicationError({ jobId, stage }: { jobId: string; stage: string }) {
  const tab = useApplicationTab(jobId).data;
  if (!offered(tab, stage) || !tab.fill_error) return null;
  return (
    <div>
      <p className={styles.alert}>{CHROME_DOWN.test(tab.fill_error) ? CONNECT : `Filling the application failed: ${tab.fill_error}`}</p>
      {tab.fill_log ? (
        <Details summary="Fill output">
          <pre>{tab.fill_log}</pre>
        </Details>
      ) : null}
    </div>
  );
}
