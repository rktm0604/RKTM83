"""
github_skill.py — GitHub Contribution Skill
Plugs into agent_brain.Agent via agent.load_skill(github_skill)

Registers these tools with the agent:
  - search_repos         : find repos to contribute to
  - find_issues          : find good-first-issue / help-wanted issues
  - track_contribution   : store a contribution opportunity in memory

Uses the GitHub API (unauthenticated — 60 req/hour limit).
Set GITHUB_TOKEN in .env for 5000 req/hour.

Usage:
  Enable in config.yaml:
    skills:
      - github
"""

import os
import re
import json
import time
import logging
import datetime
import requests

logger = logging.getLogger("agent.github")

SKILL_NAME = "github"

GITHUB_API = "https://api.github.com"

_CONFIG = None

# ── SEARCH TOPICS ─────────────────────────────────────────────────────────────

SEARCH_TOPICS = [
    "RAG retrieval augmented generation",
    "autonomous agent LLM",
    "chromadb vector database",
    "LLaMA fine-tuning",
    "NLP pipeline python",
    "gradio machine learning",
]

ISSUE_LABELS = [
    "good first issue",
    "help wanted",
    "beginner",
    "easy",
    "hacktoberfest",
]


def set_config(full_config: dict):
    """Receive full config from run_agent.py."""
    global _CONFIG
    _CONFIG = full_config


def _github_headers() -> dict:
    """Build headers, including auth token if available."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "RKTM83-Agent",
    }
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def _github_get(url: str, params: dict = None) -> dict:
    """Make a GitHub API request with retry."""
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=_github_headers(),
                                params=params, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 403:
                logger.warning("GitHub API rate limited")
                return {"error": "rate_limited"}
            logger.warning("GitHub API %d (attempt %d)", resp.status_code, attempt + 1)
        except Exception as e:
            logger.error("GitHub API error: %s", e)
            if attempt < 2:
                time.sleep(2 ** attempt)
    return {"error": "failed"}


# ── TOOL HANDLERS ─────────────────────────────────────────────────────────────

def _search_repos(params: dict, context: dict, brain) -> dict:
    """
    Search GitHub for repos to contribute to.
    Looks for recently active repos matching AI/ML topics.
    """
    verdict, reason = brain.policy.check("search")
    if verdict == "deny":
        return {"success": False, "reason": reason}

    brain.policy.record("search")
    found = []

    topic = params.get("topic", "")
    queries = [topic] if topic else SEARCH_TOPICS[:3]

    for query in queries:
        search_url = f"{GITHUB_API}/search/repositories"
        search_params = {
            "q": f"{query} language:python stars:>10 pushed:>2025-01-01",
            "sort": "updated",
            "order": "desc",
            "per_page": 5,
        }

        data = _github_get(search_url, search_params)
        if "error" in data:
            continue

        for repo in data.get("items", []):
            name  = repo.get("full_name", "")
            desc  = repo.get("description", "") or ""
            url   = repo.get("html_url", "")
            stars = repo.get("stargazers_count", 0)
            lang  = repo.get("language", "")

            if not name or not url:
                continue
            if brain.memory.has_link(url):
                continue

            found.append({
                "repo":  name,
                "desc":  desc[:120],
                "url":   url,
                "stars": stars,
                "lang":  lang,
            })

            brain.memory.observe(
                f"GitHub repo: {name} — {desc[:80]}",
                {
                    "source": "github",
                    "type":   "repo",
                    "title":  name,
                    "link":   url,
                    "stars":  str(stars),
                    "status": "new",
                }
            )
        time.sleep(1)

    logger.info("search_repos: found %d repos", len(found))
    return {
        "success": True,
        "found":   len(found),
        "summary": f"Found {len(found)} repos to contribute to",
    }


def _find_issues(params: dict, context: dict, brain) -> dict:
    """
    Find good-first-issue and help-wanted issues on GitHub.
    Searches for Python AI/ML repos with beginner-friendly issues.
    """
    verdict, reason = brain.policy.check("search")
    if verdict == "deny":
        return {"success": False, "reason": reason}

    brain.policy.record("search")
    found = []

    repo = params.get("repo", "")
    labels = params.get("labels", ISSUE_LABELS[:3])

    if repo:
        # Search issues in a specific repo
        for label in labels:
            url = f"{GITHUB_API}/repos/{repo}/issues"
            issue_params = {
                "labels": label,
                "state": "open",
                "sort": "created",
                "direction": "desc",
                "per_page": 5,
            }
            data = _github_get(url, issue_params)
            if isinstance(data, dict) and "error" in data:
                continue
            if not isinstance(data, list):
                continue
            for issue in data:
                title = issue.get("title", "")
                link  = issue.get("html_url", "")
                if not title or not link:
                    continue
                if brain.memory.has_link(link):
                    continue
                found.append({
                    "title": title,
                    "repo":  repo,
                    "url":   link,
                    "label": label,
                })
                brain.memory.observe(
                    f"Issue: {title} in {repo}",
                    {
                        "source": "github",
                        "type":   "issue",
                        "title":  title,
                        "repo":   repo,
                        "link":   link,
                        "label":  label,
                        "status": "new",
                    }
                )
            time.sleep(0.5)
    else:
        # Search all of GitHub for good first issues in AI/ML
        for label in labels[:2]:
            search_url = f"{GITHUB_API}/search/issues"
            search_params = {
                "q": f'label:"{label}" language:python state:open AI OR ML OR LLM',
                "sort": "created",
                "order": "desc",
                "per_page": 5,
            }
            data = _github_get(search_url, search_params)
            if "error" in data:
                continue
            for issue in data.get("items", []):
                title = issue.get("title", "")
                link  = issue.get("html_url", "")
                repo_url = issue.get("repository_url", "")
                repo_name = "/".join(repo_url.split("/")[-2:]) if repo_url else ""
                if not title or not link:
                    continue
                if brain.memory.has_link(link):
                    continue
                found.append({
                    "title": title,
                    "repo":  repo_name,
                    "url":   link,
                    "label": label,
                })
                brain.memory.observe(
                    f"Issue: {title} in {repo_name}",
                    {
                        "source": "github",
                        "type":   "issue",
                        "title":  title,
                        "repo":   repo_name,
                        "link":   link,
                        "label":  label,
                        "status": "new",
                    }
                )
            time.sleep(1)

    logger.info("find_issues: found %d issues", len(found))
    return {
        "success": True,
        "found":   len(found),
        "summary": f"Found {len(found)} beginner-friendly issues",
    }


def _track_contribution(params: dict, context: dict, brain) -> dict:
    """
    Store a contribution opportunity in memory.
    params: {"repo": str, "issue": str, "url": str, "notes": str}
    """
    repo  = params.get("repo", "")
    issue = params.get("issue", "")
    url   = params.get("url", "")
    notes = params.get("notes", "")

    if not repo:
        return {"success": False, "error": "repo required"}

    identifier = url or f"{repo}_{issue}"
    brain.memory.remember_entity(
        repo, "contribution", identifier,
        {
            "issue":      issue,
            "url":        url,
            "notes":      notes,
            "tracked_at": datetime.datetime.now().isoformat(),
        }
    )
    logger.info("Contribution tracked: %s — %s", repo, issue)
    return {"success": True, "tracked": repo, "issue": issue}


# ── SKILL REGISTRATION ───────────────────────────────────────────────────────

def register(agent):
    """Called by agent.load_skill(github_skill)."""
    agent.brain.register_tool(
        "search_repos",
        "Search GitHub for repos to contribute to in AI/ML and Python. "
        "Finds recently active repos with good star counts.",
        _search_repos
    )
    agent.brain.register_tool(
        "find_issues",
        "Find good-first-issue and help-wanted issues on GitHub. "
        "Great for making first open source contributions.",
        _find_issues
    )
    agent.brain.register_tool(
        "track_contribution",
        "Store a contribution opportunity (repo + issue) in memory.",
        _track_contribution
    )

    logger.info("GitHub skill registered: 3 tools")
    return agent
