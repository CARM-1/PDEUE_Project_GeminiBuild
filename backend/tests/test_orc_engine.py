from app.domain.orc_engine import OpportunityResearchCenter

def test_orc_evaluate_weather_hypothesis():
    orc = OpportunityResearchCenter()
    dossier = orc.evaluate_hypothesis("Research opportunity in Florida citrus freeze damage")
    assert dossier["dossier_id"].startswith("DOS-")
    assert dossier["category"] == "WEATHER"
    assert dossier["verdict"] == "VALIDATED_ASYMMETRIC_EDGE"
    assert dossier["matched_contract"]["venue"] == "KALSHI"
    assert dossier["matched_contract"]["net_edge_pct"] > 25.0
    assert dossier["recommended_action_card"]["action_type"] == "STAGE_ORC_TRACKING_ORDER"

def test_orc_evaluate_crypto_hypothesis():
    orc = OpportunityResearchCenter()
    dossier = orc.evaluate_hypothesis("Analyze high-volatility Bitcoin asymmetry")
    assert dossier["category"] == "CRYPTO"
    assert dossier["matched_contract"]["contract_id"] == "POLY-239496"
    assert dossier["matched_contract"]["venue"] == "POLYMARKET"
    assert dossier["recommended_action_card"]["destructive"] is False

def test_orc_evaluate_generic_macro():
    orc = OpportunityResearchCenter()
    dossier = orc.evaluate_hypothesis("Check macro interest rate decisions")
    assert dossier["category"] == "MACRO"
    assert dossier["matched_contract"]["contract_id"] == "KX-ORD-26"
    assert "87% SCMA" in dossier["governance_compliance"]["waterfall_split"]
