"""PR #95 Verification Suite:
1. MPEG-1/2/2.5 Layer III duration parsing & --resync-vtt-only across all 50 Studio Mentor tracks ($0 API cost).
2. Canonical Class H & House Genealogist Manual + /companion wiring.
3. Upgradeable Local Media & Role Playbook Registry + GET /api/v1/portal/companion/playbooks filtering.
4. Upgraded portal_discovery.py (<select>, <textarea>, <details> + Playbook coverage).
5. Zero external CDN links and byte-for-byte parity across all 9 dual-served HTML templates.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import sys

from fastapi.testclient import TestClient
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.domain.training_media_registry import (  # noqa: E402
    CANONICAL_ROLE_CLASSES,
    ROLE_FAMILIES,
    SUPPORTED_MEDIA_TYPES,
    load_training_media_registry,
    validate_training_media_registry,
)
from app.main import app  # noqa: E402
from app.portal_discovery import (  # noqa: E402
    PORTALS,
    ComponentParser,
    audit_ui_lexicon_curriculum_parity,
    generate_inventory,
)
from scripts import build_companion_audio as audio_builder  # noqa: E402

COMPANION_MEDIA_DIR = BACKEND_DIR / "app" / "static" / "media" / "companion"
PLAYBOOKS_DIR = BACKEND_DIR / "app" / "static" / "media" / "playbooks"
CLASS_H_MANUAL_PATH = REPO_ROOT / "docs" / "manuals" / "CLASS_H_LINEAGE_AND_HERITAGE_MANUAL.md"

NINE_PORTAL_TEMPLATES = (
    "home.html",
    "dashboard.html",
    "member.html",
    "tech.html",
    "advisor.html",
    "lineage_house.html",
    "community.html",
    "heritage.html",
    "companion.html",
)

_VTT_CUE_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s+-->\s+(\d{2}):(\d{2}):(\d{2})\.(\d{3})"
)


def _hms_to_seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def _build_synthetic_mp3(version_bits: int, bitrate_idx: int, sample_idx: int, frame_count: int) -> bytes:
    """Construct valid synthetic MPEG-1, MPEG-2, or MPEG-2.5 Layer III frames."""
    is_mpeg1 = version_bits == 3
    br_table = audio_builder._MPEG1_L3_BITRATES_KBPS if is_mpeg1 else audio_builder._MPEG2_L3_BITRATES_KBPS
    sr = audio_builder._MPEG_SAMPLE_RATES_BY_VERSION[version_bits][sample_idx]
    br = br_table[bitrate_idx]
    coef = 144 if is_mpeg1 else 72
    frame_len = (coef * br * 1000) // sr
    b0 = 0xFF
    b1 = 0xE0 | (version_bits << 3) | (1 << 1) | 1  # sync + version + Layer III + no CRC
    b2 = (bitrate_idx << 4) | (sample_idx << 2)
    b3 = 0x00
    header = bytes([b0, b1, b2, b3])
    frame = header + (b"\x00" * (frame_len - 4))
    return frame * frame_count


# ---------------------------------------------------------------------------
# 1. MPEG-1/2/2.5 Duration Parsing & 50-Track WebVTT Synchronization
# ---------------------------------------------------------------------------


def test_estimate_mp3_duration_supports_mpeg1_mpeg2_and_mpeg25() -> None:
    # MPEG-1 Layer III: 128 kbps, 44100 Hz, 1152 samples/frame -> 100 frames = 2.612s
    mpeg1_bytes = _build_synthetic_mp3(version_bits=3, bitrate_idx=9, sample_idx=0, frame_count=100)
    assert abs(audio_builder.estimate_mp3_duration_seconds(mpeg1_bytes, "fallback") - round(100 * 1152 / 44100, 3)) < 0.002

    # MPEG-2 Layer III: 48 kbps (idx 6), 24000 Hz (idx 1), 576 samples/frame -> 500 frames = 12.000s
    mpeg2_bytes = _build_synthetic_mp3(version_bits=2, bitrate_idx=6, sample_idx=1, frame_count=500)
    assert abs(audio_builder.estimate_mp3_duration_seconds(mpeg2_bytes, "fallback") - 12.0) < 0.002

    # MPEG-2.5 Layer III: 32 kbps (idx 4), 12000 Hz (idx 1), 576 samples/frame -> 250 frames = 12.000s
    mpeg25_bytes = _build_synthetic_mp3(version_bits=0, bitrate_idx=4, sample_idx=1, frame_count=250)
    assert abs(audio_builder.estimate_mp3_duration_seconds(mpeg25_bytes, "fallback") - 12.0) < 0.002


def test_all_50_companion_tracks_have_accurate_durations_and_non_compressed_vtt() -> None:
    manifest_path = COMPANION_MEDIA_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tracks_by_voice = manifest["tracks"]
    assert set(tracks_by_voice.keys()) == {"mentor_f_aa", "mentor_m_aa"}

    total_tracks = 0
    for voice_id, tracks in tracks_by_voice.items():
        assert len(tracks) == 25, f"{voice_id} expected 25 tracks, got {len(tracks)}"
        for beat_id, meta in tracks.items():
            total_tracks += 1
            mp3_file = COMPANION_MEDIA_DIR / voice_id / f"{beat_id}.mp3"
            vtt_file = COMPANION_MEDIA_DIR / voice_id / f"{beat_id}.vtt"
            assert mp3_file.is_file() and mp3_file.stat().st_size > 10_000
            assert vtt_file.is_file() and vtt_file.stat().st_size > 40

            recomputed = audio_builder.estimate_mp3_duration_seconds(mp3_file.read_bytes(), beat_id)
            manifest_dur = float(meta["duration_seconds"])
            assert manifest_dur >= 8.0, f"{voice_id}/{beat_id} duration looks compressed: {manifest_dur}s"
            assert abs(manifest_dur - recomputed) <= 0.01, (
                f"{voice_id}/{beat_id} manifest duration {manifest_dur}s != recomputed {recomputed}s"
            )

            vtt_text = vtt_file.read_text(encoding="utf-8")
            assert vtt_text.startswith("WEBVTT\n")
            cues = [
                (_hms_to_seconds(*m.groups()[:4]), _hms_to_seconds(*m.groups()[4:]))
                for m in _VTT_CUE_RE.finditer(vtt_text)
            ]
            assert len(cues) >= 2, f"{voice_id}/{beat_id} expected >= 2 cues"
            prev_end = 0.0
            for start_s, end_s in cues:
                assert start_s >= prev_end - 0.002
                assert end_s > start_s
                prev_end = end_s
            assert abs(cues[-1][1] - manifest_dur) <= 0.05, (
                f"{voice_id}/{beat_id} VTT end {cues[-1][1]}s does not match track duration {manifest_dur}s"
            )

    assert total_tracks == 50


def test_resync_vtt_only_works_offline_with_zero_api_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    voice_dir = tmp_path / "mentor_f_aa"
    voice_dir.mkdir(parents=True)
    shutil.copy2(COMPANION_MEDIA_DIR / "mentor_f_aa" / "ch0_orientation.mp3", voice_dir / "ch0_orientation.mp3")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"provider": "deepgram", "voices": [{"id": "mentor_f_aa", "provider": "deepgram", "model": "aura-2-athena-en"}], "tracks": {}}),
        encoding="utf-8",
    )

    rc = audio_builder.main(
        [
            "--resync-vtt-only",
            "--output-dir",
            str(tmp_path),
            "--voices",
            "mentor_f_aa",
            "--only",
            "ch0_orientation",
        ]
    )
    assert rc == 0
    out_manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    track = out_manifest["tracks"]["mentor_f_aa"]["ch0_orientation"]
    assert track["provider"] == "deepgram"
    assert track["model"] == "aura-2-athena-en"
    assert track["duration_seconds"] > 20.0
    assert (voice_dir / "ch0_orientation.vtt").is_file()


# ---------------------------------------------------------------------------
# 2. Canonical Class H & House Genealogist Manual + /companion Wiring
# ---------------------------------------------------------------------------


def test_class_h_manual_exists_complete_and_served_via_api() -> None:
    assert CLASS_H_MANUAL_PATH.is_file(), "CLASS_H_LINEAGE_AND_HERITAGE_MANUAL.md missing"
    text = CLASS_H_MANUAL_PATH.read_text(encoding="utf-8")
    assert len(text) >= 12_000, "Class H manual should match depth of existing manuals"

    required_tokens = (
        "H1",
        "H2",
        "HOUSE_GENEALOGIST",
        "/lineage/house/{id}",
        "/community/heritage",
        "Directive R-12",
        "$****.**",
        "Freeze Dial (0%)",
        "Cancel Orders",
        "Sovereign Immune",
        "FOUNDER_APEX_IMMUNITY_VIOLATION",
        "ADVISORY_PETITION_FILTER",
        "BICAMERAL_VETO_ACTIVE",
        "EXECUTIVE_COMMAND",
        "IMMUTABLE_CORE_INVARIANT",
        "SHTF",
        "Bordure Differencing",
        "ADR-008",
        "ADR-011",
        "ADR-012",
        "Rule A14",
        "FSAP (Phase II)",
        "HTTP 403",
    )
    for token in required_tokens:
        assert token in text, f"CLASS_H_LINEAGE_AND_HERITAGE_MANUAL.md missing required token: {token}"
    assert re.search(r"\bLCCF\b", text) is None, "Stale visible LCCF token found in Class H manual"

    client = TestClient(app)
    resp = client.get("/api/v1/portal/companion/manual/CLASS_H_LINEAGE_AND_HERITAGE_MANUAL.md")
    assert resp.status_code == 200
    assert "Class H Lineage Governance and House Genealogist Manual" in resp.text

    companion_html = (BACKEND_DIR / "app" / "api" / "v1" / "companion.html").read_text(encoding="utf-8")
    assert 'data-manual-card="CLASS_H_LINEAGE_AND_HERITAGE_MANUAL.md"' in companion_html
    assert 'data-manual-load="CLASS_H_LINEAGE_AND_HERITAGE_MANUAL.md"' in companion_html
    assert '<option value="CLASS_H_LINEAGE_AND_HERITAGE_MANUAL.md">' in companion_html


# ---------------------------------------------------------------------------
# 3. Local Media & Role Playbook Registry + API Filtering
# ---------------------------------------------------------------------------


def test_training_media_registry_validates_and_all_local_files_exist() -> None:
    registry = load_training_media_registry()
    errors = validate_training_media_registry(registry, repo_root=REPO_ROOT, check_files=True)
    assert errors == [], f"Registry validation errors: {errors}"

    assert registry["zero_cdn"] is True
    assert set(SUPPORTED_MEDIA_TYPES).issubset(set(registry["supported_media_types"]))
    assert set(CANONICAL_ROLE_CLASSES).issubset(set(registry["role_classes"]))

    # Verify all 5 role families have BOTH routine and outlier_incident playbooks
    for fam, members in ROLE_FAMILIES.items():
        fam_pbs = [
            pb
            for pb in registry["playbooks"]
            if any(rc in members for rc in pb["role_classes"])
        ]
        scenarios = {pb["scenario_type"] for pb in fam_pbs}
        assert {"routine", "outlier_incident"}.issubset(scenarios), (
            f"Role family {fam} missing routine or outlier_incident playbook (found {scenarios})"
        )

    # Verify curated screenshot set physically exists under backend/app/static/media/playbooks/screenshots/
    screenshots = list((PLAYBOOKS_DIR / "screenshots").glob("*.png"))
    assert len(screenshots) >= 10, f"Expected >= 10 curated annotated screenshots, found {len(screenshots)}"
    for shot in screenshots:
        assert shot.stat().st_size > 10_000, f"Screenshot too small/corrupt: {shot}"


def test_companion_playbooks_api_filtering() -> None:
    client = TestClient(app)

    all_resp = client.get("/api/v1/portal/companion/playbooks")
    assert all_resp.status_code == 200
    all_data = all_resp.json()
    assert all_data["zero_cdn"] is True
    assert all_data["matched_count"] == all_data["total_playbooks"] >= 10

    # Role family filter (CLASS_H) + scenario filter (outlier_incident)
    h_out = client.get("/api/v1/portal/companion/playbooks", params={"role": "CLASS_H", "scenario_type": "outlier_incident"})
    assert h_out.status_code == 200
    h_data = h_out.json()
    assert h_data["matched_count"] >= 1
    for pb in h_data["playbooks"]:
        assert pb["scenario_type"] == "outlier_incident"
        assert any(r in {"H1", "H2", "HOUSE_GENEALOGIST"} for r in pb["role_classes"])

    # Exact sub-role filter (F3, HOUSE_GENEALOGIST, CHIEF_ADMIN_DEPUTY, T2-HOUSEHOLD)
    for role_tok in ("F3", "F2-H", "T3", "T2-HOUSEHOLD", "H2", "HOUSE_GENEALOGIST", "CHIEF_ADMIN_DEPUTY", "CLASS_M"):
        r = client.get("/api/v1/portal/companion/playbooks", params={"role": role_tok})
        assert r.status_code == 200
        payload = r.json()
        assert payload["matched_count"] >= 1, f"Expected >= 1 playbook for role={role_tok}"
        for pb in payload["playbooks"]:
            assert role_tok in pb["role_classes"]

    # Scenario-only filter
    routine_resp = client.get("/api/v1/portal/companion/playbooks", params={"scenario_type": "routine"})
    assert routine_resp.status_code == 200
    assert routine_resp.json()["matched_count"] >= 5
    assert all(pb["scenario_type"] == "routine" for pb in routine_resp.json()["playbooks"])


# ---------------------------------------------------------------------------
# 4. Upgraded portal_discovery.py Coverage & Parity
# ---------------------------------------------------------------------------


def test_portal_discovery_inventories_select_textarea_details_and_playbooks() -> None:
    parser = ComponentParser()
    parser.feed(
        """
        <button id="b1">Run</button>
        <input id="i1" placeholder="Type">
        <select id="s1" aria-label="Role"><option>A</option></select>
        <textarea id="ta1" placeholder="Notes"></textarea>
        <details id="d1"><summary>Open Studio</summary><p>Body</p></details>
        """
    )
    kinds = {c["kind"] for c in parser.components}
    assert {"button", "input", "select", "textarea", "details"}.issubset(kinds)
    details_item = next(c for c in parser.components if c["kind"] == "details")
    assert details_item["id"] == "d1"
    assert details_item["label"] == "Open Studio"

    audit = audit_ui_lexicon_curriculum_parity(REPO_ROOT)
    assert audit["passed"] is True, f"Parity audit failed: {audit}"
    assert audit["playbook_coverage"]["registry_present"] is True
    assert audit["playbook_coverage"]["total_playbooks"] >= 10
    for route in PORTALS:
        assert audit["portal_catalog"][route]["playbook_count"] >= 1, f"Route {route} has 0 linked playbooks"

    inventory_md = (REPO_ROOT / "docs" / "PORTAL_COMPONENT_INVENTORY.md").read_text(encoding="utf-8")
    assert generate_inventory(REPO_ROOT) == inventory_md
    assert "## Playbook & Visual Media Registry Coverage" in inventory_md


# ---------------------------------------------------------------------------
# 5. Zero-CDN & Byte-for-Byte Parity Across All 9 Dual-Served HTML Templates
# ---------------------------------------------------------------------------


def test_zero_cdn_and_byte_parity_across_all_9_portal_templates() -> None:
    external_tag_re = re.compile(r"<(?:script|link)\b[^>]+(?:src|href)\s*=\s*['\"]https?://", re.IGNORECASE)
    for filename in NINE_PORTAL_TEMPLATES:
        api_path = BACKEND_DIR / "app" / "api" / "v1" / filename
        static_path = BACKEND_DIR / "app" / "static" / filename
        assert api_path.is_file(), f"Missing {api_path}"
        assert static_path.is_file(), f"Missing {static_path}"
        api_bytes = api_path.read_bytes()
        static_bytes = static_path.read_bytes()
        assert api_bytes == static_bytes, f"Byte-for-byte parity mismatch for {filename}"
        assert external_tag_re.search(api_bytes.decode("utf-8")) is None, f"External CDN tag detected in {filename}"
