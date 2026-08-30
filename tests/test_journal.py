import pytest

from lyceum.memory import Journal


def test_schema_and_decision_roundtrip(tmp_path):
    journal = Journal(tmp_path / "lyceum.db")
    decision_id = journal.record_decision("SPY", "NO_TRADE", "REJECTED", {"why": "test"})
    journal.record_counterfactual(decision_id, "LONG_STRADDLE", {"status": "pending"})
    assert journal.recent("decisions")[0]["action"] == "NO_TRADE"
    assert journal.recent("counterfactuals")[0]["decision_id"] == decision_id


def test_unsupported_table_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        Journal(tmp_path / "lyceum.db").recent("orders; DROP TABLE decisions")


def test_submitted_order_activates_duplicate_protection(tmp_path):
    journal = Journal(tmp_path / "lyceum.db")
    assert journal.has_client_order("lyceum-order-1") is False
    journal.record_order("lyceum-order-1", "SUBMITTED", {"id": "paper-order"})
    assert journal.has_client_order("lyceum-order-1") is True


def test_order_intent_is_durable_and_terminal_rejection_can_be_retried(tmp_path):
    journal = Journal(tmp_path / "lyceum.db")
    first_id = journal.record_order("lyceum-order-1", "SUBMISSION_INTENT", {"request": "preview"})
    assert journal.has_client_order("lyceum-order-1") is True
    assert journal.record_order("lyceum-order-1", "UNKNOWN", {"error": "timeout"}) == first_id
    assert journal.has_client_order("lyceum-order-1") is True
    assert journal.record_order("lyceum-order-1", "REJECTED", {"error": "definitive"}) == first_id
    assert journal.has_client_order("lyceum-order-1") is False
