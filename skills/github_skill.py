"""
github_skill.py — GitHub Skill
Finds contribution opportunities, tracks repos, and discovers issues.
Uses GitHub public API — works without a token (60 req/hr).
Set GITHUB_TOKEN in .env for 5000 req/hr.

Tools registered:
  - find_issues        : find beginner-friendly issues to contribute to
  - track_repo         : monitor a repo for new activity
  - find_trending      : find trending AI/ML repos
"""

import os
import logging
import requests
import time

logger = logging.getLogger("agent.github")

SKILL_NAME = "github"

GITHUB_API  = "https://api.github.com"
HEADERS     = {"Accept": "application/vnd.github+json"}

# Add token if available
_token = os.environ.get("GITHUB_TOKEN", "")
if _token:
    HEADERS["Authorization"] = f"Bearer {_token}"


def _gh_get(url: str, params: dict = {}) -> dict:
    """Safe GitHub API GET with error handling."""
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=10)
        if r.status_code == 200:
            return r.json()
        elif r.status_code == 403:
            logger.warning("GitHub rate limit hit. Set GITHUB_TOKEN in .env for more requests.")
        else:
            logger.warning("GitHub API returned %d for %s", r.status_code, url)
    except Exception as e:
        logger.error("GitHub API error: %s", e)
    return {}


# ── TOOL HANDLERS ─────────────────────────────────────────────────────────────

def _find_issues(params: dict, context: dict, brain) -> dict:
    """
    Find beginner-friendly open issues in AI/ML repos.
    params: {"topic": str, "label": str, "language": str}
    """
    verdict, reason = brain.policy.check("search")
    if verdict == "deny":
        return {"success": False, "reason": reason}

    topic    = params.get("topic", "llm agent rag")
    label    = params.get("label", "good first issue")
    language = params.get("language", "python")

    brain.policy.record("search")

    query = f"{topic} language:{language} label:\"{label}\""
    data  = _gh_get(f"{GITHUB_API}/search/issues", {
        "q":       query,
        "sort":    "created",
        "order":   "desc",
        "per_page": 10,
    })

    issues = []
    for item in data.get("items", []):
        repo_url = item.get("repository_url", "")
        repo     = repo_url.replace(f"{GITHUB_API}/repos/", "")
        issue    = {
            "title":  item.get("title", ""),
            "repo":   repo,
            "link":   item.get("html_url", ""),
            "labels": [l["name"] for l in item.get("labels", [])],
            "created": item.get("created_at", "")[:10],
        }
        issues.append(issue)
        brain.memory.observe(
            f"GitHub issue: {issue['title']} in {repo}",
            {
                "source": "github_skill",
                "type":   "issue",
                "repo":   repo,
                "link":   issue["link"],
            }
        )

    logger.info("find_issues: found %d issues for '%s'", len(issues), topic)
    return {
        "success": True,
        "topic":   topic,
        "found":   len(issues),
        "issues":  issues,
    }


def _track_repo(params: dict, context: dict, brain) -> dict:
    """
    Monitor a GitHub repo for stars, recent commits, and open issues.
    params: {"repo": str}  e.g. "NVIDIA/NemoClaw"
    """
    repo = params.get("repo", "NVIDIA/NemoClaw")

    data = _gh_get(f"{GITHUB_API}/repos/{repo}")
    if not data:
        return {"success": False, "error": f"Could not fetch repo: {repo}"}

    commits_data = _gh_get(f"{GITHUB_API}/repos/{repo}/commits", {"per_page": 3})
    recent = [
        {
            "message": c.get("commit", {}).get("message", "").split("\n")[0][:80],
            "author":  c.get("commit", {}).get("author", {}).get("name", ""),
            "date":    c.get("commit", {}).get("author", {}).get("date", "")[:10],
        }
        for c in (commits_data if isinstance(commits_data, list) else [])
    ]

    info = {
        "repo":         repo,
        "stars":        data.get("stargazers_count", 0),
        "forks":        data.get("forks_count", 0),
        "open_issues":  data.get("open_issues_count", 0),
        "language":     data.get("language", ""),
        "description":  data.get("description", ""),
        "last_push":    data.get("pushed_at", "")[:10],
        "recent_commits": recent,
    }

    brain.memory.observe(
        f"Repo {repo}: {info['stars']} stars, {info['open_issues']} issues",
        {
            "source": "github_skill",
            "type":   "repo_snapshot",
            "repo":   repo,
            "stars":  str(info["stars"]),
        }
    )

    logger.info("track_repo: %s — %d stars, %d issues",
                repo, info["stars"], info["open_issues"])
    return {"success": True, **info}


def _find_trending(params: dict, context: dict, brain) -> dict:
    """
    Find trending Python AI/ML repos created recently.
    params: {"topic": str, "days": int}
    """
    verdict, reason = brain.policy.check("search")
    if verdict == "deny":
        return {"success": False, "reason": reason}

    topic = params.get("topic", "llm agent autonomous")
    days  = params.get("days", 7)

    brain.policy.record("search")

    from datetime import datetime, timedelta
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    query = f"{topic} language:python created:>{since} stars:>10"

    data = _gh_get(f"{GITHUB_API}/search/repositories", {
        "q":       query,
        "sort":    "stars",
        "order":   "desc",
        "per_page": 8,
    })

    repos = []
    for item in data.get("items", []):
        r = {
            "name":        item.get("full_name", ""),
            "description": item.get("description", "")[:120],
            "stars":       item.get("stargazers_count", 0),
            "link":        item.get("html_url", ""),
            "created":     item.get("created_at", "")[:10],
        }
        repos.append(r)
        brain.memory.observe(
            f"Trending: {r['name']} ({r['stars']} stars)",
            {
                "source": "github_skill",
                "type":   "trending_repo",
                "repo":   r["name"],
                "stars":  str(r["stars"]),
            }
        )

    logger.info("find_trending: found %d trending repos for '%s'", len(repos), topic)
    return {
        "success": True,
        "topic":   topic,
        "found":   len(repos),
        "repos":   repos,
    }


# ── REGISTRATION ──────────────────────────────────────────────────────────────

def register(agent):
    """Called by run_agent.py when github skill is loaded."""

    agent.brain.register_tool(
        "find_issues",
        "Find beginner-friendly open GitHub issues in AI/ML Python repos. "
        "Use when looking for open source contribution opportunities.",
        _find_issues
    )

    agent.brain.register_tool(
        "track_repo",
        "Monitor a specific GitHub repo for stars, commits, and open issues. "
        "Use to check NVIDIA/NemoClaw or other target repos for activity.",
        _track_repo
    )

    agent.brain.register_tool(
        "find_trending",
        "Find trending new Python AI/ML GitHub repos from the past week. "
        "Use to discover new projects worth contributing to or learning from.",
        _find_trending
    )

    # Track NemoClaw by default — relevant to this project
    token_status = "authenticated" if _token else "unauthenticated (60 req/hr)"
    logger.info("GitHub skill loaded: 3 tools, API %s", token_status)
