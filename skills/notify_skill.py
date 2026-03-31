"""
Windows notification skill using win10toast-click.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("agent.notify")

SKILL_NAME = "notify"

try:
    from win10toast_click import ToastNotifier
except ImportError:  # pragma: no cover - dependency shim
    ToastNotifier = None

_TOASTER = None


def _get_toaster():
    global _TOASTER
    if ToastNotifier is None:
        raise RuntimeError("win10toast-click is not installed")
    if _TOASTER is None:
        _TOASTER = ToastNotifier()
    return _TOASTER


def _notify(params: dict, context: dict, brain) -> dict:
    del context, brain
    title = params.get("title", "RKTM83")
    message = params.get("message", "")
    duration = int(params.get("duration", 5))
    threaded = bool(params.get("threaded", True))

    if not message:
        return {"success": False, "error": "message required"}

    try:
        toaster = _get_toaster()
        toaster.show_toast(title, message, duration=duration, threaded=threaded)
        logger.info("Notification sent: %s", title)
        return {"success": True, "title": title, "message": message[:200]}
    except Exception as e:
        logger.error("notify error: %s", e)
        return {"success": False, "error": str(e)}


def register(agent):
    agent.brain.register_tool(
        "notify",
        "Send a Windows toast notification summarizing agent progress or results.",
        _notify,
    )
    logger.info("Notify skill registered: 1 tool")
    return agent
