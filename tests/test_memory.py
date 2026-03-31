"""
test_memory.py — Unit tests for AgentMemory
Run: python -m pytest tests/test_memory.py -v
"""

import os
import sys
import shutil
import tempfile

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_brain import AgentMemory


def _temp_memory():
    """Create an AgentMemory in a temporary directory."""
    path = tempfile.mkdtemp(prefix="rktm83_test_")
    return AgentMemory(path=path), path


class TestMemoryInit:
    """Test memory initialization."""

    def test_creates_collections(self):
        mem, path = _temp_memory()
        try:
            stats = mem.stats()
            assert "observations" in stats
            assert "entities" in stats
            assert "actions" in stats
            assert "learned" in stats
            assert all(v == 0 for v in stats.values())
        finally:
            shutil.rmtree(path, ignore_errors=True)

    def test_id_generation(self):
        mem, path = _temp_memory()
        try:
            id1 = mem._id("test content")
            assert isinstance(id1, str)
            assert len(id1) > 0
            # Should be deterministic-ish with the hash suffix
            assert "_" in id1
        finally:
            shutil.rmtree(path, ignore_errors=True)


class TestMemoryObserve:
    """Test the observe method."""

    def test_observe_basic(self):
        mem, path = _temp_memory()
        try:
            mem.observe("test observation", {"type": "test"})
            assert mem.stats()["observations"] == 1
        finally:
            shutil.rmtree(path, ignore_errors=True)

    def test_observe_multiple(self):
        mem, path = _temp_memory()
        try:
            for i in range(5):
                mem.observe(f"observation {i}", {"index": str(i)})
            assert mem.stats()["observations"] == 5
        finally:
            shutil.rmtree(path, ignore_errors=True)

    def test_observe_no_metadata(self):
        mem, path = _temp_memory()
        try:
            mem.observe("bare observation")
            assert mem.stats()["observations"] == 1
        finally:
            shutil.rmtree(path, ignore_errors=True)


class TestMemoryRemember:
    """Test entity storage."""

    def test_remember_entity(self):
        mem, path = _temp_memory()
        try:
            mem.remember("Google", "company", "google_hq")
            assert mem.stats()["entities"] == 1
        finally:
            shutil.rmtree(path, ignore_errors=True)

    def test_remember_entity_alias(self):
        mem, path = _temp_memory()
        try:
            mem.remember_entity("Google", "company", "google_hq", {"url": "google.com"})
            assert mem.stats()["entities"] == 1
        finally:
            shutil.rmtree(path, ignore_errors=True)

    def test_remember_upsert(self):
        """remember() uses upsert — same uid should NOT create duplicate."""
        mem, path = _temp_memory()
        try:
            mem.remember("Google", "company", "google_hq")
            mem.remember("Google Inc", "company", "google_hq")
            assert mem.stats()["entities"] == 1
        finally:
            shutil.rmtree(path, ignore_errors=True)


class TestMemoryEntityStatus:
    """Test entity_status and update_entity."""

    def test_entity_status_found(self):
        mem, path = _temp_memory()
        try:
            mem.remember("Alice", "person", "alice_linkedin",
                         {"company": "Google", "contacted": "false"})
            status = mem.entity_status("alice_linkedin")
            assert status.get("name") == "Alice"
            assert status.get("contacted") == "false"
        finally:
            shutil.rmtree(path, ignore_errors=True)

    def test_entity_status_not_found(self):
        mem, path = _temp_memory()
        try:
            status = mem.entity_status("nonexistent")
            assert status == {}
        finally:
            shutil.rmtree(path, ignore_errors=True)

    def test_update_entity(self):
        mem, path = _temp_memory()
        try:
            mem.remember("Alice", "person", "alice_id", {"contacted": "false"})
            mem.update_entity("alice_id", {"contacted": "true"})
            status = mem.entity_status("alice_id")
            assert status.get("contacted") == "true"
        finally:
            shutil.rmtree(path, ignore_errors=True)


class TestMemoryLog:
    """Test action logging."""

    def test_log_basic(self):
        mem, path = _temp_memory()
        try:
            mem.log("search", "ok", "found 5 results")
            assert mem.stats()["actions"] == 1
        finally:
            shutil.rmtree(path, ignore_errors=True)

    def test_log_action_alias(self):
        mem, path = _temp_memory()
        try:
            mem.log_action("outreach", "alice_id", "DM sent", "approved")
            assert mem.stats()["actions"] == 1
        finally:
            shutil.rmtree(path, ignore_errors=True)


class TestMemoryLearn:
    """Test pattern learning."""

    def test_learn_basic(self):
        mem, path = _temp_memory()
        try:
            mem.learn("AI internship at Google", "positive")
            assert mem.stats()["learned"] == 1
        finally:
            shutil.rmtree(path, ignore_errors=True)

    def test_learn_with_confidence(self):
        mem, path = _temp_memory()
        try:
            mem.learn("AI internship at Google", "positive", 0.9)
            assert mem.stats()["learned"] == 1
        finally:
            shutil.rmtree(path, ignore_errors=True)


class TestMemorySearch:
    """Test semantic search."""

    def test_search_observations(self):
        mem, path = _temp_memory()
        try:
            mem.observe("AI internship at Google", {"type": "opportunity"})
            mem.observe("Python developer job", {"type": "opportunity"})
            results = mem.search("observations", "AI internship", n=5)
            assert len(results) > 0
        finally:
            shutil.rmtree(path, ignore_errors=True)

    def test_search_empty(self):
        mem, path = _temp_memory()
        try:
            results = mem.search("observations", "anything", n=5)
            assert results == []
        finally:
            shutil.rmtree(path, ignore_errors=True)

    def test_search_entities(self):
        mem, path = _temp_memory()
        try:
            mem.remember("Google", "company", "google_id")
            results = mem.search("entities", "Google", n=5)
            assert len(results) > 0
        finally:
            shutil.rmtree(path, ignore_errors=True)
