"""PR #102 Regression Guard:
1. System-wide copy & cultural tone audit: zero matches of ``\\bcalm(?:ly)?\\b``
   (case-insensitive) across all 12 dual-served HTML templates, all 5 canonical
   manuals in ``docs/manuals/``, ``registry.json``, ``lexicon_v05.py``, companion
   captions/manifest, playbook SVGs, and user-facing AI tutor / copilot / router
   modules.
2. First-time visitor greeting on ``GET /login`` renders
   ``"Welcome — Private Family Sign-In"`` and does NOT render ``"Welcome Back"``.
3. 12/12 dual-served HTML templates remain byte-for-byte identical between
   ``backend/app/api/v1/*.html`` and ``backend/app/static/*.html`` with zero
   external CDN ``<script src="http...">`` or ``<link href="http...">`` tags.
"""
from __future__ import annotations

import pathlib
import re

from fastapi.testclient import TestClient

from app.domain.training_media_registry import (
    load_training_media_registry,
    validate_training_media_registry,
)
from app.main import app

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
API_V1_DIR = BACKEND_DIR / "app" / "api" / "v1"
STATIC_DIR = BACKEND_DIR / "app" / "static"
MANUALS_DIR = REPO_ROOT / "docs" / "manuals"
PLAYBOOKS_DIR = STATIC_DIR / "media" / "playbooks"
COMPANION_MEDIA_DIR = STATIC_DIR / "media" / "companion"
REGISTRY_JSON = PLAYBOOKS_DIR / "registry.json"
LEXICON_PY = BACKEND_DIR / "app" / "domain" / "lexicon_v05.py"

CALM_WORD_RE = re.compile(r"\bcalm(?:ly)?\b", re.IGNORECASE)
EXTERNAL_CDN_RE = re.compile(
    r"""<(?:script[^>]+src|link[^>]+href)=["']https?://""",
    re.IGNORECASE,
)

TWELVE_PORTAL_TEMPLATES = (
    "activate.html",
    "advisor.html",
    "community.html",
    "companion.html",
    "dashboard.html",
    "heritage.html",
    "heritage_tree.html",
    "home.html",
    "lineage_house.html",
    "login.html",
    "member.html",
    "tech.html",
)

FIVE_CANONICAL_MANUALS = (
    "USER_QUICKSTART.md",
    "CHIEF_ADMIN_RUNBOOK.md",
    "CLASS_F_FINANCIAL_MANUAL.md",
    "CLASS_T_TECHNICAL_MANUAL.md",
    "CLASS_H_LINEAGE_AND_HERITAGE_MANUAL.md",
)

AUDITED_PYTHON_MODULES = (
    BACKEND_DIR / "app" / "domain" / "lexicon_v05.py",
    BACKEND_DIR / "app" / "domain" / "dual_lane_tutor.py",
    BACKEND_DIR / "app" / "domain" / "member_tutor.py",
    BACKEND_DIR / "app" / "domain" / "role_copilots.py",
    BACKEND_DIR / "app" / "domain" / "chancellor_coach.py",
    BACKEND_DIR / "app" / "domain" / "lineage_tutor.py",
    BACKEND_DIR / "app" / "domain" / "session_auth_service.py",
    BACKEND_DIR / "app" / "domain" / "family_tree_service.py",
    BACKEND_DIR / "app" / "domain" / "heritage_community_service.py",
    BACKEND_DIR / "app" / "domain" / "ai_clients" / "guardrails.py",
    BACKEND_DIR / "app" / "api" / "v1" / "portal_router.py",
    BACKEND_DIR / "app" / "api" / "v1" / "social_plane_router.py",
    BACKEND_DIR / "app" / "api" / "v1" / "auth_router.py",
    BACKEND_DIR / "app" / "api" / "v1" / "onboarding_router.py",
)


def _find_calm_violations(path: pathlib.Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    violations: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if CALM_WORD_RE.search(line):
            violations.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    return violations


def test_zero_calm_wording_in_all_12_dual_served_html_templates() -> None:
    violations: list[str] = []
    for name in TWELVE_PORTAL_TEMPLATES:
        v1_path = API_V1_DIR / name
        static_path = STATIC_DIR / name
        assert v1_path.is_file(), f"Missing api/v1 template: {v1_path}"
        assert static_path.is_file(), f"Missing static template: {static_path}"
        violations.extend(_find_calm_violations(v1_path))
        violations.extend(_find_calm_violations(static_path))
    assert not violations, "Found disallowed calm/calmly copy in HTML templates:\n" + "\n".join(violations)


def test_zero_calm_wording_in_all_5_canonical_manuals() -> None:
    violations: list[str] = []
    for name in FIVE_CANONICAL_MANUALS:
        manual_path = MANUALS_DIR / name
        assert manual_path.is_file(), f"Missing canonical manual: {manual_path}"
        violations.extend(_find_calm_violations(manual_path))
    assert not violations, "Found disallowed calm/calmly copy in manuals:\n" + "\n".join(violations)


def test_zero_calm_wording_in_playbooks_registry_svgs_captions_and_lexicon() -> None:
    targets: list[pathlib.Path] = [
        REGISTRY_JSON,
        LEXICON_PY,
        COMPANION_MEDIA_DIR / "manifest.json",
        *sorted(PLAYBOOKS_DIR.glob("*.svg")),
        *sorted(COMPANION_MEDIA_DIR.rglob("*.vtt")),
    ]
    violations: list[str] = []
    for target in targets:
        assert target.is_file(), f"Missing target file: {target}"
        violations.extend(_find_calm_violations(target))
    assert not violations, "Found disallowed calm/calmly copy in playbooks/captions/lexicon:\n" + "\n".join(violations)

    # Confirm updated playbook registry still passes full schema & asset validation
    registry = load_training_media_registry()
    errors = validate_training_media_registry(registry)
    assert errors == [], f"Training media registry validation failed: {errors}"


def test_zero_calm_wording_in_audited_tutors_copilots_and_routers() -> None:
    violations: list[str] = []
    for py_path in AUDITED_PYTHON_MODULES:
        assert py_path.is_file(), f"Missing audited module: {py_path}"
        violations.extend(_find_calm_violations(py_path))
    assert not violations, "Found disallowed calm/calmly copy in audited Python modules:\n" + "\n".join(violations)


def test_login_greeting_welcomes_first_time_visitors() -> None:
    client = TestClient(app)
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "Welcome — Private Family Sign-In" in resp.text
    assert "Welcome Back" not in resp.text


def test_twelve_dual_served_html_templates_byte_parity_and_zero_external_cdn() -> None:
    v1_html_names = sorted(p.name for p in API_V1_DIR.glob("*.html"))
    assert tuple(v1_html_names) == TWELVE_PORTAL_TEMPLATES, (
        f"Expected 12 dual-served templates {TWELVE_PORTAL_TEMPLATES}, found {v1_html_names}"
    )

    for name in TWELVE_PORTAL_TEMPLATES:
        v1_path = API_V1_DIR / name
        static_path = STATIC_DIR / name
        v1_bytes = v1_path.read_bytes()
        static_bytes = static_path.read_bytes()
        assert v1_bytes == static_bytes, f"Byte-for-byte parity mismatch for {name}"

        html_text = v1_bytes.decode("utf-8")
        assert not EXTERNAL_CDN_RE.search(html_text), f"External CDN tag detected in {name}"
