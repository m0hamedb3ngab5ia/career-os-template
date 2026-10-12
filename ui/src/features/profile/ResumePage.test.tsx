import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axeViolations } from "../../test/axe";
import { mockApi, renderRoutes } from "../../test/mockApi";
import { ResumePage } from "./ResumePage";

const routes = [{ path: "/profile/resumes/:rid", element: <ResumePage /> }];
const META = { rid: "cv", name: "cv.pdf", type: "master", category: null, versions: [
  { n: 1, author: "user", source: "upload", at: "2026-09-01T10:00:00", label: "Original" },
  { n: 2, author: "ai", source: "review-edit", at: "2026-10-01T10:00:00", label: "Feedback applied" },
] };

describe("ResumePage", () => {
  it("shows the name, View PDF and versions newest first", async () => {
    mockApi({ "GET /api/profile/resumes/cv": META, "GET /api/profile/resumes/cv/feedback": { review: null, items: [] } });
    const { container } = renderRoutes(routes, "/profile/resumes/cv");
    expect(await screen.findByRole("heading", { name: "cv.pdf" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View PDF" })).toHaveAttribute("href", "/api/profile/resumes/cv/file");
    const v = screen.getAllByText(/^\d\d · /);
    expect(v.map((e) => e.textContent)).toEqual(["02 · Feedback applied", "01 · Original"]);  // current on top
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Used for tailored résumés");
    expect(items[1]).not.toHaveTextContent("Used for tailored résumés");
    expect(screen.getByRole("link", { name: "Download 01 · Original" }))
      .toHaveAttribute("href", "/api/profile/resumes/cv/file?v=1&download=true");
    expect(screen.getByRole("link", { name: "Download 02 · Feedback applied" })).toHaveAttribute("download");
    expect(await axeViolations(container)).toEqual([]);
  });
});
