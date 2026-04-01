"""
Offline filesystem skill tests.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills import filesystem_skill


class DummyMemory:
    def observe(self, *args, **kwargs):
        return None


class DummyBrain:
    def __init__(self):
        self.memory = DummyMemory()


def test_organize_folder_dry_run(tmp_path):
    filesystem_skill.WORKSPACE_ROOT = tmp_path
    (tmp_path / "photo.jpg").write_text("image", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("text", encoding="utf-8")
    (tmp_path / "script.py").write_text("print('hi')", encoding="utf-8")

    result = filesystem_skill._organize_folder(
        {"path": str(tmp_path), "dry_run": True},
        {},
        DummyBrain(),
    )

    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["moved"] == 0
    assert result["plan"]["Images"] == 1
    assert result["plan"]["Text"] == 1
    assert result["plan"]["Code"] == 1
    assert (tmp_path / "photo.jpg").exists()
    assert (tmp_path / "notes.txt").exists()
    assert (tmp_path / "script.py").exists()
