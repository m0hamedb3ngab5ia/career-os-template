import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ListInput } from "./fields";

describe("ListInput", () => {
  it("renders items that don't round-trip through comma splitting without looping", () => {
    render(<ListInput label="Skills" value={["Python, SQL", "", "Go"]} locked={false} onChange={() => {}} />);
    expect(screen.getByDisplayValue("Python, SQL, , Go")).toBeTruthy();
  });
});
