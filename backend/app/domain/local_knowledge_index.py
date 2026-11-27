"""Deterministic, zero-network, role-scoped Local Knowledge & Media Index for PDEUE tutors/copilots.

Indexes at startup (strictly from local repository files, zero outbound HTTP/LLM calls):
1. All 5 canonical role manuals in ``docs/manuals/`` chunked by Markdown section heading:
   - ``USER_QUICKSTART.md``
   - ``CHIEF_ADMIN_RUNBOOK.md``
   - ``CLASS_F_FINANCIAL_MANUAL.md``
   - ``CLASS_T_TECHNICAL_MANUAL.md``
   - ``CLASS_H_LINEAGE_AND_HERITAGE_MANUAL.md``
2. All local role playbooks and media assets from ``backend/app/static/media/playbooks/registry.json``
   via ``training_media_registry.py``.
3. All canonical Lexicon v0.5 / Plain-English v0.6 terms from ``lexicon_v05.py``.

Role Isolation Invariant:
- Non-Chief-Admin roles (``CLASS_M``, ``H1``, ``H2``, ``HOUSE_GENEALOGIST``, ``F1``–``F3``,
  ``T1``–``T3``) can ONLY retrieve playbooks whose ``role_classes`` authorize that exact role
  and manual sections belonging to manuals authorized for that role.
- Chief Admin runbook sections and Class T3 CA R-12 override playbooks are NEVER returned to
  ``CLASS_M``, ``H1``, ``H2``, ``HOUSE_GENEALOGIST``, or unauthorized sub-tiers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
import re
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

from app.domain.lexicon_v05 import LEXICON_BY_ID, LEXICON_TERMS
from app.domain.training_media_registry import (
    CANONICAL_ROLE_SET,
    DEFAULT_REGISTRY_PATH,
    PLAYBOOKS_URL_PREFIX,
    REPO_ROOT,
    load_training_media_registry,
)

MANUALS_DIR = REPO_ROOT / "docs" / "manuals"

CANONICAL_MANUAL_FILES: Tuple[str, ...] = (
    "USER_QUICKSTART.md",
    "CHIEF_ADMIN_RUNBOOK.md",
    "CLASS_F_FINANCIAL_MANUAL.md",
    "CLASS_T_TECHNICAL_MANUAL.md",
    "CLASS_H_LINEAGE_AND_HERITAGE_MANUAL.md",
)

ALL_ROLES_FROZEN: FrozenSet[str] = frozenset(CANONICAL_ROLE_SET)
CHIEF_ROLES: FrozenSet[str] = frozenset({"CHIEF_ADMIN", "CHIEF_ADMIN_DEPUTY"})
CLASS_F_ROLES: FrozenSet[str] = frozenset({"F1", "F2-H", "F2-A", "F3"})
CLASS_T_ROLES: FrozenSet[str] = frozenset({"T1", "T2", "T2-HOUSEHOLD", "T3"})
CLASS_H_ROLES: FrozenSet[str] = frozenset({"H1", "H2", "HOUSE_GENEALOGIST"})

MANUAL_ALLOWED_ROLES: Dict[str, FrozenSet[str]] = {
    "USER_QUICKSTART.md": ALL_ROLES_FROZEN,
    "CHIEF_ADMIN_RUNBOOK.md": CHIEF_ROLES,
    "CLASS_F_FINANCIAL_MANUAL.md": CLASS_F_ROLES | CHIEF_ROLES,
    "CLASS_T_TECHNICAL_MANUAL.md": CLASS_T_ROLES | CHIEF_ROLES,
    "CLASS_H_LINEAGE_AND_HERITAGE_MANUAL.md": CLASS_H_ROLES | CHIEF_ROLES,
}

_STOPWORDS: FrozenSet[str] = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "been", "being", "but", "by",
        "can", "could", "do", "does", "did", "for", "from", "get", "had", "has",
        "have", "he", "her", "here", "him", "his", "how", "i", "if", "in", "into",
        "is", "it", "its", "just", "me", "more", "my", "no", "not", "of", "on",
        "or", "our", "out", "she", "should", "so", "some", "that", "the", "their",
        "them", "then", "there", "these", "they", "this", "to", "up", "us", "was",
        "we", "were", "what", "when", "where", "which", "who", "why", "will", "with",
        "would", "you", "your", "please", "explain", "tell", "about", "simply", "work",
        "works", "use", "using", "show", "help", "need", "want",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-_/][a-z0-9]+)*%?")

# Internal PDEUE anchor markers — if present, a query is unambiguously PDEUE-internal
# even if it also mentions words like "weather" or "probability".
_INTERNAL_PDEUE_ANCHORS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:pdeue|scma|cfcp|faep|ifas|fsap|lccf|tpw|hwm|shtf|ext-ref)\b", re.IGNORECASE),
    re.compile(r"\b(?:adr-?008|adr-?011|adr-?012|rule\s+a14|gate\s+g1|auth-?0[1-4])\b", re.IGNORECASE),
    re.compile(r"\b(?:directive\s+r-?(?:04|06|07|08|12|13|15)|r-?04|r-?06|r-?12|r-?15)\b", re.IGNORECASE),
    re.compile(r"\b(?:87/10/3|high-?water\s+mark|dry-?powder|quarter-?kelly|risk\s+dial|brake\s+pedal)\b", re.IGNORECASE),
    re.compile(r"\b(?:shadow\s+paper|hunch\s+studio|family\s+hearth|hall\s+of\s+arms|pdeue\s+university|companion)\b", re.IGNORECASE),
    re.compile(r"\b(?:active[- ]hat|bordure|genealogist|house\s+secretary|house\s+head|bicameral|sovereign\s+immune)\b", re.IGNORECASE),
    re.compile(r"\b(?:class\s+[mft h]|f1|f2-?h|f2-?a|f3|t1|t2|t2-?household|t3|h1|h2|chief\s+admin|deputy)\b", re.IGNORECASE),
    re.compile(r"\b(?:kill\s+switch|red-?tier|yellow-?tier|green-?tier|custodial\s+lookup|delegated\s+onboarding)\b", re.IGNORECASE),
    re.compile(r"\b(?:freeze\s+dial|cancel\s+orders|surgical\s+freeze|snap-?back|unredact|ca\s+override|r-?12\s+mask)\b", re.IGNORECASE),
    re.compile(r"\b(?:senior\s+text\s+scale|text\s+scale|a\+\+|pay-?it-?forward|jitsi|carmichael|mccormick)\b", re.IGNORECASE),
    re.compile(r"\b(?:autonomousscanworker|settlementreconciler|daemon\s+cycle|velocity\s+radar|subordinate)\b", re.IGNORECASE),
    re.compile(r"\b(?:tab\s+[1-4]|dashboard|lineage\s+house|house\s+(?:0?[1-9]|1[0-2])|12\s+houses|enclave)\b", re.IGNORECASE),
    re.compile(r"\b(?:playbook|runbook|manual|lexicon|glossary|chancellor|fiduciary\s+copilot|devops\s+copilot)\b", re.IGNORECASE),
    re.compile(r"\b(?:sign[- ]?in|log[- ]?in|magic\s+link|6-?digit\s+code|passphrase|mfa|passwordless|where\s+is\s+my\s+password|lost\s+(?:my\s+)?(?:phone|laptop|device)|revoke\s+(?:session|device))\b", re.IGNORECASE),
)

# Pure external public-market research patterns (Lane 2)
_EXTERNAL_MARKET_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:cpi|inflation|bls|fomc|federal\s+reserve|fed\s+funds|gdp|payroll|unemployment)\b", re.IGNORECASE),
    re.compile(r"\b(?:treasury|yield\s+curve|bond\s+yield|bond\s+prices|10-?year|2-?year|t-?bill|sofr)\b", re.IGNORECASE),
    re.compile(r"\b(?:eia|natural\s+gas\s+storage|crude\s+oil|wti|brent|opec)\b", re.IGNORECASE),
    re.compile(r"\b(?:noaa|nws|hurricane|temperature\s+contracts|weather\s+oracle|heating\s+degree|cooling\s+degree)\b", re.IGNORECASE),
    re.compile(r"\b(?:implied\s+probability|expected\s+value|brier\s+score|binary\s+contract\s+implied)\b", re.IGNORECASE),
    re.compile(r"\b(?:s&p\s*500|nasdaq|vix|eur/usd|usd/jpy|fx\s+carry)\b", re.IGNORECASE),
)

# Lightweight deterministic synonym expansion for internal PDEUE vocabulary
_QUERY_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "halt": ("r-04", "kill-switch", "emergency", "directive-r04"),
    "kill": ("r-04", "halt", "emergency"),
    "switch": ("r-04", "halt", "kill"),
    "mask": ("r-12", "masking", "privacy", "redacted"),
    "masking": ("r-12", "privacy", "redacted"),
    "unredact": ("r-12", "override", "t3"),
    "override": ("r-12", "unredact", "dual-signature", "t3", "f3"),
    "withdrawal": ("distribution", "red-tier", "yellow-tier", "r-15"),
    "withdraw": ("distribution", "red-tier", "yellow-tier", "r-15"),
    "brake": ("risk-dial", "downward-only", "40%", "dry-powder"),
    "dial": ("risk-dial", "downward-only", "freeze"),
    "freeze": ("freeze-dial", "circuit-breaker", "subordinate", "surgical"),
    "cancel": ("cancel-orders", "purge", "circuit-breaker", "subordinate"),
    "bank": ("adr-011", "ifas", "ext-ref", "air-gap"),
    "banking": ("adr-011", "ifas", "ext-ref", "air-gap"),
    "waterfall": ("87/10/3", "tpw", "scma", "cfcp", "faep"),
    "hwm": ("high-water", "adr-012", "drawdown"),
    "water": ("high-water", "adr-012"),
    "loss": ("rule-a14", "isolation", "adr-012"),
    "losses": ("rule-a14", "isolation", "adr-012"),
    "shadow": ("hunch", "shadow-paper", "3-point"),
    "hunch": ("shadow", "shadow-paper", "3-point"),
    "crest": ("bordure", "heritage", "hall-of-arms", "genealogist"),
    "crests": ("bordure", "heritage", "hall-of-arms", "genealogist"),
    "chronicle": ("heritage", "genealogist", "hall-of-arms", "curate"),
    "chronicles": ("heritage", "genealogist", "hall-of-arms", "curate"),
    "curate": ("heritage", "genealogist", "hall-of-arms", "chronicle"),
    "bordure": ("heritage", "hall-of-arms", "genealogist", "differencing"),
    "vote": ("bicameral", "veto", "stage", "petition"),
    "voting": ("bicameral", "veto", "stage", "petition"),
    "veto": ("bicameral", "stage", "founder", "shtf"),
    "snapback": ("shtf", "executive-command", "stage-1"),
    "snap-back": ("shtf", "executive-command", "stage-1"),
    "text": ("text-scale", "senior", "accessibility", "a++"),
    "font": ("text-scale", "senior", "accessibility", "a++"),
    "enlarge": ("text-scale", "senior", "accessibility"),
    "audio": ("university", "companion", "studio", "narration"),
    "certification": ("university", "companion", "chapter"),
    "jitsi": ("community", "hearth", "rooms"),
    "daemon": ("autonomousscanworker", "settlementreconciler", "worker", "telemetry"),
    "latency": ("websocket", "telemetry", "worker", "rate-limit"),
    "succession": ("deputy", "chief_admin_deputy", "handoff"),
    "onboard": ("onboarding", "delegated", "ratification", "invite"),
    "onboarding": ("delegated", "ratification", "invite"),
    "roll": ("h1", "secretary", "roster", "lineage"),
    "sign": ("sign-in", "login", "6-digit", "magic-link", "passwordless", "code"),
    "signin": ("sign-in", "login", "6-digit", "magic-link", "passwordless", "code"),
    "sign-in": ("login", "6-digit", "magic-link", "passwordless", "code"),
    "login": ("sign-in", "6-digit", "magic-link", "passwordless", "code"),
    "password": ("passwordless", "sign-in", "6-digit", "magic-link", "passphrase", "mfa", "login"),
    "passwords": ("passwordless", "sign-in", "6-digit", "magic-link", "login"),
    "passphrase": ("apex", "mfa", "sign-in", "chief-admin", "t3", "f3"),
    "mfa": ("apex", "passphrase", "sign-in", "6-digit"),
    "lost": ("lost-device", "revoke", "session", "phone", "laptop", "revocation", "chief-admin"),
    "phone": ("lost-device", "revoke", "session", "revocation", "device"),
    "laptop": ("lost-device", "revoke", "session", "revocation", "device"),
    "device": ("lost-device", "revoke", "session", "revocation"),
    "revoke": ("revocation", "session", "lost-device", "chief-admin"),
}


def normalize_knowledge_role(raw_role: Optional[str]) -> str:
    """Normalize any PDEUE role string into a canonical role token from ``CANONICAL_ROLE_SET``."""
    if not raw_role or not str(raw_role).strip():
        return "CLASS_M"
    tok = str(raw_role).strip().upper().replace(" ", "_")
    alias_map = {
        "MEMBER": "CLASS_M",
        "MEMBER_USER": "CLASS_M",
        "CLASS_M": "CLASS_M",
        "CLASS-M": "CLASS_M",
        "M": "CLASS_M",
        "COMMUNITY": "CLASS_M",
        "OBSERVER": "CLASS_M",
        "H1": "H1",
        "HOUSE_SECRETARY": "H1",
        "H2": "H2",
        "HOUSE_HEAD": "H2",
        "HOUSE_LEADER": "H2",
        "CLASS_H": "H1",  # Fail-closed to least-privileged Class H role when unspecified
        "HOUSE_GENEALOGIST": "HOUSE_GENEALOGIST",
        "HOUSE-GENEALOGIST": "HOUSE_GENEALOGIST",
        "GENEALOGIST": "HOUSE_GENEALOGIST",
        "F1": "F1",
        "F2_H": "F2-H",
        "F2-H": "F2-H",
        "F2H": "F2-H",
        "F2_A": "F2-A",
        "F2-A": "F2-A",
        "F2A": "F2-A",
        "F3": "F3",
        "CLASS_F": "F1",  # Fail-closed to least-privileged Class F role when unspecified
        "ADVISOR": "F2-H",
        "T1": "T1",
        "T2": "T2",
        "T2_HOUSEHOLD": "T2-HOUSEHOLD",
        "T2-HOUSEHOLD": "T2-HOUSEHOLD",
        "T3": "T3",
        "CLASS_T": "T1",  # Fail-closed to least-privileged Class T role when unspecified
        "TECH": "T1",
        "CHIEF_ADMIN": "CHIEF_ADMIN",
        "CHIEF-ADMIN": "CHIEF_ADMIN",
        "CHIEF_ADMINISTRATOR": "CHIEF_ADMIN",
        "OPERATOR": "CHIEF_ADMIN",
        "FOUNDER": "CHIEF_ADMIN",
        "ADMIN": "CHIEF_ADMIN",
        "CHIEF_ADMIN_DEPUTY": "CHIEF_ADMIN_DEPUTY",
        "CHIEF-ADMIN-DEPUTY": "CHIEF_ADMIN_DEPUTY",
        "DEPUTY": "CHIEF_ADMIN_DEPUTY",
    }
    normalized = alias_map.get(tok, tok)
    if normalized in CANONICAL_ROLE_SET:
        return normalized
    return "CLASS_M"


def _slugify_heading(title: str) -> str:
    cleaned = re.sub(r"[`*_~()\[\]:.,!?/→←&]+", " ", title.lower())
    cleaned = re.sub(r"\s+", "-", cleaned.strip())
    return re.sub(r"-{2,}", "-", cleaned).strip("-")


def _strip_markdown(text: str) -> str:
    s = re.sub(r"`([^`]+)`", r"\1", text)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"\*([^*]+)\*", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"^>\s*", "", s, flags=re.MULTILINE)
    s = re.sub(r"\|", " · ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _tokenize(text: str) -> List[str]:
    raw_tokens = _TOKEN_RE.findall((text or "").lower())
    out: List[str] = []
    for tok in raw_tokens:
        clean = tok.strip("-_/")
        if not clean or len(clean) < 2 or clean in _STOPWORDS:
            continue
        out.append(clean)
        # Also split hyphenated/slashed tokens so e.g. "adr-012" matches "adr" & "012",
        # "87/10/3" matches "87", "10", "3", "r-04" matches "r04"
        if "-" in clean or "/" in clean or "_" in clean:
            compact = re.sub(r"[-_/]", "", clean)
            if compact and compact != clean:
                out.append(compact)
            for part in re.split(r"[-_/]+", clean):
                if len(part) >= 2 and part not in _STOPWORDS:
                    out.append(part)
    return out


def _expand_query_tokens(tokens: Sequence[str]) -> List[str]:
    expanded = list(tokens)
    for tok in tokens:
        for syn in _QUERY_SYNONYMS.get(tok, ()):
            expanded.extend(_tokenize(syn))
    return expanded


def is_external_market_only_query(query: str) -> bool:
    """Return True if query is purely general public-market research with no PDEUE anchors."""
    q = (query or "").strip()
    if not q:
        return False
    if any(pat.search(q) for pat in _INTERNAL_PDEUE_ANCHORS):
        return False
    return any(pat.search(q) for pat in _EXTERNAL_MARKET_PATTERNS)


def _format_playbook_steps(raw_steps: Sequence[Any]) -> List[str]:
    formatted: List[str] = []
    for idx, step in enumerate(raw_steps or [], start=1):
        if isinstance(step, dict):
            num = step.get("step", idx)
            action = str(step.get("action") or "").strip()
            effect = str(step.get("effect") or "").strip()
            if action and effect:
                formatted.append(f"{num}. {action} -> {effect}")
            elif action:
                formatted.append(f"{num}. {action}")
        elif isinstance(step, str) and step.strip():
            formatted.append(step.strip())
    return formatted


def _format_media_refs(
    playbook: Dict[str, Any],
    *,
    repo_root: Path,
) -> List[Dict[str, Any]]:
    refs: List[Dict[str, Any]] = []
    for asset in playbook.get("media_assets") or []:
        if not isinstance(asset, dict):
            continue
        path = str(asset.get("path") or "").strip()
        if not path.startswith(PLAYBOOKS_URL_PREFIX) or "://" in path or ".." in path:
            continue
        rel = path[len(PLAYBOOKS_URL_PREFIX):].lstrip("/")
        disk_path = repo_root / "backend" / "app" / "static" / "media" / "playbooks" / rel
        if not disk_path.is_file() or disk_path.stat().st_size == 0:
            continue
        legend = [
            {
                "badge": item.get("badge"),
                "control_id": str(item.get("control_id") or ""),
                "label": str(item.get("label") or ""),
                "note": str(item.get("note") or ""),
            }
            for item in (asset.get("callout_legend") or [])
            if isinstance(item, dict)
        ]
        refs.append(
            {
                "asset_id": str(asset.get("asset_id") or ""),
                "path": path,
                "caption": str(asset.get("caption") or ""),
                "callout_legend": legend,
                "media_type": str(asset.get("media_type") or "annotated_screenshot"),
                "playbook_id": str(playbook.get("playbook_id") or ""),
                "title": str(playbook.get("title") or ""),
                "portal_route": str(playbook.get("portal_route") or ""),
            }
        )
    return refs


@dataclass(frozen=True)
class IndexedManualSection:
    section_id: str
    manual_file: str
    relative_path: str
    section_title: str
    anchor_slug: str
    excerpt: str
    full_text: str
    allowed_roles: FrozenSet[str]
    tokens: FrozenSet[str]
    title_tokens: FrozenSet[str]


@dataclass(frozen=True)
class IndexedPlaybook:
    playbook_id: str
    title: str
    summary: str
    role_classes: FrozenSet[str]
    scenario_type: str
    portal_route: str
    control_ids: Tuple[str, ...]
    manual_anchor: str
    steps: Tuple[str, ...]
    media_refs: Tuple[Dict[str, Any], ...]
    tokens: FrozenSet[str]
    title_tokens: FrozenSet[str]


@dataclass(frozen=True)
class IndexedLexiconEntry:
    term_id: str
    term: str
    short_label: str
    category: str
    authority_ref: str
    plain_english: str
    technical_spec: str
    aliases: Tuple[str, ...]
    tokens: FrozenSet[str]
    title_tokens: FrozenSet[str]


@dataclass
class LocalKnowledgeMatch:
    playbook_id: Optional[str]
    title: str
    scenario_type: str
    score: float
    summary: str
    steps: List[str] = field(default_factory=list)
    media_refs: List[Dict[str, Any]] = field(default_factory=list)
    manual_citations: List[Dict[str, str]] = field(default_factory=list)
    control_ids: List[str] = field(default_factory=list)
    portal_route: Optional[str] = None
    lexicon_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "playbook_id": self.playbook_id,
            "title": self.title,
            "scenario_type": self.scenario_type,
            "score": round(self.score, 4),
            "summary": self.summary,
            "steps": list(self.steps),
            "media_refs": [dict(m) for m in self.media_refs],
            "manual_citations": [dict(c) for c in self.manual_citations],
            "control_ids": list(self.control_ids),
            "portal_route": self.portal_route,
            "lexicon_id": self.lexicon_id,
        }


@dataclass
class LocalKnowledgeResult:
    matched: bool
    confidence: float
    role: str
    query: str
    answer: str
    matches: List[Dict[str, Any]] = field(default_factory=list)
    media_refs: List[Dict[str, Any]] = field(default_factory=list)
    playbook_steps: List[str] = field(default_factory=list)
    manual_citations: List[Dict[str, str]] = field(default_factory=list)
    lexicon_ids: List[str] = field(default_factory=list)
    top_playbook_id: Optional[str] = None
    scenario_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matched": self.matched,
            "confidence": round(self.confidence, 4),
            "role": self.role,
            "query": self.query,
            "answer": self.answer,
            "matches": list(self.matches),
            "media_refs": list(self.media_refs),
            "playbook_steps": list(self.playbook_steps),
            "manual_citations": list(self.manual_citations),
            "lexicon_ids": list(self.lexicon_ids),
            "top_playbook_id": self.top_playbook_id,
            "scenario_type": self.scenario_type,
        }


class LocalKnowledgeIndex:
    """In-memory deterministic, role-scoped retrieval index over manuals, playbooks, and Lexicon v0.5."""

    HIGH_CONFIDENCE_THRESHOLD = 0.28

    def __init__(
        self,
        *,
        repo_root: Optional[Path] = None,
        registry_path: Optional[Path] = None,
    ) -> None:
        self._repo_root = Path(repo_root) if repo_root is not None else REPO_ROOT
        self._manuals_dir = self._repo_root / "docs" / "manuals"
        self._registry_path = Path(registry_path) if registry_path is not None else (
            self._repo_root / "backend" / "app" / "static" / "media" / "playbooks" / "registry.json"
            if repo_root is not None
            else DEFAULT_REGISTRY_PATH
        )

        self.manual_sections: List[IndexedManualSection] = []
        self.playbooks: List[IndexedPlaybook] = []
        self.lexicon_entries: List[IndexedLexiconEntry] = []
        self._idf: Dict[str, float] = {}
        self._manual_sections_by_file: Dict[str, List[IndexedManualSection]] = {}
        self._indexed_manuals: List[str] = []

        self._build_index()

    def _build_index(self) -> None:
        self._index_manuals()
        self._index_playbooks()
        self._index_lexicon()
        self._compute_idf()

    def _section_allowed_roles(self, manual_file: str, section_title: str) -> FrozenSet[str]:
        base = MANUAL_ALLOWED_ROLES.get(manual_file, CHIEF_ROLES)
        title_l = section_title.lower()
        # Extra sub-tier tightening for sensitive sections
        if manual_file == "CLASS_T_TECHNICAL_MANUAL.md":
            if "ca override" in title_l or "t3" in title_l or "incident response" in title_l:
                return frozenset({"T2", "T3"}) | CHIEF_ROLES
        if manual_file == "CLASS_F_FINANCIAL_MANUAL.md":
            if "f3" in title_l or "chief risk officer" in title_l:
                return frozenset({"F2-H", "F2-A", "F3"}) | CHIEF_ROLES
        return base

    def _index_manuals(self) -> None:
        heading_re = re.compile(r"^(#{2,3})\s+(.+?)\s*$")
        for filename in CANONICAL_MANUAL_FILES:
            path = self._manuals_dir / filename
            if not path.is_file():
                continue
            self._indexed_manuals.append(filename)
            raw_lines = path.read_text(encoding="utf-8").splitlines()
            current_title = filename.replace(".md", "").replace("_", " ").title()
            current_buf: List[str] = []
            sec_counter = 0

            def _flush(title: str, lines: List[str]) -> None:
                nonlocal sec_counter
                body = "\n".join(lines).strip()
                if not body or len(body) < 25:
                    return
                sec_counter += 1
                clean_title = _strip_markdown(title)
                clean_body = _strip_markdown(body)
                excerpt = clean_body[:380].rsplit(" ", 1)[0] + ("…" if len(clean_body) > 380 else "")
                slug = _slugify_heading(clean_title)
                allowed = self._section_allowed_roles(filename, clean_title)
                title_toks = frozenset(_tokenize(clean_title))
                body_toks = frozenset(_tokenize(f"{clean_title} {clean_body}"))
                sec = IndexedManualSection(
                    section_id=f"{filename}#{slug or sec_counter}",
                    manual_file=filename,
                    relative_path=f"docs/manuals/{filename}",
                    section_title=clean_title,
                    anchor_slug=slug,
                    excerpt=excerpt,
                    full_text=clean_body,
                    allowed_roles=allowed,
                    tokens=body_toks,
                    title_tokens=title_toks,
                )
                self.manual_sections.append(sec)
                self._manual_sections_by_file.setdefault(filename, []).append(sec)

            for line in raw_lines:
                m = heading_re.match(line)
                if m:
                    _flush(current_title, current_buf)
                    current_title = m.group(2).strip()
                    current_buf = []
                else:
                    current_buf.append(line)
            _flush(current_title, current_buf)

    def _index_playbooks(self) -> None:
        registry = load_training_media_registry(self._registry_path)
        for pb in registry.get("playbooks", []):
            if not isinstance(pb, dict):
                continue
            pb_id = str(pb.get("playbook_id") or "").strip()
            if not pb_id:
                continue
            title = str(pb.get("title") or "").strip()
            summary = str(pb.get("summary") or "").strip()
            roles = frozenset(
                normalize_knowledge_role(r) for r in (pb.get("role_classes") or []) if str(r).strip()
            )
            scenario = str(pb.get("scenario_type") or "routine").strip()
            portal_route = str(pb.get("portal_route") or "").strip()
            control_ids = tuple(str(c) for c in (pb.get("control_ids") or []) if str(c).strip())
            manual_anchor = str(pb.get("manual_anchor") or "").strip()
            steps = tuple(_format_playbook_steps(pb.get("steps") or []))
            media_refs = tuple(_format_media_refs(pb, repo_root=self._repo_root))

            caption_blob = " ".join(
                f"{m['caption']} " + " ".join(f"{c['label']} {c['note']}" for c in m["callout_legend"])
                for m in media_refs
            )
            full_blob = " ".join(
                [pb_id, title, summary, scenario, portal_route, " ".join(control_ids), " ".join(steps), caption_blob]
            )
            self.playbooks.append(
                IndexedPlaybook(
                    playbook_id=pb_id,
                    title=title,
                    summary=summary,
                    role_classes=roles,
                    scenario_type=scenario,
                    portal_route=portal_route,
                    control_ids=control_ids,
                    manual_anchor=manual_anchor,
                    steps=steps,
                    media_refs=media_refs,
                    tokens=frozenset(_tokenize(full_blob)),
                    title_tokens=frozenset(_tokenize(f"{title} {summary}")),
                )
            )

    def _index_lexicon(self) -> None:
        for entry in LEXICON_TERMS:
            term_id = str(entry.get("id") or "").strip()
            if not term_id:
                continue
            term = str(entry.get("term") or "").strip()
            short_label = str(entry.get("short_label") or term).strip()
            category = str(entry.get("category") or "").strip()
            authority_ref = str(entry.get("authority_ref") or "").strip()
            plain = str(entry.get("plain_english") or "").strip()
            tech = str(entry.get("technical_spec") or "").strip()
            aliases = tuple(str(a).strip() for a in (entry.get("aliases") or []) if str(a).strip())
            title_blob = " ".join([term_id, term, short_label, *aliases])
            full_blob = " ".join([title_blob, category, authority_ref, plain, tech])
            self.lexicon_entries.append(
                IndexedLexiconEntry(
                    term_id=term_id,
                    term=term,
                    short_label=short_label,
                    category=category,
                    authority_ref=authority_ref,
                    plain_english=plain,
                    technical_spec=tech,
                    aliases=aliases,
                    tokens=frozenset(_tokenize(full_blob)),
                    title_tokens=frozenset(_tokenize(title_blob)),
                )
            )

    def _compute_idf(self) -> None:
        all_docs: List[FrozenSet[str]] = (
            [s.tokens for s in self.manual_sections]
            + [p.tokens for p in self.playbooks]
            + [l.tokens for l in self.lexicon_entries]
        )
        total_docs = max(1, len(all_docs))
        df: Dict[str, int] = {}
        for doc_tokens in all_docs:
            for tok in doc_tokens:
                df[tok] = df.get(tok, 0) + 1
        self._idf = {
            tok: math.log((total_docs + 1.0) / (count + 1.0)) + 1.0
            for tok, count in df.items()
        }

    def stats(self) -> Dict[str, Any]:
        return {
            "indexed_manuals": list(self._indexed_manuals),
            "manual_count": len(self._indexed_manuals),
            "manual_section_count": len(self.manual_sections),
            "playbook_count": len(self.playbooks),
            "lexicon_term_count": len(self.lexicon_entries),
            "media_asset_count": len(
                {m["path"] for pb in self.playbooks for m in pb.media_refs}
            ),
            "zero_network": True,
        }

    def _is_playbook_authorized(self, pb: IndexedPlaybook, norm_role: str) -> bool:
        if norm_role in CHIEF_ROLES:
            return True
        return norm_role in pb.role_classes

    def _is_manual_section_authorized(self, sec: IndexedManualSection, norm_role: str) -> bool:
        if norm_role in CHIEF_ROLES:
            return True
        return norm_role in sec.allowed_roles

    def _resolve_anchor_citation(
        self,
        manual_anchor: str,
        norm_role: str,
    ) -> Optional[Dict[str, str]]:
        if not manual_anchor or ".md" not in manual_anchor:
            return None
        file_part, _, frag = manual_anchor.partition("#")
        filename = Path(file_part).name
        sections = self._manual_sections_by_file.get(filename) or []
        authorized = [s for s in sections if self._is_manual_section_authorized(s, norm_role)]
        if not authorized:
            return None
        if frag:
            frag_norm = _slugify_heading(frag)
            for sec in authorized:
                if sec.anchor_slug == frag_norm or frag_norm in sec.anchor_slug or sec.anchor_slug in frag_norm:
                    return {
                        "manual_file": sec.manual_file,
                        "section_title": sec.section_title,
                        "excerpt": sec.excerpt,
                    }
        # Fallback to first authorized section of that manual
        first = authorized[0]
        return {
            "manual_file": first.manual_file,
            "section_title": first.section_title,
            "excerpt": first.excerpt,
        }

    def _score_tokens(
        self,
        query_tokens: Sequence[str],
        expanded_tokens: Sequence[str],
        doc_tokens: FrozenSet[str],
        title_tokens: FrozenSet[str],
        raw_query_lower: str,
        title_lower: str,
    ) -> float:
        if not query_tokens or not doc_tokens:
            return 0.0
        unique_q = list(dict.fromkeys(query_tokens))
        unique_exp = list(dict.fromkeys(expanded_tokens))
        max_possible = sum(self._idf.get(t, 1.5) for t in unique_q) or 1.0

        direct_score = 0.0
        direct_hits = 0
        title_hits = 0
        for tok in unique_q:
            weight = self._idf.get(tok, 1.5)
            if tok in doc_tokens:
                direct_score += weight
                direct_hits += 1
            if tok in title_tokens:
                direct_score += weight * 0.55
                title_hits += 1

        syn_bonus = 0.0
        q_set = set(unique_q)
        for tok in unique_exp:
            if tok in q_set:
                continue
            if tok in doc_tokens:
                syn_bonus += self._idf.get(tok, 1.2) * 0.35
            if tok in title_tokens:
                syn_bonus += self._idf.get(tok, 1.2) * 0.25

        if direct_hits == 0 and syn_bonus < 0.8:
            return 0.0

        normalized = (direct_score + min(syn_bonus, max_possible * 0.65)) / (max_possible * 1.45)

        # Phrase match bonus
        if len(title_lower) >= 4 and title_lower in raw_query_lower:
            normalized += 0.25
        elif title_hits >= 2:
            normalized += 0.12

        return min(1.0, normalized)

    def _best_role_playbook_for_topic(
        self,
        query_tokens: Sequence[str],
        expanded_tokens: Sequence[str],
        raw_query_lower: str,
        norm_role: str,
    ) -> Optional[Tuple[IndexedPlaybook, float]]:
        best_pb: Optional[IndexedPlaybook] = None
        best_score = 0.0
        for pb in self.playbooks:
            if not self._is_playbook_authorized(pb, norm_role):
                continue
            s = self._score_tokens(
                query_tokens,
                expanded_tokens,
                pb.tokens,
                pb.title_tokens,
                raw_query_lower,
                pb.title.lower(),
            )
            # Prefer playbooks explicitly targeting the actor's exact role (especially for Chief Admin)
            if norm_role in pb.role_classes:
                s = min(1.0, s + 0.08)
            if s > best_score:
                best_score = s
                best_pb = pb
        if best_pb is not None and best_score >= 0.14:
            return best_pb, best_score
        return None

    def query(
        self,
        query: str,
        *,
        role: Optional[str] = "CLASS_M",
        top_k: int = 3,
        allow_external_bypass: bool = True,
    ) -> LocalKnowledgeResult:
        """Search local manuals, playbooks, and Lexicon v0.5 under strict role isolation."""
        cleaned = (query or "").strip()
        norm_role = normalize_knowledge_role(role)
        if not cleaned:
            return LocalKnowledgeResult(
                matched=False,
                confidence=0.0,
                role=norm_role,
                query=cleaned,
                answer="",
            )

        if allow_external_bypass and is_external_market_only_query(cleaned):
            return LocalKnowledgeResult(
                matched=False,
                confidence=0.0,
                role=norm_role,
                query=cleaned,
                answer="",
            )

        raw_lower = cleaned.lower()
        q_tokens = _tokenize(cleaned)
        exp_tokens = _expand_query_tokens(q_tokens)
        has_internal_anchor = any(pat.search(cleaned) for pat in _INTERNAL_PDEUE_ANCHORS)
        wants_incident = any(
            kw in raw_lower
            for kw in (
                "emergency", "outlier", "incident", "halt", "r-04", "kill switch",
                "freeze", "cancel", "shtf", "snap-back", "snapback", "override",
                "unredact", "red-tier", "red tier", "scam", "24h", "stress", "off",
                "broken", "wrong", "revoke", "recovery", "403", "blocked",
            )
        )

        # 1. Score role-authorized playbooks
        scored_playbooks: List[Tuple[float, IndexedPlaybook]] = []
        for pb in self.playbooks:
            if not self._is_playbook_authorized(pb, norm_role):
                continue
            score = self._score_tokens(
                q_tokens, exp_tokens, pb.tokens, pb.title_tokens, raw_lower, pb.title.lower()
            )
            if score <= 0.0:
                continue
            if norm_role in pb.role_classes:
                score = min(1.0, score + 0.08)
            if wants_incident and pb.scenario_type == "outlier_incident":
                score = min(1.0, score + 0.14)
            elif not wants_incident and pb.scenario_type == "routine":
                score = min(1.0, score + 0.03)
            scored_playbooks.append((score, pb))
        scored_playbooks.sort(key=lambda pair: (-pair[0], pair[1].playbook_id))

        # 2. Score role-authorized manual sections
        scored_sections: List[Tuple[float, IndexedManualSection]] = []
        for sec in self.manual_sections:
            if not self._is_manual_section_authorized(sec, norm_role):
                continue
            score = self._score_tokens(
                q_tokens, exp_tokens, sec.tokens, sec.title_tokens, raw_lower, sec.section_title.lower()
            )
            if score <= 0.0:
                continue
            # Slight role-affinity boost for the role's primary dedicated manual
            if (
                (norm_role in CHIEF_ROLES and sec.manual_file == "CHIEF_ADMIN_RUNBOOK.md")
                or (norm_role in CLASS_F_ROLES and sec.manual_file == "CLASS_F_FINANCIAL_MANUAL.md")
                or (norm_role in CLASS_T_ROLES and sec.manual_file == "CLASS_T_TECHNICAL_MANUAL.md")
                or (norm_role in CLASS_H_ROLES and sec.manual_file == "CLASS_H_LINEAGE_AND_HERITAGE_MANUAL.md")
                or (norm_role == "CLASS_M" and sec.manual_file == "USER_QUICKSTART.md")
            ):
                score = min(1.0, score + 0.07)
            scored_sections.append((score, sec))
        scored_sections.sort(key=lambda pair: (-pair[0], pair[1].section_id))

        # 3. Score Lexicon v0.5 entries
        scored_lexicon: List[Tuple[float, IndexedLexiconEntry]] = []
        for lex in self.lexicon_entries:
            score = self._score_tokens(
                q_tokens, exp_tokens, lex.tokens, lex.title_tokens, raw_lower, lex.short_label.lower()
            )
            if any(alias.lower() in raw_lower for alias in lex.aliases if len(alias) >= 4):
                score = min(1.0, max(score, 0.55) + 0.22)
            if lex.short_label.lower() in raw_lower and len(lex.short_label) >= 3:
                score = min(1.0, max(score, 0.52) + 0.20)
            if score > 0.0:
                scored_lexicon.append((score, lex))
        scored_lexicon.sort(key=lambda pair: (-pair[0], pair[1].term_id))

        # Determine top confidence
        top_pb_score = scored_playbooks[0][0] if scored_playbooks else 0.0
        top_sec_score = scored_sections[0][0] if scored_sections else 0.0
        top_lex_score = scored_lexicon[0][0] if scored_lexicon else 0.0
        best_confidence = max(top_pb_score, top_sec_score, top_lex_score)
        if has_internal_anchor and best_confidence > 0.16:
            best_confidence = min(1.0, best_confidence + 0.14)

        if best_confidence < self.HIGH_CONFIDENCE_THRESHOLD:
            return LocalKnowledgeResult(
                matched=False,
                confidence=best_confidence,
                role=norm_role,
                query=cleaned,
                answer="",
            )

        # Build ranked LocalKnowledgeMatch objects
        ranked_matches: List[LocalKnowledgeMatch] = []
        best_fallback_pb_pair = (
            (scored_playbooks[0][1], scored_playbooks[0][0])
            if scored_playbooks
            else self._best_role_playbook_for_topic(q_tokens, exp_tokens, raw_lower, norm_role)
        )

        # Add top playbooks
        for pb_score, pb in scored_playbooks[: max(2, top_k)]:
            if pb_score < 0.20:
                continue
            cites: List[Dict[str, str]] = []
            anchor_cite = self._resolve_anchor_citation(pb.manual_anchor, norm_role)
            if anchor_cite is not None:
                cites.append(anchor_cite)
            ranked_matches.append(
                LocalKnowledgeMatch(
                    playbook_id=pb.playbook_id,
                    title=pb.title,
                    scenario_type=pb.scenario_type,
                    score=pb_score,
                    summary=pb.summary,
                    steps=list(pb.steps),
                    media_refs=[dict(m) for m in pb.media_refs],
                    manual_citations=cites,
                    control_ids=list(pb.control_ids),
                    portal_route=pb.portal_route,
                )
            )

        # Add top manual sections
        for sec_score, sec in scored_sections[:2]:
            if sec_score < 0.24:
                continue
            linked_pb = best_fallback_pb_pair[0] if best_fallback_pb_pair else None
            ranked_matches.append(
                LocalKnowledgeMatch(
                    playbook_id=linked_pb.playbook_id if linked_pb else None,
                    title=f"{sec.manual_file}: {sec.section_title}",
                    scenario_type=linked_pb.scenario_type if linked_pb else "manual_section",
                    score=sec_score,
                    summary=sec.excerpt,
                    steps=list(linked_pb.steps) if linked_pb else [],
                    media_refs=[dict(m) for m in linked_pb.media_refs] if linked_pb else [],
                    manual_citations=[
                        {
                            "manual_file": sec.manual_file,
                            "section_title": sec.section_title,
                            "excerpt": sec.excerpt,
                        }
                    ],
                    control_ids=list(linked_pb.control_ids) if linked_pb else [],
                    portal_route=linked_pb.portal_route if linked_pb else None,
                )
            )

        # Add top Lexicon entry if strong match
        if scored_lexicon and scored_lexicon[0][0] >= 0.40:
            lex_score, lex = scored_lexicon[0]
            linked_pb = best_fallback_pb_pair[0] if best_fallback_pb_pair else None
            cites = []
            if scored_sections:
                top_s = scored_sections[0][1]
                cites.append(
                    {
                        "manual_file": top_s.manual_file,
                        "section_title": top_s.section_title,
                        "excerpt": top_s.excerpt,
                    }
                )
            ranked_matches.append(
                LocalKnowledgeMatch(
                    playbook_id=linked_pb.playbook_id if linked_pb else None,
                    title=f"Lexicon v0.5 · {lex.term}",
                    scenario_type="lexicon",
                    score=lex_score,
                    summary=f"{lex.term} ({lex.authority_ref}): {lex.plain_english}",
                    steps=list(linked_pb.steps) if linked_pb else [],
                    media_refs=[dict(m) for m in linked_pb.media_refs] if linked_pb else [],
                    manual_citations=cites,
                    lexicon_id=lex.term_id,
                    portal_route=linked_pb.portal_route if linked_pb else None,
                )
            )

        ranked_matches.sort(key=lambda m: -m.score)
        ranked_matches = ranked_matches[: max(1, top_k)]

        # Aggregate deduplicated media_refs, playbook_steps, manual_citations, and lexicon_ids
        media_refs: List[Dict[str, Any]] = []
        seen_media_paths: set[str] = set()
        playbook_steps: List[str] = []
        manual_citations: List[Dict[str, str]] = []
        seen_cite_keys: set[Tuple[str, str]] = set()
        lexicon_ids: List[str] = []

        # Prioritize top matched playbook for steps & media
        primary_pb: Optional[IndexedPlaybook] = (
            scored_playbooks[0][1]
            if scored_playbooks and scored_playbooks[0][0] >= 0.18
            else (best_fallback_pb_pair[0] if best_fallback_pb_pair else None)
        )
        if primary_pb is not None:
            playbook_steps = list(primary_pb.steps)
            for m in primary_pb.media_refs:
                if m["path"] not in seen_media_paths:
                    seen_media_paths.add(m["path"])
                    media_refs.append(dict(m))
            anchor_cite = self._resolve_anchor_citation(primary_pb.manual_anchor, norm_role)
            if anchor_cite is not None:
                key = (anchor_cite["manual_file"], anchor_cite["section_title"])
                if key not in seen_cite_keys:
                    seen_cite_keys.add(key)
                    manual_citations.append(anchor_cite)

        for match in ranked_matches:
            if not playbook_steps and match.steps:
                playbook_steps = list(match.steps)
            for m in match.media_refs:
                if m["path"] not in seen_media_paths and len(media_refs) < 2:
                    seen_media_paths.add(m["path"])
                    media_refs.append(dict(m))
            for c in match.manual_citations:
                key = (c["manual_file"], c["section_title"])
                if key not in seen_cite_keys and len(manual_citations) < 3:
                    seen_cite_keys.add(key)
                    manual_citations.append(dict(c))

        for lex_score, lex in scored_lexicon[:3]:
            if lex_score >= 0.35 and lex.term_id in LEXICON_BY_ID and lex.term_id not in lexicon_ids:
                lexicon_ids.append(lex.term_id)

        # Synthesize crisp, plain-English local answer
        answer_parts: List[str] = []
        if primary_pb is not None and top_pb_score >= max(top_sec_score, top_lex_score) - 0.08:
            answer_parts.append(f"{primary_pb.title}: {primary_pb.summary}")
            if manual_citations:
                answer_parts.append(
                    f"Reference ({manual_citations[0]['manual_file']} — {manual_citations[0]['section_title']}): "
                    f"{manual_citations[0]['excerpt']}"
                )
        elif scored_lexicon and top_lex_score >= top_sec_score:
            top_lex = scored_lexicon[0][1]
            answer_parts.append(f"{top_lex.term} ({top_lex.authority_ref}): {top_lex.plain_english}")
            if primary_pb is not None:
                answer_parts.append(f"Visual Playbook: {primary_pb.title} — {primary_pb.summary}")
        elif scored_sections:
            top_sec = scored_sections[0][1]
            answer_parts.append(
                f"{top_sec.manual_file} — {top_sec.section_title}: {top_sec.excerpt}"
            )
            if primary_pb is not None:
                answer_parts.append(f"Related Playbook ({primary_pb.playbook_id}): {primary_pb.summary}")

        synthesized_answer = " ".join(part.strip() for part in answer_parts if part.strip())

        return LocalKnowledgeResult(
            matched=True,
            confidence=best_confidence,
            role=norm_role,
            query=cleaned,
            answer=synthesized_answer,
            matches=[m.to_dict() for m in ranked_matches],
            media_refs=media_refs,
            playbook_steps=playbook_steps,
            manual_citations=manual_citations,
            lexicon_ids=lexicon_ids,
            top_playbook_id=primary_pb.playbook_id if primary_pb else None,
            scenario_type=primary_pb.scenario_type if primary_pb else (ranked_matches[0].scenario_type if ranked_matches else None),
        )


_DEFAULT_LOCAL_KNOWLEDGE_INDEX: Optional[LocalKnowledgeIndex] = None


def get_local_knowledge_index() -> LocalKnowledgeIndex:
    """Return the process-wide startup-cached LocalKnowledgeIndex singleton (zero network calls)."""
    global _DEFAULT_LOCAL_KNOWLEDGE_INDEX
    if _DEFAULT_LOCAL_KNOWLEDGE_INDEX is None:
        _DEFAULT_LOCAL_KNOWLEDGE_INDEX = LocalKnowledgeIndex()
    return _DEFAULT_LOCAL_KNOWLEDGE_INDEX


def reset_local_knowledge_index() -> None:
    """Reset cached singleton (useful in tests)."""
    global _DEFAULT_LOCAL_KNOWLEDGE_INDEX
    _DEFAULT_LOCAL_KNOWLEDGE_INDEX = None


__all__ = [
    "CANONICAL_MANUAL_FILES",
    "LocalKnowledgeIndex",
    "LocalKnowledgeMatch",
    "LocalKnowledgeResult",
    "MANUAL_ALLOWED_ROLES",
    "get_local_knowledge_index",
    "is_external_market_only_query",
    "normalize_knowledge_role",
    "reset_local_knowledge_index",
]
