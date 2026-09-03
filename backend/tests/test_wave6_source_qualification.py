import pytest
from app.domain.source_qualification import SourceQualificationRegistry

def test_source_qualification_valid():
    reg = SourceQualificationRegistry()
    reg.register_source(
        source_id="SRC-NOAA-01",
        name="NOAA GFS Weather Feed",
        license_type="US_PUBLIC_DOMAIN",
        quality_tier="TIER_1",
        is_public_or_lawful=True,
        commercial_allowed=True
    )
    res = reg.evaluate_source("SRC-NOAA-01")
    assert res["qualified"] is True
    assert res["quality_tier"] == "TIER_1"
    assert res["reason"] == "QUALIFIED"

def test_source_qualification_unlawful_or_expired():
    reg = SourceQualificationRegistry()
    reg.register_source(
        source_id="SRC-LEAK-01",
        name="Confidential Feed",
        license_type="UNAUTHORIZED",
        quality_tier="TIER_3",
        is_public_or_lawful=False
    )
    res_leak = reg.evaluate_source("SRC-LEAK-01")
    assert res_leak["qualified"] is False
    assert res_leak["reason"] == "UNLAWFUL_OR_NONPUBLIC_DATA"

    reg.register_source(
        source_id="SRC-PAID-01",
        name="Expiring Data Feed",
        license_type="COMMERCIAL_EULA",
        quality_tier="TIER_2",
        expires_at="2025-01-01T00:00:00Z"
    )
    res_expired = reg.evaluate_source("SRC-PAID-01", current_time_iso="2026-09-03T00:00:00Z")
    assert res_expired["qualified"] is False
    assert res_expired["reason"] == "SOURCE_LICENSE_EXPIRED"

def test_source_unregistered():
    reg = SourceQualificationRegistry()
    res = reg.evaluate_source("SRC-UNKNOWN")
    assert res["qualified"] is False
    assert res["reason"] == "SOURCE_NOT_REGISTERED"
