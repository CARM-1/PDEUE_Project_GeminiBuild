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
