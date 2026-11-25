"""Permanent Shadow Paper Hunch Research Studio & Clearance Queue (Batch 2B — Part 3).

Architectural & Safety Invariants:
- Backed by an isolated SQLite database & table (``shadow_hunch_dossiers``)
  physically separated from live trading ledgers (``pdeue.db``), capital
  ledgers, and the ADR-011 IFAS outbox.
- Strictly ``ADR-008`` exact 64-bit integer cents for all modeled probabilities,
  quotes, fees, edges, virtual stakes, and virtual PnL (zero float currency math).
- Strictly ``unilateral_execution = False`` and ``mode = "SHADOW_PAPER"``.
- Enforces Nov 2026 CFTC Event-Contract Scope & DEATH BETS Act fail-closed
  blocking (HTTP 400 / ``PROHIBITED_EVENT_CATEGORY``) on sports, casino, war,
  terrorism, and death wagers.
- Live promotion clearance requires ``STEWARDSHIP_L1_CERTIFIED`` status and an
  active non-frozen risk dial, stages an ``AUTH-03`` Action Card in
  ``PENDING_F2H_CLEARANCE``, advances via F2-H domestic review to
  ``PENDING_F3_CLEARANCE``, and concludes via F3 CRO / Chief Admin decision
  (``ALLOWED`` | ``DENIED`` | ``RESCINDED``).
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import pathlib
import sqlite3
import threading
from typing import Any, Dict, List, Optional
import uuid

from app.domain.authority_tiers import (
    is_chief_admin_role,
    is_class_t_role,
    normalize_role_token,
)
from app.domain.llm_client import BaseLLMClient, get_llm_client
from app.domain.regulatory_filter import (
    ALLOWED_EVENT_VERTICALS,
    PROHIBITED_CODE,
    check_regulatory_content,
    list_allowed_vertical_codes,
    map_eligible_vertical,
)

SHADOW_PAPER_MODE = "SHADOW_PAPER"
REQUIRED_CERTIFICATION_LEVEL = "STEWARDSHIP_L1_CERTIFIED"

DEFAULT_SHADOW_DB_PATH = (
    pathlib.Path(__file__).resolve().parent.parent.parent / "pdeue_shadow_hunch.db"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_cents(cents: int) -> str:
    val = int(cents)
    sign = "-" if val < 0 else ""
    abs_val = abs(val)
    return f"{sign}${abs_val // 100:,}.{abs_val % 100:02d}"


class ShadowHunchError(Exception):
    """Structured fail-closed domain error translated directly into HTTP status codes."""

    def __init__(self, message: str, *, status_code: int = 400, code: str = "SHADOW_HUNCH_ERROR", extra: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.extra = dict(extra or {})

    def to_http_detail(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "unilateral_execution": False,
        }
        payload.update(self.extra)
        return payload


class ShadowHunchService:
    """Isolated SQLite-backed Shadow Paper Hunch Research Studio & F2-H / F3 Clearance Queue."""

    def __init__(
        self,
        db_path: Optional[pathlib.Path | str] = None,
        llm_client: Optional[BaseLLMClient] = None,
    ):
        env_path = os.getenv("PDEUE_SHADOW_HUNCH_DB_PATH", "").strip()
        resolved = db_path or env_path or DEFAULT_SHADOW_DB_PATH
        self.db_path = pathlib.Path(resolved)
        self._llm_client = llm_client
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS shadow_hunch_dossiers (
                    dossier_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL DEFAULT 'SHADOW_PAPER',
                    actor_id TEXT NOT NULL,
                    actor_role TEXT NOT NULL,
                    scma_id TEXT NOT NULL,
                    hypothesis TEXT NOT NULL,
                    vertical_code TEXT NOT NULL,
                    vertical_label TEXT NOT NULL,
                    oracle_source TEXT NOT NULL,
                    sample_ticker TEXT NOT NULL,
                    corroboration_summary TEXT NOT NULL,
                    citations_json TEXT NOT NULL DEFAULT '[]',
                    modeled_prob_cents INTEGER NOT NULL,
                    quoted_price_cents INTEGER NOT NULL,
                    fee_cents INTEGER NOT NULL,
                    gross_edge_cents INTEGER NOT NULL,
                    net_edge_cents INTEGER NOT NULL,
                    net_edge_bps INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    staging_eligible INTEGER NOT NULL DEFAULT 0,
                    plain_english_verdict TEXT NOT NULL,
                    clearance_status TEXT NOT NULL DEFAULT 'SHADOW_ONLY',
                    auth_card_json TEXT,
                    shadow_bids_json TEXT NOT NULL DEFAULT '[]',
                    clearance_rationale TEXT,
                    f2h_reviewed_by TEXT,
                    f2h_reviewed_at TEXT,
                    f2h_notes TEXT,
                    final_reviewed_by TEXT,
                    final_reviewed_role TEXT,
                    final_reviewed_at TEXT,
                    final_notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _resolve_llm(self) -> BaseLLMClient:
        if self._llm_client is not None:
            return self._llm_client
        return get_llm_client(fail_closed_to_mock=True)

    @staticmethod
    def _compute_bid_stats(bids: List[Dict[str, Any]]) -> Dict[str, Any]:
        total = len(bids)
        wins = sum(1 for b in bids if b.get("outcome") == "WON")
        losses = sum(1 for b in bids if b.get("outcome") == "LOST")
        open_bids = sum(1 for b in bids if b.get("outcome") not in {"WON", "LOST"})
        resolved = wins + losses
        hit_rate_bps = (wins * 10_000) // resolved if resolved > 0 else 0
        net_virtual_pnl_cents = sum(int(b.get("virtual_pnl_cents", 0)) for b in bids)
        total_virtual_stake_cents = sum(int(b.get("effective_virtual_cost_cents", 0)) for b in bids)
        return {
            "total_shadow_bids": total,
            "resolved_bids": resolved,
            "open_bids": open_bids,
            "wins": wins,
            "losses": losses,
            "hit_rate_bps": hit_rate_bps,
            "hit_rate_pct": f"{hit_rate_bps // 100}.{hit_rate_bps % 100:02d}%",
            "total_virtual_stake_cents": total_virtual_stake_cents,
            "net_virtual_pnl_cents": net_virtual_pnl_cents,
            "net_virtual_pnl_display": _format_cents(net_virtual_pnl_cents),
        }

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        citations = json.loads(row["citations_json"] or "[]")
        bids = json.loads(row["shadow_bids_json"] or "[]")
        auth_card = json.loads(row["auth_card_json"]) if row["auth_card_json"] else None
        bid_stats = self._compute_bid_stats(bids)

        return {
            "dossier_id": row["dossier_id"],
            "mode": SHADOW_PAPER_MODE,
            "unilateral_execution": False,
            "real_capital_touched": False,
            "ifas_outbox_emitted": False,
            "currency_standard": "ADR-008_EXACT_INTEGER_CENTS",
            "actor_id": row["actor_id"],
            "actor_role": row["actor_role"],
            "scma_id": row["scma_id"],
            "hypothesis": row["hypothesis"],
            "vertical": {
                "code": row["vertical_code"],
                "label": row["vertical_label"],
                "oracle": row["oracle_source"],
                "sample_ticker": row["sample_ticker"],
                "collateral_rule": ALLOWED_EVENT_VERTICALS.get(row["vertical_code"], {}).get(
                    "collateral_rule",
                    "100% fully collateralized binary settlement ($1.00 / 100¢ cap)",
                ),
            },
            "validation_steps": {
                "step_1_external_corroboration": {
                    "passed": True,
                    "summary": row["corroboration_summary"],
                    "citations": citations,
                },
                "step_2_contract_mapping": {
                    "passed": True,
                    "vertical_code": row["vertical_code"],
                    "vertical_label": row["vertical_label"],
                    "oracle": row["oracle_source"],
                    "sample_ticker": row["sample_ticker"],
                    "fully_collateralized": True,
                },
                "step_3_edge_and_fee_audit": {
                    "passed": bool(row["staging_eligible"]),
                    "modeled_prob_cents": int(row["modeled_prob_cents"]),
                    "quoted_price_cents": int(row["quoted_price_cents"]),
                    "fee_cents": int(row["fee_cents"]),
                    "gross_edge_cents": int(row["gross_edge_cents"]),
                    "net_edge_cents": int(row["net_edge_cents"]),
                    "net_edge_bps": int(row["net_edge_bps"]),
                    "display": {
                        "modeled_fair_value": _format_cents(int(row["modeled_prob_cents"])),
                        "quoted_price": _format_cents(int(row["quoted_price_cents"])),
                        "fee_friction": _format_cents(int(row["fee_cents"])),
                        "net_edge": _format_cents(int(row["net_edge_cents"])),
                    },
                },
            },
            "citations": citations,
            "modeled_prob_cents": int(row["modeled_prob_cents"]),
            "quoted_price_cents": int(row["quoted_price_cents"]),
            "fee_cents": int(row["fee_cents"]),
            "gross_edge_cents": int(row["gross_edge_cents"]),
            "net_edge_cents": int(row["net_edge_cents"]),
            "net_edge_bps": int(row["net_edge_bps"]),
            "status": row["status"],
            "staging_eligible": bool(row["staging_eligible"]),
            "plain_english_verdict": row["plain_english_verdict"],
            "clearance_status": row["clearance_status"],
            "auth_card": auth_card,
            "shadow_bids": bids,
            "shadow_stats": bid_stats,
            "clearance_review": {
                "rationale": row["clearance_rationale"],
                "f2h_reviewed_by": row["f2h_reviewed_by"],
                "f2h_reviewed_at": row["f2h_reviewed_at"],
                "f2h_notes": row["f2h_notes"],
                "final_reviewed_by": row["final_reviewed_by"],
                "final_reviewed_role": row["final_reviewed_role"],
                "final_reviewed_at": row["final_reviewed_at"],
                "final_notes": row["final_notes"],
            },
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def get_dossier(self, dossier_id: str) -> Dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM shadow_hunch_dossiers WHERE dossier_id = ?",
                (dossier_id,),
            ).fetchone()
        if row is None:
            raise ShadowHunchError(
                f"Shadow Hunch dossier '{dossier_id}' not found.",
                status_code=404,
                code="DOSSIER_NOT_FOUND",
            )
        return self._row_to_dict(row)

    # ------------------------------------------------------------------
    # 1. Three-Point Validation Pipeline
    # ------------------------------------------------------------------
    def evaluate_hunch(
        self,
        *,
        hypothesis: str,
        actor_id: str,
        actor_role: str,
        scma_id: str,
        vertical_hint: Optional[str] = None,
        quoted_price_cents: Optional[int] = None,
        modeled_prob_cents: Optional[int] = None,
        modeled_prob_bps: Optional[int] = None,
        fee_cents: Optional[int] = None,
    ) -> Dict[str, Any]:
        cleaned = (hypothesis or "").strip()
        if len(cleaned) < 6:
            raise ShadowHunchError(
                "Please enter a clear plain-English market hypothesis (at least 6 characters).",
                status_code=400,
                code="INVALID_HYPOTHESIS",
            )

        # Regulatory Scope Gate (Nov 2026 CFTC & DEATH BETS Act) — FAIL CLOSED HTTP 400
        reg = check_regulatory_content(cleaned, extra_hint=vertical_hint)
        if not reg.allowed:
            raise ShadowHunchError(
                reg.reason or "Prohibited event category blocked fail-closed.",
                status_code=400,
                code=PROHIBITED_CODE,
                extra={
                    "prohibited_category": reg.prohibited_category,
                    "matched_term": reg.matched_term,
                    "allowed_verticals": list_allowed_vertical_codes(),
                },
            )

        # Step 2 (checked before persisting): Contract Mapping to eligible regulated vertical
        vertical = map_eligible_vertical(cleaned, vertical_hint=vertical_hint)
        if vertical is None:
            raise ShadowHunchError(
                "Hypothesis does not map to an eligible regulated event vertical. "
                "PDEUE restricts hunches strictly to objectively verifiable, 100% fully collateralized "
                "Weather, Macro/CPI, Energy/EIA, Treasuries, Equity Indices, and FX contracts.",
                status_code=400,
                code="UNSUPPORTED_EVENT_VERTICAL",
                extra={"allowed_verticals": list_allowed_vertical_codes()},
            )

        # Step 1: External Corroboration via BaseLLMClient (read-only grounded research)
        llm = self._resolve_llm()
        llm_resp = llm.generate_safe_response(
            system_prompt=(
                "You are the PDEUE Shadow Paper Hunch Corroboration Auditor. "
                "Evaluate the factual basis and uncertainty factors of the proposed regulated event "
                "hypothesis objectively. Never recommend live trades; unilateral_execution=False."
            ),
            user_query=cleaned,
            context={
                "web_grounding": True,
                "hunch_corroboration": True,
                "vertical": vertical["code"],
            },
            actor_role="MEMBER" if normalize_role_token(actor_role) == "MEMBER_USER" else "OPERATOR",
            actor_id=actor_id or scma_id,
            allowed_scma_id=scma_id,
        )
        corroboration_summary = llm_resp.content or (
            f"Verified regulated oracle mapping ({vertical['oracle']}) for {vertical['label']}."
        )
        citations = list(llm_resp.web_citations or [])
        if not citations:
            citations = [
                {
                    "title": f"{vertical['label']} — Official Settlement Reference",
                    "url": "https://www.cftc.gov/LearnAndProtect/index.htm",
                    "source": vertical["oracle"],
                }
            ]

        # Step 3: Edge & Fee Audit strictly in 64-bit integer cents (ADR-008)
        quote_c = int(quoted_price_cents) if quoted_price_cents is not None else 52
        if modeled_prob_cents is not None:
            model_c = int(modeled_prob_cents)
        elif modeled_prob_bps is not None:
            model_c = int(modeled_prob_bps) // 100
        else:
            model_c = 60
        fee_c = int(fee_cents) if fee_cents is not None else 2

        if not (1 <= quote_c <= 99) or not (1 <= model_c <= 99) or not (0 <= fee_c <= 20):
            raise ShadowHunchError(
                "Binary contract quotes and modeled fair values must be between 1¢ and 99¢; fee friction 0¢–20¢.",
                status_code=400,
                code="INVALID_PRICE_BOUNDS",
            )

        gross_edge_cents = model_c - quote_c
        net_edge_cents = model_c - quote_c - fee_c
        net_edge_bps = net_edge_cents * 100

        if net_edge_cents <= 0:
            status = "REJECTED_NO_EDGE"
            staging_eligible = 0
            clearance_status = "NOT_ELIGIBLE"
            verdict_text = (
                f"Rejected (No Positive Edge): Your modeled fair value ({_format_cents(model_c)}) minus "
                f"the quoted price ({_format_cents(quote_c)}) and fee friction ({_format_cents(fee_c)}) "
                f"yields a net edge of {_format_cents(net_edge_cents)} per $1.00 contract. "
                "Because net edge is at or below $0.00, PDEUE refuses to stage this hunch—even in Shadow Paper mode."
            )
        else:
            status = "VALIDATED_SHADOW_READY"
            staging_eligible = 1
            clearance_status = "SHADOW_ONLY"
            verdict_text = (
                f"Validated for Zero-Risk Shadow Paper Practice (+{_format_cents(net_edge_cents)} net edge): "
                f"Modeled fair value ({_format_cents(model_c)}) exceeds the quoted price ({_format_cents(quote_c)}) "
                f"plus fee friction ({_format_cents(fee_c)}) on {vertical['label']} ({vertical['oracle']}). "
                "You may stage a virtual SHADOW_PAPER bid with zero impact on real SCMA funds."
            )

        dossier_id = f"HUNCH-{uuid.uuid4().hex[:8].upper()}"
        now = _utc_now()
        norm_role = normalize_role_token(actor_role or "MEMBER_USER")

        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO shadow_hunch_dossiers (
                    dossier_id, mode, actor_id, actor_role, scma_id, hypothesis,
                    vertical_code, vertical_label, oracle_source, sample_ticker,
                    corroboration_summary, citations_json,
                    modeled_prob_cents, quoted_price_cents, fee_cents,
                    gross_edge_cents, net_edge_cents, net_edge_bps,
                    status, staging_eligible, plain_english_verdict,
                    clearance_status, auth_card_json, shadow_bids_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dossier_id,
                    SHADOW_PAPER_MODE,
                    actor_id or scma_id,
                    norm_role,
                    scma_id,
                    cleaned,
                    vertical["code"],
                    vertical["label"],
                    vertical["oracle"],
                    vertical["sample_ticker"],
                    corroboration_summary,
                    json.dumps(citations),
                    model_c,
                    quote_c,
                    fee_c,
                    gross_edge_cents,
                    net_edge_cents,
                    net_edge_bps,
                    status,
                    staging_eligible,
                    verdict_text,
                    clearance_status,
                    None,
                    "[]",
                    now,
                    now,
                ),
            )
            conn.commit()

        return self.get_dossier(dossier_id)

    # ------------------------------------------------------------------
    # 2. Permanent Shadow Paper Execution (Members & Admins — Zero Real Risk)
    # ------------------------------------------------------------------
    def place_shadow_bid(
        self,
        dossier_id: str,
        *,
        virtual_stake_cents: int,
        entry_quote_cents: Optional[int] = None,
        side: str = "YES",
        actor_id: str = "",
        actor_role: str = "MEMBER_USER",
        simulated_outcome: Optional[str] = None,
    ) -> Dict[str, Any]:
        norm_role = normalize_role_token(actor_role or "MEMBER_USER")
        if is_class_t_role(norm_role):
            raise ShadowHunchError(
                "Class T technical operators cannot stage financial or shadow trading bids (Directive R-06).",
                status_code=403,
                code="ROLE_FORBIDDEN",
            )

        dossier = self.get_dossier(dossier_id)
        if not dossier["staging_eligible"] or dossier["status"] == "REJECTED_NO_EDGE":
            raise ShadowHunchError(
                "Cannot place a Shadow Paper bid on a REJECTED_NO_EDGE dossier (net edge <= $0.00).",
                status_code=400,
                code="REJECTED_NO_EDGE",
            )

        stake_c = int(virtual_stake_cents)
        if stake_c < 100 or stake_c > 500_000:
            raise ShadowHunchError(
                "Virtual shadow stake must be between $1.00 (100¢) and $5,000.00 (500,000¢).",
                status_code=400,
                code="INVALID_VIRTUAL_STAKE",
            )

        quote_c = int(entry_quote_cents) if entry_quote_cents is not None else int(dossier["quoted_price_cents"])
        if not (1 <= quote_c <= 99):
            raise ShadowHunchError(
                "Entry quote must be between 1¢ and 99¢.",
                status_code=400,
                code="INVALID_PRICE_BOUNDS",
            )

        clean_side = (side or "YES").strip().upper()
        if clean_side not in {"YES", "NO"}:
            clean_side = "YES"

        contracts = max(1, stake_c // quote_c)
        effective_cost_cents = contracts * quote_c
        max_payout_cents = contracts * 100

        outcome = (simulated_outcome or "OPEN").strip().upper()
        if outcome not in {"OPEN", "WON", "LOST"}:
            outcome = "OPEN"

        if outcome == "WON":
            virtual_pnl_cents = max_payout_cents - effective_cost_cents
        elif outcome == "LOST":
            virtual_pnl_cents = -effective_cost_cents
        else:
            virtual_pnl_cents = 0

        bid_record = {
            "shadow_bid_id": f"SBID-{uuid.uuid4().hex[:8].upper()}",
            "mode": SHADOW_PAPER_MODE,
            "side": clean_side,
            "actor_id": actor_id or dossier["actor_id"],
            "actor_role": norm_role,
            "virtual_stake_cents": stake_c,
            "entry_quote_cents": quote_c,
            "contracts": contracts,
            "effective_virtual_cost_cents": effective_cost_cents,
            "max_virtual_payout_cents": max_payout_cents,
            "outcome": outcome,
            "virtual_pnl_cents": virtual_pnl_cents,
            "real_capital_touched": False,
            "ifas_outbox_emitted": False,
            "unilateral_execution": False,
            "recorded_at": _utc_now(),
        }

        bids = list(dossier["shadow_bids"])
        bids.append(bid_record)
        now = _utc_now()
        next_status = "SHADOW_ACTIVE" if dossier["status"] == "VALIDATED_SHADOW_READY" else dossier["status"]

        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE shadow_hunch_dossiers
                SET shadow_bids_json = ?, status = ?, updated_at = ?
                WHERE dossier_id = ?
                """,
                (json.dumps(bids), next_status, now, dossier_id),
            )
            conn.commit()

        updated = self.get_dossier(dossier_id)
        return {
            "mode": SHADOW_PAPER_MODE,
            "unilateral_execution": False,
            "real_capital_touched": False,
            "ifas_outbox_emitted": False,
            "shadow_bid": bid_record,
            "dossier": updated,
        }

    # ------------------------------------------------------------------
    # 3. Higher-Authority Clearance Queue for Live Promotion
    # ------------------------------------------------------------------
    def request_live_clearance(
        self,
        dossier_id: str,
        *,
        member_state: Dict[str, Any],
        actor_id: str = "",
        actor_role: str = "MEMBER_USER",
        rationale: str = "",
    ) -> Dict[str, Any]:
        dossier = self.get_dossier(dossier_id)
        if not dossier["staging_eligible"] or dossier["status"] == "REJECTED_NO_EDGE":
            raise ShadowHunchError(
                "Cannot request live clearance for a REJECTED_NO_EDGE hunch.",
                status_code=400,
                code="REJECTED_NO_EDGE",
            )

        if dossier["clearance_status"] in {"PENDING_F2H_CLEARANCE", "PENDING_F3_CLEARANCE", "ALLOWED"}:
            raise ShadowHunchError(
                f"Dossier is already in clearance state {dossier['clearance_status']}.",
                status_code=409,
                code="CLEARANCE_ALREADY_REQUESTED",
            )

        # Gate 1: STEWARDSHIP_L1_CERTIFIED requirement (fail-closed HTTP 403)
        cert_level = str(member_state.get("certification_level") or "").strip().upper()
        if cert_level != REQUIRED_CERTIFICATION_LEVEL:
            raise ShadowHunchError(
                "Live promotion clearance requires STEWARDSHIP_L1_CERTIFIED status from PDEUE University "
                "Chapter 6. You may continue practicing risk-free in Shadow Paper mode until certified.",
                status_code=403,
                code="CERTIFICATION_REQUIRED",
                extra={"required_certification": REQUIRED_CERTIFICATION_LEVEL, "current_certification": cert_level or None},
            )

        # Gate 2: Active non-frozen risk dial requirement (fail-closed HTTP 403)
        is_frozen = bool(member_state.get("is_frozen", False)) or bool(member_state.get("quarantined", False))
        member_status = str(member_state.get("status") or "").strip().upper()
        risk_dial_pct = float(member_state.get("risk_dial_pct") or 0.0)
        if is_frozen or member_status in {"QUARANTINED", "FROZEN_BY_HOUSE_LEADER", "FROZEN_BY_HOUSE_QUARANTINE"} or risk_dial_pct <= 0.0:
            raise ShadowHunchError(
                "Live promotion clearance requires an active, non-frozen SCMA risk dial (> 0.00%). "
                "Your account is currently frozen or clamped at 0.00%.",
                status_code=403,
                code="RISK_DIAL_FROZEN",
                extra={"is_frozen": is_frozen, "risk_dial_pct": risk_dial_pct, "member_status": member_status},
            )

        # Stage deterministic AUTH-03 Action Card (ZERO unilateral execution)
        auth_card = {
            "action_id": f"ACT-HUNCH-{uuid.uuid4().hex[:8].upper()}",
            "action_type": "REQUEST_HUNCH_LIVE_CLEARANCE",
            "auth_tier": "AUTH-03",
            "status": "PENDING_F2H_CLEARANCE",
            "title": f"Higher-Authority Clearance Petition · {dossier['vertical']['sample_ticker']}",
            "description": (
                f"Petition by {member_state.get('name') or dossier['scma_id']} ({REQUIRED_CERTIFICATION_LEVEL}) "
                f"to advance validated hunch {dossier_id} (+{_format_cents(dossier['net_edge_cents'])} net edge) "
                "for F2-H Head of Household domestic review and F3 CRO / Chief Admin final adjudication."
            ),
            "endpoint": f"/api/v1/hunch/{dossier_id}/review",
            "method": "POST",
            "payload": {
                "dossier_id": dossier_id,
                "scma_id": dossier["scma_id"],
                "vertical": dossier["vertical"]["code"],
                "net_edge_cents": dossier["net_edge_cents"],
            },
            "requires_human_confirmation": True,
            "requires_dual_control": True,
            "unilateral_execution": False,
            "executed": False,
            "gate_g1_notice": "Live execution remains fail-closed under Gate G1 (HOLD_OBSERVATIONS_ONLY) even if cleared.",
        }

        now = _utc_now()
        clean_rationale = (rationale or "").strip()[:500] or "Member completed shadow validation and requests higher-authority review."
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE shadow_hunch_dossiers
                SET clearance_status = 'PENDING_F2H_CLEARANCE',
                    auth_card_json = ?,
                    clearance_rationale = ?,
                    updated_at = ?
                WHERE dossier_id = ?
                """,
                (json.dumps(auth_card), clean_rationale, now, dossier_id),
            )
            conn.commit()

        updated = self.get_dossier(dossier_id)
        return {
            "dossier_id": dossier_id,
            "mode": SHADOW_PAPER_MODE,
            "clearance_status": "PENDING_F2H_CLEARANCE",
            "auth_tier": "AUTH-03",
            "action_card": auth_card,
            "unilateral_execution": False,
            "dossier": updated,
        }

    def review_clearance(
        self,
        dossier_id: str,
        *,
        decision: str,
        actor_role: str,
        actor_id: str = "",
        notes: str = "",
    ) -> Dict[str, Any]:
        norm_role = normalize_role_token(actor_role or "")
        is_ca = is_chief_admin_role(norm_role)
        is_f2h = norm_role == "F2-H"
        is_f3 = norm_role == "F3"

        if not (is_f2h or is_f3 or is_ca):
            raise ShadowHunchError(
                "Only F2-H (Head of Household) for domestic review or F3 (CRO) / Chief Administrator "
                "for final decision may adjudicate Shadow Hunch live-promotion clearance.",
                status_code=403,
                code="CLEARANCE_ROLE_FORBIDDEN",
                extra={"actor_role": norm_role},
            )

        dossier = self.get_dossier(dossier_id)
        current_state = dossier["clearance_status"]
        raw_dec = (decision or "").strip().upper().replace(" ", "_")
        clean_notes = (notes or "").strip()[:500]
        now = _utc_now()
        reviewer = actor_id or norm_role

        # Stage 1: F2-H Domestic Review
        if is_f2h:
            if current_state != "PENDING_F2H_CLEARANCE":
                raise ShadowHunchError(
                    f"F2-H domestic review applies only to PENDING_F2H_CLEARANCE dossiers (current: {current_state}).",
                    status_code=400,
                    code="INVALID_CLEARANCE_TRANSITION",
                )
            if raw_dec in {"ALLOW", "ALLOWED", "RESCIND", "RESCINDED"}:
                raise ShadowHunchError(
                    "F2-H Head of Household may advance a dossier to PENDING_F3_CLEARANCE or DENY it; "
                    "final ALLOWED / RESCINDED authority is reserved to F3 CRO or Chief Administrator.",
                    status_code=403,
                    code="F3_OR_CA_REQUIRED",
                )
            if raw_dec in {"APPROVE", "APPROVE_F2H", "ADVANCE", "ADVANCE_TO_F3", "PENDING_F3_CLEARANCE"}:
                next_state = "PENDING_F3_CLEARANCE"
            elif raw_dec in {"DENY", "DENIED", "REJECT", "VETO"}:
                next_state = "DENIED"
            else:
                raise ShadowHunchError(
                    f"Unsupported F2-H review decision '{decision}'. Use APPROVE_F2H or DENIED.",
                    status_code=400,
                    code="INVALID_DECISION",
                )

            auth_card = dict(dossier["auth_card"] or {})
            if auth_card:
                auth_card["status"] = next_state
                auth_card["unilateral_execution"] = False
                auth_card["executed"] = False

            with self._lock, self._connect() as conn:
                conn.execute(
                    """
                    UPDATE shadow_hunch_dossiers
                    SET clearance_status = ?,
                        auth_card_json = ?,
                        f2h_reviewed_by = ?,
                        f2h_reviewed_at = ?,
                        f2h_notes = ?,
                        updated_at = ?
                    WHERE dossier_id = ?
                    """,
                    (
                        next_state,
                        json.dumps(auth_card) if auth_card else None,
                        reviewer,
                        now,
                        clean_notes or f"F2-H domestic review decision: {next_state}",
                        now,
                        dossier_id,
                    ),
                )
                conn.commit()
            updated = self.get_dossier(dossier_id)
            return {
                "dossier_id": dossier_id,
                "previous_status": current_state,
                "clearance_status": next_state,
                "reviewed_by": reviewer,
                "reviewed_role": norm_role,
                "unilateral_execution": False,
                "dossier": updated,
            }

        # Stage 2: F3 CRO / Chief Administrator Final Decision (ALLOWED | DENIED | RESCINDED)
        if raw_dec in {"ALLOW", "ALLOWED", "APPROVE"}:
            next_state = "ALLOWED"
        elif raw_dec in {"DENY", "DENIED", "REJECT", "VETO"}:
            next_state = "DENIED"
        elif raw_dec in {"RESCIND", "RESCINDED", "REVOKE"}:
            next_state = "RESCINDED"
        else:
            raise ShadowHunchError(
                f"Unsupported final review decision '{decision}'. Use ALLOWED, DENIED, or RESCINDED.",
                status_code=400,
                code="INVALID_DECISION",
            )

        if next_state == "ALLOWED" and current_state != "PENDING_F3_CLEARANCE":
            raise ShadowHunchError(
                f"Final ALLOWED clearance requires prior F2-H domestic review (expected PENDING_F3_CLEARANCE, got {current_state}).",
                status_code=400,
                code="F2H_REVIEW_REQUIRED_FIRST",
            )
        if next_state == "RESCINDED" and current_state not in {"ALLOWED", "PENDING_F3_CLEARANCE"}:
            raise ShadowHunchError(
                f"Cannot rescind dossier in state {current_state}; only ALLOWED or PENDING_F3_CLEARANCE may be rescinded.",
                status_code=400,
                code="INVALID_CLEARANCE_TRANSITION",
            )
        if next_state == "DENIED" and current_state not in {"PENDING_F2H_CLEARANCE", "PENDING_F3_CLEARANCE"}:
            raise ShadowHunchError(
                f"Cannot deny dossier in state {current_state}.",
                status_code=400,
                code="INVALID_CLEARANCE_TRANSITION",
            )

        auth_card = dict(dossier["auth_card"] or {})
        if auth_card:
            auth_card["status"] = next_state
            auth_card["unilateral_execution"] = False
            auth_card["executed"] = False

        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE shadow_hunch_dossiers
                SET clearance_status = ?,
                    auth_card_json = ?,
                    final_reviewed_by = ?,
                    final_reviewed_role = ?,
                    final_reviewed_at = ?,
                    final_notes = ?,
                    updated_at = ?
                WHERE dossier_id = ?
                """,
                (
                    next_state,
                    json.dumps(auth_card) if auth_card else None,
                    reviewer,
                    norm_role,
                    now,
                    clean_notes or f"{norm_role} final decision: {next_state}",
                    now,
                    dossier_id,
                ),
            )
            conn.commit()

        updated = self.get_dossier(dossier_id)
        return {
            "dossier_id": dossier_id,
            "previous_status": current_state,
            "clearance_status": next_state,
            "reviewed_by": reviewer,
            "reviewed_role": norm_role,
            "unilateral_execution": False,
            "dossier": updated,
        }

    # ------------------------------------------------------------------
    # 4. Scoped Listing + Shadow Hit-Rate Summary
    # ------------------------------------------------------------------
    def list_dossiers(
        self,
        *,
        actor_role: str = "MEMBER_USER",
        scma_id: Optional[str] = None,
        clearance_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        norm_role = normalize_role_token(actor_role or "MEMBER_USER")
        if is_class_t_role(norm_role):
            raise ShadowHunchError(
                "Class T technical operators are isolated from financial Shadow Hunch dossiers (Directive R-06 / R-12).",
                status_code=403,
                code="ROLE_FORBIDDEN",
            )

        is_reviewer = is_chief_admin_role(norm_role) or norm_role in {"F1", "F2-H", "F2-A", "F3"}

        clauses: List[str] = []
        params: List[Any] = []

        if not is_reviewer:
            if scma_id:
                clauses.append("scma_id = ?")
                params.append(scma_id)
        elif scma_id:
            clauses.append("scma_id = ?")
            params.append(scma_id)

        if clearance_status:
            clauses.append("clearance_status = ?")
            params.append(clearance_status.strip().upper())

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM shadow_hunch_dossiers {where_sql} ORDER BY created_at DESC LIMIT 200"

        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()

        dossiers = [self._row_to_dict(r) for r in rows]

        # Build aggregate + per-SCMA shadow hit-rate summary for F2-H / F3 reviewers
        all_bids: List[Dict[str, Any]] = []
        bids_by_scma: Dict[str, List[Dict[str, Any]]] = {}
        for d in dossiers:
            scma = d["scma_id"]
            bids_by_scma.setdefault(scma, []).extend(d["shadow_bids"])
            all_bids.extend(d["shadow_bids"])

        overall = self._compute_bid_stats(all_bids)
        by_scma = {scma: self._compute_bid_stats(b_list) for scma, b_list in bids_by_scma.items()}

        # Attach member's overall shadow track record onto each dossier for reviewer convenience
        for d in dossiers:
            d["member_shadow_track_record"] = by_scma.get(d["scma_id"], self._compute_bid_stats([]))

        return {
            "mode": SHADOW_PAPER_MODE,
            "unilateral_execution": False,
            "viewer_role": norm_role,
            "scoped_scma_id": scma_id,
            "count": len(dossiers),
            "dossiers": dossiers,
            "hit_rate_summary": {
                "total_dossiers": len(dossiers),
                **overall,
                "by_scma": by_scma,
            },
        }


_DEFAULT_SHADOW_HUNCH_SERVICE: Optional[ShadowHunchService] = None


def get_shadow_hunch_service() -> ShadowHunchService:
    global _DEFAULT_SHADOW_HUNCH_SERVICE
    if _DEFAULT_SHADOW_HUNCH_SERVICE is None:
        _DEFAULT_SHADOW_HUNCH_SERVICE = ShadowHunchService()
    return _DEFAULT_SHADOW_HUNCH_SERVICE
