"""
test_policy.py — Unit tests for PolicyEngine
Run: python -m pytest tests/test_policy.py -v
"""

import os
import sys
import json
import tempfile
import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_brain import PolicyEngine


class TestPolicyDefaults:
    """Test default policy limits and behavior."""

    def test_default_limits(self):
        p = PolicyEngine(state_path=None)
        assert p.limits["outreach_per_day"] == 5
        assert p.limits["outreach_per_week"] == 20
        assert p.limits["llm_calls_per_day"] == 150
        assert p.limits["search_calls_per_hour"] == 10

    def test_overrides(self):
        p = PolicyEngine({"outreach_per_day": 10}, state_path=None)
        assert p.limits["outreach_per_day"] == 10
        assert p.limits["llm_calls_per_day"] == 150  # unchanged

    def test_initial_status(self):
        p = PolicyEngine(state_path=None)
        s = p.status()
        assert "outreach" in s
        assert "llm_calls" in s
        assert "searches" in s
        assert s["total"] == 0


class TestPolicyDecisions:
    """Test ALLOW / DENY / ROUTE decisions."""

    def test_allow_outreach(self):
        p = PolicyEngine(state_path=None)
        verdict, _ = p.check("outreach")
        assert verdict == PolicyEngine.ALLOW

    def test_deny_outreach_at_limit(self):
        p = PolicyEngine({"outreach_per_day": 2}, state_path=None)
        p.record("outreach")
        p.record("outreach")
        verdict, reason = p.check("outreach")
        assert verdict == PolicyEngine.DENY
        assert "limit" in reason.lower()

    def test_deny_weekly_outreach(self):
        p = PolicyEngine({"outreach_per_day": 100, "outreach_per_week": 3}, state_path=None)
        for _ in range(3):
            p.record("outreach")
        verdict, reason = p.check("outreach")
        assert verdict == PolicyEngine.DENY
        assert "weekly" in reason.lower()

    def test_route_inference(self):
        p = PolicyEngine(state_path=None)
        verdict, _ = p.check("inference")
        assert verdict == PolicyEngine.ROUTE

    def test_allow_search(self):
        p = PolicyEngine(state_path=None)
        verdict, _ = p.check("search")
        assert verdict == PolicyEngine.ALLOW

    def test_deny_search_at_limit(self):
        p = PolicyEngine({"search_calls_per_hour": 2}, state_path=None)
        p.record("search")
        p.record("search")
        verdict, reason = p.check("search")
        assert verdict == PolicyEngine.DENY

    def test_allow_unknown_action(self):
        p = PolicyEngine(state_path=None)
        verdict, _ = p.check("unknown_action")
        assert verdict == PolicyEngine.ALLOW

    def test_network_check_with_target(self):
        """career_skill calls check('network', 'internshala.com')."""
        p = PolicyEngine(state_path=None)
        verdict, _ = p.check("network", "internshala.com")
        assert verdict == PolicyEngine.ALLOW


class TestPolicyRecording:
    """Test counter increments."""

    def test_record_outreach(self):
        p = PolicyEngine(state_path=None)
        p.record("outreach")
        assert p._state["outreach_today"] == 1
        assert p._state["outreach_week"] == 1
        assert p._state["total"] == 1

    def test_record_llm(self):
        p = PolicyEngine(state_path=None)
        p.record("llm")
        assert p._state["llm_calls_today"] == 1

    def test_record_search(self):
        p = PolicyEngine(state_path=None)
        p.record("search")
        assert p._state["search_calls_hour"] == 1

    def test_total_increments(self):
        p = PolicyEngine(state_path=None)
        p.record("outreach")
        p.record("llm")
        p.record("search")
        assert p._state["total"] == 3


class TestPolicyPersistence:
    """Test state save/load to JSON."""

    def test_save_and_load(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            tmp = f.name

        try:
            p1 = PolicyEngine(state_path=tmp)
            p1.record("outreach")
            p1.record("outreach")
            p1.record("llm")

            # Load in a new instance
            p2 = PolicyEngine(state_path=tmp)
            assert p2._state["outreach_today"] == 2
            assert p2._state["llm_calls_today"] == 1
            assert p2._state["total"] == 3
        finally:
            os.unlink(tmp)

    def test_no_state_path(self):
        """state_path=None should work without errors."""
        p = PolicyEngine(state_path=None)
        p.record("outreach")
        assert p._state["outreach_today"] == 1
