import re

# OCRed text matching this marks the region as an expected change (by default, a date label).
# Kept apart from analysis.py so the CLI can show it in --help without importing OpenCV.
EXPECTED_CHANGE_RE = re.compile(
    r"(data\s*as\s*of|as\s*of\s*:|donn[ée]es\s*en\s*date)", re.IGNORECASE
)
