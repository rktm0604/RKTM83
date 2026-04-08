"""
desktop_skill.py — Desktop Control Skill
Plugs into agent_brain.Agent via agent.load_skill(desktop_skill)

Registers these tools with the agent:
  - open_app      : launch any application by name
  - type_text     : type text into the active window
  - screenshot    : capture the screen
  - hotkey        : send keyboard shortcuts

Tech: pyautogui + subprocess

Usage:
  pip install pyautogui Pillow
  Enable in config.yaml:
    skills:
      - desktop
"""

import os
import re
import json
import time
import logging
import subprocess
import datetime

logger = logging.getLogger("agent.desktop")

SKILL_NAME = "desktop"

_CONFIG = None

# ── KNOWN APPS (Windows) ─────────────────────────────────────────────────────

KNOWN_APPS = {
    "notepad":     "notepad.exe",
    "calculator":  "calc.exe",
    "cmd":         "cmd.exe",
    "powershell":  "powershell.exe",
    "terminal":    "wt.exe",
    "explorer":    "explorer.exe",
    "paint":       "mspaint.exe",
    "chrome":      r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "firefox":     r"C:\Program Files\Mozilla Firefox\firefox.exe",
    "edge":        "msedge.exe",
    "vscode":      "code",
    "code":        "code",
    "word":        "winword.exe",
    "excel":       "excel.exe",
    "powerpoint":  "powerpnt.exe",
    "spotify":     r"C:\Users\{user}\AppData\Roaming\Spotify\Spotify.exe",
    "microsoft word": "winword.exe",
    "microsoft excel": "excel.exe",
    "microsoft powerpoint": "powerpnt.exe",
    "wps":         r"C:\Program Files (x86)\WPS Office\10.1.0.6714\office6\wps.exe",
    "wpse":        r"C:\Program Files (x86)\WPS Office\10.1.0.6714\office6\et.exe",
    "wpp":         r"C:\Program Files (x86)\WPS Office\10.1.0.6714\office6\wpp.exe",
}


def set_config(full_config: dict):
    global _CONFIG
    _CONFIG = full_config


def _resolve_app(name: str) -> str | None:
    """Resolve app name to executable path. Only allows KNOWN_APPS."""
    name_lower = name.lower().strip()

    # Check known apps
    if name_lower in KNOWN_APPS:
        path = KNOWN_APPS[name_lower]
        # Replace {user} placeholder
        if "{user}" in path:
            path = path.replace("{user}", os.environ.get("USERNAME", ""))
        return path

    # Security block: Do not allow arbitrary paths or unapproved executables.
    return None


# ── TOOL HANDLERS ─────────────────────────────────────────────────────────────

def _open_app(params: dict, context: dict, brain) -> dict:
    """
    Open an application by name, optionally with a file.
    params: {"app": str, "file_path": str (optional), "args": str (optional)}
    """
    app_name = params.get("app", "")
    file_path = params.get("file_path", "")
    args = params.get("args", "")

    if not app_name:
        return {"success": False, "error": "app name required"}

    exe = _resolve_app(app_name)
    if not exe:
        logger.warning("Desktop blocked launching unapproved app: %s", app_name)
        brain.memory.observe(
            f"Blocked unapproved app launch: {app_name}",
            {"source": "desktop", "type": "warning", "reason": "Not in KNOWN_APPS"}
        )
        return {"success": False, "error": f"App '{app_name}' is not in approved apps. Add it to KNOWN_APPS in desktop_skill.py."}

    try:
        # If file_path is provided, try to open it
        if file_path:
            # Convert to Windows path - handle both forward and back slashes
            win_path = file_path.replace("/", "\\")
            
            # Expand user home directory if ~ is used
            if win_path.startswith("~"):
                win_path = os.path.expanduser(win_path)
            
            # Check if file exists first
            if not os.path.exists(win_path):
                # Try to find the file in common locations
                filename = os.path.basename(win_path)
                possible_paths = [
                    win_path,
                    os.path.join(os.path.expanduser("~"), "Downloads", filename),
                    os.path.join(os.path.expanduser("~"), "Desktop", filename),
                    os.path.join(os.path.expanduser("~"), "Documents", filename),
                ]
                
                for p in possible_paths:
                    if os.path.exists(p):
                        win_path = p
                        break
                else:
                    return {"success": False, "error": f"File not found: {win_path}. Checked: {possible_paths}"}
            
            # Try to open the file with the associated app
            try:
                # Method 1: Use startfile for the file
                os.startfile(win_path)
                brain.memory.observe(
                    f"Opened file: {file_path} with {app_name}",
                    {"source": "desktop", "type": "file_open", "app": app_name, "file": win_path}
                )
                logger.info("Opened file: %s", win_path)
                return {"success": True, "app": app_name, "file": win_path, "method": "startfile"}
            except Exception as e:
                # Method 2: Try opening the app and then the file
                logger.warning("startfile failed: %s, trying subprocess", e)
                try:
                    subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(2)
                    os.startfile(win_path)
                    return {"success": True, "app": app_name, "file": win_path, "method": "app+startfile"}
                except Exception as e2:
                    return {"success": False, "error": f"Could not open {file_path}: {e2}"}
        
        # No file, just open the app
        subprocess.Popen(
            [exe],
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1)

        brain.memory.observe(
            f"Opened app: {app_name}",
            {"source": "desktop", "type": "app_launch", "app": app_name}
        )
        logger.info("Opened: %s → %s", app_name, exe)
        return {"success": True, "app": app_name, "exe": exe}

    except FileNotFoundError:
        return {"success": False, "error": f"Could not open {app_name}: executable not found"}
    except Exception as e:
        logger.error("open_app error: %s", e)
        return {"success": False, "error": str(e)}


def _type_text(params: dict, context: dict, brain) -> dict:
    """
    Type text into the currently active window.
    params: {"text": str, "interval": float (default 0.02)}
    """
    import pyautogui

    text = params.get("text", "")
    interval = float(params.get("interval", 0.02))

    if not text:
        return {"success": False, "error": "text required"}

    try:
        pyautogui.typewrite(text, interval=interval) if text.isascii() else None
        # For non-ASCII, use pyperclip + Ctrl+V
        if not text.isascii():
            import pyperclip
            pyperclip.copy(text)
            pyautogui.hotkey('ctrl', 'v')

        logger.info("Typed %d characters", len(text))
        return {"success": True, "typed": len(text)}
    except Exception as e:
        logger.error("type_text error: %s", e)
        return {"success": False, "error": str(e)}


def _screenshot(params: dict, context: dict, brain) -> dict:
    """
    Take a screenshot of the entire screen.
    params: {"save_path": str (optional, default "screenshot.png")}
    """
    import pyautogui

    save_path = params.get("save_path", "screenshot.png")

    try:
        img = pyautogui.screenshot()
        img.save(save_path)

        brain.memory.observe(
            f"Screenshot saved: {save_path}",
            {"source": "desktop", "type": "screenshot", "path": save_path}
        )
        logger.info("Screenshot saved: %s", save_path)
        return {"success": True, "path": save_path, "size": f"{img.size[0]}x{img.size[1]}"}
    except Exception as e:
        logger.error("screenshot error: %s", e)
        return {"success": False, "error": str(e)}


def _hotkey(params: dict, context: dict, brain) -> dict:
    """
    Send a keyboard shortcut.
    params: {"keys": str} — e.g. "ctrl+s", "alt+tab", "ctrl+shift+n", "enter"
    """
    import pyautogui

    keys = params.get("keys", "")
    if not keys:
        return {"success": False, "error": "keys required (e.g. 'ctrl+s')"}

    try:
        key_list = [k.strip().lower() for k in keys.split("+")]
        pyautogui.hotkey(*key_list)

        logger.info("Hotkey: %s", keys)
        return {"success": True, "keys": keys}
    except Exception as e:
        logger.error("hotkey error: %s", e)
        return {"success": False, "error": str(e)}


# ── SKILL REGISTRATION ───────────────────────────────────────────────────────

def register(agent):
    """Called by agent.load_skill(desktop_skill)."""
    agent.brain.register_tool(
        "open_app",
        "Open an application by name (e.g. 'notepad', 'chrome', 'vscode', 'calculator', 'word'). "
        "Use to launch any program on the computer. Optionally specify a file to open with it.",
        _open_app
    )
    agent.brain.register_tool(
        "type_text",
        "Type text into the currently active window. "
        "Use after opening an app to enter content.",
        _type_text
    )
    agent.brain.register_tool(
        "screenshot",
        "Take a screenshot of the entire screen and save it. "
        "Use to see what's on screen or capture results.",
        _screenshot
    )
    agent.brain.register_tool(
        "hotkey",
        "Send a keyboard shortcut like ctrl+s, alt+tab, ctrl+shift+n. "
        "Use to save files, switch apps, trigger shortcuts.",
        _hotkey
    )

    logger.info("Desktop skill registered: 4 tools")
    return agent