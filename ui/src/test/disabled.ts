// REQ-119: a control that cannot be used says why.
/** Disabled controls with no stated reason, by their text. */
export function unexplainedDisabled(root: ParentNode = document): string[] {
  return [...root.querySelectorAll<HTMLElement>("button:disabled, [aria-disabled='true']")]
    .filter((b) => b.getAttribute("aria-busy") !== "true") // pending: the spinner label is the reason
    .filter((b) => !b.title && !b.getAttribute("aria-describedby"))
    .map((b) => b.textContent?.trim() || b.outerHTML.slice(0, 80));
}
