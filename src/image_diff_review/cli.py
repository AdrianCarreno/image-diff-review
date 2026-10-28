# The analysis and output modules import OpenCV, whose first load after an install can take ~20s
# on macOS. They are imported inside the functions that need them, so --help, option errors and
# shell completion never pay that cost.
from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click

from image_diff_review.patterns import EXPECTED_CHANGE_PATTERN
from image_diff_review.patterns import compile_expected_change_re

if TYPE_CHECKING:
    from image_diff_review.analysis import ImageAnalyzer
    from image_diff_review.output import OverlayWriter


def validate_expected_pattern(ctx: click.Context, param: click.Parameter, value: str) -> str:
    import regex

    try:
        compile_expected_change_re(value)
    except regex.error as error:
        raise click.BadParameter(f"not a valid regular expression: {error}") from error
    return value


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--target", default="origin/develop", show_default=True, help="Branch the PR targets")
@click.option("--head", default="HEAD", show_default=True, help="Revision holding the new images")
@click.option(
    "--out",
    default="image_diff_review_out",
    show_default=True,
    type=click.Path(path_type=Path),
    help="Directory for overlay images of flagged files",
)
@click.option("--path-filter", default="", help="Only consider paths containing this substring")
@click.option(
    "--expected-pattern",
    default=EXPECTED_CHANGE_PATTERN,
    show_default=True,
    callback=validate_expected_pattern,
    help="Regular expression (case-insensitive) that marks OCRed text as an expected change",
)
@click.option(
    "--max-ocr-errors",
    default=0,
    show_default=True,
    type=click.IntRange(min=0),
    help="Characters OCR may misread (inserted, deleted, or substituted) while text still matches "
    "--expected-pattern; helps with tiny text. 1 is usually enough; higher values start "
    "matching unrelated text and hiding real changes",
)
@click.option(
    "--show-expected-only",
    is_flag=True,
    help="Also list the images dismissed as having only expected changes",
)
@click.option(
    "--side-by-side",
    is_flag=True,
    help="Save flagged images as old | new side by side instead of as a difference image",
)
@click.pass_context
def main(
    ctx: click.Context,
    target: str,
    head: str,
    out: Path,
    path_filter: str,
    expected_pattern: str,
    max_ocr_errors: int,
    show_expected_only: bool,
    side_by_side: bool,
) -> None:
    """Review expected-image fixture changes on a PR branch.

    Compares every PNG modified between `merge-base(target, HEAD)` and the new images, pixel-diffs
    old vs new with OpenCV, and reports only the images whose changes are NOT explained by
    expected changes: text matching --expected-pattern, by default a "Data as of: ..." label being
    added/changed (commits that landed on the target branch after the PR branched are ignored).
    The new images are read from --head. Run it from the repo/worktree root.

    \b
    Each changed region is classified by OCR:
      * expected  - a one-line region whose old or new text matches --expected-pattern (by
                    default "Data as of" / "Données en date du" (fr_CA)).
      * shifted   - the same content, moved by a few pixels (e.g. a column re-centred because a
                    neighbouring cell got wider), or a non-numeric label that OCRs identically on
                    both sides. Not a content change.
      * other     - anything else, including a module title truncated to make room for the expected
                    label; an image with any `other` region (or a size change) is reported for
                    review.

    Needs the `tesseract` binary (brew install tesseract) and git-lfs (PNGs are LFS pointers in
    git, so they are read through `git lfs smudge`).

    \b
    Each flagged file gets an image in --out:
      * default         - new minus old ink, fully saturated: green where the new image is
                          darker (content added), black where unchanged, red where it is
                          lighter (content removed).
      * --side-by-side  - old | new next to each other, every changed region boxed red on the
                          old side and green on the new side.

    Exits 0 when nothing needs review, 1 when an image is flagged, and 2 on an unusable --out.
    """
    from image_diff_review.analysis import ImageAnalyzer
    from image_diff_review.analysis import RegionClassifier
    from image_diff_review.output import DifferenceRenderer
    from image_diff_review.output import OverlayWriter
    from image_diff_review.output import SideBySideRenderer

    renderer = SideBySideRenderer() if side_by_side else DifferenceRenderer()
    analyzer = ImageAnalyzer(
        classifier=RegionClassifier(compile_expected_change_re(expected_pattern, max_ocr_errors))
    )
    overlays = OverlayWriter(out, renderer)
    ctx.exit(run(target, head, analyzer, overlays, path_filter, show_expected_only))


def run(
    target: str,
    head: str,
    analyzer: ImageAnalyzer,
    overlays: OverlayWriter,
    path_filter: str,
    show_expected_only: bool,
) -> int:
    from image_diff_review.analysis import Verdict
    from image_diff_review.git import GitRepo
    from image_diff_review.output import FlaggedImage
    from image_diff_review.output import OutputDirError
    from image_diff_review.output import Report

    try:
        removed = overlays.prepare()
    except OutputDirError as error:
        print(error, file=sys.stderr)
        return 2
    if removed:
        print(
            f"removed {len(removed)} overlay(s) from a previous run in {overlays.out_dir}",
            file=sys.stderr,
        )

    repo = GitRepo()
    base = repo.merge_base(target, head)
    print(f"merge-base {base[:11]}  ->  {head}", file=sys.stderr)

    report = Report()
    for status, path in repo.changed_pngs(base, head):
        if path_filter not in path:
            continue
        if status != "M":  # added/deleted images have no old/new pair to diff
            report.skipped.append((status, path))
            continue
        old, new = repo.load_png(base, path), repo.load_png(head, path)
        analysis = analyzer.analyze(old, new)
        if analysis.verdict == Verdict.IDENTICAL:
            report.identical.append(path)
        elif analysis.verdict == Verdict.EXPECTED_ONLY:
            report.expected_only.append((path, analysis))
        else:
            overlay = overlays.write(path, old, new, analysis.regions)
            report.flagged.append(FlaggedImage(path, analysis, overlay))

    report.print(show_expected_only=show_expected_only)
    return report.exit_code
