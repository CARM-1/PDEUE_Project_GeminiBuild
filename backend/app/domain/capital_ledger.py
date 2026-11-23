from typing import Dict, Any, Optional

from app.domain.settlement_engine import calculate_hwm_waterfall_cents, _require_int_cents


class CapitalLedger:
    def __init__(self, initial_balance_cents: int = 10000000):
        _require_int_cents(initial_balance_cents, "initial_balance_cents")
        self.master_balance_cents = initial_balance_cents
        self.master_high_water_mark_cents = max(0, initial_balance_cents)
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
        _require_int_cents(seed_capital_cents, "seed_capital_cents")
        if member_id not in self.members:
            seed = max(0, seed_capital_cents)
            self.members[member_id] = {
                'member_id': member_id,
                'seed_capital_cents': seed,
                'balance_cents': seed,
                'reserved_cents': 0,
                'high_water_mark_cents': seed,
                'max_risk_pct': max(0.01, min(0.05, max_risk_pct)),
                'lifetime_profit_cents': 0
            }
        return self.members[member_id]

    def get_member_equity_cents(self, member_id: str) -> int:
        mem = self.members.get(member_id)
        if not mem:
            raise KeyError(f"SCMA account {member_id} not registered in ledger")
        return mem['balance_cents'] + mem.get('reserved_cents', 0)

    def get_member_high_water_mark_cents(self, member_id: str) -> int:
        mem = self.members.get(member_id)
        if not mem:
            raise KeyError(f"SCMA account {member_id} not registered in ledger")
        if 'high_water_mark_cents' not in mem:
            mem['high_water_mark_cents'] = self.get_member_equity_cents(member_id)
        return mem['high_water_mark_cents']

    def deposit_member_capital(self, member_id: str, amount_cents: int) -> Dict[str, Any]:
        """
        Credit new external principal to an SCMA.
        Under ADR-012, capital deposits raise high_water_mark_cents dollar-for-dollar
        so newly deposited principal is never treated as waterfall-eligible trading profit.
        """
        _require_int_cents(amount_cents, "amount_cents")
        if amount_cents <= 0:
            raise ValueError("Deposit amount_cents must be strictly positive")
        mem = self.members.get(member_id)
        if not mem:
            raise KeyError(f"SCMA account {member_id} not registered in ledger")

        hwm_before = self.get_member_high_water_mark_cents(member_id)
        mem['balance_cents'] += amount_cents
        mem['seed_capital_cents'] = mem.get('seed_capital_cents', 0) + amount_cents
        mem['high_water_mark_cents'] = hwm_before + amount_cents
        return {
            'member_id': member_id,
            'deposited_cents': amount_cents,
            'balance_cents': mem['balance_cents'],
            'equity_cents': self.get_member_equity_cents(member_id),
            'high_water_mark_before_cents': hwm_before,
            'high_water_mark_after_cents': mem['high_water_mark_cents'],
        }

    def withdraw_member_capital(self, member_id: str, amount_cents: int) -> Dict[str, Any]:
        """
        Debit an authorized withdrawal from an SCMA's unreserved balance.
        Under ADR-012, adjusts high_water_mark_cents proportionally in exact integer cents:
          H_after = (H_before * E_after) // E_before  (0 if E_before == 0 or E_after == 0)
        This preserves drawdown ratio during underwater withdrawals and reduces HWM
        dollar-for-dollar when at HWM, preventing post-withdrawal HWM lock-in.
        """
        _require_int_cents(amount_cents, "amount_cents")
        if amount_cents <= 0:
            raise ValueError("Withdrawal amount_cents must be strictly positive")
        mem = self.members.get(member_id)
        if not mem:
            raise KeyError(f"SCMA account {member_id} not registered in ledger")
        if amount_cents > mem['balance_cents']:
            raise ValueError("Insufficient unreserved balance for withdrawal")

        equity_before = self.get_member_equity_cents(member_id)
        hwm_before = self.get_member_high_water_mark_cents(member_id)

        mem['balance_cents'] -= amount_cents
        equity_after = self.get_member_equity_cents(member_id)

        if equity_before <= 0 or equity_after <= 0:
            hwm_after = max(0, equity_after)
        else:
            hwm_after = max(equity_after, (hwm_before * equity_after) // equity_before)

        mem['high_water_mark_cents'] = hwm_after
        return {
            'member_id': member_id,
            'withdrawn_cents': amount_cents,
            'balance_cents': mem['balance_cents'],
            'equity_cents': equity_after,
            'high_water_mark_before_cents': hwm_before,
            'high_water_mark_after_cents': hwm_after,
        }

    def settle_member_trade(
        self,
        member_id: str,
        realized_pnl_cents: int,
        reservation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Settle realized PnL for a member SCMA enforcing ADR-008 (exact integer cents),
        ADR-012 (per-SCMA High-Water Mark waterfall), and Rule A14 (100% SCMA loss isolation).

        - Realized losses stay 100% inside the executing SCMA; CFCP and FAEP never decrease.
        - Winning settlements below HWM stay 100% inside the SCMA (0% CFCP/FAEP skim).
        - Winning settlements above HWM apply 87/10/3 ONLY to net new profit above HWM
          (remainder cents routed to CFCP) and advance HWM to the new post-waterfall SCMA peak.
        """
        _require_int_cents(realized_pnl_cents, "realized_pnl_cents")
        mem = self.members.get(member_id)
        if not mem:
            raise KeyError(f"SCMA account {member_id} not registered in ledger")

        equity_before = self.get_member_equity_cents(member_id)
        hwm_before = self.get_member_high_water_mark_cents(member_id)

        if reservation_id is not None and reservation_id in self.reservations:
            if self.reservation_owners.get(reservation_id) != member_id:
                raise ValueError(f"Reservation {reservation_id} does not belong to {member_id}")
            self.release_member_reservation(reservation_id)

        result = calculate_hwm_waterfall_cents(
            realized_profit_cents=realized_pnl_cents,
            current_scma_equity_cents=equity_before,
            high_water_mark_cents=hwm_before,
        )

        mem['balance_cents'] += result['scma_cents']
        mem['high_water_mark_cents'] = result['high_water_mark_after_cents']
        mem['lifetime_profit_cents'] = mem.get('lifetime_profit_cents', 0) + result['scma_cents']

        if result['cfcp_cents'] > 0:
            self.credit_central_family_pool(result['cfcp_cents'])
        if result['faep_cents'] > 0:
            self.credit_founder_pool(result['faep_cents'])

        return result

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

    def get_capital_headroom(self) -> dict:
        total_equity_cents = (
            self.balance_cents
            + sum(member["balance_cents"] for member in self.members.values())
            + sum(self.reservations.values())
            + sum(self.commitments.values())
        )
        dry_powder_floor_cents = max(4_000, (total_equity_cents * 40 + 99) // 100)
        return {
            "total_equity_cents": total_equity_cents,
            "dry_powder_floor_cents": dry_powder_floor_cents,
            "dry_powder_compliant": self.balance_cents >= dry_powder_floor_cents,
        }
