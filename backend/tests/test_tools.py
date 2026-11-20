# tests/test_tools.py
# Author: Suresh D R | AI Product Developer & Technology Mentor

from src.tools.database_tools import _fallback_churn_score


def test_fallback_churn_score_is_deterministic():
    score1 = _fallback_churn_score("CUST_1000")
    score2 = _fallback_churn_score("CUST_1000")
    assert score1 == score2


def test_fallback_churn_score_in_valid_range():
    for cid in ["CUST_1000", "CUST_1001", "CUST_9999"]:
        score = _fallback_churn_score(cid)
        assert 0.0 <= score <= 1.0


def test_fallback_churn_score_varies_by_customer():
    scores = {_fallback_churn_score(f"CUST_{i}") for i in range(20)}
    assert len(scores) > 1, "Expected different customers to get different scores"
