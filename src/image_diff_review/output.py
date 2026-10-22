from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from image_diff_review.analysis import Analysis, Region


class OverlayWriter:
    """Writes side-by-side old | new images with the changed regions boxed; red = needs review, green = dismissed."""

    REVIEW_COLOR = (0, 0, 255)
    DISMISSED_COLOR = (0, 160, 0)

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir

    def path_for(self, image_path: str) -> Path:
        return self.out_dir / (image_path.replace('/', '__') + '.diff.png')

    def write(self, image_path: str, old: np.ndarray, new: np.ndarray, regions: list[Region]) -> Path:
        canvas = np.full((max(old.shape[0], new.shape[0]), old.shape[1] + new.shape[1], 3), 255, np.uint8)
        canvas[: old.shape[0], : old.shape[1]] = old
        canvas[: new.shape[0], old.shape[1] :] = new
        for region in regions:
            x0, y0, x1, y1 = region.box
            color = self.REVIEW_COLOR if region.needs_review else self.DISMISSED_COLOR
            cv2.rectangle(canvas, (x0, y0), (x1, y1), color, 3)
            cv2.rectangle(canvas, (old.shape[1] + x0, y0), (old.shape[1] + x1, y1), color, 3)
        out_path = self.path_for(image_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_path), canvas)
        return out_path


@dataclass
class FlaggedImage:
    path: str
    analysis: Analysis
    overlay: Path


@dataclass
class Report:
    """Collects the per-image outcomes and prints the summary."""

    flagged: list[FlaggedImage] = field(default_factory=list)
    date_only: list[tuple[str, Analysis]] = field(default_factory=list)
    identical: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return 1 if self.flagged else 0

    def print(self, show_date_only: bool = False) -> None:
        print(f'\n{len(self.flagged)} image(s) with changes beyond the date label:')
        for item in self.flagged:
            print(f'  {item.path}\n      {item.analysis}\n      overlay: {item.overlay}')
            for region in item.analysis.regions:
                if region.needs_review:
                    print(f'      - {region.box} {region.note}')
        print(
            f'\nsummary: {len(self.flagged)} flagged, {len(self.date_only)} date-only, '
            f'{len(self.identical)} pixel-identical, {len(self.skipped)} added/deleted (not compared)'
        )
        if show_date_only:
            print('\ndate-only:')
            for path, analysis in self.date_only:
                print(f'  {path}')
                for region in analysis.regions:
                    print(f'      - {region.kind} {region.box} {region.note}')
        for status, path in self.skipped:
            print(f'  [{status}] {path}')
