import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Skills } from "@/components/Skills";
import { getSkills } from "@/lib/api";
import { renderWithProviders } from "@/test/utils";

vi.mock("@/lib/api", () => ({
  getSkills: vi.fn(),
  approveSkill: vi.fn(),
  retireSkill: vi.fn(),
  getSkillLibrary: vi.fn(async () => []),
  getSkillLibraryCard: vi.fn(),
  importSkillLibraryCard: vi.fn(),
  getSkillCatalog: vi.fn(async () => []),
  getSkillBundles: vi.fn(async () => []),
  installSkillBundle: vi.fn(),
  setSkillBundleStatus: vi.fn(),
  uninstallSkillBundle: vi.fn(),
  checkSkillBundleUpdate: vi.fn(),
  getEffectiveSkills: vi.fn(async () => ({ bundles: [], bundle_text: "", cards_read: false, cards: [], cards_k: 0 })),
  // The upload panel sits on the same screen; nothing here presses its buttons.
  importSkill: vi.fn(),
  getSkillBundleText: vi.fn(),
}));

function stat(over: Record<string, unknown> = {}) {
  return {
    name: "chimera-thin-vertical-slice",
    kind: "pattern",
    status: "active",
    provenance: "clean",
    uses: 0,
    successes: 0,
    rate: null,
    ...over,
  };
}

/**
 * The learned-skills rows printed two English literals in every language ("tainted", "retire?"), the
 * second in the red of a failure for what is a suggestion. And the one section that asks something of
 * the person sat second in a stack of five, with nothing above the fold saying it was waiting.
 */
describe("the skills screen in the reader's words", () => {
  beforeEach(() => {
    vi.mocked(getSkills).mockReset();
  });

  it("translates the provenance and the retirement hint instead of printing them raw", async () => {
    vi.mocked(getSkills).mockResolvedValue({
      stats: [stat({ provenance: "tainted" })],
      retirement_candidates: ["chimera-thin-vertical-slice"],
      cards_read: true,
    } as never);
    renderWithProviders(<Skills />);
    expect(await screen.findByText("unverified")).toBeInTheDocument();
    expect(screen.queryByText("tainted")).not.toBeInTheDocument();
    expect(screen.getByText("retire?")).toBeInTheDocument();
  });

  it("says above the fold when a learned skill waits for a decision", async () => {
    const user = userEvent.setup();
    vi.mocked(getSkills).mockResolvedValue({
      stats: [stat({ status: "pending" }), stat({ name: "other", status: "pending" })],
      retirement_candidates: [],
      cards_read: true,
    } as never);
    renderWithProviders(<Skills />);
    expect(await screen.findByText("2 learned skill(s) wait for your decision.")).toBeInTheDocument();
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    await user.click(screen.getByRole("button", { name: "Review" }));
    expect(scroll).toHaveBeenCalled();
  });

  it("links to each of its five sections", async () => {
    vi.mocked(getSkills).mockResolvedValue({ stats: [], retirement_candidates: [], cards_read: true } as never);
    renderWithProviders(<Skills />);
    const nav = await screen.findByRole("navigation", { name: "Sections" });
    expect(nav.querySelectorAll("a")).toHaveLength(5);
    for (const a of Array.from(nav.querySelectorAll("a"))) {
      const target = a.getAttribute("href")?.slice(1) ?? "";
      expect(document.getElementById(target), target).not.toBeNull();
    }
  });
});
