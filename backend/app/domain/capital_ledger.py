from typing import Dict, Any, Optional

class CapitalLedger:
    def __init__(self, initial_balance_cents: int = 10000000):
        self.master_balance_cents = initial_balance_cents
        self.central_family_pool_cents = 0
        self.founder_pool_cents = 0
        self.members: Dict[str, Dict[str, Any]] = {}
        self.reservations: Dict[str, int] = {}
        self.reservation_owners: Dict[str, str] = {}
        self.commitments: Dict[str, int] = {}

    @property
    def balance_cents(self) -> int:
        return self.master_balance_cents

    @balance_cents.setter
    def balance_cents(self, value: int) -> None:
        self.master_balance_cents = value

    def register_member_account(self, member_id: str, seed_capital_cents: int, max_risk_pct: float = 0.05) -> Dict[str, Any]:
        if member_id not in self.members:
            self.members[member_id] = {
                'member_id': member_id,
                'balance_cents': max(0, seed_capital_cents),
                'reserved_cents': 0,
                'max_risk_pct': max(0.01, min(0.05, max_risk_pct)),
                'lifetime_profit_cents': 0
            }
        return self.members[member_id]

    def reserve_member_capital(self, reservation_id: str, member_id: str, amount_cents: int) -> bool:
        if amount_cents <= 0:
            return False
        mem = self.members.get(member_id)
        if not mem or mem['balance_cents'] < amount_cents:
            return False
        mem['balance_cents'] -= amount_cents
        mem['reserved_cents'] += amount_cents
        self.reservations[reservation_id] = amount_cents
        self.reservation_owners[reservation_id] = member_id
        return True

    def release_member_reservation(self, reservation_id: str) -> bool:
        amt = self.reservations.pop(reservation_id, None)
        if amt is None:
            return False
        mid = self.reservation_owners.pop(reservation_id, 'MASTER')
        if mid == 'MASTER':
            self.master_balance_cents += amt
            return True
        mem = self.members.get(mid)
        if mem:
            mem['balance_cents'] += amt
            mem['reserved_cents'] -= amt
            return True
        return False

    def credit_member_balance(self, member_id: str, amount_cents: int) -> int:
        mem = self.members.get(member_id)
        if mem and amount_cents > 0:
            mem['balance_cents'] += amount_cents
            return mem['balance_cents']
        return 0

    def credit_central_family_pool(self, amount_cents: int) -> int:
        if amount_cents > 0:
            self.central_family_pool_cents += amount_cents
        return self.central_family_pool_cents

    def credit_founder_pool(self, amount_cents: int) -> int:
        if amount_cents > 0:
            self.founder_pool_cents += amount_cents
        return self.founder_pool_cents

    def reserve_capital(self, reservation_id: str, amount_cents: int, account_id: str = 'MASTER') -> bool:
        if account_id != 'MASTER' and account_id in self.members:
            return self.reserve_member_capital(reservation_id, account_id, amount_cents)
        if amount_cents <= 0 or amount_cents > self.master_balance_cents:
            return False
        self.master_balance_cents -= amount_cents
        self.reservations[reservation_id] = amount_cents
        self.reservation_owners[reservation_id] = 'MASTER'
        return True

    def release_reservation(self, reservation_id: str, account_id: str = 'MASTER') -> bool:
        return self.release_member_reservation(reservation_id)

    def commit_reservation(self, reservation_id: str) -> bool:
        amt = self.reservations.pop(reservation_id, None)
        if amt is None:
            return False
        self.reservation_owners.pop(reservation_id, None)
        self.commitments[reservation_id] = amt
        return True

    def credit_balance(self, amount_cents: int, account_id: str = 'MASTER') -> int:
        if account_id != 'MASTER' and account_id in self.members:
            return self.credit_member_balance(account_id, amount_cents)
        if amount_cents > 0:
            self.master_balance_cents += amount_cents
        return self.master_balance_cents
