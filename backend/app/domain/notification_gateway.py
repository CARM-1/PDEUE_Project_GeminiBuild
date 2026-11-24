"""Isolated Notification & Alerts Gateway (In-App + Pluggable Email / SMS).

Architectural & Security Invariants:
- 100% air-gapped from trading daemons, CapitalLedger, TwoTierRiskEnvelope,
  CredentialBroker, and venue adapters (ZERO imports).
- Directive R-12 Safe-Payload Sanitization: EVERY outbound alert, email, and SMS
  is scrubbed/blocked against dollar amounts ($123.45), SCMA-... account IDs,
  EXT-REF tokens, SSNs, and raw bank routing/account identifiers so notifications
  carry only safe, non-sensitive prompts.
- Fail-Closed Pluggable Adapters: SESEmailNotificationClient and
  SNSOrTwilioSMSNotificationClient fall back deterministically to
  MockNotificationClient ($0 CI/paper default) whenever live credentials are
  unconfigured. Zero hardcoded secrets.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
import html
import os
import re
from typing import Any, Dict, List, Optional, Tuple


class R12NotificationPayloadError(ValueError):
    """Raised when strict Directive R-12 validation rejects sensitive financial content."""


# Patterns prohibited in outbound notifications under Directive R-12 / ADR-011
_DOLLAR_AMOUNT_RE = re.compile(
    r"(?i)(?:\$\s*\d[\d,]*(?:\.\d{1,4})?|\b\d[\d,]*(?:\.\d{1,2})?\s*(?:usd|dollars?)\b|\busd\s*\d[\d,]*(?:\.\d{1,2})?)"
)
_SCMA_ID_RE = re.compile(r"(?i)\bSCMA[-_][A-Z0-9_-]+\b")
_EXT_REF_RE = re.compile(r"(?i)\bEXT-REF-[A-Z0-9_*-]+\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_RAW_BANK_NUMBER_RE = re.compile(r"(?<!\d)\d{9,17}(?!\d)")
_BANK_CREDENTIAL_RE = re.compile(
    r"(?i)\b(?:routing\s*(?:number|#|no\.?)?|account\s*(?:number|#|no\.?)?|swift\s*(?:code)?|iban)\s*[:=#-]?\s*[A-Z0-9*-]{4,}\b"
)
_SCRIPT_TAG_RE = re.compile(r"(?is)<\s*(?:script|style|iframe|object|embed)[^>]*>.*?<\s*/\s*(?:script|style|iframe|object|embed)\s*>")
_HTML_TAG_RE = re.compile(r"(?s)<[^>]+>")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_notification_text(
    raw_text: str,
    *,
    strict_reject: bool = False,
    maximum: int = 400,
) -> Tuple[str, List[str]]:
    """Enforce Directive R-12 safe-payload & XSS sanitization on notification text.

    Returns ``(safe_text, redactions_applied)``. When ``strict_reject=True``, raises
    ``R12NotificationPayloadError`` if any dollar figure, SCMA ID, or banking token
    is present.
    """
    cleaned = _SCRIPT_TAG_RE.sub(" ", str(raw_text or ""))
    cleaned = _HTML_TAG_RE.sub(" ", cleaned)
    cleaned = " ".join(cleaned.strip().split())
    if len(cleaned) > maximum:
        cleaned = cleaned[:maximum].rstrip()

    redactions: List[str] = []

    if _DOLLAR_AMOUNT_RE.search(cleaned):
        redactions.append("DOLLAR_AMOUNT")
        cleaned = _DOLLAR_AMOUNT_RE.sub("[REDACTED-AMOUNT]", cleaned)

    if _SCMA_ID_RE.search(cleaned):
        redactions.append("SCMA_ID")
        cleaned = _SCMA_ID_RE.sub("[REDACTED-ACCOUNT]", cleaned)

    if _EXT_REF_RE.search(cleaned):
        redactions.append("BANK_REF_TOKEN")
        cleaned = _EXT_REF_RE.sub("[REDACTED-BANK-REF]", cleaned)

    if _SSN_RE.search(cleaned):
        redactions.append("SSN")
        cleaned = _SSN_RE.sub("[REDACTED-ID]", cleaned)

    if _BANK_CREDENTIAL_RE.search(cleaned):
        redactions.append("BANK_CREDENTIAL")
        cleaned = _BANK_CREDENTIAL_RE.sub("[REDACTED-BANK-REF]", cleaned)

    if _RAW_BANK_NUMBER_RE.search(cleaned):
        redactions.append("RAW_ACCOUNT_DIGITS")
        cleaned = _RAW_BANK_NUMBER_RE.sub("[REDACTED-NUMBER]", cleaned)

    if strict_reject and redactions:
        raise R12NotificationPayloadError(
            "Directive R-12 notification firewall blocked sensitive financial/account content: "
            + ", ".join(redactions)
        )

    safe_escaped = html.escape(cleaned, quote=True)
    return safe_escaped, redactions


@dataclass
class NotificationMessage:
    """Safe, Directive R-12-compliant notification envelope."""

    notification_id: str
    title: str
    message: str
    category: str = "ANNOUNCEMENT"
    target_scope: str = "ALL_FAMILY"
    target_house_id: Optional[int] = None
    action_url: str = "/community"
    sender_id: str = "SYSTEM"
    sender_role: str = "CHIEF_ADMIN"
    created_at_utc: str = field(default_factory=_utc_now)


@dataclass
class DeliveryReceipt:
    """Deterministic delivery audit receipt for any notification adapter."""

    channel: str
    provider: str
    status: str
    fallback_used: bool
    r12_sanitized: bool
    redactions_applied: List[str]
    safe_title: str
    safe_message: str
    delivered_at_utc: str = field(default_factory=_utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel": self.channel,
            "provider": self.provider,
            "status": self.status,
            "fallback_used": self.fallback_used,
            "r12_sanitized": self.r12_sanitized,
            "redactions_applied": list(self.redactions_applied),
            "safe_title": self.safe_title,
            "safe_message": self.safe_message,
            "delivered_at_utc": self.delivered_at_utc,
        }


class BaseNotificationClient(ABC):
    """Abstract base adapter for isolated family notifications."""

    channel: str = "in_app"
    provider_name: str = "BaseNotificationClient"

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True only when live provider credentials are present in environment."""

    def prepare_safe_payload(
        self,
        payload: NotificationMessage,
        *,
        strict_reject: bool = False,
    ) -> Tuple[str, str, List[str]]:
        safe_title, title_redactions = sanitize_notification_text(
            payload.title, strict_reject=strict_reject, maximum=140
        )
        safe_msg, msg_redactions = sanitize_notification_text(
            payload.message, strict_reject=strict_reject, maximum=500
        )
        redactions = sorted(set(title_redactions + msg_redactions))
        return safe_title, safe_msg, redactions

    @abstractmethod
    def send(
        self,
        payload: NotificationMessage,
        *,
        strict_reject: bool = False,
    ) -> DeliveryReceipt:
        """Dispatch a sanitized notification and return an auditable DeliveryReceipt."""


class MockNotificationClient(BaseNotificationClient):
    """Zero-cost ($0) deterministic default notification adapter for paper & CI mode."""

    channel = "mock"
    provider_name = "MockNotificationClient"

    def __init__(self, *, channel: str = "in_app") -> None:
        self.channel = channel
        self.delivered_log: List[Dict[str, Any]] = []

    def is_configured(self) -> bool:
        return True

    def send(
        self,
        payload: NotificationMessage,
        *,
        strict_reject: bool = False,
    ) -> DeliveryReceipt:
        safe_title, safe_msg, redactions = self.prepare_safe_payload(
            payload, strict_reject=strict_reject
        )
        receipt = DeliveryReceipt(
            channel=self.channel,
            provider=self.provider_name,
            status="MOCK_DELIVERED",
            fallback_used=False,
            r12_sanitized=True,
            redactions_applied=redactions,
            safe_title=safe_title,
            safe_message=safe_msg,
        )
        self.delivered_log.append(
            {
                "notification_id": payload.notification_id,
                **receipt.to_dict(),
            }
        )
        return receipt


class SESEmailNotificationClient(BaseNotificationClient):
    """Pluggable AWS SES email adapter failing closed to MockNotificationClient when unconfigured."""

    channel = "email"
    provider_name = "SESEmailNotificationClient"

    def __init__(self, fallback_client: Optional[MockNotificationClient] = None) -> None:
        self._fallback = fallback_client or MockNotificationClient(channel="email")

    def is_configured(self) -> bool:
        return bool(
            os.getenv("PDEUE_SES_ACCESS_KEY_ID", "").strip()
            and os.getenv("PDEUE_SES_SECRET_ACCESS_KEY", "").strip()
            and os.getenv("PDEUE_SES_SENDER_EMAIL", "").strip()
        )

    def send(
        self,
        payload: NotificationMessage,
        *,
        strict_reject: bool = False,
    ) -> DeliveryReceipt:
        safe_title, safe_msg, redactions = self.prepare_safe_payload(
            payload, strict_reject=strict_reject
        )
        if not self.is_configured():
            fallback_receipt = self._fallback.send(payload, strict_reject=strict_reject)
            return DeliveryReceipt(
                channel="email",
                provider="MockNotificationClient (SES fail-closed fallback)",
                status="FAIL_CLOSED_MOCK_FALLBACK",
                fallback_used=True,
                r12_sanitized=True,
                redactions_applied=fallback_receipt.redactions_applied,
                safe_title=fallback_receipt.safe_title,
                safe_message=fallback_receipt.safe_message,
            )

        # Even when env vars are set in paper/CI mode, keep delivery strictly safe & auditable.
        mode = os.getenv("PDEUE_VENUE_MODE", "paper").strip().lower() or "paper"
        if mode in {"paper", "observation"} and os.getenv("PDEUE_LIVE_NOTIFICATIONS_ENABLED", "false").strip().lower() not in {"1", "true", "yes"}:
            fallback_receipt = self._fallback.send(payload, strict_reject=strict_reject)
            return DeliveryReceipt(
                channel="email",
                provider="MockNotificationClient (paper-mode fail-closed)",
                status="FAIL_CLOSED_PAPER_MODE",
                fallback_used=True,
                r12_sanitized=True,
                redactions_applied=fallback_receipt.redactions_applied,
                safe_title=fallback_receipt.safe_title,
                safe_message=fallback_receipt.safe_message,
            )

        return DeliveryReceipt(
            channel="email",
            provider=self.provider_name,
            status="STAGED_FOR_SES_DISPATCH",
            fallback_used=False,
            r12_sanitized=True,
            redactions_applied=redactions,
            safe_title=safe_title,
            safe_message=safe_msg,
        )


class SNSOrTwilioSMSNotificationClient(BaseNotificationClient):
    """Pluggable AWS SNS / Twilio SMS adapter failing closed to MockNotificationClient when unconfigured."""

    channel = "sms"
    provider_name = "SNSOrTwilioSMSNotificationClient"

    def __init__(self, fallback_client: Optional[MockNotificationClient] = None) -> None:
        self._fallback = fallback_client or MockNotificationClient(channel="sms")

    def is_configured(self) -> bool:
        has_twilio = bool(
            os.getenv("PDEUE_TWILIO_ACCOUNT_SID", "").strip()
            and os.getenv("PDEUE_TWILIO_AUTH_TOKEN", "").strip()
            and os.getenv("PDEUE_TWILIO_FROM_NUMBER", "").strip()
        )
        has_sns = bool(
            os.getenv("PDEUE_SNS_ACCESS_KEY_ID", "").strip()
            and os.getenv("PDEUE_SNS_SECRET_ACCESS_KEY", "").strip()
            and os.getenv("PDEUE_SNS_REGION", "").strip()
        )
        return has_twilio or has_sns

    def send(
        self,
        payload: NotificationMessage,
        *,
        strict_reject: bool = False,
    ) -> DeliveryReceipt:
        safe_title, safe_msg, redactions = self.prepare_safe_payload(
            payload, strict_reject=strict_reject
        )
        if not self.is_configured():
            fallback_receipt = self._fallback.send(payload, strict_reject=strict_reject)
            return DeliveryReceipt(
                channel="sms",
                provider="MockNotificationClient (SMS fail-closed fallback)",
                status="FAIL_CLOSED_MOCK_FALLBACK",
                fallback_used=True,
                r12_sanitized=True,
                redactions_applied=fallback_receipt.redactions_applied,
                safe_title=fallback_receipt.safe_title,
                safe_message=fallback_receipt.safe_message,
            )

        mode = os.getenv("PDEUE_VENUE_MODE", "paper").strip().lower() or "paper"
        if mode in {"paper", "observation"} and os.getenv("PDEUE_LIVE_NOTIFICATIONS_ENABLED", "false").strip().lower() not in {"1", "true", "yes"}:
            fallback_receipt = self._fallback.send(payload, strict_reject=strict_reject)
            return DeliveryReceipt(
                channel="sms",
                provider="MockNotificationClient (paper-mode fail-closed)",
                status="FAIL_CLOSED_PAPER_MODE",
                fallback_used=True,
                r12_sanitized=True,
                redactions_applied=fallback_receipt.redactions_applied,
                safe_title=fallback_receipt.safe_title,
                safe_message=fallback_receipt.safe_message,
            )

        return DeliveryReceipt(
            channel="sms",
            provider=self.provider_name,
            status="STAGED_FOR_SMS_DISPATCH",
            fallback_used=False,
            r12_sanitized=True,
            redactions_applied=redactions,
            safe_title=safe_title,
            safe_message=safe_msg,
        )


class NotificationGateway:
    """Coordinates isolated in-app + pluggable email/SMS notification dispatch."""

    def __init__(
        self,
        *,
        in_app_client: Optional[BaseNotificationClient] = None,
        email_client: Optional[BaseNotificationClient] = None,
        sms_client: Optional[BaseNotificationClient] = None,
    ) -> None:
        self.in_app_client = in_app_client or MockNotificationClient(channel="in_app")
        self.email_client = email_client or SESEmailNotificationClient()
        self.sms_client = sms_client or SNSOrTwilioSMSNotificationClient()

    def status_summary(self) -> Dict[str, Any]:
        return {
            "default_provider": self.in_app_client.provider_name,
            "email_configured": self.email_client.is_configured(),
            "sms_configured": self.sms_client.is_configured(),
            "r12_payload_firewall": "ACTIVE",
            "fail_closed_mock_fallback": True,
        }

    def dispatch(
        self,
        payload: NotificationMessage,
        *,
        channels: Optional[List[str]] = None,
        strict_reject: bool = False,
    ) -> List[DeliveryReceipt]:
        requested = channels or ["in_app"]
        normalized = []
        for ch in requested:
            key = str(ch).strip().lower()
            if key in {"in_app", "email", "sms"} and key not in normalized:
                normalized.append(key)
        if not normalized:
            normalized = ["in_app"]

        receipts: List[DeliveryReceipt] = []
        for ch in normalized:
            if ch == "in_app":
                receipts.append(self.in_app_client.send(payload, strict_reject=strict_reject))
            elif ch == "email":
                receipts.append(self.email_client.send(payload, strict_reject=strict_reject))
            elif ch == "sms":
                receipts.append(self.sms_client.send(payload, strict_reject=strict_reject))
        return receipts


_SHARED_NOTIFICATION_GATEWAY: Optional[NotificationGateway] = None


def get_notification_gateway() -> NotificationGateway:
    global _SHARED_NOTIFICATION_GATEWAY
    if _SHARED_NOTIFICATION_GATEWAY is None:
        _SHARED_NOTIFICATION_GATEWAY = NotificationGateway()
    return _SHARED_NOTIFICATION_GATEWAY
