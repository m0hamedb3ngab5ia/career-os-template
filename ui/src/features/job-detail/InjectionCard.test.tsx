import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi } from "../../test/apiMock";
import { InjectionCard } from "./InjectionCard";
import { renderWithProviders } from "./testUtils";

afterEach(() => vi.unstubAllGlobals());

describe("InjectionCard (REQ-109)", () => {
  it("I checked it POSTs the clear; a refusal is announced as an alert", async () => {
    const api = mockApi({
      "POST /api/jobs/nw01/injection/clear": { status: 409, body: { detail: "job is not flagged as a possible injection" } },
    });
    renderWithProviders(<InjectionCard jobId="nw01" reasons="hidden text" />);
    expect(screen.getByText(/Flagged because: hidden text/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "I checked it" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("job is not flagged as a possible injection");
    expect(api.callsTo("POST /api/jobs/nw01/injection/clear")).toHaveLength(1);
  });
});
