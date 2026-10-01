"""Retention checks for the ratified PDEUE canonical lexicon v0.5."""

from pathlib import Path


LEXICON = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "PDEUE_Canonical_Terminology_and_Replay_Lexicon_v0.5.md"
)


def test_canonical_lexicon_v05_exists_and_is_comprehensive():
    assert LEXICON.is_file()
    assert len(LEXICON.read_text(encoding="utf-8").split()) > 2_000


def test_canonical_lexicon_v05_retains_ratified_anchors():
    text = LEXICON.read_text(encoding="utf-8")
    for anchor in (
        "ADR-008",
        "ADR-011",
        "87/10/3",
        "FSAP",
        "F2-H",
        "Directive R-04",
        "Directive R-12",
        "Concentric Asset Engine Rings",
        "AUTH-01",
    ):
        assert anchor in text, f"missing ratified lexicon anchor: {anchor}"
