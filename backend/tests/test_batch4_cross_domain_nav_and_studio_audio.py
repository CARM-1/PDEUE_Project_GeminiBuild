"""Batch 4 Verification Suite:
1. Cross-Domain Plane Doorway Routing (`GET /api/v1/portal/planes`, query-preserving
   hydration in `senior_a11y.js`, `data-plane-doorway` tags across all 9 portals,
   and Caddy `/api/v1/hunch/*` allowlist + strict air-gap on social/university/IFAS).
2. Autonomous Studio Audio & WebVTT Pipeline (`backend/scripts/build_companion_audio.py`)
   supporting Mock, Deepgram (Aura-2/Flux TTS), and DeepSeek TTS with zero hardcoded secrets,
   and `manifest.json` wiring into `GET /api/v1/portal/companion/state`.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
from typing import Any, Dict, List

import httpx
import pytest
from fastapi.testclient import TestClient

from app.domain.plane_routing import get_plane_config
from app.main import app
from app.portal_discovery import PORTALS, audit_ui_lexicon_curriculum_parity, generate_inventory

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
API_V1_DIR = BACKEND_DIR / "app" / "api" / "v1"
STATIC_DIR = BACKEND_DIR / "app" / "static"
CADDYFILE_PATH = REPO_ROOT / "deploy" / "caddy" / "Caddyfile"
SCRIPT_PATH = BACKEND_DIR / "scripts" / "build_companion_audio.py"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts import build_companion_audio as audio_builder  # noqa: E402

ALL_NINE_TEMPLATES = (
    "home.html",
    "dashboard.html",
    "member.html",
    "advisor.html",
    "tech.html",
    "lineage_house.html",
    "community.html",
    "heritage.html",
    "companion.html",
)

EXPECTED_MULTI_DOMAIN_ENV: Dict[str, str] = {
    "FAMILY_HUB_BASE_URL": "https://narratixai.org",
    "UNIVERSITY_BASE_URL": "https://narratixai.info",
    "PDEUE_VAULT_BASE_URL": "https://vault.narratixai.io",
    "PDEUE_ADMIN_BASE_URL": "https://admin.narratixai.io",
    "IFAS_ACCOUNTING_BASE_URL": "https://narratixai.net",
}


def _extract_caddy_site_block(caddyfile_text: str, host: str) -> str:
    pattern = re.compile(rf"(?m)^{re.escape(host)}\s*\{{")
    match = pattern.search(caddyfile_text)
    assert match is not None, f"Missing Caddy site block for {host}"
    start = match.start()
    depth = 0
    for idx in range(match.end() - 1, len(caddyfile_text)):
        ch = caddyfile_text[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return caddyfile_text[start : idx + 1]
    raise AssertionError(f"Unbalanced braces in Caddyfile site block for {host}")


# ---------------------------------------------------------------------------
# PART 1: CROSS-DOMAIN DOORWAY ROUTING & CADDY /api/v1/hunch/* ALLOWLIST
# ---------------------------------------------------------------------------


def test_portal_planes_exposes_all_explicit_doorway_keys_in_relative_and_multi_domain_modes(
    monkeypatch: pytest.MonkeyPatch,
):
    for key in EXPECTED_MULTI_DOMAIN_ENV:
        monkeypatch.delenv(key, raising=False)

    client = TestClient(app)

    # 1. Default CI/local mode: relative_single_host
    rel_resp = client.get("/api/v1/portal/planes")
    assert rel_resp.status_code == 200
    rel = rel_resp.json()
    assert rel["routing_mode"] == "relative_single_host"
    rel_doors = rel["doorways"]
    expected_relative = {
        "home": "/home",
        "community": "/community",
        "heritage": "/community/heritage",
        "companion": "/companion",
        "member": "/member",
        "advisor": "/advisor",
        "dashboard": "/dashboard",
        "admin_tech": "/admin/tech",
        "tech": "/admin/tech",
        "ifas": "",
    }
    for k, expected in expected_relative.items():
        assert rel_doors.get(k) == expected, f"Expected relative doorway {k}={expected!r}, got {rel_doors.get(k)!r}"

    # 2. Production 4-domain mode: multi_domain_air_gapped
    for key, val in EXPECTED_MULTI_DOMAIN_ENV.items():
        monkeypatch.setenv(key, val)

    prod_resp = client.get("/api/v1/portal/planes")
    assert prod_resp.status_code == 200
    prod = prod_resp.json()
    assert prod["routing_mode"] == "multi_domain_air_gapped"
    prod_doors = prod["doorways"]
    expected_prod = {
        "home": "https://narratixai.org/home",
        "community": "https://narratixai.org/community",
        "heritage": "https://narratixai.org/community/heritage",
        "companion": "https://narratixai.info/companion",
        "member": "https://vault.narratixai.io/member",
        "advisor": "https://vault.narratixai.io/advisor",
        "dashboard": "https://admin.narratixai.io/dashboard",
        "admin_tech": "https://admin.narratixai.io/admin/tech",
        "tech": "https://admin.narratixai.io/admin/tech",
        "ifas": "https://narratixai.net",
    }
    for k, expected in expected_prod.items():
        assert prod_doors.get(k) == expected, f"Expected prod doorway {k}={expected!r}, got {prod_doors.get(k)!r}"

    # Direct domain helper parity
    cfg = get_plane_config()
    assert cfg["doorways"]["admin_tech"] == "https://admin.narratixai.io/admin/tech"


def test_all_cross_plane_header_links_tagged_shared_a11y_script_and_9_of_9_template_parity():
    # Every portal hydrates doorways cleanly and stays byte-for-byte synced
    # (advisor.html & tech.html preserve WP4 zero-<script src=> inline lock)
    for filename in ALL_NINE_TEMPLATES:
        api_text = (API_V1_DIR / filename).read_text(encoding="utf-8")
        static_text = (STATIC_DIR / filename).read_text(encoding="utf-8")
        assert api_text == static_text, f"Byte-for-byte template drift detected for {filename}"
        if filename in {"advisor.html", "tech.html"}:
            assert "<script src=" not in api_text.lower()
            assert "multi_domain_air_gapped" in api_text and "resolveDoorwayUrl" in api_text
        else:
            assert '<script src="/static/js/senior_a11y.js"></script>' in api_text, (
                f"{filename} must load shared /static/js/senior_a11y.js for query-preserving doorway hydration"
            )

    # dashboard.html cross-plane header links
    dash = (API_V1_DIR / "dashboard.html").read_text(encoding="utf-8")
    for token in (
        'data-plane-doorway="home"',
        'data-plane-doorway="heritage"',
        'data-plane-doorway="dashboard"',
        'data-plane-doorway="admin_tech"',
        'data-plane-doorway="advisor"',
        'data-plane-doorway="member"',
        'data-plane-doorway="companion"',
    ):
        assert token in dash, f"dashboard.html missing {token}"

    # companion.html cross-plane header links
    comp = (API_V1_DIR / "companion.html").read_text(encoding="utf-8")
    for token in (
        'data-plane-doorway="home"',
        'data-plane-doorway="heritage"',
        'data-plane-doorway="dashboard"',
        'data-plane-doorway="member"',
        'data-plane-doorway="companion"',
    ):
        assert token in comp, f"companion.html missing {token}"

    # advisor.html, member.html, tech.html, lineage_house.html cross-plane header links
    for fname in ("advisor.html", "member.html", "tech.html", "lineage_house.html"):
        text = (API_V1_DIR / fname).read_text(encoding="utf-8")
        for token in ('data-plane-doorway="home"', 'data-plane-doorway="heritage"', 'data-plane-doorway="companion"'):
            assert token in text, f"{fname} missing {token}"

    # senior_a11y.js preserves query strings & only rewrites in multi_domain_air_gapped mode
    a11y_js = (STATIC_DIR / "js" / "senior_a11y.js").read_text(encoding="utf-8")
    assert "multi_domain_air_gapped" in a11y_js
    assert "parsedCurrent.search" in a11y_js
    assert "resolveDoorwayUrl" in a11y_js


def test_caddyfile_allows_hunch_on_vault_and_admin_while_blocking_on_social_university_ifas():
    text = CADDYFILE_PATH.read_text(encoding="utf-8")

    # vault.narratixai.io: /api/v1/hunch and /api/v1/hunch/* allowed; admin/dashboard still 403
    vault_block = _extract_caddy_site_block(text, "vault.narratixai.io")
    assert "/api/v1/hunch" in vault_block
    assert "/api/v1/hunch/*" in vault_block
    vault_allowed_match = re.search(r"@vault_allowed\s*\{([^}]*)\}", vault_block, re.S)
    assert vault_allowed_match is not None
    assert "/api/v1/hunch /api/v1/hunch/*" in vault_allowed_match.group(1)
    vault_blocked_match = re.search(r"@vault_blocked\s*\{([^}]*)\}", vault_block, re.S)
    assert vault_blocked_match is not None
    assert "/dashboard" in vault_blocked_match.group(1) and "/admin" in vault_blocked_match.group(1)

    # admin.narratixai.io: /api/v1/hunch and /api/v1/hunch/* allowed
    admin_block = _extract_caddy_site_block(text, "admin.narratixai.io")
    admin_allowed_match = re.search(r"@admin_allowed\s*\{([^}]*)\}", admin_block, re.S)
    assert admin_allowed_match is not None
    assert "/api/v1/hunch" in admin_allowed_match.group(1)
    assert "/api/v1/hunch/*" in admin_allowed_match.group(1)

    # narratixai.org (social) & narratixai.info (university): /api/v1/hunch* explicitly blocked (403)
    org_block = _extract_caddy_site_block(text, "narratixai.org")
    social_blocked = re.search(r"@social_blocked\s*\{([^}]*)\}", org_block, re.S)
    assert social_blocked is not None
    assert "/api/v1/hunch /api/v1/hunch/*" in social_blocked.group(1)

    info_block = _extract_caddy_site_block(text, "narratixai.info")
    uni_blocked = re.search(r"@university_blocked\s*\{([^}]*)\}", info_block, re.S)
    assert uni_blocked is not None
    assert "/api/v1/hunch /api/v1/hunch/*" in uni_blocked.group(1)

    # narratixai.net (IFAS): zero proxy & /api/* blocked
    net_block = _extract_caddy_site_block(text, "narratixai.net")
    assert "reverse_proxy" not in net_block
    assert "/api/*" in net_block


# ---------------------------------------------------------------------------
# PART 2: AUTONOMOUS BATCH 4 STUDIO AUDIO & WEBVTT PIPELINE + MANIFEST WIRING
# ---------------------------------------------------------------------------


def test_build_companion_audio_zero_hardcoded_secrets_and_fail_closed_env_keys(
    monkeypatch: pytest.MonkeyPatch,
):
    assert SCRIPT_PATH.is_file(), "backend/scripts/build_companion_audio.py must exist"
    src = SCRIPT_PATH.read_text(encoding="utf-8")

    # Zero literal secret assignments
    assert not re.search(r"""DEEPGRAM_API_KEY\s*=\s*["'][^"']{6,}["']""", src)
    assert not re.search(r"""DEEPSEEK_API_KEY\s*=\s*["'][^"']{6,}["']""", src)
    assert 'os.getenv("DEEPGRAM_API_KEY"' in src
    assert 'os.getenv("DEEPSEEK_API_KEY"' in src

    # Fail closed when API keys are missing
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DEEPGRAM_API_KEY"):
        audio_builder.create_provider("deepgram")
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        audio_builder.create_provider("deepseek")


def test_extract_narration_beats_covers_orientation_18_beats_and_6_deep_dives():
    beats = audio_builder.extract_narration_beats()
    ids = [b.id for b in beats]
    assert len(beats) == 25, f"Expected 25 narration beats (1 + 18 + 6), got {len(beats)}: {ids}"
    assert ids[0] == "ch0_orientation"
    for ch in range(1, 7):
        for step in range(1, 4):
            assert f"ch{ch}_b{step}" in ids
    for dd in (
        "dd_compounding",
        "dd_prediction_odds",
        "dd_hwm_deep",
        "dd_phase_fsap",
        "dd_ai_tutor",
        "dd_shadow_hunch",
    ):
        assert dd in ids
    assert all(len(b.text) >= 40 for b in beats)


def _parse_vtt_seconds(ts: str) -> float:
    hh, mm, rest = ts.split(":")
    ss, ms = rest.split(".")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0


def test_mock_pipeline_generates_valid_mp3_webvtt_manifest_and_caches_idempotently(tmp_path: pathlib.Path):
    provider = audio_builder.create_provider("mock")

    # First build: synthesizes all 50 tracks (25 beats x 2 voices)
    first = audio_builder.build_companion_audio(provider=provider, output_dir=tmp_path)
    assert first["beat_count"] == 25
    assert first["voice_count"] == 2
    assert first["synthesized_count"] == 50
    assert first["skipped_cached_count"] == 0

    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "studio_audio_ready"
    assert manifest["provider"] == "mock"
    assert manifest["zero_runtime_tts_api"] is True
    assert len(manifest["voices"]) == 2
    for voice in manifest["voices"]:
        assert voice["audio_ready"] is True
        assert voice["track_count"] == 25

    cue_re = re.compile(r"^(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})$")
    for voice_id in ("mentor_f_aa", "mentor_m_aa"):
        tracks = manifest["tracks"][voice_id]
        assert len(tracks) == 25
        for beat_id, entry in tracks.items():
            mp3_file = tmp_path / voice_id / f"{beat_id}.mp3"
            vtt_file = tmp_path / voice_id / f"{beat_id}.vtt"
            assert mp3_file.is_file() and mp3_file.stat().st_size > 1000
            assert vtt_file.is_file()
            mp3_bytes = mp3_file.read_bytes()
            assert mp3_bytes[:2] == b"\xff\xfb", f"Invalid MPEG-1 Layer 3 header in {mp3_file}"
            assert entry["mp3"] == f"/static/media/companion/{voice_id}/{beat_id}.mp3"
            assert entry["vtt"] == f"/static/media/companion/{voice_id}/{beat_id}.vtt"
            assert entry["duration_seconds"] > 0.5

            vtt_text = vtt_file.read_text(encoding="utf-8")
            assert vtt_text.startswith("WEBVTT\n\n")
            prev_end = -1.0
            cue_count = 0
            for line in vtt_text.splitlines():
                m = cue_re.match(line)
                if m:
                    start_s = _parse_vtt_seconds(m.group(1))
                    end_s = _parse_vtt_seconds(m.group(2))
                    assert end_s > start_s, f"Non-positive cue duration in {vtt_file}: {line}"
                    assert start_s >= prev_end - 1e-6, f"Overlapping cue in {vtt_file}: {line}"
                    prev_end = end_s
                    cue_count += 1
            assert cue_count >= 1

    # Second build without --force: 100% cache hit
    second = audio_builder.build_companion_audio(provider=provider, output_dir=tmp_path)
    assert second["synthesized_count"] == 0
    assert second["skipped_cached_count"] == 50

    # Forced rebuild regenerates requested subset
    forced = audio_builder.build_companion_audio(
        provider=provider,
        output_dir=tmp_path,
        only_beat_ids=["ch0_orientation"],
        voice_ids=["mentor_f_aa"],
        force=True,
    )
    assert forced["synthesized_count"] == 1


def test_deepgram_and_deepseek_providers_request_contracts_retries_and_zero_secret_leakage(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
):
    fake_mp3 = audio_builder.build_mock_mp3_bytes(duration_seconds=1.5)

    # 1. Deepgram Aura-2 provider (including retry on HTTP 429)
    dg_calls: List[httpx.Request] = []

    def dg_handler(request: httpx.Request) -> httpx.Response:
        dg_calls.append(request)
        if len(dg_calls) == 1:
            return httpx.Response(429, text="rate limited")
        return httpx.Response(200, content=fake_mp3, headers={"content-type": "audio/mpeg"})

    dg_secret = "dg_test_env_only_secret_987654"
    monkeypatch.setenv("DEEPGRAM_API_KEY", dg_secret)
    dg_client = httpx.Client(transport=httpx.MockTransport(dg_handler))
    dg_provider = audio_builder.DeepgramTTSProvider(http_client=dg_client, sleep_fn=lambda _s: None)
    dg_out = tmp_path / "deepgram_out"
    dg_summary = audio_builder.build_companion_audio(
        provider=dg_provider,
        output_dir=dg_out,
        voice_ids=["mentor_f_aa"],
        only_beat_ids=["ch0_orientation"],
    )
    assert dg_summary["synthesized_count"] == 1
    assert len(dg_calls) == 2
    req = dg_calls[-1]
    assert req.url.path == "/v1/speak"
    assert req.url.params.get("model") == "aura-2-thalia-en"
    assert req.url.params.get("encoding") == "mp3"
    assert req.headers.get("authorization") == f"Token {dg_secret}"
    body = json.loads(req.content.decode("utf-8"))
    assert "PDEUE University" in body["text"]
    # Zero secret leakage into manifest or VTT
    assert dg_secret not in (dg_out / "manifest.json").read_text(encoding="utf-8")
    assert dg_secret not in (dg_out / "mentor_f_aa" / "ch0_orientation.vtt").read_text(encoding="utf-8")

    # 2. DeepSeek TTS provider
    ds_calls: List[httpx.Request] = []

    def ds_handler(request: httpx.Request) -> httpx.Response:
        ds_calls.append(request)
        return httpx.Response(200, content=fake_mp3, headers={"content-type": "audio/mpeg"})

    ds_secret = "ds_test_env_only_secret_123456"
    monkeypatch.setenv("DEEPSEEK_API_KEY", ds_secret)
    ds_client = httpx.Client(transport=httpx.MockTransport(ds_handler))
    ds_provider = audio_builder.DeepSeekTTSProvider(http_client=ds_client, sleep_fn=lambda _s: None)
    ds_out = tmp_path / "deepseek_out"
    ds_summary = audio_builder.build_companion_audio(
        provider=ds_provider,
        output_dir=ds_out,
        voice_ids=["mentor_m_aa"],
        only_beat_ids=["ch1_b1"],
    )
    assert ds_summary["synthesized_count"] == 1
    assert len(ds_calls) == 1
    ds_req = ds_calls[0]
    assert ds_req.url.path == "/v1/audio/speech"
    assert ds_req.headers.get("authorization") == f"Bearer {ds_secret}"
    ds_body = json.loads(ds_req.content.decode("utf-8"))
    assert ds_body["model"] == "deepseek-tts"
    assert ds_body["voice"] == "marcus"
    assert ds_body["response_format"] == "mp3"
    assert ds_secret not in (ds_out / "manifest.json").read_text(encoding="utf-8")


def test_companion_state_endpoint_wires_manifest_and_enforces_zero_404_zero_cdn(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
):
    client = TestClient(app)

    # 1. Default repository manifest (clean ready_for_batch4_audio state)
    monkeypatch.delenv("PDEUE_COMPANION_MEDIA_DIR", raising=False)
    default_resp = client.get("/api/v1/portal/companion/state")
    assert default_resp.status_code == 200
    default_state = default_resp.json()
    assert default_state["zero_runtime_tts_api"] is True
    assert "media_manifest" in default_state
    assert default_state["media_manifest"]["status"] in {"ready_for_batch4_audio", "studio_audio_ready"}
    assert default_state["studio_audio_ready"] is (default_state["media_manifest"]["status"] == "studio_audio_ready")

    # 2. Populated local studio audio build via PDEUE_COMPANION_MEDIA_DIR
    audio_builder.build_companion_audio(
        provider=audio_builder.MockTTSProvider(),
        output_dir=tmp_path,
        only_beat_ids=["ch0_orientation", "ch1_b1"],
    )
    # Inject hostile external CDN + missing 404 + path-traversal entries to verify fail-closed filtering
    manifest_path = tmp_path / "manifest.json"
    mutated = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutated["tracks"]["mentor_f_aa"]["cdn_hack"] = {
        "mp3": "https://cdn.example.com/evil.mp3",
        "vtt": "https://cdn.example.com/evil.vtt",
    }
    mutated["tracks"]["mentor_f_aa"]["missing_404"] = {
        "mp3": "/static/media/companion/mentor_f_aa/does_not_exist.mp3",
    }
    mutated["tracks"]["mentor_f_aa"]["traversal_hack"] = {
        "mp3": "/static/media/companion/../../secret.mp3",
    }
    manifest_path.write_text(json.dumps(mutated), encoding="utf-8")

    monkeypatch.setenv("PDEUE_COMPANION_MEDIA_DIR", str(tmp_path))
    live_resp = client.get("/api/v1/portal/companion/state")
    assert live_resp.status_code == 200
    live_state = live_resp.json()
    assert live_state["studio_audio_ready"] is True
    assert live_state["zero_runtime_tts_api"] is True
    mm = live_state["media_manifest"]
    assert mm["status"] == "studio_audio_ready"
    f_tracks = mm["tracks"]["mentor_f_aa"]
    assert set(f_tracks.keys()) == {"ch0_orientation", "ch1_b1"}
    assert "cdn_hack" not in f_tracks
    assert "missing_404" not in f_tracks
    assert "traversal_hack" not in f_tracks
    assert f_tracks["ch1_b1"]["mp3"] == "/static/media/companion/mentor_f_aa/ch1_b1.mp3"
    assert f_tracks["ch1_b1"]["vtt"] == "/static/media/companion/mentor_f_aa/ch1_b1.vtt"


def test_batch4_preserves_ui_lexicon_curriculum_parity_and_registered_openapi_routes():
    report = audit_ui_lexicon_curriculum_parity(REPO_ROOT)
    assert report["passed"] is True
    assert report["undocumented_controls"] == []
    assert report["dangling_data_terms"] == []
    assert report["jargon_violations"] == []
    assert set(report["portals_scanned"]) == set(PORTALS.keys())

    inventory_md = (REPO_ROOT / "docs" / "PORTAL_COMPONENT_INVENTORY.md").read_text(encoding="utf-8")
    assert inventory_md == generate_inventory(REPO_ROOT)
