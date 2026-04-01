"""
research_skill.py — Research Skill
Finds papers, professors, labs, and research programs.
Uses DuckDuckGo — no API key needed.

Tools registered:
  - find_papers        : search recent AI/ML papers
  - find_professors    : find professors at target institutions
  - find_research_programs : find summer research programs in India
"""

import logging
import time

logger = logging.getLogger("agent.research")

SKILL_NAME = "research"

# ── TOOL HANDLERS ─────────────────────────────────────────────────────────────

def _find_papers(params: dict, context: dict, brain) -> dict:
    """
    Search for recent AI/ML papers on arXiv and semantic scholar.
    params: {"topic": str, "max_results": int}
    """
    verdict, reason = brain.policy.check("search")
    if verdict == "deny":
        return {"success": False, "reason": reason}

    topic = params.get("topic", "large language models agents 2026")
    max_r = params.get("max_results", 5)

    brain.policy.record("search")
    results = []

    try:
        from ddgs import DDGS
        queries = [
            f"arxiv {topic} 2026 paper",
            f"site:arxiv.org {topic} 2025 2026",
        ]
        with DDGS() as ddgs:
            for query in queries[:1]:
                for r in list(ddgs.text(query, max_results=max_r)):
                    title = r.get("title", "")
                    link  = r.get("href", "")
                    body  = r.get("body", "")
                    if not title or not link:
                        continue
                    results.append({
                        "title":   title,
                        "link":    link,
                        "summary": body[:200],
                    })
                    brain.memory.observe(
                        f"Paper: {title}",
                        {
                            "source": "research_skill",
                            "type":   "paper",
                            "topic":  topic,
                            "link":   link,
                        }
                    )
    except Exception as e:
        logger.error("find_papers error: %s", e)
        return {"success": False, "error": str(e)}

    logger.info("find_papers: found %d results for '%s'", len(results), topic)
    return {
        "success": True,
        "found":   len(results),
        "topic":   topic,
        "results": results,
    }


def _find_professors(params: dict, context: dict, brain) -> dict:
    """
    Find professors at target institutions working on relevant topics.
    params: {"institution": str, "topic": str}
    """
    verdict, reason = brain.policy.check("search")
    if verdict == "deny":
        return {"success": False, "reason": reason}

    institution = params.get("institution", "IIT")
    topic       = params.get("topic", "AI ML deep learning")

    brain.policy.record("search")
    found = []

    try:
        from ddgs import DDGS
        query = f"{institution} professor {topic} research lab India 2026 email"
        with DDGS() as ddgs:
            for r in list(ddgs.text(query, max_results=5)):
                title = r.get("title", "")
                link  = r.get("href", "")
                body  = r.get("body", "")
                if not title:
                    continue
                # Score relevance — prefer faculty pages
                if any(k in link.lower() for k in ["faculty", "people", "professor", "staff"]):
                    found.append({"name": title, "link": link, "context": body[:150]})
                    brain.memory.remember(
                        title, "professor", link,
                        {"institution": institution, "topic": topic}
                    )
    except Exception as e:
        logger.error("find_professors error: %s", e)
        return {"success": False, "error": str(e)}

    logger.info("find_professors: found %d at %s", len(found), institution)
    return {
        "success":     True,
        "institution": institution,
        "topic":       topic,
        "found":       len(found),
        "professors":  found,
    }


def _find_research_programs(params: dict, context: dict, brain) -> dict:
    """
    Find summer research programs, fellowships, and internships in India.
    params: {"field": str}
    """
    verdict, reason = brain.policy.check("search")
    if verdict == "deny":
        return {"success": False, "reason": reason}

    field = params.get("field", "computer science AI ML")
    brain.policy.record("search")
    programs = []

    try:
        from ddgs import DDGS
        queries = [
            f"summer research program India 2026 {field} undergraduate stipend",
            f"IIT IISC IIIT research fellowship 2026 {field} application open",
            f"SURGE SRFP MITACS 2026 {field} India student",
        ]
        with DDGS() as ddgs:
            for query in queries:
                for r in list(ddgs.text(query, max_results=3)):
                    title = r.get("title", "")
                    link  = r.get("href", "")
                    body  = r.get("body", "")
                    if not title or not link:
                        continue
                    if any(k in (title + body).lower() for k in
                           ["research", "fellowship", "intern", "stipend", "program"]):
                        programs.append({
                            "title":   title,
                            "link":    link,
                            "details": body[:200],
                        })
                        brain.memory.observe(
                            f"Research program: {title}",
                            {
                                "source": "research_skill",
                                "type":   "program",
                                "field":  field,
                                "link":   link,
                            }
                        )
                time.sleep(1)
    except Exception as e:
        logger.error("find_research_programs error: %s", e)
        return {"success": False, "error": str(e)}

    logger.info("find_research_programs: found %d programs", len(programs))
    return {
        "success":  True,
        "field":    field,
        "found":    len(programs),
        "programs": programs,
    }


# ── REGISTRATION ──────────────────────────────────────────────────────────────

def register(agent):
    """Called by run_agent.py when research skill is loaded."""

    # Graceful check for required package
    try:
        from ddgs import DDGS
    except ImportError:
        logger.warning(
            "research_skill: duckduckgo-search not installed. "
            "Run: pip install duckduckgo-search"
        )
        return

    agent.brain.register_tool(
        "find_papers",
        "Search for recent AI/ML research papers on arXiv. "
        "Use when the user asks about papers or wants to stay updated on research.",
        _find_papers
    )

    agent.brain.register_tool(
        "find_professors",
        "Find professors at IITs, IISc, IIITs working on relevant AI/ML topics. "
        "Use when looking for research internship supervisors to cold email.",
        _find_professors
    )

    agent.brain.register_tool(
        "find_research_programs",
        "Find summer research programs, fellowships, and stipended internships in India. "
        "Use when looking for academic research opportunities beyond job portals.",
        _find_research_programs
    )

    logger.info("Research skill loaded: 3 tools registered")
