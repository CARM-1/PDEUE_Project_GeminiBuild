from typing import Dict, Any

class CapitalLedger:
    def __init__(self, initial_balance_cents: int):
        self.balance_cents = initial_balance_cents
        self.reservations: Dict[str, int] = {}

    def reserve_capital(self, reservation_id: str, amount_cents: int) -> bool:
        if amount_cents <= 0 or amount_cents > self.balance_cents:
            return False
        self.balance_cents -= amount_cents
        self.reservations[reservation_id] = amount_cents
        return True
