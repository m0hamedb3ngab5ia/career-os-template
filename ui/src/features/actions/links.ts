// What an Action Item's link opens, in words ("Open Greenhouse application"), and a short host/path for context.

const ATS: [RegExp, string][] = [
  [/(^|\.)greenhouse\.io$/, "Greenhouse"],
  [/(^|\.)lever\.co$/, "Lever"],
  [/(^|\.)ashbyhq\.com$/, "Ashby"],
  [/(^|\.)myworkdayjobs\.com$/, "Workday"],
  [/(^|\.)smartrecruiters\.com$/, "SmartRecruiters"],
];

export function isWebLink(link: string | null | undefined): link is string {
  return !!link && /^https?:\/\/\S+$/i.test(link);
}

export function linkLabel(link: string): string {
  let url: URL;
  try {
    url = new URL(link);
  } catch {
    return "Open link";
  }
  const host = url.hostname.toLowerCase().replace(/^www\./, "");
  if (host === "mail.google.com") return "Open Gmail thread";
  if (host.endsWith("linkedin.com")) return url.pathname.startsWith("/in/") ? "Open LinkedIn profile" : "Open on LinkedIn";
  for (const [re, name] of ATS) if (re.test(host)) return `Open ${name} application`;
  return "Open posting";
}

/** "jobs.lever.co/acme/…": host plus the first path segment, ellipsised when there is more. */
export function shortLink(link: string): string {
  try {
    const url = new URL(link);
    const parts = url.pathname.split("/").filter(Boolean);
    const host = url.hostname.replace(/^www\./, "");
    if (!parts.length) return host;
    return `${host}/${parts[0]}${parts.length > 1 || url.search ? "/…" : ""}`;
  } catch {
    return link;
  }
}
