"""
Academic research skill.
"""

from __future__ import annotations

import logging
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

logger = logging.getLogger("agent.research")

SKILL_NAME = "research"

_CONFIG = None

RESEARCH_INTERESTS = [
    "large language models",
    "retrieval augmented generation",
    "autonomous agents",
    "NLP",
    "VLSI machine learning",
]

SEARCH_QUERIES_PROFESSORS = [
    "AI ML professor research internship India 2026",
    "IIT professor machine learning research opportunity",
    "NLP research lab India internship student",
    "LLM research group accepting interns 2026",
    "autonomous agents research lab Europe internship",
]

SEARCH_QUERIES_PAPERS = [
    "RAG retrieval augmented generation 2025 2026",
    "autonomous agent LLM planning 2025",
    "NemoClaw NVIDIA agent architecture",
    "LLaMA fine-tuning small models efficient",
    "vector database semantic search survey",
]

SCRAPE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def set_config(full_config: dict):
    global _CONFIG
    _CONFIG = full_config


@api_circuit_breaker("semantic_scholar", logger=logger)
@retry(
    wait=wait_exponential(min=1, max=30),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(Exception),
    reraise=True,
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def _semantic_scholar_get(url: str):
    resp = requests.get(url, headers=SCRAPE_HEADERS, timeout=10)
    resp.raise_for_status()
    return resp


def _search_professors(params: dict, context: dict, brain) -> dict:
    del params, context
    verdict, reason = brain.policy.check("search")
    if verdict == "deny":
        return {"success": False, "reason": reason}

    brain.policy.record("search")
    found = []

    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            for query in SEARCH_QUERIES_PROFESSORS[:3]:
                for result in list(ddgs.text(query, max_results=5)):
                    title = result.get("title", "")
                    link = result.get("href", "")
                    body = result.get("body", "")
                    if not title or not link or brain.memory.has_link(link):
                        continue

                    found.append(
                        {
                            "title": title,
                            "link": link,
                            "body": body[:200],
                            "source": "search",
                        }
                    )
                    brain.memory.observe(
                        f"Research: {title} - {body[:100]}",
                        {
                            "source": "research_search",
                            "type": "professor",
                            "title": title,
                            "link": link,
                            "status": "new",
                        },
                    )
                time.sleep(1)
    except Exception as e:
        logger.error("Professor search error: %s", e)

    logger.info("search_professors: found %d results", len(found))
    return {
        "success": True,
        "found": len(found),
        "summary": f"Found {len(found)} professor/lab results",
    }


def _search_papers(params: dict, context: dict, brain) -> dict:
    del params, context
    verdict, reason = brain.policy.check("search")
    if verdict == "deny":
        return {"success": False, "reason": reason}

    brain.policy.record("search")
    found = []

    try:
        for interest in RESEARCH_INTERESTS[:3]:
            url = (
                "https://api.semanticscholar.org/graph/v1/paper/search"
                f"?query={requests.utils.quote(interest)}"
                "&limit=5&fields=title,url,year,abstract"
            )
            try:
                resp = _semantic_scholar_get(url)
            except CircuitBreakerError as e:
                logger.warning("Semantic Scholar circuit open: %s", e)
                break

            data = resp.json()
            for paper in data.get("data", []):
                title = paper.get("title", "")
                link = paper.get("url", "")
                year = paper.get("year", "")
                abstract = paper.get("abstract", "") or ""

                if not title or brain.memory.has_link(link):
                    continue

                found.append(
                    {
                        "title": title,
                        "link": link,
                        "year": year,
                        "abstract": abstract[:200],
                    }
                )
                brain.memory.observe(
                    f"Paper: {title} ({year})",
                    {
                        "source": "semantic_scholar",
                        "type": "paper",
                        "title": title,
                        "link": link,
                        "year": str(year),
                        "status": "new",
                    },
                )
            time.sleep(1)
    except Exception as e:
        logger.error("Semantic Scholar search error: %s", e)

    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            for query in SEARCH_QUERIES_PAPERS[:2]:
                for result in list(ddgs.text(query + " arxiv", max_results=3)):
                    title = result.get("title", "")
                    link = result.get("href", "")
                    if not title or not link or brain.memory.has_link(link):
                        continue
                    found.append({"title": title, "link": link, "source": "search"})
                    brain.memory.observe(
                        f"Paper (web): {title}",
                        {
                            "source": "duckduckgo",
                            "type": "paper",
                            "title": title,
                            "link": link,
                            "status": "new",
                        },
                    )
    except Exception as e:
        logger.error("DuckDuckGo paper search error: %s", e)

    logger.info("search_papers: found %d results", len(found))
    return {
        "success": True,
        "found": len(found),
        "summary": f"Found {len(found)} papers",
    }


def _track_lab(params: dict, context: dict, brain) -> dict:
    del context
    name = params.get("name", "")
    institution = params.get("institution", "")
    url = params.get("url", "")
    notes = params.get("notes", "")

    if not name:
        return {"success": False, "error": "name required"}

    identifier = url or f"{name}_{institution}"
    brain.memory.remember_entity(
        name,
        "lab",
        identifier,
        {
            "institution": institution,
            "url": url,
            "notes": notes,
            "tracked_at": __import__("datetime").datetime.now().isoformat(),
        },
    )
    logger.info("Lab tracked: %s @ %s", name, institution)
    return {"success": True, "tracked": name, "institution": institution}


def register(agent):
    agent.brain.register_tool(
        "search_professors",
        "Search for professors and research labs offering AI/ML internships. "
        "Use when looking for academic research opportunities.",
        _search_professors,
    )
    agent.brain.register_tool(
        "search_papers",
        "Search for recent AI/ML papers on Semantic Scholar and the web. "
        "Use to stay updated on research trends.",
        _search_papers,
    )
    agent.brain.register_tool(
        "track_lab",
        "Store a professor, lab, or research group in memory for follow-up.",
        _track_lab,
    )

    logger.info("Research skill registered: 3 tools")
    return agent
