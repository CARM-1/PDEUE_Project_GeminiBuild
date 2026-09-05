from typing import Dict, Any, List, Optional

class VerticalSpreadEngine:
    """B7-EXE Vertical Strike Ladder Convexity & Box Spread Arbitrage Engine."""
    def __init__(self, fee_rate: float = 0.01, min_profit_cents: int = 2):
        self.fee_rate = fee_rate
        self.min_profit_cents = min_profit_cents

    def sort_ladder(self, ladder: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(ladder, key=lambda x: float(x.get('strike_value', 0.0)))

    def detect_monotonicity_inversions(self, ladder: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sorted_ladder = self.sort_ladder(ladder)
        inversions = []
        for i in range(len(sorted_ladder) - 1):
            k1 = sorted_ladder[i]
            k2 = sorted_ladder[i + 1]
            k1_ask = float(k1.get('yes_ask', 1.0))
            k2_bid = float(k2.get('yes_bid', 0.0))
            
            if k2_bid > k1_ask:
                inversion_edge = round(k2_bid - k1_ask, 4)
                fee_cost = round((k1_ask + k2_bid) * self.fee_rate, 4)
                net_profit_cents = int(round((inversion_edge - fee_cost) * 100))
                if net_profit_cents >= self.min_profit_cents:
                    inversions.append({
                        'type': 'MONOTONICITY_INVERSION',
                        'lower_strike': k1['strike_value'],
                        'higher_strike': k2['strike_value'],
                        'buy_contract_id': k1['contract_id'],
                        'sell_contract_id': k2['contract_id'],
                        'buy_ask': k1_ask,
                        'sell_bid': k2_bid,
                        'net_profit_cents': net_profit_cents
                    })
        return inversions

    def detect_vertical_box_spreads(self, ladder: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sorted_ladder = self.sort_ladder(ladder)
        opportunities = []
        for i in range(len(sorted_ladder) - 1):
            for j in range(i + 1, len(sorted_ladder)):
                k1 = sorted_ladder[i]
                k2 = sorted_ladder[j]
                k1_yes_ask = float(k1.get('yes_ask', 1.0))
                k2_no_ask = float(k2.get('no_ask', 1.0 - float(k2.get('yes_bid', 0.0))))
                
                total_entry_cost = k1_yes_ask + k2_no_ask
                fee_cost = round(total_entry_cost * self.fee_rate, 4)
                net_cost = total_entry_cost + fee_cost
                
                if net_cost < 1.0:
                    net_floor_profit_cents = int(round((1.0 - net_cost) * 100))
                    if net_floor_profit_cents >= self.min_profit_cents:
                        opportunities.append({
                            'type': 'VERTICAL_BOX_ARBITRAGE',
                            'lower_strike': k1['strike_value'],
                            'higher_strike': k2['strike_value'],
                            'leg1_buy_yes_id': k1['contract_id'],
                            'leg2_buy_no_id': k2['contract_id'],
                            'leg1_price': k1_yes_ask,
                            'leg2_price': round(k2_no_ask, 4),
                            'total_entry_cents': int(round(net_cost * 100)),
                            'floor_profit_cents': net_floor_profit_cents,
                            'max_potential_profit_cents': net_floor_profit_cents + 100
                        })
        return opportunities

    def evaluate_ladder(self, ladder: List[Dict[str, Any]]) -> Dict[str, Any]:
        inversions = self.detect_monotonicity_inversions(ladder)
        box_spreads = self.detect_vertical_box_spreads(ladder)
        return {
            'total_contracts_scanned': len(ladder),
            'inversions_count': len(inversions),
            'box_spreads_count': len(box_spreads),
            'opportunities': inversions + box_spreads
        }
