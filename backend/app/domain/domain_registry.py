from typing import Dict, Any, Callable, Optional
from app.domain.weather_engine import WeatherProbabilityEngine
from app.domain.economic_engine import EconomicUnderwritingEngine
from app.domain.sports_adapter import SportsDomainAdapter
from app.domain.crypto_adapter import CryptoDomainAdapter

class DomainRegistry:
    def __init__(self):
        self.domains: Dict[str, Callable[[Dict[str, Any]], float]] = {}
        self._weather = WeatherProbabilityEngine()
        self._macro = EconomicUnderwritingEngine()
        self._sports = SportsDomainAdapter()
        self._crypto = CryptoDomainAdapter()

        self.register_domain('WEATHER', lambda s: self._weather.calculate_exceedance_probability(s.get('ensemble_members', []), s.get('strike_temp_c', 0.0), s.get('station_id')))
        self.register_domain('MACROECONOMIC', lambda s: self._macro.underwrite_indicator(s))
        self.register_domain('SPORTS', lambda s: self._sports.underwrite_game(s))
        self.register_domain('CRYPTO', lambda s: self._crypto.underwrite_threshold(s))

    def register_domain(self, category: str, underwriter: Callable[[Dict[str, Any]], float]) -> None:
        self.domains[category.upper()] = underwriter

    def underwrite(self, category: str, spec: Dict[str, Any]) -> Optional[float]:
        fn = self.domains.get(category.upper())
        if not fn:
            return None
        try:
            return float(fn(spec))
        except Exception:
            return None

    def get_underwriter(self, category: str) -> Optional[Callable]:
        return self.domains.get(category.upper())

    def get_domain(self, category: str) -> Optional[Callable]:
        return self.domains.get(category.upper())

    def get_adapter(self, category: str) -> Optional[Callable]:
        return self.domains.get(category.upper())
