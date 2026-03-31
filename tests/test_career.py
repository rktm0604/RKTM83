"""
Offline career skill tests.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills import career_skill


class DummyMemory:
    def __init__(self):
        self.learned = []

    def learn(self, pattern, signal, confidence):
        self.learned.append((pattern, signal, confidence))


class DummyBrain:
    def __init__(self, response):
        self._response = response
        self.memory = DummyMemory()

    def _infer(self, prompt):
        assert "Evaluate this opportunity" in prompt
        return self._response


def test_score_opportunity_parses_json():
    brain = DummyBrain(
        '{"score": 8, "fit": "HIGH", "reason": "Great fit", "angle": "Lead with RAG work"}'
    )
    result = career_skill._score_opportunity(
        {
            "title": "AI Intern",
            "company": "Acme",
            "description": "Build RAG pipelines",
        },
        {},
        brain,
    )

    assert result["success"] is True
    assert result["score"] == 8
    assert result["fit"] == "HIGH"
    assert brain.memory.learned
