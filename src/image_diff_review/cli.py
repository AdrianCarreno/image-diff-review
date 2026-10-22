import sys
from pathlib import Path

import click

from image_diff_review.analysis import ImageAnalyzer
from image_diff_review.analysis import Verdict
from image_diff_review.git import GitRepo
from image_diff_review.output import DifferenceRenderer
from image_diff_review.output import FlaggedImage
from image_diff_review.output import OutputDirError
from image_diff_review.output import OverlayWriter
from image_diff_review.output import Report
from image_diff_review.output import SideBySideRenderer


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
@click.option("--show-date-only", is_flag=True, help="Also list the images dismissed as date-only")
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
    show_date_only: bool,
    side_by_side: bool,
) -> None:
    """Review expected-image fixture changes on a PR branch.

    Compares every PNG modified between `merge-base(target, HEAD)` and the new images, pixel-diffs
    old vs new with OpenCV, and reports only the images whose changes are NOT explained by a
    "Data as of: ..." label being added/changed (commits that landed on the target branch after the
    PR branched are ignored). The new images are read from --head. Run it from the repo/worktree
    root.

    \b
    Each changed region is classified by OCR:
      * date      - a one-line region whose old or new text reads "Data as of" /
                    "Données en date du" (fr_CA).
      * shifted   - the same content, moved by a few pixels (e.g. a column re-centred because a
                    neighbouring cell got wider), or a non-numeric label that OCRs identically on
                    both sides. Not a content change.
      * other     - anything else, including a module title truncated to make room for the date
                    label; an image with any `other` region (or a size change) is reported for
                    review.

    Needs the `tesseract` binary (brew install tesseract) and git-lfs (PNGs are LFS pointers in
    git, so they are read through `git lfs smudge`).

    \b
    Each flagged file gets an image in --out:
      * default         - new minus old brightness: red where the new image is darker, black
                          where unchanged, green where it is brighter. Boxes: yellow = needs
                          review, gray = dismissed.
      * --side-by-side  - old | new next to each other. Boxes: red = needs review, green =
                          dismissed.

    Exits 0 when nothing needs review, 1 when an image is flagged, and 2 on an unusable --out.
    """
    renderer = SideBySideRenderer() if side_by_side else DifferenceRenderer()
    ctx.exit(run(target, head, OverlayWriter(out, renderer), path_filter, show_date_only))


def run(
    target: str, head: str, overlays: OverlayWriter, path_filter: str, show_date_only: bool
) -> int:
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

    analyzer = ImageAnalyzer()
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
        elif analysis.verdict == Verdict.DATE_ONLY:
            report.date_only.append((path, analysis))
        else:
            overlay = overlays.write(path, old, new, analysis.regions)
            report.flagged.append(FlaggedImage(path, analysis, overlay))

    report.print(show_date_only=show_date_only)
    return report.exit_code
