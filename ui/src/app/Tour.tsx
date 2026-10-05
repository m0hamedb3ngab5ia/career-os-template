import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { apiFetch, apiSend } from "../api/client";
import { Button } from "../kit/Button";
import { Dialog } from "../kit/Dialog";
import { useToast } from "../kit/Toast";
import styles from "./Tour.module.css";

interface UiState {
  tour_done: boolean;
}

/** One step per main nav item + Start pipeline (REQ-121, ≤8). `selector` points at a page control when it is on
 *  screen (the Jobs page), else the step points at its nav item. */
export const TOUR_STEPS: { to: string; title: string; text: string; selector?: string }[] = [
  { to: "/", title: "Today", text: "What needs you now: tasks, running batches and your next step." },
  { to: "/jobs", title: "Jobs", text: "Every job found. Tick the ones you want to work on." },
  { to: "/jobs", selector: '[data-tour="start-pipeline"]', title: "Start pipeline", text: "Tick jobs, then Start pipeline to choose how far each one goes: prepare, fill or submit." },
  { to: "/pipeline", title: "Pipeline", text: "Where each application stands, from found to offer." },
  { to: "/inbox", title: "Inbox", text: "Replies from companies, sorted so you see what matters first." },
  { to: "/profile", title: "Profile", text: "Your résumés, saved answers and writing samples, plus the checklist to finish before applying." },
  { to: "/settings", title: "Settings", text: "Searches, limits and schedule. “How to use” here replays this tour." },
];

const RESTART = "careeros:tour";

/** Restart the tour from step 1 (Settings › How to use). */
export function startTour() {
  window.dispatchEvent(new Event(RESTART));
}

function target(to: string, selector?: string): HTMLElement | null {
  return (selector && document.querySelector<HTMLElement>(selector)) || document.querySelector<HTMLElement>(`nav[aria-label="Sections"] a[href="${to}"]`);
}

/** Ring drawn above the backdrop around the nav item the current step points at. */
function Ring({ to, selector }: { to: string; selector?: string }) {
  const [rect, setRect] = useState<DOMRect | null>(null);
  useLayoutEffect(() => {
    const update = () => setRect(target(to, selector)?.getBoundingClientRect() ?? null);
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, [to, selector]);
  if (!rect) return null;
  return createPortal(
    <div
      className={styles.ring}
      aria-hidden="true"
      data-testid="tour-ring"
      style={{ top: rect.top - 4, left: rect.left - 4, width: rect.width + 8, height: rect.height + 8 }}
    />,
    document.body,
  );
}

/**
 * First-run tour (REQ-121): shows once per install while data/ui_state.json says tour_done is false. Finish,
 * Skip, Close or Escape marks it done; focus goes back to where it was (the Dialog returns it).
 */
export function Tour() {
  const qc = useQueryClient();
  const toast = useToast();
  const { data } = useQuery({
    queryKey: ["ui-state"],
    queryFn: () => apiFetch<UiState>("/api/ui-state"),
    staleTime: Infinity,
    retry: false,
  });
  const save = useMutation({
    mutationFn: (s: UiState) => apiSend<UiState>("PUT", "/api/ui-state", s),
    onSuccess: (s) => qc.setQueryData(["ui-state"], s),
    onError: () => toast.show({ message: "Couldn’t save tour progress. It may show again next time." }),
  });
  const [step, setStep] = useState<number | null>(null);
  const shown = useRef(false);
  const nextRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (data && !data.tour_done && !shown.current) {
      shown.current = true;
      setStep(0);
    }
  }, [data]);

  useEffect(() => {
    const restart = () => setStep(0);
    window.addEventListener(RESTART, restart);
    return () => window.removeEventListener(RESTART, restart);
  }, []);

  if (step === null) return null;
  const s = TOUR_STEPS[step]!;
  const last = step === TOUR_STEPS.length - 1;
  const end = () => {
    setStep(null);
    if (!data?.tour_done) save.mutate({ tour_done: true });
  };

  return (
    <>
      <Ring to={s.to} selector={s.selector} />
      <Dialog
        open
        onClose={end}
        title={s.title}
        initialFocusRef={nextRef}
        className={styles.card}
        footer={
          <>
            <span className={styles.count}>
              Step {step + 1} of {TOUR_STEPS.length}
            </span>
            <Button onClick={end}>
              Skip tour
            </Button>
            {step > 0 ? (
              <Button
                onClick={() => {
                  // Back unmounts itself on step 1; keep focus inside the dialog.
                  nextRef.current?.focus();
                  setStep(step - 1);
                }}
              >
                Back
              </Button>
            ) : null}
            <Button ref={nextRef} variant="primary" onClick={last ? end : () => setStep(step + 1)}>
              {last ? "Done" : "Next"}
            </Button>
          </>
        }
      >
        <p className={styles.text} aria-live="polite" aria-atomic="true">
          <span className="sr-only">Step {step + 1} of {TOUR_STEPS.length}: </span>
          {s.text}
        </p>
      </Dialog>
    </>
  );
}
