import subprocess

import cv2
import numpy as np


class GitRepo:
    """Thin wrapper over the `git` CLI for the repository containing the current directory."""

    def run(self, *args: str) -> bytes:
        return subprocess.run(["git", *args], check=True, capture_output=True).stdout

    def merge_base(self, target: str, head: str) -> str:
        return self.run("merge-base", target, head).decode().strip()

    def changed_pngs(self, base: str, new_rev: str) -> list[tuple[str, str]]:
        """[(status, path)] of PNGs that differ between `base` and `new_rev`."""
        lines = (
            self.run("diff", "--name-status", "--no-renames", base, new_rev, "--", "*.png")
            .decode()
            .splitlines()
        )
        return [(status, path) for status, path in (line.split("\t", 1) for line in lines)]

    def load_png(self, rev: str, path: str) -> np.ndarray:
        """Reads `path` at `rev`, resolving LFS pointers, as a BGR array."""
        blob = self.run("show", f"{rev}:{path}")
        if blob.startswith(b"version https://git-lfs"):
            blob = subprocess.run(
                ["git", "lfs", "smudge"], input=blob, check=True, capture_output=True
            ).stdout
        image = cv2.imdecode(np.frombuffer(blob, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"could not decode {path} at {rev} as an image")
        return image
