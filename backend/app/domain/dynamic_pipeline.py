from typing import Dict, Any, Optional
from app.domain.data_ingestion import DataIngestionEngine
from app.domain.market_stream import MarketStreamAdapter

class DynamicUnderwritingEngine:
    def __init__(self):
        self.ingestion = DataIngestionEngine()
        self.stream = MarketStreamAdapter()

    def process_event_and_evaluate(self, station_id: str, temp_c: float, timestamp: str, ticker: str, yes_bid: float, yes_ask: float) -> Dict[str, Any]:
        obs = self.ingestion.ingest_noaa_observation(station_id, temp_c, timestamp)
        book = self.stream.update_order_book(ticker, yes_bid, yes_ask)
        
        estimated_prob = 0.75 if temp_c > 20.0 else 0.25
        edge = round(estimated_prob - book["yes_ask"], 4)
        
        decision_packet = {
            "ticker": ticker,
            "observation": obs,
            "market_book": book,
            "estimated_probability": estimated_prob,
            "edge": edge,
            "recommended_action": "BUY_YES" if edge > 0.05 else "HOLD"
        }
        return decision_packet
