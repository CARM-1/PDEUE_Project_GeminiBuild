from typing import Dict, Any, Callable, Optional
from app.domain.advanced_weather_engine import AdvancedWeatherEngine
from app.domain.domain_adapter_sdk import EconomicIndicatorAdapter

class DomainRegistry:
    def __init__(self):
        self._handlers: Dict[str, Callable] = {}
        self.weather_engine = AdvancedWeatherEngine()
        self.economic_adapter = EconomicIndicatorAdapter()
        self._register_default_domains()

    def _register_default_domains(self):
        self._handlers['WEATHER'] = self._underwrite_weather
        self._handlers['MACROECONOMIC'] = self._underwrite_macro

    def register_domain(self, category: str, handler: Callable):
        self._handlers[category.upper()] = handler

    def has_domain(self, category: str) -> bool:
        return category.upper() in self._handlers

    def _underwrite_weather(self, spec: Dict[str, Any]) -> float:
        strike = float(spec['strike_temp_c'])
        ensemble = spec.get('ensemble_members', [])
        station_id = spec.get('station_id', 'KORD')
        res = self.weather_engine.calculate_exceedance_probability(strike, ensemble, station_id)
        return res['probability']

    def _underwrite_macro(self, spec: Dict[str, Any]) -> float:
        threshold = float(spec['threshold'])
        evidence = spec.get('evidence', [])
        features = self.economic_adapter.extract_features(evidence)
        features['threshold'] = threshold
        artifact = self.economic_adapter.underwrite(features)
        return artifact['calibrated_probability']

    def calculate_probability(self, category: str, spec: Dict[str, Any]) -> Dict[str, Any]:
        cat = category.upper()
        if cat not in self._handlers:
            raise ValueError(f'Unsupported domain category: {category}')
        prob = self._handlers[cat](spec)
        return {'category': cat, 'model_probability': round(prob, 4), 'underwritten': True}
