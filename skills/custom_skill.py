"""
custom_skill.py — Your Own Skill Template
Drop this in the skills/ folder, add "custom" to config.yaml skills list.

A skill is just a Python file with a register(agent) function.
That function calls agent.brain.register_tool() for each tool you want.

Tool handler signature:
  def my_tool(params: dict, context: dict, brain) -> dict:
      # params   — whatever the LLM passes in
      # context  — current agent context (cycle, time, memory stats, etc.)
      # brain    — access to brain._call_inference(), brain.memory, brain.policy
      return {"success": True, "data": "whatever you want"}
"""

import logging
logger = logging.getLogger("agent.custom")

SKILL_NAME = "custom"


# ── YOUR TOOLS ────────────────────────────────────────────────────────────────
# Add as many tools as you want below.
# Each tool is a function + a description the LLM reads to decide when to use it.


def _my_first_tool(params: dict, context: dict, brain) -> dict:
    """
    Example tool — replace this with whatever you want.
    The LLM will call this when it decides it's the right action.
    """
    logger.info("my_first_tool called with params: %s", params)

    # Example: call the LLM with a custom prompt
    response = brain._call_inference(
        "Say something funny about autonomous agents in one sentence."
    )

    return {
        "success": True,
        "response": response,
    }


def _my_second_tool(params: dict, context: dict, brain) -> dict:
    """Another example tool."""
    # Store something in memory
    brain.memory.observe(
        "custom tool ran successfully",
        {"source": "custom_skill", "type": "event"}
    )
    return {"success": True}


# ── REGISTER ──────────────────────────────────────────────────────────────────

def register(agent):
    """
    Called automatically by run_agent.py when this skill is loaded.
    Register all your tools here.
    """
    agent.brain.register_tool(
        "my_first_tool",
        "Say something funny. Use when the agent needs a break from being serious.",
        _my_first_tool
    )

    agent.brain.register_tool(
        "my_second_tool",
        "Run the second custom tool. Use when my_first_tool has already run this cycle.",
        _my_second_tool
    )

    logger.info("Custom skill loaded: 2 tools registered")
    return agent
