"""
General-purpose task execution skill.

The runtime now executes generated code in a short-lived subprocess instead of
direct `exec()` inside the agent process.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile

logger = logging.getLogger("agent.executor")

SKILL_NAME = "executor"

_CONFIG = None

DANGEROUS_PATTERNS = [
    r"import\s+os\b",
    r"from\s+os\s+import",
    r"os\.",
    r"import\s+sys\b",
    r"from\s+sys\s+import",
    r"import\s+subprocess",
    r"import\s+shutil",
    r"import\s+pty",
    r"__import__",
    r"eval\s*\(",
    r"exec\s*\(",
    r"open\s*\(",
    r"import\s+ctypes",
    r"import\s+socket",
]

RESULT_MARKER = "__RKTM83_RESULT__="


def set_config(full_config: dict):
    global _CONFIG
    _CONFIG = full_config


def _allow_dangerous() -> bool:
    if _CONFIG:
        return _CONFIG.get("executor", {}).get("allow_dangerous", False)
    return False


def _get_timeout() -> int:
    if _CONFIG:
        return _CONFIG.get("executor", {}).get("timeout", 10)
    return 10


def _check_safety(code: str) -> tuple:
    """
    Checks the code for dangerous patterns and blocks execution.
    """

    if _allow_dangerous():
        return True, "dangerous mode enabled"

    matches = []
    for pattern in DANGEROUS_PATTERNS:
        match = re.search(pattern, code)
        if match:
            matches.append(match.group())

    if matches:
        return False, f"Flagged dangerous patterns: {', '.join(matches)}"
    return True, "ok"


def _build_subprocess_code(code: str) -> str:
    return f"""import json
result = None

{code}

if 'result' in locals() and result is not None:
    try:
        print("{RESULT_MARKER}" + json.dumps(result, default=str))
    except Exception:
        print("{RESULT_MARKER}" + json.dumps(str(result)))
"""


def _execute_task(params: dict, context: dict, brain) -> dict:
    task = params.get("task", "")
    if not task:
        return {"success": False, "error": "task description required"}

    prompt = f"""Write Python code to accomplish this task:

TASK: {task}

RULES:
- Write ONLY executable Python code, no markdown, no explanations
- Use print() for any output you want to show
- Keep it under 30 lines
- Only use standard library modules
- Store results in a variable called 'result' if applicable

Output ONLY the Python code:"""

    code = brain._infer(prompt)
    if not code:
        return {"success": False, "error": "LLM failed to generate code"}

    code = re.sub(r"^```(?:python)?\n?", "", code.strip())
    code = re.sub(r"\n?```$", "", code.strip())
    return _run_code({"code": code, "task": task}, context, brain)


def _run_code(params: dict, context: dict, brain) -> dict:
    del context
    code = params.get("code", "")
    task = params.get("task", "manual execution")

    if not code:
        return {"success": False, "error": "code required"}

    safe, reason = _check_safety(code)
    if not safe:
        logger.warning("Executor blocked: %s", reason)
        brain.memory.observe(
            f"Executor blocked: {reason}",
            {"source": "executor", "type": "warning", "reason": reason},
        )
        return {"success": False, "error": f"Security block: {reason}"}

    wrapped_code = _build_subprocess_code(code)
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            encoding="utf-8",
        ) as temp_file:
            temp_file.write(wrapped_code)
            temp_path = temp_file.name

        completed = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True,
            text=True,
            timeout=_get_timeout(),
            check=False,
        )

        stdout_lines = []
        result_value = None
        for line in completed.stdout.splitlines():
            if line.startswith(RESULT_MARKER):
                payload = line[len(RESULT_MARKER) :]
                try:
                    result_value = json.loads(payload)
                except json.JSONDecodeError:
                    result_value = payload
            else:
                stdout_lines.append(line)

        stdout = "\n".join(stdout_lines).strip()
        stderr = completed.stderr.strip()

        if completed.returncode == 0:
            brain.memory.observe(
                f"Executed: {task[:80]}",
                {
                    "source": "executor",
                    "type": "execution",
                    "task": task[:100],
                    "output": (stdout or str(result_value))[:200],
                    "status": "success",
                },
            )
            brain.memory.log(
                "executor",
                "ok",
                f"{task[:40]}: {(stdout or str(result_value))[:40]}",
            )
            return {
                "success": True,
                "output": stdout[:2000],
                "stderr": stderr[:1000],
                "result": str(result_value)[:500] if result_value is not None else None,
                "returncode": completed.returncode,
                "code": code,
            }

        brain.memory.observe(
            f"Execution failed: {task[:80]}",
            {
                "source": "executor",
                "type": "error",
                "task": task[:100],
                "error": stderr[:200] or f"returncode={completed.returncode}",
            },
        )
        logger.error(
            "Execution failed: %s - returncode=%s",
            task[:40],
            completed.returncode,
        )
        return {
            "success": False,
            "error": stderr[:500] or f"Process exited with code {completed.returncode}",
            "output": stdout[:1000],
            "stderr": stderr[:1000],
            "returncode": completed.returncode,
            "code": code,
        }
    except subprocess.TimeoutExpired as e:
        logger.error("Execution timed out: %s", task[:40])
        return {
            "success": False,
            "error": f"Execution timed out after {_get_timeout()}s",
            "output": (e.stdout or "")[:1000],
            "stderr": (e.stderr or "")[:1000],
            "code": code,
        }
    except Exception as e:
        logger.error("Execution failed: %s", e)
        return {"success": False, "error": str(e), "code": code}
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def register(agent):
    agent.brain.register_tool(
        "execute_task",
        "Describe ANY task in plain English and the LLM will write Python code to do it. "
        "Use for data processing, calculations, text manipulation, API calls, "
        "or anything that Python can do. The code runs locally in a subprocess.",
        _execute_task,
    )
    agent.brain.register_tool(
        "run_code",
        "Run a specific Python code snippet directly. "
        "Use when you already know what code to run. "
        "Execution happens in a short-lived subprocess sandbox.",
        _run_code,
    )

    mode = "DANGEROUS" if _allow_dangerous() else "SAFE"
    logger.info("Executor skill registered: 2 tools (%s mode)", mode)
    return agent
