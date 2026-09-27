import { describe, expect, it } from "vitest";
import { isWebLink, linkLabel, shortLink } from "./links";

describe("links", () => {
  it("names what the link opens", () => {
    expect(linkLabel("https://boards.greenhouse.io/acme/jobs/1")).toBe("Open Greenhouse application");
    expect(linkLabel("https://jobs.lever.co/acme/1")).toBe("Open Lever application");
    expect(linkLabel("https://jobs.ashbyhq.com/acme")).toBe("Open Ashby application");
    expect(linkLabel("https://mail.google.com/mail/u/0/#inbox/abc")).toBe("Open Gmail thread");
    expect(linkLabel("https://www.linkedin.com/in/example")).toBe("Open LinkedIn profile");
    expect(linkLabel("https://careers.example.com/1")).toBe("Open posting");
  });

  it("shortens to host and first segment", () => {
    expect(shortLink("https://jobs.lever.co/acme/1")).toBe("jobs.lever.co/acme/…");
    expect(shortLink("https://example.com/")).toBe("example.com");
    expect(shortLink("https://www.example.com/jobs")).toBe("example.com/jobs");
  });

  it("only http(s) counts as a web link", () => {
    expect(isWebLink("https://a.b/c")).toBe(true);
    expect(isWebLink("javascript:alert(1)")).toBe(false);
    expect(isWebLink("profile/master.yaml")).toBe(false);
    expect(isWebLink("")).toBe(false);
  });
});
