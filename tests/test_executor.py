"""
Offline tests for executor skill safety diagnostics and subprocess sandbox.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from skills import executor_skill


class DummyMemory:
    def __init__(self):
        self.events = []

    def observe(self, *args, **kwargs):
        self.events.append((args, kwargs))

    def log(self, *args, **kwargs):
        self.events.append((args, kwargs))


class DummyBrain:
    def __init__(self):
        self.memory = DummyMemory()


class TestExecutorSafety:
    def test_flags_subprocess_pattern(self):
        safe, reason = executor_skill._check_safety("import subprocess\nsubprocess.run(['dir'])")
        assert safe is False
        assert "subprocess" in reason

    def test_flags_os_system_pattern(self):
        safe, reason = executor_skill._check_safety("import os\nos.system('dir')")
        assert safe is False
        assert "os.system" in reason


class TestExecutorSandbox:
    def test_runs_code_in_subprocess(self):
        brain = DummyBrain()
        result = executor_skill._run_code(
            {"code": "result = 2 + 2\nprint('hello')", "task": "math"},
            {},
            brain,
        )
        assert result["success"] is True
        assert result["returncode"] == 0
        assert "hello" in result["output"]
        assert result["result"] == "4"
