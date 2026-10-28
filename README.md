# image-diff-review

Review expected-image fixture changes on a PR branch. Pixel-diffs every PNG modified since
`merge-base(target, HEAD)` and reports only the images whose changes are not explained by
expected changes: text matching `--expected-pattern`, by default a "Data as of: ..." label being
added or changed.

## Install

Requires the `tesseract` binary and `git-lfs`:

```sh
brew install tesseract git-lfs
```

### From GitHub

```sh
uv tool install git+https://github.com/AdrianCarreno/image-diff-review
```

Use `git+ssh://git@github.com/AdrianCarreno/image-diff-review` if you authenticate with SSH. Pin a
branch, tag, or commit by appending `@<ref>`, e.g. `...image-diff-review@v1.0.0`.

To update to the latest commit:

```sh
uv tool install --reinstall git+https://github.com/AdrianCarreno/image-diff-review
```

To remove it: `uv tool uninstall image-diff-review`.

### From a local clone

```sh
git clone git@github.com:AdrianCarreno/image-diff-review.git
cd image-diff-review
uv tool install --editable .
```

With `--editable`, code changes apply without reinstalling. A non-editable `uv tool install .`
caches the build and needs `uv tool install --reinstall .` after each change.

## Shell completion

Tab completion for options, with their descriptions, comes from click. Save the completion script
once and load it from your shell config. The script asks `image-diff-review` for completions on
each Tab, so it keeps working across upgrades without being regenerated.

### zsh

```sh
_IMAGE_DIFF_REVIEW_COMPLETE=zsh_source image-diff-review > ~/.image-diff-review-complete.zsh
```

Then add this to `~/.zshrc`, after `compinit` runs (with oh-my-zsh, after
`source $ZSH/oh-my-zsh.sh`):

```sh
source ~/.image-diff-review-complete.zsh
```

### bash

Needs bash 4.4 or newer. macOS ships bash 3.2, so install a newer one first with `brew install bash`.

```sh
_IMAGE_DIFF_REVIEW_COMPLETE=bash_source image-diff-review > ~/.image-diff-review-complete.bash
echo 'source ~/.image-diff-review-complete.bash' >> ~/.bashrc
```

### fish

```sh
_IMAGE_DIFF_REVIEW_COMPLETE=fish_source image-diff-review > ~/.config/fish/completions/image-diff-review.fish
```

Open a new shell (or `source` your config), then type `image-diff-review --` and press Tab.

## Usage

Run from the root of the repo (or worktree) under review:

```sh
image-diff-review [--target origin/develop] [--head HEAD] [--out DIR] [--path-filter SUBSTR] [--expected-pattern REGEX] [--max-ocr-errors N] [--show-expected-only] [--side-by-side]
```

OCR misreads very small text (e.g. "Data as of" as "Dats ss of"), which makes expected changes
look unexpected. `--max-ocr-errors N` lets matched text differ from `--expected-pattern` by up to
`N` inserted, deleted, or substituted characters. `1` is usually enough; higher values start
matching unrelated text and hide real changes.

Each flagged image gets a `<path>.diff.png` in `--out`. By default it is a difference image: new
minus old ink (darkness), fully saturated so even tiny changes stand out: green where the new
image is darker (content added), black where unchanged, red where it is lighter (content
removed). `--side-by-side` saves old | new next
to each other instead, with every changed region boxed red on the old side and green on the new
side.

The `--out` folder (default `image_diff_review_out`) gets a
`.gitignore` containing `*` so it never shows up in `git status`. Overlays from a previous run
(`*.diff.png`) are deleted at startup; if the folder holds anything else, the tool lists it and
exits without deleting anything.

Exit code: `0` when nothing needs review, `1` when at least one image is flagged, `2` on bad `--out`.
See `image-diff-review --help` for the full description.

## Layout

| Module | Contents |
| --- | --- |
| `cli.py` | Argument parsing and the `main` entry point |
| `git.py` | `GitRepo`: merge-base, changed PNGs, LFS-aware image loading |
| `analysis.py` | `ImageDiffer`, `RegionClassifier`, `ImageAnalyzer`, and the `Region` / `Analysis` results |
| `output.py` | `OverlayWriter` (side-by-side diff images) and `Report` (summary printing) |
