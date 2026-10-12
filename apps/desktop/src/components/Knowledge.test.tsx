import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Knowledge, knowledgeTab, type KnowledgeTab } from "@/components/Knowledge";
import { I18nProvider } from "@/lib/i18n";

const getMemoryProfile = vi.fn();
const getMemory = vi.fn();
const getMemoryLayers = vi.fn();
const getSkills = vi.fn();

vi.mock("@/lib/api", () => ({
  getMemoryProfile: (...a: unknown[]) => getMemoryProfile(...a),
  getMemory: (...a: unknown[]) => getMemory(...a),
  getMemoryLayers: (...a: unknown[]) => getMemoryLayers(...a),
  addMemory: vi.fn(),
  deleteMemory: vi.fn(),
  getSkills: (...a: unknown[]) => getSkills(...a),
  approveSkill: vi.fn(),
  retireSkill: vi.fn(),
}));

function renderKnowledge(props: { tab?: KnowledgeTab; onTabChange?: (tab: KnowledgeTab) => void } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <I18nProvider>
      <QueryClientProvider client={qc}>
        <Knowledge {...props} />
      </QueryClientProvider>
    </I18nProvider>,
  );
}

afterEach(() => {
  getMemoryProfile.mockReset();
  getMemory.mockReset();
  getMemoryLayers.mockReset();
  getSkills.mockReset();
});

function stubEmpty() {
  getMemory.mockResolvedValue([]);
  getMemoryLayers.mockResolvedValue({ layers: [], total: 0 });
  getSkills.mockResolvedValue({ stats: [], retirement_candidates: [], cards_read: true });
  getMemoryProfile.mockResolvedValue({ profile: "", persona: [] });
}

describe("Knowledge", () => {
  it("groups memory, profile and skills under one destination", () => {
    stubEmpty();
    renderKnowledge();
    // Three rail icons collapsed into three tabs. Fifteen icons is past the point where anyone
    // reads them; they become positions to memorise.
    expect(screen.getByRole("tab", { name: /memory/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /profile/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /skills/i })).toBeInTheDocument();
  });

  it("shows exactly one page heading, not one per nested screen", () => {
    stubEmpty();
    renderKnowledge();
    // Memory and Skills each render their own <h1> when standalone. Embedded, they must not — two
    // headings for one page reads fine visually and sounds wrong to a screen reader.
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("reads back the profile the agent learned", async () => {
    stubEmpty();
    getMemoryProfile.mockResolvedValue({
      profile: "Prefers concise answers. Works in Python and TypeScript.",
      persona: [
        { id: "p1", content: "Based in Brazil", kind: "persona", source: "chat", provenance: "clean" },
      ],
    });
    const user = userEvent.setup();
    renderKnowledge();

    await user.click(screen.getByRole("tab", { name: /profile/i }));

    // The point of this screen: Memory could already WRITE persona facts, and nothing could read
    // them back — you fed a picture of yourself that you were never shown.
    expect(await screen.findByText(/Prefers concise answers/)).toBeInTheDocument();
    expect(screen.getByText("Based in Brazil")).toBeInTheDocument();
    expect(getMemoryProfile).toHaveBeenCalled();
  });

  it("says plainly when no facts are stored yet", async () => {
    stubEmpty();
    const user = userEvent.setup();
    renderKnowledge();
    await user.click(screen.getByRole("tab", { name: /profile/i }));
    expect(await screen.findByText(/No facts stored yet/i)).toBeInTheDocument();
  });

  it("marks a fact whose provenance is not clean", async () => {
    stubEmpty();
    getMemoryProfile.mockResolvedValue({
      profile: "x",
      persona: [
        { id: "p1", content: "Untrusted claim", kind: "persona", source: "web", provenance: "tainted" },
      ],
    });
    const user = userEvent.setup();
    renderKnowledge();
    await user.click(screen.getByRole("tab", { name: /profile/i }));
    // A fact the agent picked up from a page it read is not the same as one you told it, and the
    // difference should be visible rather than inferred. It is said with Memory's own word for it
    // ("unverified"), not the store's id ("tainted"), which was English in every language; an
    // unknown source is still shown as sent.
    expect(await screen.findByText("unverified")).toBeInTheDocument();
    expect(screen.getByText("web")).toBeInTheDocument();
    expect(screen.queryByText(/tainted/)).not.toBeInTheDocument();
  });
});

describe("Knowledge's tabs have addresses", () => {
  it("shows the tab the route names and reports a change instead of keeping it", async () => {
    stubEmpty();
    getMemoryProfile.mockResolvedValue({ profile: "", persona: [] });
    const onTabChange = vi.fn();
    const user = userEvent.setup();
    renderKnowledge({ tab: "profile", onTabChange });
    expect(screen.getByRole("tab", { name: /profile/i })).toHaveAttribute("aria-selected", "true");
    await user.click(screen.getByRole("tab", { name: /skills/i }));
    expect(onTabChange).toHaveBeenCalledWith("skills");
  });

  it("reads an unknown tab as the first one, so a stale link lands on the screen", () => {
    expect(knowledgeTab("skills")).toBe("skills");
    expect(knowledgeTab("nonsense")).toBe("memory");
    expect(knowledgeTab(null)).toBe("memory");
  });
});
