"""
filesystem_skill.py — Filesystem Skill
Plugs into agent_brain.Agent via agent.load_skill(filesystem_skill)

Registers these tools with the agent:
  - list_files        : list files in a directory
  - read_file         : read a file's contents
  - move_file         : move or rename a file
  - organize_folder   : auto-sort files by extension into sub-folders

Usage:
  Enable in config.yaml:
    skills:
      - filesystem
"""

import os
import shutil
import logging
import datetime
from pathlib import Path

logger = logging.getLogger("agent.filesystem")

SKILL_NAME = "filesystem"

_CONFIG = None

# ── EXTENSION CATEGORIES ─────────────────────────────────────────────────────

EXTENSION_MAP = {
    "Images":    [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico"],
    "Videos":    [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"],
    "Audio":     [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma"],
    "Documents": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt"],
    "Text":      [".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml", ".log"],
    "Code":      [".py", ".js", ".ts", ".java", ".cpp", ".c", ".h", ".cs", ".go", ".rs", ".html", ".css"],
    "Archives":  [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"],
    "Installers":[".exe", ".msi", ".dmg", ".deb", ".rpm"],
}


def set_config(full_config: dict):
    global _CONFIG
    _CONFIG = full_config


def _get_category(ext: str) -> str:
    """Get the category for a file extension."""
    ext = ext.lower()
    for category, extensions in EXTENSION_MAP.items():
        if ext in extensions:
            return category
    return "Other"


# ── TOOL HANDLERS ─────────────────────────────────────────────────────────────

def _list_files(params: dict, context: dict, brain) -> dict:
    """
    List files in a directory.
    params: {"path": str, "recursive": bool (default false), "max_items": int (default 50)}
    """
    path = params.get("path", ".")
    recursive = params.get("recursive", False)
    max_items = min(int(params.get("max_items", 50)), 200)

    target = Path(path).expanduser().resolve()
    if not target.exists():
        return {"success": False, "error": f"Path not found: {target}"}
    if not target.is_dir():
        return {"success": False, "error": f"Not a directory: {target}"}

    try:
        items = []
        iterator = target.rglob("*") if recursive else target.iterdir()

        for item in iterator:
            if len(items) >= max_items:
                break
            try:
                stat = item.stat()
                items.append({
                    "name": item.name,
                    "path": str(item),
                    "type": "dir" if item.is_dir() else "file",
                    "size": stat.st_size if item.is_file() else 0,
                    "modified": datetime.datetime.fromtimestamp(
                        stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                })
            except PermissionError:
                continue

        logger.info("Listed %d items in %s", len(items), target)
        return {
            "success": True,
            "path": str(target),
            "count": len(items),
            "items": items,
        }
    except Exception as e:
        logger.error("list_files error: %s", e)
        return {"success": False, "error": str(e)}


def _read_file(params: dict, context: dict, brain) -> dict:
    """
    Read a file's contents.
    params: {"path": str, "max_chars": int (default 5000)}
    """
    path = params.get("path", "")
    max_chars = int(params.get("max_chars", 5000))

    if not path:
        return {"success": False, "error": "path required"}

    target = Path(path).expanduser().resolve()
    if not target.exists():
        return {"success": False, "error": f"File not found: {target}"}
    if not target.is_file():
        return {"success": False, "error": f"Not a file: {target}"}

    # Safety: don't read huge binary files
    size = target.stat().st_size
    if size > 10_000_000:
        return {"success": False, "error": f"File too large: {size} bytes"}

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        truncated = len(content) > max_chars
        content = content[:max_chars]

        brain.memory.observe(
            f"Read file: {target.name} ({size} bytes)",
            {"source": "filesystem", "type": "file_read", "path": str(target)}
        )
        logger.info("Read: %s (%d bytes)", target.name, size)
        return {
            "success": True,
            "path": str(target),
            "name": target.name,
            "size": size,
            "content": content,
            "truncated": truncated,
        }
    except Exception as e:
        logger.error("read_file error: %s", e)
        return {"success": False, "error": str(e)}


def _move_file(params: dict, context: dict, brain) -> dict:
    """
    Move or rename a file.
    params: {"source": str, "destination": str}
    """
    source = params.get("source", "")
    destination = params.get("destination", "")

    if not source or not destination:
        return {"success": False, "error": "source and destination required"}

    src = Path(source).expanduser().resolve()
    dst = Path(destination).expanduser().resolve()

    if not src.exists():
        return {"success": False, "error": f"Source not found: {src}"}

    try:
        # Create destination directory if needed
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

        brain.memory.observe(
            f"Moved: {src.name} → {dst}",
            {"source": "filesystem", "type": "file_move",
             "from": str(src), "to": str(dst)}
        )
        logger.info("Moved: %s → %s", src, dst)
        return {"success": True, "from": str(src), "to": str(dst)}
    except Exception as e:
        logger.error("move_file error: %s", e)
        return {"success": False, "error": str(e)}


def _organize_folder(params: dict, context: dict, brain) -> dict:
    """
    Auto-sort files in a folder into sub-folders by extension category.
    params: {"path": str (default ~/Downloads), "dry_run": bool (default true)}
    """
    path = params.get("path", str(Path.home() / "Downloads"))
    dry_run = params.get("dry_run", True)

    target = Path(path).expanduser().resolve()
    if not target.exists() or not target.is_dir():
        return {"success": False, "error": f"Not a directory: {target}"}

    try:
        plan = {}  # category -> list of files

        for item in target.iterdir():
            if item.is_file() and not item.name.startswith("."):
                ext = item.suffix
                if not ext:
                    continue
                category = _get_category(ext)
                if category not in plan:
                    plan[category] = []
                plan[category].append(item)

        moved = 0
        summary = {}

        for category, files in plan.items():
            summary[category] = len(files)
            if not dry_run:
                dest_dir = target / category
                dest_dir.mkdir(exist_ok=True)
                for f in files:
                    dest = dest_dir / f.name
                    if not dest.exists():
                        shutil.move(str(f), str(dest))
                        moved += 1

        brain.memory.observe(
            f"Organize {'(dry run)' if dry_run else ''}: {target.name} — {sum(summary.values())} files",
            {"source": "filesystem", "type": "organize", "path": str(target), "dry_run": str(dry_run)}
        )

        logger.info("Organize %s: %s (dry_run=%s)", target, summary, dry_run)
        return {
            "success": True,
            "path": str(target),
            "dry_run": dry_run,
            "plan": summary,
            "moved": moved,
            "tip": "Set dry_run=false to actually move files" if dry_run else f"Moved {moved} files",
        }
    except Exception as e:
        logger.error("organize_folder error: %s", e)
        return {"success": False, "error": str(e)}


# ── SKILL REGISTRATION ───────────────────────────────────────────────────────

def register(agent):
    """Called by agent.load_skill(filesystem_skill)."""
    agent.brain.register_tool(
        "list_files",
        "List files and folders in a directory. "
        "Use to explore the filesystem, check Downloads, etc.",
        _list_files
    )
    agent.brain.register_tool(
        "read_file",
        "Read the contents of a text file. "
        "Use to inspect configs, logs, code, or documents.",
        _read_file
    )
    agent.brain.register_tool(
        "move_file",
        "Move or rename a file from one location to another.",
        _move_file
    )
    agent.brain.register_tool(
        "organize_folder",
        "Auto-sort files in a folder into sub-folders by type "
        "(Images, Videos, Documents, Code, etc.). "
        "Defaults to dry_run=true — shows plan without moving. "
        "Set dry_run=false to actually organize.",
        _organize_folder
    )

    logger.info("Filesystem skill registered: 4 tools")
    return agent
