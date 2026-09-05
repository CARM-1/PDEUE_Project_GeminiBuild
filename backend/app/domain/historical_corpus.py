from typing import List, Dict, Any

def get_historical_tick_corpus() -> List[Dict[str, Any]]:
    ticks = []
    # Weather (12 ticks)
    for i in range(12):
        ticks.append({
            'contract_id': f'WX-KORD-D{i+1:02d}', 'category': 'WEATHER',
            'entry_ask': 0.15 + (i % 4) * 0.05, 'peak_midpoint': 0.82 if i % 2 == 0 else 0.45,
            'final_payout': 1.0 if i % 3 != 0 else 0.0, 'fee_rate': 0.01
        })
    # Macro (12 ticks)
    for i in range(12):
        ticks.append({
            'contract_id': f'MACRO-CPI-M{i+1:02d}', 'category': 'MACROECONOMIC',
            'entry_ask': 0.40 + (i % 3) * 0.08, 'peak_midpoint': 0.88 if i % 3 == 0 else 0.55,
            'final_payout': 1.0 if i % 2 == 0 else 0.0, 'fee_rate': 0.01
        })
    # Sports (12 ticks)
    for i in range(12):
        ticks.append({
            'contract_id': f'SPORTS-NFL-W{i+1:02d}', 'category': 'SPORTS',
            'entry_ask': 0.45 + (i % 2) * 0.05, 'peak_midpoint': 0.94 if i % 2 == 1 else 0.60,
            'final_payout': 1.0 if i % 4 != 0 else 0.0, 'fee_rate': 0.01
        })
    # Crypto (12 ticks)
    for i in range(12):
        ticks.append({
            'contract_id': f'CRYPTO-BTC-T{i+1:02d}', 'category': 'CRYPTO',
            'entry_ask': 0.22 + (i % 4) * 0.06, 'peak_midpoint': 0.80 if i % 2 == 0 else 0.30,
            'final_payout': 1.0 if i % 3 == 1 else 0.0, 'fee_rate': 0.00
        })
    return ticks
