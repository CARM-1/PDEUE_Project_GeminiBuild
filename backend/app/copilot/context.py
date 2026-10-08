"""Role-scoped live context harvesting and Directive R12 redaction."""

import re
from typing import Any, Dict, Mapping, Optional

from .models import CopilotQuery


_TOKEN_KEY = re.compile(r"(?:token|secret|api[_-]?key|authorization|credential)", re.I)
_SCMA_ID = re.compile(r"\bSCMA[-_:]?[A-Z0-9]{4,}\b", re.I)


class ContextHarvester:
    """Project only the fields authorized for the querying actor's role."""

    ROLE_FIELDS = {
        "MEMBER": ("scma_balance_cents", "current_risk_pct", "dry_powder_cents", "downward_only_locked"),
        "ADVISOR": ("household_tree", "audit_log_queue", "sub_account_summaries"),
        "TECH": ("orderbook_state", "active_dispatches", "telemetry_status"),
        "OPERATOR": ("orderbook_state", "active_dispatches", "telemetry_status"),
    }

    def __init__(self, context_source: Any = None):
        self.context_source = context_source

    def harvest(self, query: CopilotQuery, live_context: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        source = dict(live_context or self._load_source(query))
        role = query.role.upper()
        projected = {key: source[key] for key in self.ROLE_FIELDS.get(role, self.ROLE_FIELDS["TECH"]) if key in source}
        if role == "MEMBER":
            projected["risk_telemetry"] = {
                key: projected.get(key, default) for key, default in (
                    ("current_risk_pct", 0.0), ("dry_powder_cents", 0), ("downward_only_locked", True)
                )
            }
        override = query.context_filters.get("ca_override_token")
        expected = source.get("ca_override_token")
        allow_ids = bool(override and expected and override == expected)
        return self._redact(projected, allow_ids=allow_ids)

    def _load_source(self, query: CopilotQuery) -> Mapping[str, Any]:
        if self.context_source is None:
            return query.context_filters.get("live_context", {})
        if callable(self.context_source):
            return self.context_source(query)
        if hasattr(self.context_source, "get_context"):
            return self.context_source.get_context(query.user_id)
        return self.context_source

    def _redact(self, value: Any, allow_ids: bool = False) -> Any:
        if isinstance(value, Mapping):
            return {
                key: "[REDACTED]" if _TOKEN_KEY.search(str(key)) else self._redact(item, allow_ids)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._redact(item, allow_ids) for item in value]
        if isinstance(value, tuple):
            return tuple(self._redact(item, allow_ids) for item in value)
        if isinstance(value, str):
            value = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [REDACTED]", value)
            return value if allow_ids else _SCMA_ID.sub("SCMA-[REDACTED]", value)
        return value


def harvest_context(query: CopilotQuery, live_context: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Convenience entry point for callers that do not require dependency injection."""
    return ContextHarvester().harvest(query, live_context)
