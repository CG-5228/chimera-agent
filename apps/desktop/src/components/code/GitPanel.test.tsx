import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GitPanel } from "@/components/code/GitPanel";
import { getGitDiff, getGitStatus, getPullRequestReadiness, gitCommit, gitRevert } from "@/lib/api";
import type { GitFile } from "@/lib/types";
import { gitStatus } from "@/test/code-api-mock";
import { renderWithProviders } from "@/test/utils";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getGitStatus: vi.fn(),
  getGitDiff: vi.fn(),
  gitCommit: vi.fn(),
  gitRevert: vi.fn(),
  getPullRequestReadiness: vi.fn(),
}));

const file = (path: string, over: Partial<GitFile> = {}): GitFile => ({
  path,
  staged: false,
  untracked: false,
  x: " ",
  y: "M",
  ...over,
});

/**
 * Trabalho › Git. The panel had no tests at all; these pin what the redesign changed: the discard
 * question is asked on the page rather than in `window.confirm`, every checkbox says which file it
 * puts in the commit, and an empty diff is described as a file's.
 */
describe("the git panel", () => {
  beforeEach(() => {
    vi.mocked(getGitStatus).mockResolvedValue(
      gitStatus({ files: [file("src/a.py"), file("src/b.py"), file("new.txt", { untracked: true, x: "?", y: "?" })] }),
    );
    vi.mocked(getGitDiff).mockResolvedValue({ patch: "" } as Awaited<ReturnType<typeof getGitDiff>>);
    vi.mocked(gitRevert).mockResolvedValue({} as Awaited<ReturnType<typeof gitRevert>>);
    vi.mocked(gitCommit).mockResolvedValue({ ok: true, commit: "abc1234" } as Awaited<ReturnType<typeof gitCommit>>);
    vi.mocked(getPullRequestReadiness).mockResolvedValue(null as never);
  });

  it("names every checkbox after the file it puts in the commit", async () => {
    renderWithProviders(<GitPanel workspace="/repo" />);
    expect(await screen.findByRole("checkbox", { name: "Include src/a.py in the commit" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Include new.txt in the commit" })).toBeChecked();
  });

  it("says how many files the commit takes, and follows the boxes", async () => {
    const user = userEvent.setup();
    renderWithProviders(<GitPanel workspace="/repo" />);
    expect(await screen.findByRole("button", { name: /Commit \(3\)/ })).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Include src/b.py in the commit" }));
    expect(screen.getByRole("button", { name: /Commit \(2\)/ })).toBeInTheDocument();
  });

  it("asks before discarding, on the page, and discards nothing when cancelled", async () => {
    const confirm = vi.spyOn(window, "confirm");
    const user = userEvent.setup();
    renderWithProviders(<GitPanel workspace="/repo" />);

    await user.click(await screen.findByRole("button", { name: /Discard changes/ }));
    const question = screen.getByRole("alertdialog", { name: "Discard changes" });
    expect(question).toHaveTextContent("3 file(s)");
    // The browser's dialog is gone: it cannot say which files and does not look like the app.
    expect(confirm).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(gitRevert).not.toHaveBeenCalled();
    confirm.mockRestore();
  });

  it("discards exactly the selected files once confirmed", async () => {
    const user = userEvent.setup();
    renderWithProviders(<GitPanel workspace="/repo" />);
    await user.click(await screen.findByRole("checkbox", { name: "Include new.txt in the commit" }));
    await user.click(screen.getByRole("button", { name: /Discard changes/ }));

    const question = screen.getByRole("alertdialog", { name: "Discard changes" });
    await user.click(question.querySelector("button:last-of-type") as HTMLButtonElement);
    await waitFor(() => expect(gitRevert).toHaveBeenCalledWith("/repo", ["src/a.py", "src/b.py"]));
  });

  it("describes an empty diff as the file's, not as a run's", async () => {
    const user = userEvent.setup();
    renderWithProviders(<GitPanel workspace="/repo" />);
    await user.click(await screen.findByRole("button", { name: "src/a.py" }));
    expect(await screen.findByText("No differences to show for this file.")).toBeInTheDocument();
    expect(screen.queryByText(/This run changed nothing/)).not.toBeInTheDocument();
  });
});
