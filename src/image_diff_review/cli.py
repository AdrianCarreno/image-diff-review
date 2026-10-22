"""
Review expected-image fixture changes on a PR branch.

Compares every PNG modified between `merge-base(target, HEAD)` and the new images, pixel-diffs
old vs new with OpenCV, and reports only the images whose changes are NOT explained by a
"Data as of: ..." label being added/changed (commits that landed on the target branch after the PR
branched are ignored). The new images are read from --head (HEAD by default).

Each changed region is classified by OCR:
  * date      - a one-line region whose old or new text reads "Data as of" /
                "Données en date du" (fr_CA).
  * shifted   - the same content, moved by a few pixels (e.g. a column re-centred because a
                neighbouring cell got wider), or a non-numeric label that OCRs identically on both
                sides. Not a content change.
  * other     - anything else, including a module title truncated to make room for the date
                label; an image with any `other` region (or a size change) is reported for review.

Usage (from the repo/worktree root):
    image-diff-review [--target origin/develop] [--head HEAD] [--out DIR]
                      [--path-filter SUBSTR] [--show-date-only]

Needs the `tesseract` binary (brew install tesseract) and git-lfs (PNGs are LFS pointers in git,
so they are read through `git lfs smudge`).
"""

import argparse
import sys
from pathlib import Path

from image_diff_review.analysis import ImageAnalyzer
from image_diff_review.analysis import Verdict
from image_diff_review.git import GitRepo
from image_diff_review.output import FlaggedImage
from image_diff_review.output import OutputDirError
from image_diff_review.output import OverlayWriter
from image_diff_review.output import Report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="image-diff-review",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--target", default="origin/develop", help="Branch the PR targets")
    parser.add_argument("--head", default="HEAD", help="Revision holding the new images")
    parser.add_argument(
        "--out",
        default="image_diff_review_out",
        help="Directory for overlay images of flagged files",
    )
    parser.add_argument(
        "--path-filter", default="", help="Only consider paths containing this substring"
    )
    parser.add_argument(
        "--show-date-only", action="store_true", help="Also list the images dismissed as date-only"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    overlays = OverlayWriter(Path(args.out))
    try:
        removed = overlays.prepare()
    except OutputDirError as error:
        print(error, file=sys.stderr)
        return 2
    if removed:
        print(
            f"removed {len(removed)} overlay(s) from a previous run in {args.out}", file=sys.stderr
        )

    repo = GitRepo()
    base = repo.merge_base(args.target, args.head)
    print(f"merge-base {base[:11]}  ->  {args.head}", file=sys.stderr)

    analyzer = ImageAnalyzer()
    report = Report()
    for status, path in repo.changed_pngs(base, args.head):
        if args.path_filter not in path:
            continue
        if status != "M":  # added/deleted images have no old/new pair to diff
            report.skipped.append((status, path))
            continue
        old, new = repo.load_png(base, path), repo.load_png(args.head, path)
        analysis = analyzer.analyze(old, new)
        if analysis.verdict == Verdict.IDENTICAL:
            report.identical.append(path)
        elif analysis.verdict == Verdict.DATE_ONLY:
            report.date_only.append((path, analysis))
        else:
            overlay = overlays.write(path, old, new, analysis.regions)
            report.flagged.append(FlaggedImage(path, analysis, overlay))

    report.print(show_date_only=args.show_date_only)
    return report.exit_code
