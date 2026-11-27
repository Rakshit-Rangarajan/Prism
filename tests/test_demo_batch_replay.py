from demo.erp_learning_pipeline import Demo

def test_approved_rule_reused_on_independent_batch(tmp_path):
    engine = Demo(tmp_path / "replay.sqlite")
    try:
        first = engine.run(apply=True, batch=1)
        assert next(x for x in first if x["scenario"] == "currency_symbol")["status"] == "rejected"
        assert engine.approve("amount:legacy_format")
        second = engine.run(apply=True, batch=2)
        fixed = next(x for x in second if x["scenario"] == "currency_symbol")
        assert fixed["status"] == "migrated"
        assert "amount:legacy_format" in fixed["reused_lessons"]
        assert fixed["record"]["customer_id"].startswith("B2-")
        assert next(x for x in second if x["scenario"] == "duplicate_id")["status"] == "rejected"
    finally:
        engine.db.close()
