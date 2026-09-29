import { Button } from "../../kit/Button";
import { Chip } from "../../kit/chips";
import { Details } from "../../kit/Details";
import { useToast } from "../../kit/Toast";
import { errorText, useApplicationTab, useOpenApplication, type ApplicationTab } from "./api";
import styles from "./JobDetail.module.css";

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
  if (!offered(tab, stage)) return null;
  const live = tab.tab === "open";
  const label = live ? "Open application" : tab.fill_error ? "Retry fill" : tab.tab === "needs_refill" ? "Refill application" : "Fill application";
  function onOpen() {
    openApp.mutate(undefined, {
      onSuccess: (r) =>
        toast.show({
          message: r.action === "focused" ? "Switched to the filled tab" : "Filling the form in a new browser tab; it stops before submit",
        }),
      onError: (e) => toast.show({ message: errorText(e) }),
    });
  }
  return (
    <>
      <Button
        variant={live ? "primary" : undefined}
        disabled={openApp.isPending}
        title={live ? "Focus the tab with the filled form" : "Open a visible tab and fill the form from your saved answers (stops before submit)"}
        onClick={onOpen}
      >
        {label}
      </Button>
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
      <p className={styles.alert}>Filling the application failed: {tab.fill_error}</p>
      {tab.fill_log ? (
        <Details summary="Fill output">
          <pre>{tab.fill_log}</pre>
        </Details>
      ) : null}
    </div>
  );
}
