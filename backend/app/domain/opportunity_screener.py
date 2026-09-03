from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import math
from app.domain.advanced_weather_engine import AdvancedWeatherEngine

class OpportunityScreener:
    def __init__(self, weather_engine: Optional[AdvancedWeatherEngine] = None, min_edge_threshold: float = 0.03, fee_rate: float = 0.01):
        self.weather_engine = weather_engine or AdvancedWeatherEngine()
        self.min_edge_threshold = min_edge_threshold
        self.fee_rate = fee_rate

    def screen_weather_strike_ladder(
        self,
        ensemble_members: List[float],
        strike_ladder: List[Dict[str, Any]],
        station_id: Optional[str] = 'KORD'
    ) -> Dict[str, Any]:
        dist = self.weather_engine.compute_ngr_distribution(ensemble_members, station_id=station_id)
        mu, sigma = dist['mu'], dist['sigma']
        evaluated_candidates = []

        for contract in strike_ladder:
            strike = float(contract['strike_temp_c'])
            contract_id = contract.get('contract_id', f'STRIKE-{strike}')
            yes_ask = float(contract.get('yes_ask', 1.0))
            yes_bid = float(contract.get('yes_bid', 0.0))

            prob_res = self.weather_engine.calculate_exceedance_probability(
                strike_temp_c=strike,
                ensemble_members=ensemble_members,
                station_id=station_id
            )
            p_model = prob_res['probability']

            cost_yes = round(yes_ask * (1.0 + self.fee_rate), 4)
            net_edge_yes = round(p_model - cost_yes, 4)

            cost_no = round((1.0 - yes_bid) * (1.0 + self.fee_rate), 4)
            net_edge_no = round((1.0 - p_model) - cost_no, 4)

            if net_edge_yes >= net_edge_no and net_edge_yes >= self.min_edge_threshold:
                action = 'BUY_YES'
                best_edge = net_edge_yes
                entry_price = yes_ask
                target_prob = p_model
            elif net_edge_no > net_edge_yes and net_edge_no >= self.min_edge_threshold:
                action = 'BUY_NO'
                best_edge = net_edge_no
                entry_price = round(1.0 - yes_bid, 4)
                target_prob = round(1.0 - p_model, 4)
            else:
                action = 'PASS'
                best_edge = max(net_edge_yes, net_edge_no)
                entry_price = yes_ask
                target_prob = p_model

            variance = max(0.0001, target_prob * (1.0 - target_prob))
            sharpe = round(best_edge / math.sqrt(variance), 4)

            candidate = {
                'contract_id': contract_id,
                'strike_temp_c': strike,
                'model_probability': p_model,
                'yes_bid': yes_bid,
                'yes_ask': yes_ask,
                'recommended_action': action,
                'net_edge': best_edge,
                'entry_price': entry_price,
                'sharpe_ratio': sharpe,
                'method': prob_res['method']
            }
            if action != 'PASS':
                evaluated_candidates.append(candidate)

        evaluated_candidates.sort(key=lambda x: (x['net_edge'], x['sharpe_ratio']), reverse=True)
        for idx, item in enumerate(evaluated_candidates, 1):
            item['rank'] = idx

        return {
            'screened_at': datetime.now(timezone.utc).isoformat(),
            'station_id': station_id,
            'distribution': {'mu': mu, 'sigma': sigma},
            'total_evaluated': len(strike_ladder),
            'admissible_count': len(evaluated_candidates),
            'opportunities': evaluated_candidates,
            'top_pick': evaluated_candidates[0] if evaluated_candidates else None
        }
