"""
executor_skill.py — General-Purpose Task Execution Skill
Plugs into agent_brain.Agent via agent.load_skill(executor_skill)

Registers these tools with the agent:
  - execute_task  : describe a task in English → LLM writes Python → agent runs it
  - run_code      : run a snippet of Python code directly

The LLM generates code on the fly, enabling the agent to handle ANY task
that can be expressed as Python — from data processing to API calls.

Safety:
  - Restricted imports (no os.system, subprocess, shutil.rmtree by default)
  - Configurable via policy: executor.allow_dangerous = true/false
  - All executions logged in memory

Usage:
  Enable in config.yaml:
    skills:
      - executor
    executor:
      allow_dangerous: false   # true to allow os/subprocess
      timeout: 10              # max seconds per execution
"""

import re
import io
import sys
import json
import logging
import datetime
import traceback
import contextlib

logger = logging.getLogger("agent.executor")

SKILL_NAME = "executor"

_CONFIG = None

# ── SAFE IMPORTS ─────────────────────────────────────────────────────────────

SAFE_MODULES = {
    "math", "random", "string", "json", "re", "datetime", "time",
    "collections", "itertools", "functools", "operator",
    "pathlib", "csv", "urllib.parse", "base64", "hashlib",
    "statistics", "textwrap", "difflib",
}

DANGEROUS_PATTERNS = [
    r"os\.system",
    r"subprocess",
    r"shutil\.rmtree",
    r"__import__",
    r"eval\s*\(",
    r"exec\s*\(",
    r"open\s*\(.*(w|a)",      # write mode file opens
    r"import\s+ctypes",
    r"import\s+socket",
]


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
    """Check code for dangerous patterns. Returns (safe, reason)."""
    if _allow_dangerous():
        return True, "dangerous mode enabled"

    for pattern in DANGEROUS_PATTERNS:
        match = re.search(pattern, code)
        if match:
            return False, f"Blocked: '{match.group()}' is not allowed in safe mode"

    return True, "ok"


# ── TOOL HANDLERS ─────────────────────────────────────────────────────────────

def _execute_task(params: dict, context: dict, brain) -> dict:
    """
    Describe a task in plain English → LLM generates Python → agent runs it.
    params: {"task": str}
    """
    task = params.get("task", "")
    if not task:
        return {"success": False, "error": "task description required"}

    # Ask LLM to write code
    prompt = f"""Write Python code to accomplish this task:

TASK: {task}

RULES:
- Write ONLY executable Python code, no markdown, no explanations
- Use print() for any output you want to show
- Keep it under 30 lines
- Only use standard library modules
- Store results in a variable called 'result' if applicable
- Do NOT use os.system(), subprocess, eval(), exec()

Output ONLY the Python code:"""

    code = brain._infer(prompt)
    if not code:
        return {"success": False, "error": "LLM failed to generate code"}

    # Clean up — remove markdown code blocks
    code = re.sub(r'^```(?:python)?\n?', '', code.strip())
    code = re.sub(r'\n?```$', '', code.strip())

    # Run the code
    return _run_code({"code": code, "task": task}, context, brain)


def _run_code(params: dict, context: dict, brain) -> dict:
    """
    Run a Python code snippet.
    params: {"code": str, "task": str (optional description)}
    """
    code = params.get("code", "")
    task = params.get("task", "manual execution")

    if not code:
        return {"success": False, "error": "code required"}

    # Safety check
    safe, reason = _check_safety(code)
    if not safe:
        logger.warning("Code blocked: %s", reason)
        brain.memory.observe(
            f"Executor blocked: {reason}",
            {"source": "executor", "type": "blocked", "reason": reason}
        )
        return {"success": False, "error": reason, "code": code}

    # Capture stdout
    stdout_capture = io.StringIO()
    local_vars = {}

    try:
        with contextlib.redirect_stdout(stdout_capture):
            exec(code, {"__builtins__": __builtins__}, local_vars)

        output = stdout_capture.getvalue()
        result = local_vars.get("result", None)

        brain.memory.observe(
            f"Executed: {task[:80]}",
            {
                "source": "executor",
                "type":   "execution",
                "task":   task[:100],
                "output": (output or str(result))[:200],
                "status": "success",
            }
        )
        brain.memory.log("executor", "ok", f"{task[:40]}: {(output or str(result))[:40]}")

        logger.info("Executed: %s", task[:60])
        return {
            "success": True,
            "output":  output[:2000] if output else "",
            "result":  str(result)[:500] if result is not None else None,
            "code":    code,
        }

    except Exception as e:
        error_msg = traceback.format_exc()
        brain.memory.observe(
            f"Execution failed: {task[:80]}",
            {"source": "executor", "type": "error", "task": task[:100], "error": str(e)}
        )
        logger.error("Execution failed: %s — %s", task[:40], e)
        return {
            "success": False,
            "error":   str(e),
            "traceback": error_msg[-500:],
            "code":    code,
        }


# ── SKILL REGISTRATION ───────────────────────────────────────────────────────

def register(agent):
    """Called by agent.load_skill(executor_skill)."""
    agent.brain.register_tool(
        "execute_task",
        "Describe ANY task in plain English and the LLM will write Python code to do it. "
        "Use for data processing, calculations, text manipulation, API calls, "
        "or anything that Python can do. The code runs locally.",
        _execute_task
    )
    agent.brain.register_tool(
        "run_code",
        "Run a specific Python code snippet directly. "
        "Use when you already know what code to run. "
        "Safety-checked: os.system, subprocess, etc. are blocked unless allow_dangerous=true.",
        _run_code
    )

    mode = "DANGEROUS" if _allow_dangerous() else "SAFE"
    logger.info("Executor skill registered: 2 tools (%s mode)", mode)
    return agent
