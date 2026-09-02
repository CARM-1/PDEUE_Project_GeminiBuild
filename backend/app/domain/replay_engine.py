from datetime import datetime
from typing import List, Dict, Any
from app.domain.underwriting_pipeline import UnderwritingPipeline

class ReplayEngine:
    def run_replay(self, cutoff_times: List[datetime], evidence_stream: List[Dict[str, Any]], market_snapshot: Dict[str, Any], strike_temp: float) -> List[Dict[str, Any]]:
        pipeline = UnderwritingPipeline()
        results = []
        for cutoff in cutoff_times:
            res = pipeline.run_underwriting(cutoff, evidence_stream, market_snapshot, strike_temp)
            results.append({"cutoff": cutoff.isoformat(), "result": res})
        return results
