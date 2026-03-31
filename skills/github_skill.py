"""
GitHub contribution skill.
"""

from __future__ import annotations

import datetime
import logging
import os
import time

import requests

from resilience import (
    CircuitBreakerError,
    api_circuit_breaker,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger("agent.github")

SKILL_NAME = "github"
GITHUB_API = "https://api.github.com"

_CONFIG = None

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
    global _CONFIG
    _CONFIG = full_config


def _github_headers() -> dict:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "RKTM83-Agent",
    }
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


@api_circuit_breaker("github_api", logger=logger)
@retry(
    wait=wait_exponential(min=1, max=30),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(Exception),
    reraise=True,
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def _github_request(url: str, params: dict = None):
    resp = requests.get(url, headers=_github_headers(), params=params, timeout=15)
    if resp.status_code == 403:
        raise RuntimeError("GitHub API rate limited")
    resp.raise_for_status()
    return resp


def _github_get(url: str, params: dict = None) -> dict:
    try:
        return _github_request(url, params).json()
    except CircuitBreakerError as e:
        logger.warning("GitHub circuit open: %s", e)
        return {"error": "circuit_open"}
    except Exception as e:
        logger.error("GitHub API error: %s", e)
        return {"error": "failed"}


def _search_repos(params: dict, context: dict, brain) -> dict:
    del context
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
            name = repo.get("full_name", "")
            desc = repo.get("description", "") or ""
            url = repo.get("html_url", "")
            stars = repo.get("stargazers_count", 0)
            lang = repo.get("language", "")

            if not name or not url or brain.memory.has_link(url):
                continue

            found.append(
                {
                    "repo": name,
                    "desc": desc[:120],
                    "url": url,
                    "stars": stars,
                    "lang": lang,
                }
            )

            brain.memory.observe(
                f"GitHub repo: {name} - {desc[:80]}",
                {
                    "source": "github",
                    "type": "repo",
                    "title": name,
                    "link": url,
                    "stars": str(stars),
                    "status": "new",
                },
            )
        time.sleep(1)

    logger.info("search_repos: found %d repos", len(found))
    return {
        "success": True,
        "found": len(found),
        "summary": f"Found {len(found)} repos to contribute to",
    }


def _find_issues(params: dict, context: dict, brain) -> dict:
    del context
    verdict, reason = brain.policy.check("search")
    if verdict == "deny":
        return {"success": False, "reason": reason}

    brain.policy.record("search")
    found = []

    repo = params.get("repo", "")
    labels = params.get("labels", ISSUE_LABELS[:3])

    if repo:
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
                link = issue.get("html_url", "")
                if not title or not link or brain.memory.has_link(link):
                    continue
                found.append(
                    {"title": title, "repo": repo, "url": link, "label": label}
                )
                brain.memory.observe(
                    f"Issue: {title} in {repo}",
                    {
                        "source": "github",
                        "type": "issue",
                        "title": title,
                        "repo": repo,
                        "link": link,
                        "label": label,
                        "status": "new",
                    },
                )
            time.sleep(0.5)
    else:
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
                link = issue.get("html_url", "")
                repo_url = issue.get("repository_url", "")
                repo_name = "/".join(repo_url.split("/")[-2:]) if repo_url else ""
                if not title or not link or brain.memory.has_link(link):
                    continue
                found.append(
                    {
                        "title": title,
                        "repo": repo_name,
                        "url": link,
                        "label": label,
                    }
                )
                brain.memory.observe(
                    f"Issue: {title} in {repo_name}",
                    {
                        "source": "github",
                        "type": "issue",
                        "title": title,
                        "repo": repo_name,
                        "link": link,
                        "label": label,
                        "status": "new",
                    },
                )
            time.sleep(1)

    logger.info("find_issues: found %d issues", len(found))
    return {
        "success": True,
        "found": len(found),
        "summary": f"Found {len(found)} beginner-friendly issues",
    }


def _track_contribution(params: dict, context: dict, brain) -> dict:
    del context
    repo = params.get("repo", "")
    issue = params.get("issue", "")
    url = params.get("url", "")
    notes = params.get("notes", "")

    if not repo:
        return {"success": False, "error": "repo required"}

    identifier = url or f"{repo}_{issue}"
    brain.memory.remember_entity(
        repo,
        "contribution",
        identifier,
        {
            "issue": issue,
            "url": url,
            "notes": notes,
            "tracked_at": datetime.datetime.now().isoformat(),
        },
    )
    logger.info("Contribution tracked: %s - %s", repo, issue)
    return {"success": True, "tracked": repo, "issue": issue}


def register(agent):
    agent.brain.register_tool(
        "search_repos",
        "Search GitHub for repos to contribute to in AI/ML and Python. "
        "Finds recently active repos with good star counts.",
        _search_repos,
    )
    agent.brain.register_tool(
        "find_issues",
        "Find good-first-issue and help-wanted issues on GitHub. "
        "Great for making first open source contributions.",
        _find_issues,
    )
    agent.brain.register_tool(
        "track_contribution",
        "Store a contribution opportunity (repo + issue) in memory.",
        _track_contribution,
    )

    logger.info("GitHub skill registered: 3 tools")
    return agent
