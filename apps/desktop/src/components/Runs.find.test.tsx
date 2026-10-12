import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Runs } from "@/components/Runs";
import { getPausedRuns, getRuns } from "@/lib/api";
import { attempt, receipt } from "@/test/code-api-mock";
import { renderWithProviders } from "@/test/utils";

vi.mock("@/lib/api", async () => (await import("@/test/code-api-mock")).makeCodeApiMock());

/**
 * Work › Runs only grew: every run, every attempt, drawn at once, with no way to look for one. These
 * pin the redesign: a filter by outcome with counts, a search over the task, the earlier attempts
 * folded under the one that decided the run, and twenty runs before "show older".
 */
function mount(runs: ReturnType<typeof receipt>[]) {
  vi.mocked(getRuns).mockResolvedValue(runs);
  vi.mocked(getPausedRuns).mockResolvedValue([]);
  return renderWithProviders(<Runs />);
}

const titles = () => screen.getAllByRole("heading").map((h) => h.textContent ?? "");

describe("finding a run", () => {
  beforeEach(() => vi.clearAllMocks());

  it("filters by outcome, and each filter says how many it holds", async () => {
    const user = userEvent.setup();
    mount([
      receipt({ task: "fix the loader", success: true }),
      receipt({ task: "migrate the viewer", success: false }),
      receipt({ task: "translate the schedule", success: true }),
    ]);
    const failed = await screen.findByRole("button", { name: "Failed 1" });
    expect(screen.getByRole("button", { name: "All 3" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Passed 2" })).toBeInTheDocument();

    await user.click(failed);
    expect(failed).toHaveAttribute("aria-pressed", "true");
    expect(titles()).toContain("migrate the viewer");
    expect(titles()).not.toContain("fix the loader");
  });

  it("searches the task text, and says so when nothing matches", async () => {
    const user = userEvent.setup();
    mount([receipt({ task: "fix the loader" }), receipt({ task: "migrate the viewer" })]);
    await user.type(await screen.findByRole("searchbox", { name: "Search by task" }), "VIEWER");
    expect(titles()).toEqual(expect.arrayContaining(["migrate the viewer"]));
    expect(titles()).not.toContain("fix the loader");

    await user.clear(screen.getByRole("searchbox", { name: "Search by task" }));
    await user.type(screen.getByRole("searchbox", { name: "Search by task" }), "nothing like this");
    expect(screen.getByText("No run matches this search.")).toBeInTheDocument();
  });

  it("folds the earlier attempts under the one that decided the run", async () => {
    mount([
      receipt({
        task: "retried twice",
        attempts: [attempt({ index: 1 }), attempt({ index: 2 }), attempt({ index: 3 })],
      }),
    ]);
    const fold = await screen.findByText("2 earlier attempt(s)");
    const details = fold.closest("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(within(details).getByText("Attempt 1")).toBeInTheDocument();
    // The deciding attempt stays outside the fold.
    const last = screen.getAllByText("Attempt 3");
    expect(last.some((el) => !details.contains(el))).toBe(true);
  });

  it("draws twenty runs, then offers the rest", async () => {
    const user = userEvent.setup();
    mount(Array.from({ length: 23 }, (_, i) => receipt({ task: `task ${i}`, ts: `2026-10-11T12:${String(i).padStart(2, "0")}:00Z` })));
    const more = await screen.findByRole("button", { name: "Show older runs (3 more)" });
    expect(titles().filter((t) => t.startsWith("task "))).toHaveLength(20);
    await user.click(more);
    expect(titles().filter((t) => t.startsWith("task "))).toHaveLength(23);
    expect(screen.queryByRole("button", { name: /Show older runs/ })).not.toBeInTheDocument();
  });
});
