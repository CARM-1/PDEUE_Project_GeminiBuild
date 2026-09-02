from sqlalchemy import Column, String, Integer, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db.database import Base

class UserModel(Base):
    __tablename__ = "users"
    user_id = Column(String, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    created_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    accounts = relationship("AccountModel", back_populates="owner")

class AccountModel(Base):
    __tablename__ = "accounts"
    account_id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    account_name = Column(String, nullable=False)
    balance_cents = Column(Integer, nullable=False, default=0)
    created_at = Column(String, default=lambda: datetime.now(timezone.utc).isoformat())
    owner = relationship("UserModel", back_populates="accounts")
