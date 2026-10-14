import { useSyncExternalStore } from "react";

const WIDE = "(min-width: 900px)";
const mq = () => (typeof window.matchMedia === "function" ? window.matchMedia(WIDE) : null);
/** Master-detail needs room (REQ-129): under 900px a job opens as a full page. */
export function useWide(): boolean {
  return useSyncExternalStore(
    (cb) => (mq()?.addEventListener("change", cb), () => mq()?.removeEventListener("change", cb)),
    () => mq()?.matches ?? false,
  );
}
