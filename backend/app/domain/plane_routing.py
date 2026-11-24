"""4-Domain Air-Gapped Plane Routing Configuration (Zero-Rewrite Cutover).

Strictly social/navigation metadata only — ZERO imports of trading daemons,
CapitalLedger, TwoTierRiskEnvelope, CredentialBroker, or venue adapters.

Production Domain Topology (never touches carm-aerotech.com or narratixai.com):
- FAMILY_HUB_BASE_URL      -> https://narratixai.org       (/home, /community, /community/heritage)
- UNIVERSITY_BASE_URL      -> https://narratixai.info      (/companion)
- PDEUE_VAULT_BASE_URL     -> https://vault.narratixai.io  (/member, /advisor, /lineage/house/{id})
- PDEUE_ADMIN_BASE_URL     -> https://admin.narratixai.io  (/dashboard, /admin/tech)
- IFAS_ACCOUNTING_BASE_URL -> https://narratixai.net       (standalone IFAS banking/tax/accounting)

In local, Codespaces, and CI modes all base URLs default to "" (relative paths)
so all doorway links work seamlessly on a single FastAPI server without code changes.
"""
from __future__ import annotations

import os
from typing import Any, Dict
from urllib.parse import urlparse

PROHIBITED_DOMAINS: tuple[str, ...] = ("carm-aerotech.com", "narratixai.com")

PLANE_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "family_hub": {
        "env_var": "FAMILY_HUB_BASE_URL",
        "production_target": "https://narratixai.org",
        "label": "Family Hub & Heritage",
        "plane_badge": "Family Social Space — No Financial Data",
        "financial_data_present": False,
        "routes": ["/home", "/community", "/community/heritage"],
    },
    "university": {
        "env_var": "UNIVERSITY_BASE_URL",
        "production_target": "https://narratixai.info",
        "label": "PDEUE University",
        "plane_badge": "Plain-English Learning Campus — No Financial Data",
        "financial_data_present": False,
        "routes": ["/companion"],
    },
    "pdeue_vault": {
        "env_var": "PDEUE_VAULT_BASE_URL",
        "production_target": "https://vault.narratixai.io",
        "label": "Personal Account Vault",
        "plane_badge": "Personal Account Vault",
        "financial_data_present": True,
        "routes": ["/member", "/advisor", "/lineage/house/{id}"],
    },
    "pdeue_admin": {
        "env_var": "PDEUE_ADMIN_BASE_URL",
        "production_target": "https://admin.narratixai.io",
        "label": "Operator & Sovereign Control Plane",
        "plane_badge": "Sovereign & Technical Operations Plane",
        "financial_data_present": True,
        "routes": ["/dashboard", "/admin/tech"],
    },
    "ifas_accounting": {
        "env_var": "IFAS_ACCOUNTING_BASE_URL",
        "production_target": "https://narratixai.net",
        "label": "Banking & Tax Statements (IFAS)",
        "plane_badge": "Independent Financial Accounting System (ADR-011 Air-Gap)",
        "financial_data_present": True,
        "routes": ["/"],
    },
}


def _normalize_base_url(raw: str | None) -> str:
    """Normalize an optional base URL; fail closed if a prohibited domain is configured."""
    value = (raw or "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    for blocked in PROHIBITED_DOMAINS:
        if host == blocked or host.endswith(f".{blocked}"):
            raise ValueError(
                f"Prohibited domain '{host}' cannot be bound to a PDEUE/Family plane."
            )
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid plane base URL '{value}': expected http(s)://host.")
    return value


def get_base_url(env_var: str) -> str:
    """Read and normalize one plane base URL from environment (defaults to relative '')."""
    return _normalize_base_url(os.getenv(env_var, ""))


def join_plane_url(base_url: str, path: str) -> str:
    """Join an optional plane base URL with an absolute route path."""
    clean_path = path if path.startswith("/") else f"/{path}"
    if not base_url:
        return clean_path
    return f"{base_url.rstrip('/')}{clean_path}"


def get_plane_config() -> Dict[str, Any]:
    """Return read-only, secret-free 4-domain plane routing metadata & resolved doorway links."""
    planes: Dict[str, Dict[str, Any]] = {}
    any_configured = False

    for key, spec in PLANE_DEFINITIONS.items():
        base_url = get_base_url(spec["env_var"])
        configured = bool(base_url)
        if configured:
            any_configured = True
        planes[key] = {
            "plane_key": key,
            "env_var": spec["env_var"],
            "base_url": base_url,
            "production_target": spec["production_target"],
            "configured": configured,
            "label": spec["label"],
            "plane_badge": spec["plane_badge"],
            "financial_data_present": spec["financial_data_present"],
            "routes": list(spec["routes"]),
        }

    family_base = planes["family_hub"]["base_url"]
    uni_base = planes["university"]["base_url"]
    vault_base = planes["pdeue_vault"]["base_url"]
    admin_base = planes["pdeue_admin"]["base_url"]
    ifas_base = planes["ifas_accounting"]["base_url"]

    doorways = {
        "home": join_plane_url(family_base, "/home"),
        "community": join_plane_url(family_base, "/community"),
        "heritage": join_plane_url(family_base, "/community/heritage"),
        "genealogist_desk": f"{join_plane_url(family_base, '/community/heritage')}#genealogist-desk",
        "companion": join_plane_url(uni_base, "/companion"),
        "member": join_plane_url(vault_base, "/member"),
        "advisor": join_plane_url(vault_base, "/advisor"),
        "lineage_house_template": join_plane_url(vault_base, "/lineage/house/{house_id}"),
        "dashboard": join_plane_url(admin_base, "/dashboard"),
        "tech": join_plane_url(admin_base, "/admin/tech"),
        "ifas": ifas_base,
        "ifas_configured": bool(ifas_base),
        "ifas_production_target": planes["ifas_accounting"]["production_target"],
    }

    return {
        "routing_mode": "multi_domain_air_gapped" if any_configured else "relative_single_host",
        "air_gapped_social_plane": True,
        "prohibited_corporate_domains_untouched": list(PROHIBITED_DOMAINS),
        "planes": planes,
        "doorways": doorways,
    }


def resolve_lineage_house_url(house_id: int) -> str:
    """Resolve the vault URL for a specific House (1..12)."""
    safe_house = max(1, min(12, int(house_id)))
    vault_base = get_base_url("PDEUE_VAULT_BASE_URL")
    return join_plane_url(vault_base, f"/lineage/house/{safe_house}")
