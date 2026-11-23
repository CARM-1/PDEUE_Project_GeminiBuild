"""Play #16 Pre-Pilot Security & Bot-Defense hygiene tests."""
from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"


def test_backend_html_templates_have_zero_external_cdn_scripts():
    html_files = sorted(BACKEND_DIR.rglob("*.html"))
    assert html_files, "Expected HTML templates under backend/"
    cdn_pattern = re.compile(
        r"""<script[^>]+src=["']https?://[^"']*(?:cdn|jsdelivr|unpkg|cdnjs|bootstrapcdn|tailwind)""",
        re.IGNORECASE,
    )
    for html_file in html_files:
        content = html_file.read_text(encoding="utf-8", errors="ignore")
        assert not cdn_pattern.search(content), f"External CDN script found in {html_file}"


def test_tracked_backend_source_has_no_raw_routing_or_bank_credentials():
    py_files = sorted(BACKEND_DIR.rglob("*.py"))
    assert py_files, "Expected Python modules under backend/"
    suspicious_assign = re.compile(
        r"""(?i)(?:routing_number|bank_account_number|swift_code|iban)\s*=\s*["'][^"']{4,}["']"""
    )
    for py_file in py_files:
        if "test_" in py_file.name:
            continue
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        assert not suspicious_assign.search(content), f"Suspicious banking credential assignment in {py_file}"
