"""Upgradeable Local Media & Role Playbook Registry loader and validator for PDEUE University.

All media assets (annotated screenshots, SVG diagrams, slide decks, and optional motion clips)
are strictly local static files under `backend/app/static/media/playbooks/` with zero external CDNs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PLAYBOOKS_DIR = REPO_ROOT / "backend" / "app" / "static" / "media" / "playbooks"
DEFAULT_REGISTRY_PATH = DEFAULT_PLAYBOOKS_DIR / "registry.json"
PLAYBOOKS_URL_PREFIX = "/static/media/playbooks/"

SUPPORTED_MEDIA_TYPES: Tuple[str, ...] = (
    "annotated_screenshot",
    "diagram_svg",
    "slide_deck",
    "motion_clip",
)

CANONICAL_ROLE_CLASSES: Tuple[str, ...] = (
    "CHIEF_ADMIN",
    "CHIEF_ADMIN_DEPUTY",
    "T1",
    "T2",
    "T2-HOUSEHOLD",
    "T3",
    "F1",
    "F2-H",
    "F2-A",
    "F3",
    "H1",
    "H2",
    "HOUSE_GENEALOGIST",
    "CLASS_M",
)
CANONICAL_ROLE_SET = frozenset(CANONICAL_ROLE_CLASSES)

ROLE_FAMILIES: Dict[str, Tuple[str, ...]] = {
    "CHIEF_ADMIN": ("CHIEF_ADMIN", "CHIEF_ADMIN_DEPUTY"),
    "CLASS_T": ("T1", "T2", "T2-HOUSEHOLD", "T3"),
    "CLASS_F": ("F1", "F2-H", "F2-A", "F3"),
    "CLASS_H": ("H1", "H2", "HOUSE_GENEALOGIST"),
    "CLASS_M": ("CLASS_M",),
}

SCENARIO_TYPES: Tuple[str, ...] = ("routine", "outlier_incident")
SCENARIO_TYPE_SET = frozenset(SCENARIO_TYPES)


def _normalize_role_filter(raw_role: Optional[str]) -> Optional[Tuple[str, ...]]:
    if not raw_role or not raw_role.strip():
        return None
    token = raw_role.strip().upper().replace("_", "-")
    # Restore canonical underscore tokens
    underscore_aliases = {
        "CHIEF-ADMIN": "CHIEF_ADMIN",
        "CHIEF-ADMIN-DEPUTY": "CHIEF_ADMIN_DEPUTY",
        "HOUSE-GENEALOGIST": "HOUSE_GENEALOGIST",
        "CLASS-M": "CLASS_M",
        "CLASS-F": "CLASS_F",
        "CLASS-T": "CLASS_T",
        "CLASS-H": "CLASS_H",
        "MEMBER": "CLASS_M",
        "MEMBER-USER": "CLASS_M",
    }
    normalized = underscore_aliases.get(token, token)
    if normalized in ROLE_FAMILIES:
        return ROLE_FAMILIES[normalized]
    if normalized in CANONICAL_ROLE_SET:
        return (normalized,)
    return (normalized,)


def load_training_media_registry(registry_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load the canonical local playbook & media registry JSON."""
    target = Path(registry_path) if registry_path is not None else DEFAULT_REGISTRY_PATH
    if not target.is_file():
        raise FileNotFoundError(f"Training media registry not found: {target}")
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Training media registry root must be a JSON object")
    return data


def _resolve_static_asset_path(static_url: str, repo_root: Path) -> Optional[Path]:
    if not isinstance(static_url, str) or not static_url.startswith(PLAYBOOKS_URL_PREFIX):
        return None
    if "://" in static_url or ".." in static_url:
        return None
    rel = static_url[len(PLAYBOOKS_URL_PREFIX):].lstrip("/")
    if not rel:
        return None
    return repo_root / "backend" / "app" / "static" / "media" / "playbooks" / rel


def validate_training_media_registry(
    registry: Dict[str, Any],
    *,
    repo_root: Optional[Path] = None,
    check_files: bool = True,
) -> List[str]:
    """Validate registry schema, zero-CDN containment, role coverage, and physical asset presence."""
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    errors: List[str] = []

    if registry.get("zero_cdn") is not True:
        errors.append("registry.zero_cdn must be true")

    supported = registry.get("supported_media_types")
    if not isinstance(supported, list) or not set(SUPPORTED_MEDIA_TYPES).issubset(set(supported)):
        errors.append(f"registry.supported_media_types must include all of {SUPPORTED_MEDIA_TYPES}")

    playbooks = registry.get("playbooks")
    if not isinstance(playbooks, list) or not playbooks:
        errors.append("registry.playbooks must be a non-empty list")
        return errors

    seen_ids: set[str] = set()
    family_scenarios: Dict[str, set[str]] = {fam: set() for fam in ROLE_FAMILIES}

    for idx, pb in enumerate(playbooks):
        if not isinstance(pb, dict):
            errors.append(f"playbooks[{idx}] must be an object")
            continue
        pb_id = str(pb.get("playbook_id") or "").strip()
        if not pb_id:
            errors.append(f"playbooks[{idx}] missing playbook_id")
            pb_id = f"index-{idx}"
        elif pb_id in seen_ids:
            errors.append(f"Duplicate playbook_id: {pb_id}")
        seen_ids.add(pb_id)

        if not str(pb.get("title") or "").strip():
            errors.append(f"{pb_id}: missing title")

        role_classes = pb.get("role_classes")
        if not isinstance(role_classes, list) or not role_classes:
            errors.append(f"{pb_id}: role_classes must be a non-empty list")
            role_classes = []
        else:
            for rc in role_classes:
                if rc not in CANONICAL_ROLE_SET:
                    errors.append(f"{pb_id}: unknown role_class {rc!r}")

        scenario_type = pb.get("scenario_type")
        if scenario_type not in SCENARIO_TYPE_SET:
            errors.append(f"{pb_id}: scenario_type must be one of {SCENARIO_TYPES}, got {scenario_type!r}")
        else:
            for fam, members in ROLE_FAMILIES.items():
                if any(rc in members for rc in role_classes):
                    family_scenarios[fam].add(scenario_type)

        portal_route = str(pb.get("portal_route") or "").strip()
        if not portal_route.startswith("/"):
            errors.append(f"{pb_id}: portal_route must start with '/'")

        control_ids = pb.get("control_ids")
        if not isinstance(control_ids, list) or not control_ids or not all(isinstance(c, str) and c.strip() for c in control_ids):
            errors.append(f"{pb_id}: control_ids must be a non-empty list of DOM IDs")

        manual_anchor = str(pb.get("manual_anchor") or "").strip()
        if not manual_anchor.startswith("docs/manuals/") or ".md" not in manual_anchor:
            errors.append(f"{pb_id}: manual_anchor must reference docs/manuals/*.md (#section)")
        elif check_files:
            manual_rel = manual_anchor.split("#", 1)[0]
            if not (root / manual_rel).is_file():
                errors.append(f"{pb_id}: referenced manual file missing: {manual_rel}")

        steps = pb.get("steps")
        if not isinstance(steps, list) or not steps:
            errors.append(f"{pb_id}: steps must be a non-empty ordered checklist")
        else:
            for s_idx, step in enumerate(steps):
                if isinstance(step, dict):
                    if not str(step.get("action") or "").strip() or not str(step.get("effect") or "").strip():
                        errors.append(f"{pb_id}: steps[{s_idx}] must include non-empty action and effect")
                elif not isinstance(step, str) or not step.strip():
                    errors.append(f"{pb_id}: steps[{s_idx}] invalid")

        assets = pb.get("media_assets")
        if not isinstance(assets, list) or not assets:
            errors.append(f"{pb_id}: media_assets must be a non-empty list")
            continue
        for a_idx, asset in enumerate(assets):
            if not isinstance(asset, dict):
                errors.append(f"{pb_id}: media_assets[{a_idx}] must be an object")
                continue
            mtype = asset.get("media_type")
            if mtype not in SUPPORTED_MEDIA_TYPES:
                errors.append(f"{pb_id}: media_assets[{a_idx}] unsupported media_type {mtype!r}")
            if not isinstance(asset.get("narrated"), bool):
                errors.append(f"{pb_id}: media_assets[{a_idx}] narrated must be a boolean")
            if asset.get("replaceable") is not True:
                errors.append(f"{pb_id}: media_assets[{a_idx}] replaceable must be true")
            if not str(asset.get("caption") or "").strip():
                errors.append(f"{pb_id}: media_assets[{a_idx}] missing caption")
            legend = asset.get("callout_legend")
            if not isinstance(legend, list) or not legend:
                errors.append(f"{pb_id}: media_assets[{a_idx}] callout_legend must be a non-empty list")
            path_val = asset.get("path", "")
            resolved = _resolve_static_asset_path(str(path_val), root)
            if resolved is None:
                errors.append(
                    f"{pb_id}: media_assets[{a_idx}] path must be local under {PLAYBOOKS_URL_PREFIX} (got {path_val!r})"
                )
            elif check_files and (not resolved.is_file() or resolved.stat().st_size == 0):
                errors.append(f"{pb_id}: media_assets[{a_idx}] file missing or empty: {resolved}")

    for fam, scenarios in family_scenarios.items():
        missing = set(SCENARIO_TYPES) - scenarios
        if missing:
            errors.append(f"Role family {fam} missing playbook scenario_type(s): {sorted(missing)}")

    return errors


def list_playbooks(
    *,
    role: Optional[str] = None,
    scenario_type: Optional[str] = None,
    media_type: Optional[str] = None,
    portal_route: Optional[str] = None,
    registry_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Return filtered playbooks and summary metadata for GET /api/v1/portal/companion/playbooks."""
    registry = load_training_media_registry(registry_path)
    all_playbooks: List[Dict[str, Any]] = list(registry.get("playbooks", []))

    role_tokens = _normalize_role_filter(role)
    scenario_norm = scenario_type.strip().lower() if scenario_type and scenario_type.strip() else None
    media_norm = media_type.strip().lower() if media_type and media_type.strip() else None
    route_norm = portal_route.strip() if portal_route and portal_route.strip() else None

    filtered: List[Dict[str, Any]] = []
    for pb in all_playbooks:
        if role_tokens is not None:
            pb_roles = set(pb.get("role_classes") or [])
            if not any(tok in pb_roles for tok in role_tokens):
                continue
        if scenario_norm is not None and str(pb.get("scenario_type") or "").lower() != scenario_norm:
            continue
        if route_norm is not None and str(pb.get("portal_route") or "") != route_norm:
            continue
        if media_norm is not None:
            assets = pb.get("media_assets") or []
            if not any(str(a.get("media_type") or "").lower() == media_norm for a in assets):
                continue
        filtered.append(pb)

    return {
        "schema_version": registry.get("schema_version", "1.0"),
        "zero_cdn": bool(registry.get("zero_cdn", True)),
        "supported_media_types": list(registry.get("supported_media_types", SUPPORTED_MEDIA_TYPES)),
        "role_classes": list(registry.get("role_classes", CANONICAL_ROLE_CLASSES)),
        "role_families": {k: list(v) for k, v in ROLE_FAMILIES.items()},
        "scenario_types": list(SCENARIO_TYPES),
        "filters": {
            "role": role.strip() if role and role.strip() else None,
            "scenario_type": scenario_norm,
            "media_type": media_norm,
            "portal_route": route_norm,
        },
        "total_playbooks": len(all_playbooks),
        "matched_count": len(filtered),
        "playbooks": filtered,
    }


def summarize_playbook_coverage(
    registry_path: Optional[Path] = None,
    *,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Compute per-portal and per-role-family playbook coverage metadata for portal_discovery.py."""
    target = Path(registry_path) if registry_path is not None else (
        (Path(repo_root) / "backend" / "app" / "static" / "media" / "playbooks" / "registry.json")
        if repo_root is not None
        else DEFAULT_REGISTRY_PATH
    )
    if not target.is_file():
        return {
            "registry_present": False,
            "total_playbooks": 0,
            "covered_control_ids": [],
            "by_portal": {},
            "by_role_family": {fam: {"routine": 0, "outlier_incident": 0} for fam in ROLE_FAMILIES},
            "media_asset_count": 0,
        }

    registry = load_training_media_registry(target)
    playbooks = registry.get("playbooks", [])
    by_portal: Dict[str, Dict[str, Any]] = {}
    covered_controls: set[str] = set()
    by_family: Dict[str, Dict[str, int]] = {
        fam: {"routine": 0, "outlier_incident": 0} for fam in ROLE_FAMILIES
    }
    media_paths: set[str] = set()

    for pb in playbooks:
        route = str(pb.get("portal_route") or "").split("?", 1)[0]
        entry = by_portal.setdefault(route, {"playbook_ids": [], "control_ids": set(), "scenario_types": set()})
        entry["playbook_ids"].append(pb.get("playbook_id", ""))
        sc = str(pb.get("scenario_type") or "")
        if sc:
            entry["scenario_types"].add(sc)
        for cid in pb.get("control_ids") or []:
            entry["control_ids"].add(cid)
            covered_controls.add(cid)
        pb_roles = set(pb.get("role_classes") or [])
        for fam, members in ROLE_FAMILIES.items():
            if any(m in pb_roles for m in members) and sc in by_family[fam]:
                by_family[fam][sc] += 1
        for asset in pb.get("media_assets") or []:
            if asset.get("path"):
                media_paths.add(str(asset["path"]))

    serialized_by_portal = {
        route: {
            "playbook_count": len(info["playbook_ids"]),
            "playbook_ids": info["playbook_ids"],
            "taught_control_count": len(info["control_ids"]),
            "taught_control_ids": sorted(info["control_ids"]),
            "scenario_types": sorted(info["scenario_types"]),
        }
        for route, info in sorted(by_portal.items())
    }

    return {
        "registry_present": True,
        "total_playbooks": len(playbooks),
        "covered_control_count": len(covered_controls),
        "covered_control_ids": sorted(covered_controls),
        "by_portal": serialized_by_portal,
        "by_role_family": by_family,
        "media_asset_count": len(media_paths),
    }
