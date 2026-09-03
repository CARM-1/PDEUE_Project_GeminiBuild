import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, ForeignKey, Text
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
    balance_cents = Column(Integer, default=0)
    currency = Column(String, default='USD')
    status = Column(String, default='ACTIVE')
    created_at = Column(String, default=_now)
    user = relationship('UserModel', back_populates='accounts')
    def __init__(self, **kw):
        if 'id' in kw and 'account_id' not in kw: kw['account_id'] = kw.pop('id')
        super().__init__(**kw)
    @property
    def id(self): return self.account_id

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
