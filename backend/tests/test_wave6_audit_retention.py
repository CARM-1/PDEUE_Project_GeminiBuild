from app.domain.audit_retention import AuditRetentionEngine

def test_audit_hash_chain_continuity():
    engine = AuditRetentionEngine()
    e1 = engine.record_event("tenant_alpha", "LOGIN", "user_01", {"ip": "127.0.0.1"})
    e2 = engine.record_event("tenant_alpha", "ORDER_SUBMIT", "user_01", {"order_id": "ORD_10"})
    
    assert len(engine.audit_chain) == 2
    assert e2["prev_hash"] == e1["entry_hash"]
    assert engine.verify_chain_integrity() is True

def test_tamper_detection_in_audit_chain():
    engine = AuditRetentionEngine()
    engine.record_event("tenant_beta", "CONFIG_UPDATE", "admin", {"setting": "conservative"})
    engine.record_event("tenant_beta", "RISK_OVERRIDE", "admin", {"approved": True})
    
    assert engine.verify_chain_integrity() is True
    # Simulate unauthorized record mutation
    engine.audit_chain[0]["event"]["details"]["setting"] = "aggressive"
    assert engine.verify_chain_integrity() is False

def test_tenant_export_manifest():
    engine = AuditRetentionEngine()
    engine.record_event("tenant_gamma", "DEPOSIT", "cashier", {"amount": 5000})
    manifest = engine.export_tenant_manifest("tenant_gamma")
    
    assert manifest["tenant_id"] == "tenant_gamma"
    assert manifest["total_records"] == 1
    assert manifest["chain_verified"] is True
    assert manifest["latest_root_hash"] == engine.last_hash
