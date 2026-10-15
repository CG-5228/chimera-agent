import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TaskConsole } from "@/components/work/TaskConsole";
import { renderWithProviders } from "@/test/utils";

vi.mock("@/lib/api", async () => (await import("@/test/code-api-mock")).makeCodeApiMock());

/**
 * The Task tab, laid out for what it is for: say what to do, choose how, run it. Each mode says what
 * it is for on its own card, Run comes before the options that tune it, and the options are folded
 * with the current setting on their summary line.
 */
function render() {
  renderWithProviders(<TaskConsole workspace="/repo" onOpenCode={() => {}} />);
}

describe("the task tab's layout", () => {
  it("puts a sentence on every mode, not only on the selected one", () => {
    render();
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(4);
    for (const radio of radios) {
      // The description is wired to the radio, so a screen reader hears what it is for.
      const id = radio.getAttribute("aria-describedby") ?? "";
      expect(document.getElementById(id)?.textContent?.length, radio.getAttribute("aria-label") ?? "").toBeGreaterThan(20);
    }
  });

  it("offers Run before the options that tune the run", () => {
    render();
    const run = screen.getByRole("button", { name: /^run$/i });
    const options = screen.getByText("Options");
    expect(run.compareDocumentPosition(options) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("folds the options, and the summary says what is currently set", async () => {
    render();
    const summary = screen.getByText("Options").closest("summary") as HTMLElement;
    const details = summary.closest("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(summary).toHaveTextContent(/up to 3 attempts/);
    // Folded, not removed: the controls are all still there.
    expect(screen.getByLabelText(/max\.? attempts/i)).toBeInTheDocument();

    const attempts = screen.getByLabelText(/max\.? attempts/i);
    // One change event from 3 to 5: typing it would pass through "" (which the field reads as 1).
    fireEvent.change(attempts, { target: { value: "5" } });
    expect(summary).toHaveTextContent(/up to 5 attempts/);
  });
});
