"""
research_skill.py — Academic Research Skill
Plugs into agent_brain.Agent via agent.load_skill(research_skill)

Registers these tools with the agent:
  - search_professors  : find professors and research labs in AI/ML
  - search_papers      : find recent papers relevant to your interests
  - track_lab          : store a lab or professor in agent memory

Usage:
  Enable in config.yaml:
    skills:
      - research
"""

import re
import json
import time
import logging
import requests

logger = logging.getLogger("agent.research")

SKILL_NAME = "research"

# ── CONFIG ────────────────────────────────────────────────────────────────────

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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}


def set_config(full_config: dict):
    """Receive full config from run_agent.py."""
    global _CONFIG
    _CONFIG = full_config


# ── TOOL HANDLERS ─────────────────────────────────────────────────────────────

def _search_professors(params: dict, context: dict, brain) -> dict:
    """
    Search for professors and research labs offering internships.
    Uses DuckDuckGo and stores results in agent memory.
    """
    verdict, reason = brain.policy.check("search")
    if verdict == "deny":
        return {"success": False, "reason": reason}

    brain.policy.record("search")
    found = []

    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            for query in SEARCH_QUERIES_PROFESSORS[:3]:
                for r in list(ddgs.text(query, max_results=5)):
                    title = r.get('title', '')
                    link  = r.get('href', '')
                    body  = r.get('body', '')
                    if not title or not link:
                        continue

                    # Dedup
                    if brain.memory.has_link(link):
                        continue

                    found.append({
                        "title": title,
                        "link":  link,
                        "body":  body[:200],
                        "source": "search",
                    })
                    brain.memory.observe(
                        f"Research: {title} — {body[:100]}",
                        {
                            "source": "research_search",
                            "type":   "professor",
                            "title":  title,
                            "link":   link,
                            "status": "new",
                        }
                    )
                time.sleep(1)
    except Exception as e:
        logger.error("Professor search error: %s", e)

    logger.info("search_professors: found %d results", len(found))
    return {
        "success": True,
        "found":   len(found),
        "summary": f"Found {len(found)} professor/lab results",
    }


def _search_papers(params: dict, context: dict, brain) -> dict:
    """
    Search for recent papers on arXiv and the web.
    Uses Semantic Scholar API and DuckDuckGo.
    """
    verdict, reason = brain.policy.check("search")
    if verdict == "deny":
        return {"success": False, "reason": reason}

    brain.policy.record("search")
    found = []

    # ── Semantic Scholar API (free, no key needed) ──
    try:
        for interest in RESEARCH_INTERESTS[:3]:
            url = (
                f"https://api.semanticscholar.org/graph/v1/paper/search"
                f"?query={requests.utils.quote(interest)}"
                f"&limit=5&fields=title,url,year,abstract"
            )
            resp = requests.get(url, headers=SCRAPE_HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for paper in data.get("data", []):
                    title = paper.get("title", "")
                    link  = paper.get("url", "")
                    year  = paper.get("year", "")
                    abstract = paper.get("abstract", "") or ""

                    if not title:
                        continue
                    if brain.memory.has_link(link):
                        continue

                    found.append({
                        "title":    title,
                        "link":     link,
                        "year":     year,
                        "abstract": abstract[:200],
                    })
                    brain.memory.observe(
                        f"Paper: {title} ({year})",
                        {
                            "source":   "semantic_scholar",
                            "type":     "paper",
                            "title":    title,
                            "link":     link,
                            "year":     str(year),
                            "status":   "new",
                        }
                    )
            time.sleep(1)
    except Exception as e:
        logger.error("Semantic Scholar search error: %s", e)

    # ── DuckDuckGo fallback ──
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            for query in SEARCH_QUERIES_PAPERS[:2]:
                for r in list(ddgs.text(query + " arxiv", max_results=3)):
                    title = r.get('title', '')
                    link  = r.get('href', '')
                    if not title or not link:
                        continue
                    if brain.memory.has_link(link):
                        continue
                    found.append({
                        "title": title,
                        "link":  link,
                        "source": "search",
                    })
                    brain.memory.observe(
                        f"Paper (web): {title}",
                        {
                            "source": "duckduckgo",
                            "type":   "paper",
                            "title":  title,
                            "link":   link,
                            "status": "new",
                        }
                    )
    except Exception as e:
        logger.error("DuckDuckGo paper search error: %s", e)

    logger.info("search_papers: found %d results", len(found))
    return {
        "success": True,
        "found":   len(found),
        "summary": f"Found {len(found)} papers",
    }


def _track_lab(params: dict, context: dict, brain) -> dict:
    """
    Store a professor, lab, or research group in memory.
    params: {"name": str, "institution": str, "url": str, "notes": str}
    """
    name        = params.get("name", "")
    institution = params.get("institution", "")
    url         = params.get("url", "")
    notes       = params.get("notes", "")

    if not name:
        return {"success": False, "error": "name required"}

    identifier = url or f"{name}_{institution}"
    brain.memory.remember_entity(
        name, "lab", identifier,
        {
            "institution": institution,
            "url":         url,
            "notes":       notes,
            "tracked_at":  __import__("datetime").datetime.now().isoformat(),
        }
    )
    logger.info("Lab tracked: %s @ %s", name, institution)
    return {"success": True, "tracked": name, "institution": institution}


# ── SKILL REGISTRATION ───────────────────────────────────────────────────────

def register(agent):
    """Called by agent.load_skill(research_skill)."""
    agent.brain.register_tool(
        "search_professors",
        "Search for professors and research labs offering AI/ML internships. "
        "Use when looking for academic research opportunities.",
        _search_professors
    )
    agent.brain.register_tool(
        "search_papers",
        "Search for recent AI/ML papers on Semantic Scholar and the web. "
        "Use to stay updated on research trends.",
        _search_papers
    )
    agent.brain.register_tool(
        "track_lab",
        "Store a professor, lab, or research group in memory for follow-up.",
        _track_lab
    )

    logger.info("Research skill registered: 3 tools")
    return agent
