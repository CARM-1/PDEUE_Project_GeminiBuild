import uuid
from datetime import datetime, timezone
from sqlalchemy import BigInteger, Column, String, Integer, Float, ForeignKey, Text, event, inspect, text
from sqlalchemy.orm import relationship
from app.db.session import Base

def _now(): return datetime.now(timezone.utc).isoformat()

class UserModel(Base):
    __tablename__ = 'users'
    user_id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, index=True, default='default_tenant')
    username = Column(String, nullable=False, default='user')
    email = Column(String, nullable=True)
    role = Column(String, default='USER')
    created_at = Column(String, default=_now)
    accounts = relationship('AccountModel', back_populates='user', cascade='all, delete-orphan')
    def __init__(self, **kw):
        if 'id' in kw and 'user_id' not in kw: kw['user_id'] = kw.pop('id')
        super().__init__(**kw)
    @property
    def id(self): return self.user_id

class AccountModel(Base):
    __tablename__ = 'accounts'
    account_id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey('users.user_id'), nullable=False, index=True)
    tenant_id = Column(String, nullable=False, index=True, default='default_tenant')
    account_name = Column(String, nullable=True, default='Primary')
    balance_cents = Column(BigInteger, default=0)
    high_water_mark_cents = Column(BigInteger, nullable=False, default=0)
    currency = Column(String, default='USD')
    status = Column(String, default='ACTIVE')
    created_at = Column(String, default=_now)
    user = relationship('UserModel', back_populates='accounts')
    def __init__(self, **kw):
        if 'id' in kw and 'account_id' not in kw: kw['account_id'] = kw.pop('id')
        if 'high_water_mark_cents' not in kw:
            kw['high_water_mark_cents'] = max(0, int(kw.get('balance_cents', 0) or 0))
        super().__init__(**kw)
    @property
    def id(self): return self.account_id


@event.listens_for(Base.metadata, 'after_create')
def _ensure_accounts_high_water_mark_column(target, connection, **kw):
    """Idempotently backfill accounts.high_water_mark_cents on pre-ADR-012 SQLite DBs."""
    inspector = inspect(connection)
    if 'accounts' in inspector.get_table_names():
        columns = {col['name'] for col in inspector.get_columns('accounts')}
        if 'high_water_mark_cents' not in columns:
            connection.execute(text(
                'ALTER TABLE accounts ADD COLUMN high_water_mark_cents BIGINT NOT NULL DEFAULT 0'
            ))
            connection.execute(text(
                'UPDATE accounts SET high_water_mark_cents = COALESCE(balance_cents, 0)'
            ))


class PaperSessionModel(Base):
    __tablename__ = 'paper_sessions'
    session_id = Column(String, primary_key=True, index=True)
    account_id = Column(String, ForeignKey('accounts.account_id'), nullable=True, index=True)
    tenant_id = Column(String, nullable=False, index=True, default='default_tenant')
    initial_capital_cents = Column(Integer, default=100000)
    available_capital_cents = Column(Integer, default=100000)
    status = Column(String, default='ACTIVE')
    created_at = Column(String, default=_now)

class TradeRecordModel(Base):
    __tablename__ = 'trade_records'
    trade_id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey('paper_sessions.session_id'), nullable=True, index=True)
    contract_id = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    cost_cents = Column(Integer, nullable=False)
    timestamp = Column(String, default=_now)

User, Account, PaperSession, TradeRecord = UserModel, AccountModel, PaperSessionModel, TradeRecordModel
class TenantModel(Base):
    __tablename__ = 'tenants'
    tenant_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_at = Column(String, default=_now)
    principals = relationship('PrincipalModel', back_populates='tenant', cascade='all, delete-orphan')
    positions = relationship('PositionRecordModel', back_populates='tenant', cascade='all, delete-orphan')

class PrincipalModel(Base):
    __tablename__ = 'principals'
    principal_id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, ForeignKey('tenants.tenant_id'), nullable=False, index=True)
    role = Column(String, nullable=False)
    created_at = Column(String, default=_now)
    tenant = relationship('TenantModel', back_populates='principals')

class EventRecordModel(Base):
    __tablename__ = 'event_records'
    event_id = Column(String, primary_key=True, index=True)
    domain = Column(String, nullable=False)
    title = Column(String, nullable=False)
    resolution_source = Column(String, nullable=False)
    cutoff_timestamp = Column(String, nullable=False)
    created_at = Column(String, default=_now)
    evidence_items = relationship('EvidenceItemModel', back_populates='event', cascade='all, delete-orphan')

class EvidenceItemModel(Base):
    __tablename__ = 'evidence_items'
    evidence_id = Column(String, primary_key=True, index=True)
    event_id = Column(String, ForeignKey('event_records.event_id'), nullable=False, index=True)
    source = Column(String, nullable=False)
    published_at = Column(String, nullable=False)
    payload_json = Column(Text, nullable=False)
    event = relationship('EventRecordModel', back_populates='evidence_items')

class DecisionPacketRecordModel(Base):
    __tablename__ = 'decision_packet_records'
    packet_id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    event_id = Column(String, nullable=False, index=True)
    operating_mode = Column(String, nullable=False)
    model_probability = Column(Float, nullable=False)
    recommended_stake_cents = Column(Integer, nullable=False)
    packet_payload = Column(Text, nullable=False)
    created_at = Column(String, default=_now)
class OrderRecordModel(Base):
    __tablename__ = 'order_records'
    order_id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    contract_id = Column(String, nullable=False)
    venue = Column(String, nullable=False)
    side = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String, nullable=False)
    idempotency_key = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(String, default=_now)
    fills = relationship('FillRecordModel', back_populates='order', cascade='all, delete-orphan')

class FillRecordModel(Base):
    __tablename__ = 'fill_records'
    fill_id = Column(String, primary_key=True, index=True)
    order_id = Column(String, ForeignKey('order_records.order_id'), nullable=False, index=True)
    fill_price = Column(Float, nullable=False)
    fill_quantity = Column(Integer, nullable=False)
    recorded_at = Column(String, default=_now)
    order = relationship('OrderRecordModel', back_populates='fills')

class PositionRecordModel(Base):
    __tablename__ = 'position_records'
    position_id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, ForeignKey('tenants.tenant_id'), nullable=False, index=True)
    account_id = Column(String, nullable=False, index=True)
    contract_id = Column(String, nullable=False, index=True)
    side = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False, default=0)
    cost_basis_cents = Column(Integer, nullable=False, default=0)
    realized_pnl_cents = Column(Integer, nullable=False, default=0)
    updated_at = Column(String, default=_now)
    tenant = relationship('TenantModel', back_populates='positions')

class AuditLogRecordModel(Base):
    __tablename__ = 'audit_log_records'
    entry_id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, nullable=False, index=True)
    actor_id = Column(String, nullable=False)
    action = Column(String, nullable=False)
    prev_hash = Column(String, nullable=False)
    entry_hash = Column(String, nullable=False)
    payload = Column(Text, nullable=False)
    recorded_at = Column(String, default=_now)


class OnboardingMemberModel(Base):
    __tablename__ = 'onboarding_members'
    member_id = Column(String, primary_key=True, index=True)
    scma_id = Column(String, unique=True, nullable=False, index=True)
    full_name = Column(String, nullable=False)
    house_id = Column(Integer, nullable=False, index=True)
    lineage_code = Column(String, nullable=False, index=True)
    role_tier = Column(String, nullable=False, default='MEMBER_USER')
    seed_cents = Column(BigInteger, nullable=False)
    high_water_mark_cents = Column(BigInteger, nullable=False)
    risk_dial_bps = Column(Integer, nullable=False, default=150)
    is_custodial = Column(Integer, nullable=False, default=0)
    bank_ref_token = Column(String, nullable=False)
    status = Column(String, nullable=False, default='PENDING_TUTOR_CERTIFICATION')
    certification_level = Column(String, nullable=True)
    certified_at = Column(String, nullable=True)
    invite_activated_at = Column(String, nullable=True)
    created_by = Column(String, nullable=False, default='CHIEF_ADMINISTRATOR')
    created_at = Column(String, default=_now)


class OnboardingInviteTokenModel(Base):
    __tablename__ = 'onboarding_invite_tokens'
    token_hash = Column(String, primary_key=True, index=True)
    token_prefix = Column(String, nullable=False)
    member_id = Column(String, ForeignKey('onboarding_members.member_id'), nullable=False, index=True)
    scma_id = Column(String, nullable=False, index=True)
    expires_at = Column(String, nullable=False)
    consumed_at = Column(String, nullable=True)
    created_at = Column(String, default=_now)


class LineageHouseModel(Base):
    """Milestone C6: Relational 12-House Lineage Registry (HOUSE-01..HOUSE-12)."""
    __tablename__ = 'lineage_houses'
    house_id = Column(Integer, primary_key=True, index=True)
    lineage_code = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    leader_name = Column(String, nullable=False)
    leader_role = Column(String, nullable=False, default='H2')
    status = Column(String, nullable=False, default='ACTIVE')
    governance_seat = Column(Integer, nullable=False, default=1)
    created_at = Column(String, default=_now)
    updated_at = Column(String, default=_now)
    members = relationship('LineageHouseMemberModel', back_populates='house', cascade='all, delete-orphan')


class LineageHouseMemberModel(Base):
    """Milestone C6: Subordinate SCMA membership & exact 64-bit integer-cent rollups (ADR-008)."""
    __tablename__ = 'lineage_house_members'
    scma_id = Column(String, primary_key=True, index=True)
    house_id = Column(Integer, ForeignKey('lineage_houses.house_id'), nullable=False, index=True)
    member_id = Column(String, nullable=True)
    name = Column(String, nullable=False)
    role_tag = Column(String, nullable=False, default='Lineal Member')
    cash_cents = Column(BigInteger, nullable=False, default=0)
    high_water_mark_cents = Column(BigInteger, nullable=False, default=0)
    risk_dial_bps = Column(Integer, nullable=False, default=100)
    baseline_risk_dial_bps = Column(Integer, nullable=False, default=100)
    is_custodial = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default='ACTIVE')
    literacy_completion_pct = Column(Integer, nullable=False, default=100)
    open_orders_json = Column(Text, nullable=False, default='[]')
    created_at = Column(String, default=_now)
    updated_at = Column(String, default=_now)
    house = relationship('LineageHouseModel', back_populates='members')


class GovernanceConfigModel(Base):
    """Milestone C6: Global 3-Stage Governance Mode configuration (defaults fail-closed EXECUTIVE_COMMAND)."""
    __tablename__ = 'governance_config'
    config_id = Column(String, primary_key=True, default='GLOBAL')
    governance_mode = Column(String, nullable=False, default='EXECUTIVE_COMMAND')
    updated_by = Column(String, nullable=False, default='SYSTEM_INIT')
    updated_at = Column(String, default=_now)
    last_reason = Column(Text, nullable=True)


class GovernanceBodyModel(Base):
    """Milestone C6: Data-driven FUTURE Enclave communal bodies with configurable quorum/veto thresholds."""
    __tablename__ = 'governance_bodies'
    body_id = Column(String, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, nullable=False, default='')
    quorum_numerator = Column(Integer, nullable=False, default=9)
    quorum_denominator = Column(Integer, nullable=False, default=12)
    quorum_pct = Column(Integer, nullable=False, default=75)
    veto_threshold_count = Column(Integer, nullable=False, default=9)
    veto_threshold_pct = Column(Integer, nullable=False, default=75)
    can_exercise_stage3_veto = Column(Integer, nullable=False, default=1)
    active = Column(Integer, nullable=False, default=1)
    created_by = Column(String, nullable=False, default='CHIEF_ADMINISTRATOR')
    created_at = Column(String, default=_now)
    updated_at = Column(String, default=_now)
    seats = relationship('GovernanceVoterSeatModel', back_populates='body', cascade='all, delete-orphan')


class GovernanceVoterSeatModel(Base):
    """Milestone C6: Grants voting/veto rights to either a House/Role office or a specific named individual."""
    __tablename__ = 'governance_voter_seats'
    seat_id = Column(String, primary_key=True, index=True)
    body_id = Column(String, ForeignKey('governance_bodies.body_id'), nullable=False, index=True)
    seat_type = Column(String, nullable=False, default='HOUSE_OFFICE')
    house_id = Column(Integer, nullable=True, index=True)
    office_role = Column(String, nullable=True)
    user_id = Column(String, nullable=True, index=True)
    display_name = Column(String, nullable=False)
    can_vote = Column(Integer, nullable=False, default=1)
    can_veto = Column(Integer, nullable=False, default=0)
    active = Column(Integer, nullable=False, default=1)
    granted_by = Column(String, nullable=False, default='CHIEF_ADMINISTRATOR')
    granted_at = Column(String, default=_now)
    revoked_by = Column(String, nullable=True)
    revoked_at = Column(String, nullable=True)
    body = relationship('GovernanceBodyModel', back_populates='seats')


class GovernancePetitionModel(Base):
    """Milestone C6: Persisted governance proposals/petitions with ADR-008 exact-cent amounts."""
    __tablename__ = 'governance_petitions'
    proposal_id = Column(String, primary_key=True, index=True)
    body_id = Column(String, ForeignKey('governance_bodies.body_id'), nullable=False, default='COUNCIL_OF_12_HOUSES', index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False, default='')
    proposal_category = Column(String, nullable=False, default='CFCP_GRANT')
    target_house_id = Column(Integer, nullable=False, default=1)
    amount_cents = Column(BigInteger, nullable=False, default=0)
    status = Column(String, nullable=False, default='HOUSE_VOTE_OPEN')
    created_by = Column(String, nullable=False, default='SYSTEM')
    settled_by = Column(String, nullable=True)
    settled_at = Column(String, nullable=True)
    veto_reason = Column(Text, nullable=True)
    created_at = Column(String, default=_now)
    updated_at = Column(String, default=_now)
    votes = relationship('GovernanceVoteModel', back_populates='petition', cascade='all, delete-orphan')


class GovernanceVoteModel(Base):
    """Milestone C6: Persisted AYE / NAY / VETO ballots cast by House office or named individual seats."""
    __tablename__ = 'governance_votes'
    vote_id = Column(String, primary_key=True, index=True)
    proposal_id = Column(String, ForeignKey('governance_petitions.proposal_id'), nullable=False, index=True)
    body_id = Column(String, ForeignKey('governance_bodies.body_id'), nullable=False, index=True)
    seat_id = Column(String, ForeignKey('governance_voter_seats.seat_id'), nullable=True, index=True)
    voter_house_id = Column(Integer, nullable=True, index=True)
    voter_user_id = Column(String, nullable=True, index=True)
    voter_display_name = Column(String, nullable=False)
    vote_choice = Column(String, nullable=False)
    rationale = Column(Text, nullable=True, default='')
    cast_at = Column(String, default=_now)
    petition = relationship('GovernancePetitionModel', back_populates='votes')


