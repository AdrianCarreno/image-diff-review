from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import regex

# OCRed text matching this marks the region as an expected change (by default, a date label).
# Kept apart from analysis.py so the CLI can show it in --help without importing OpenCV.
EXPECTED_CHANGE_PATTERN = r"(data\s*as\s*of|as\s*of\s*:|donn[ée]es\s*en\s*date)"


def compile_expected_change_re(
    pattern: str = EXPECTED_CHANGE_PATTERN, max_errors: int = 0
) -> regex.Pattern[str]:
    """Compiles `pattern` case-insensitively, tolerating up to `max_errors` OCR mistakes.

    Each inserted, deleted, or substituted character counts as one error (Levenshtein distance),
    so tiny text that OCR misreads ("Data ss of") still matches. Raises regex.error if the pattern
    is invalid.
    """
    import regex  # native extension, loaded only when a pattern is compiled

    if max_errors:
        pattern = f"(?:{pattern}){{e<={max_errors}}}"
    return regex.compile(pattern, regex.IGNORECASE)
