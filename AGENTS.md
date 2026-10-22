# AGENTS.md

## Pull requests and versioning

Every change lands on `main` through a squash-merged PR, and the PR title becomes the commit
message. On each merge, python-semantic-release (`.github/workflows/release.yaml`) reads that
title, bumps the version in `pyproject.toml` and `uv.lock`, updates `CHANGELOG.md`, and tags and
publishes the GitHub release. The version belongs to that workflow; keep it as is in your PRs.

PR titles follow Conventional Commits (CI checks this), because the type decides the bump:

| Change to the installed `image-diff-review` command | PR title | Bump |
| --- | --- | --- |
| Removed or renamed flag, changed default, exit code, or output format | `feat!: ...` / `fix!: ...` | major |
| New flag or new behavior that existing invocations don't notice | `feat: ...` | minor |
| Bug fix, or a speed-up users notice | `fix: ...` / `perf: ...` | patch |
| Internal change under `src/` with no visible effect | `refactor: ...` | none |
| README, CI, lint config, tooling | `docs: ...` / `ci: ...` / `chore: ...` | none |

The title is what users read in the changelog, so describe the change in user-facing terms.
Each merge adds a `chore(release)` commit to `main`; pull before branching for the next change.
