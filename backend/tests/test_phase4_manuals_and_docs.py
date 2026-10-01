"""Publication contract for the Phase 4 canonical operating manuals."""

import re
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MANUALS_DIRECTORY = REPOSITORY_ROOT / "docs" / "manuals"
REQUIRED_MANUALS = (
    "USER_QUICKSTART.md",
    "CHIEF_ADMIN_RUNBOOK.md",
    "CLASS_T_TECHNICAL_MANUAL.md",
    "CLASS_F_FINANCIAL_MANUAL.md",
)
REQUIRED_GOVERNANCE_REFERENCES = ("ADR-008", "ADR-011", "R-04", "R-12")


def _words(document: str) -> list[str]:
    """Count prose and identifiers while excluding Markdown punctuation."""

    return re.findall(r"\b[\w$%-]+\b", document, flags=re.UNICODE)


@pytest.mark.parametrize("filename", REQUIRED_MANUALS)
def test_canonical_manual_exists_and_exceeds_publication_floor(filename: str) -> None:
    manual = MANUALS_DIRECTORY / filename

    assert manual.is_file(), f"missing canonical manual: {manual}"
    document = manual.read_text(encoding="utf-8")
    assert document.strip(), f"canonical manual is empty: {manual}"
    word_count = len(_words(document))
    assert word_count > 1_500, (
        f"{filename} must contain more than 1,500 words; found {word_count}"
    )


@pytest.mark.parametrize("filename", REQUIRED_MANUALS)
@pytest.mark.parametrize("reference", REQUIRED_GOVERNANCE_REFERENCES)
def test_every_manual_documents_cross_referenced_governance(
    filename: str, reference: str
) -> None:
    document = (MANUALS_DIRECTORY / filename).read_text(encoding="utf-8")

    assert reference in document, f"{filename} does not document {reference}"
