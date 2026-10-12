import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorthPanel } from "@/components/code/WorthPanel";
import { getWorth } from "@/lib/api";
import { renderWithProviders } from "@/test/utils";

vi.mock("@/lib/api", async () => (await import("@/test/code-api-mock")).makeCodeApiMock());

/**
 * "Was it worth it?" is a screen about evidence, so what it says when it has none matters. A failed
 * request used to render exactly like "no runs yet" — a finding, when the truth was that nothing
 * could be asked.
 */
describe("the worth panel's states", () => {
  it("says the request failed instead of reporting no runs", async () => {
    vi.mocked(getWorth).mockRejectedValue(new Error("backend down"));
    renderWithProviders(<WorthPanel workspace="/repo" />);
    expect(await screen.findByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.getByText("Couldn't load this.")).toBeInTheDocument();
  });
});
