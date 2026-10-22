# AGENTS.md

## Versioning

People install this tool from GitHub with `uv tool install git+...`, and the version in
`pyproject.toml` is how they tell builds apart (`uv tool list`). Every commit that changes what
the installed `image-diff-review` command does carries a version bump in the same commit:

| Change | Bump |
| --- | --- |
| Removed or renamed flag, changed default, exit code, or output format | `major` |
| New flag or new behavior that existing invocations don't notice | `minor` |
| Bug fix, or internal change to the code under `src/` with no visible effect | `patch` |

Bump with `uv version --bump <major|minor|patch>`, which updates `pyproject.toml` and `uv.lock`
together. Commits touching only the README, CI, or lint config keep the current version.
