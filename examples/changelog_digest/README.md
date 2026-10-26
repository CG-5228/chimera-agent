# Changelog digest

Point Chimera at any git repository; it inspects recent commit history and diff stats, drafts
structured release notes (`release_notes.md`) citing commit hashes, and distills a 3-line
upgrade summary (`digest.md`). Read-only except for the two markdown outputs.

## Run it

```bash
chimera workflow examples/changelog_digest/digest.yaml -w /path/to/your/repo
cat /path/to/your/repo/release_notes.md
cat /path/to/your/repo/digest.md
```

By default the workflow inspects the last 20 commits (`git log -n 20 --oneline`). Edit the
`task:` prompt in `digest.yaml` to target a tag range (for example `v0.1.0..HEAD`) or a time
window (`--since="7 days ago"`).

## Schedule a weekly release digest

```bash
# Every Friday at 17:00
chimera cron add "weekly changelog digest" "0 17 * * 5" \
  "Inspect git log --since='7 days ago' --oneline with run_shell and write release_notes.md and a 3-line digest.md."
chimera serve
```

## Honest notes

- Uses `run_shell` to run `git log` and `git diff --stat` inside the workspace. It does not push,
  tag, or modify tracked files.
- Commit messages determine how much context the model has; pairing `git log` with `git diff --stat`
  helps the agent ground vague commit titles in the actual files touched.
- Both steps are gated by executable `verify:` checks so empty or unformatted outputs are retried.
