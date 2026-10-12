import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/shell/AppShell";
import { AgentProvider, useAgent, type AgentState } from "@/lib/agent-context";
import { useLayout } from "@/lib/layout/context";
import type { ToolEvent } from "@/lib/types";
import { renderWithProviders } from "@/test/utils";

vi.mock("@/components/VersionBadge", () => ({ VersionBadge: () => null }));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getApprovals: vi.fn(async () => []),
}));

/**
 * The Code screen's right column describes the agent's turn. Before there is one it was a stack of
 * empty panels taking a quarter of the window, so it now stands aside until there is something to
 * watch — and a tab on its edge still opens it on demand.
 */
let publish: AgentState["publish"] = () => {};
let regionVisible = true;
let dispatch: ReturnType<typeof useLayout>["dispatch"] = () => false;

function Shell() {
  publish = useAgent().publish;
  const layout = useLayout();
  regionVisible = layout.layout.regions.right.visible;
  dispatch = layout.dispatch;
  return (
    <AppShell
      viewKey="code"
      viewLabel="Code"
      rail={<nav aria-label="rail">rail</nav>}
      inspector={<aside aria-label="activity">tools</aside>}
      inspectorFollowsAgent
    >
      <p>conversation</p>
    </AppShell>
  );
}

function mount() {
  return renderWithProviders(
    <AgentProvider>
      <Shell />
    </AgentProvider>,
  );
}

const panel = () => screen.queryByRole("complementary", { name: "activity" });
const aTool = { name: "read_file" } as unknown as ToolEvent;

describe("the right panel follows the agent's turn", () => {
  beforeEach(() => localStorage.clear());

  it("stands aside while nothing has run, leaving a tab that opens it", async () => {
    mount();
    expect(panel()).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Show the right panel" }));
    expect(panel()).toBeInTheDocument();
    // A peek, not a change of layout: the region the person chose to show stays chosen.
    expect(regionVisible).toBe(true);
  });

  it("appears when a turn starts, and stays for a failed turn's tool calls", () => {
    mount();
    act(() => publish({ status: "thinking", busy: true }));
    expect(panel()).toBeInTheDocument();

    // A failure publishes idle but keeps what ran — the moment someone wants to see it.
    act(() => publish({ status: "idle", busy: false, tools: [aTool] }));
    expect(panel()).toBeInTheDocument();
  });

  it("stands aside again once the conversation is cleared", () => {
    mount();
    act(() => publish({ status: "done", tools: [aTool] }));
    expect(panel()).toBeInTheDocument();
    act(() => publish({ status: "idle", tools: [] }));
    expect(panel()).not.toBeInTheDocument();
  });

  it("stays hidden during a turn when the person hid the region, and its tab shows it for good", async () => {
    mount();
    act(() => {
      dispatch({ type: "set-region", region: "right", visible: false });
    });
    act(() => publish({ status: "thinking", busy: true }));
    expect(panel()).not.toBeInTheDocument();

    // The person's choice is the layout's, so this tab changes the layout rather than peeking.
    await userEvent.click(screen.getByRole("button", { name: "Show the right panel" }));
    expect(panel()).toBeInTheDocument();
    expect(regionVisible).toBe(true);
  });
});
