from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

import cv2
import numpy as np

from image_diff_review.analysis import Analysis
from image_diff_review.analysis import Region


class OutputDirError(Exception):
    """The output directory can't be used without risking files this tool didn't create."""


class OverlayRenderer(ABC):
    """Draws the image saved for a flagged file from its old and new versions."""

    @abstractmethod
    def render(self, old: np.ndarray, new: np.ndarray, regions: list[Region]) -> np.ndarray: ...


class SideBySideRenderer(OverlayRenderer):
    """Old | new side by side with the changed regions boxed.

    Red = needs review, green = dismissed.
    """

    REVIEW_COLOR = (0, 0, 255)
    DISMISSED_COLOR = (0, 160, 0)

    def render(self, old: np.ndarray, new: np.ndarray, regions: list[Region]) -> np.ndarray:
        canvas = np.full(
            (max(old.shape[0], new.shape[0]), old.shape[1] + new.shape[1], 3), 255, np.uint8
        )
        canvas[: old.shape[0], : old.shape[1]] = old
        canvas[: new.shape[0], old.shape[1] :] = new
        for region in regions:
            x0, y0, x1, y1 = region.box
            color = self.REVIEW_COLOR if region.needs_review else self.DISMISSED_COLOR
            cv2.rectangle(canvas, (x0, y0), (x1, y1), color, 3)
            cv2.rectangle(canvas, (old.shape[1] + x0, y0), (old.shape[1] + x1, y1), color, 3)
        return canvas


class DifferenceRenderer(OverlayRenderer):
    """Sign of new minus old ink (darkness), per pixel.

    Fixtures are dark content on a light background, so ink tracks content: full green where the
    new image is darker (content added), black where unchanged, full red where it is lighter
    (content removed). Every change is fully saturated, so even a one-level difference stands out.
    """

    def render(self, old: np.ndarray, new: np.ndarray, regions: list[Region]) -> np.ndarray:
        # Images of different sizes are compared on a shared white canvas, top-left aligned.
        shape = (max(old.shape[0], new.shape[0]), max(old.shape[1], new.shape[1]))
        difference = self.ink(new, shape) - self.ink(old, shape)
        canvas = np.zeros((*shape, 3), np.uint8)
        canvas[difference > 0, 1] = 255
        canvas[difference < 0, 2] = 255
        return canvas

    @staticmethod
    def ink(image: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
        """Darkness of each pixel (0 = white, 255 = black), padded to `shape` with white."""
        padded = np.zeros(shape, np.int16)
        padded[: image.shape[0], : image.shape[1]] = 255 - cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return padded


class OverlayWriter:
    """Saves one rendered image per flagged file into the output directory."""

    OVERLAY_SUFFIX = ".diff.png"
    GITIGNORE = ".gitignore"

    def __init__(self, out_dir: Path, renderer: OverlayRenderer):
        self.out_dir = out_dir
        self.renderer = renderer

    def path_for(self, image_path: str) -> Path:
        return self.out_dir / (image_path.replace("/", "__") + self.OVERLAY_SUFFIX)

    def is_own_overlay(self, entry: Path) -> bool:
        return entry.is_file() and entry.name.endswith(self.OVERLAY_SUFFIX)

    def prepare(self) -> list[Path]:
        """Readies an empty output directory holding only a `.gitignore` that ignores everything.

        Overlays left by a previous run are deleted and returned. Raises OutputDirError, deleting
        nothing, if the path is not a directory or holds anything this tool would not have written.
        """
        if not self.out_dir.exists():
            self.out_dir.mkdir(parents=True)
        if not self.out_dir.is_dir():
            raise OutputDirError(f"--out {self.out_dir} exists but is not a directory")

        entries = [entry for entry in self.out_dir.iterdir() if entry.name != self.GITIGNORE]
        foreign = sorted(entry.name for entry in entries if not self.is_own_overlay(entry))
        if foreign:
            listing = "\n".join(f"  {name}" for name in foreign)
            raise OutputDirError(
                f"--out {self.out_dir} contains files not created by image-diff-review:\n"
                f"{listing}\nMove or delete them first, or pick another --out."
            )

        for entry in entries:
            entry.unlink()
        gitignore = self.out_dir / self.GITIGNORE
        if not gitignore.exists():
            gitignore.write_text("*\n")
        return sorted(entries)

    def write(
        self, image_path: str, old: np.ndarray, new: np.ndarray, regions: list[Region]
    ) -> Path:
        canvas = self.renderer.render(old, new, regions)
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
        print(f"\n{len(self.flagged)} image(s) with changes beyond the date label:")
        for item in self.flagged:
            print(f"  {item.path}\n      {item.analysis}\n      overlay: {item.overlay}")
            for region in item.analysis.regions:
                if region.needs_review:
                    print(f"      - {region.box} {region.note}")
        print(
            f"\nsummary: {len(self.flagged)} flagged, {len(self.date_only)} date-only, "
            f"{len(self.identical)} pixel-identical, "
            f"{len(self.skipped)} added/deleted (not compared)"
        )
        if show_date_only:
            print("\ndate-only:")
            for path, analysis in self.date_only:
                print(f"  {path}")
                for region in analysis.regions:
                    print(f"      - {region.kind} {region.box} {region.note}")
        for status, path in self.skipped:
            print(f"  [{status}] {path}")
