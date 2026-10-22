import re
from dataclasses import dataclass
from dataclasses import field
from enum import StrEnum

import cv2
import numpy as np
import pytesseract

Box = tuple[int, int, int, int]  # x0, y0, x1, y1 inclusive


class RegionKind(StrEnum):
    DATE = "date"
    SHIFTED = "shifted"
    OTHER = "other"


@dataclass(frozen=True)
class Region:
    box: Box
    kind: RegionKind
    note: str

    @property
    def needs_review(self) -> bool:
        return self.kind == RegionKind.OTHER


class Verdict(StrEnum):
    IDENTICAL = "identical"
    DATE_ONLY = "date-only"
    REVIEW = "review"


@dataclass(frozen=True)
class Analysis:
    verdict: Verdict
    regions: list[Region] = field(default_factory=list)
    reason: str = ""

    def __str__(self) -> str:
        return f"{self.verdict}:{self.reason}" if self.reason else str(self.verdict)


class ImageDiffer:
    """Finds the clusters of changed pixels between two same-sized images."""

    # Pixel is "changed" if any channel differs by more than this (absorbs anti-aliasing noise).
    PIXEL_THRESHOLD = 24
    # Changed pixels closer than this are merged into the same region
    # (joins letters/words of one label).
    MERGE_X, MERGE_Y = 18, 4
    # Diff detection runs on images shrunk by this factor first (INTER_AREA averaging drowns out the
    # single-pixel font-rendering jitter between environments); boxes are scaled back up before use.
    DOWNSCALE = 2

    def changed_boxes(self, old: np.ndarray, new: np.ndarray) -> list[Box]:
        """Bounding boxes (of the actual changed pixels) of each cluster of differences."""
        scale = self.DOWNSCALE
        if scale > 1:
            small_old = cv2.resize(
                old, None, fx=1 / scale, fy=1 / scale, interpolation=cv2.INTER_AREA
            )
            small_new = cv2.resize(
                new, None, fx=1 / scale, fy=1 / scale, interpolation=cv2.INTER_AREA
            )
        else:
            small_old, small_new = old, new

        changed = (cv2.absdiff(small_old, small_new).max(axis=2) > self.PIXEL_THRESHOLD).astype(
            np.uint8
        )
        if not changed.any():
            return []

        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (2 * self.MERGE_X + 1, 2 * self.MERGE_Y + 1)
        )
        count, labels = cv2.connectedComponents(cv2.dilate(changed, kernel))
        boxes = []
        for label in range(1, count):
            ys, xs = np.nonzero((labels == label) & (changed == 1))
            boxes.append(
                (
                    int(xs.min()) * scale,
                    int(ys.min()) * scale,
                    int(xs.max()) * scale,
                    int(ys.max()) * scale,
                )
            )
        return sorted(boxes, key=lambda b: (b[1], b[0]))


class RegionClassifier:
    """Decides whether a changed region is a date label, moved content, or a real change."""

    # Regions taller than this are never a one-line label, so they are not OCRed.
    LINE_MAX_HEIGHT = 30
    OCR_SCALE = 3
    DATE_LABEL_RE = re.compile(
        r"(data\s*as\s*of|as\s*of\s*:|donn[ée]es\s*en\s*date)", re.IGNORECASE
    )

    # A region whose old pixels reappear in the new image within this many px is the same content,
    # just moved.
    MAX_SHIFT = 3
    SHIFT_PAD = 3
    # Looser than ImageDiffer.PIXEL_THRESHOLD: a fractional-pixel move re-antialiases glyph edges.
    SHIFT_PIXEL_THRESHOLD = 70
    # Fraction of the patch's ink pixels allowed to still differ after the best shift.
    SHIFT_MAX_MISMATCH = 0.08

    def classify(self, old: np.ndarray, new: np.ndarray, boxes: list[Box]) -> list[Region]:
        return [self.classify_box(old, new, box) for box in boxes]

    def classify_box(self, old: np.ndarray, new: np.ndarray, box: Box) -> Region:
        if self.is_shifted(old, new, box):
            return Region(box, RegionKind.SHIFTED, "same content, moved")
        if box[3] - box[1] + 1 > self.LINE_MAX_HEIGHT:
            return Region(box, RegionKind.OTHER, "tall region")

        old_text, new_text = self.ocr(old, box), self.ocr(new, box)
        note = f"{old_text!r} -> {new_text!r}"
        if self.DATE_LABEL_RE.search(old_text) or self.DATE_LABEL_RE.search(new_text):
            return Region(box, RegionKind.DATE, note)
        if old_text == new_text and len(old_text) >= 3 and not any(c.isdigit() for c in old_text):
            # Same words on both sides (e.g. a column header nudged against a re-sized background).
            return Region(box, RegionKind.SHIFTED, note)
        return Region(box, RegionKind.OTHER, note)

    def ocr(self, image: np.ndarray, box: Box) -> str:
        x0, y0, x1, y1 = box
        crop = image[max(y0 - 2, 0) : y1 + 3, max(x0 - 2, 0) : x1 + 3]
        crop = cv2.resize(
            crop, None, fx=self.OCR_SCALE, fy=self.OCR_SCALE, interpolation=cv2.INTER_CUBIC
        )
        return pytesseract.image_to_string(crop, config="--psm 7").strip()

    def is_shifted(self, old: np.ndarray, new: np.ndarray, box: Box) -> bool:
        """True if the old content of `box` appears in `new` translated by at most MAX_SHIFT px."""
        max_shift, pad = self.MAX_SHIFT, self.SHIFT_PAD
        x0, y0, x1, y1 = box
        height, width = old.shape[:2]
        # Padded so the patch holds whole glyphs, and so a shifted copy stays inside the image.
        x0, y0 = max(x0 - pad, max_shift), max(y0 - pad, max_shift)
        x1, y1 = min(x1 + pad, width - max_shift - 1), min(y1 + pad, height - max_shift - 1)
        old_gray = cv2.cvtColor(old, cv2.COLOR_BGR2GRAY).astype(np.int16)
        new_gray = cv2.cvtColor(new, cv2.COLOR_BGR2GRAY).astype(np.int16)
        patch = old_gray[y0 : y1 + 1, x0 : x1 + 1]
        background = np.median(patch)
        ink = max(int((np.abs(patch - background) > self.SHIFT_PIXEL_THRESHOLD).sum()), 1)
        if ink < 3:  # blank patch: something appeared or disappeared, not moved
            return False

        for dy in range(-max_shift, max_shift + 1):
            for dx in range(-max_shift, max_shift + 1):
                moved = new_gray[y0 + dy : y1 + dy + 1, x0 + dx : x1 + dx + 1]
                if (
                    np.abs(patch - moved) > self.SHIFT_PIXEL_THRESHOLD
                ).sum() <= self.SHIFT_MAX_MISMATCH * ink:
                    return True
        return False


class ImageAnalyzer:
    """Diffs an old/new image pair and decides whether the changes need human review."""

    def __init__(
        self, differ: ImageDiffer | None = None, classifier: RegionClassifier | None = None
    ):
        self.differ = differ or ImageDiffer()
        self.classifier = classifier or RegionClassifier()

    def analyze(self, old: np.ndarray, new: np.ndarray) -> Analysis:
        if old.shape != new.shape:
            reason = f"size changed {old.shape[1]}x{old.shape[0]} -> {new.shape[1]}x{new.shape[0]}"
            return Analysis(Verdict.REVIEW, reason=reason)

        boxes = self.differ.changed_boxes(old, new)
        if not boxes:
            return Analysis(Verdict.IDENTICAL)
        regions = self.classifier.classify(old, new, boxes)
        others = [region for region in regions if region.needs_review]
        if others:
            return Analysis(
                Verdict.REVIEW,
                regions,
                f"{len(others)} of {len(regions)} regions are not date-related",
            )
        return Analysis(Verdict.DATE_ONLY, regions)
