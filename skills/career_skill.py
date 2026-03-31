"""
Career intelligence skill.
"""

from __future__ import annotations

import csv
import datetime
import json
import logging
import os
import re
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

logger = logging.getLogger("agent.career")

SKILL_NAME = "career"

_PROFILE = None

DEFAULT_PROFILE = {
    "name": "Raktim Banerjee",
    "education": "2nd year BTech CSE, NIIT University (2024-2028)",
    "role": "Microsoft Student Ambassador",
    "target": "AI/ML internship, Summer 2026, India or remote",
    "projects": [
        "RAG Study Assistant - ChromaDB + Gradio, streaming, OCR fallback, pytest suite",
        "AI Code Review Assistant - LLaMA 3.2, 7 languages",
        "RakBot v9 - Autonomous career agent",
        "FachuBot v6 - Cold email automation",
    ],
    "skills": "Python, LLMs, RAG, ChromaDB, NLP, Gradio, Node.js, Azure",
    "github": "github.com/rktm0604",
    "linkedin": "linkedin.com/in/raktim-banerjee4421b6322",
}

INTERNSHALA_CATEGORIES = [
    {"label": "AI & ML", "url": "https://internshala.com/internships/artificial-intelligence-internship/"},
    {"label": "ML", "url": "https://internshala.com/internships/machine-learning-internship/"},
    {"label": "Python", "url": "https://internshala.com/internships/python-internship/"},
    {"label": "Data Science", "url": "https://internshala.com/internships/data-science-internship/"},
    {"label": "WFH AI", "url": "https://internshala.com/internships/work-from-home-artificial-intelligence-internship/"},
    {"label": "WFH Python", "url": "https://internshala.com/internships/work-from-home-python-internship/"},
    {"label": "Deep Learning", "url": "https://internshala.com/internships/deep-learning-internship/"},
    {"label": "NLP", "url": "https://internshala.com/internships/natural-language-processing-internship/"},
]

SEARCH_QUERIES = [
    "remote AI ML internship 2026 India stipend",
    "LLM RAG internship 2026 India remote",
    "IIT summer research internship 2026 CS AI",
    "Microsoft Research India internship 2026",
    "Google internship India 2026 AI ML student",
]

SCRAPE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://internshala.com/",
}


def set_config(full_config: dict):
    global _PROFILE
    identity = full_config.get("identity", {})
    if identity:
        _PROFILE = {
            "name": identity.get("name", DEFAULT_PROFILE["name"]),
            "education": identity.get("education", DEFAULT_PROFILE["education"]),
            "role": ", ".join(identity.get("roles", [DEFAULT_PROFILE["role"]])),
            "target": (
                identity.get("goals", [DEFAULT_PROFILE["target"]])[0]
                if identity.get("goals")
                else DEFAULT_PROFILE["target"]
            ),
            "projects": identity.get("projects", DEFAULT_PROFILE["projects"]),
            "skills": identity.get("skills", DEFAULT_PROFILE["skills"]),
            "github": identity.get("github", DEFAULT_PROFILE["github"]),
            "linkedin": identity.get("linkedin", DEFAULT_PROFILE["linkedin"]),
        }
        logger.info("Career skill: profile loaded from config.yaml")
    else:
        _PROFILE = DEFAULT_PROFILE


def _get_profile() -> dict:
    return _PROFILE or DEFAULT_PROFILE


@api_circuit_breaker("career_web", logger=logger)
@retry(
    wait=wait_exponential(min=1, max=30),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(Exception),
    reraise=True,
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def _safe_get(url: str, timeout: int = 15):
    resp = requests.get(url, headers=SCRAPE_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp


def _profile_str() -> str:
    profile = _get_profile()
    projects = profile.get("projects", [])
    if isinstance(projects, list):
        projects = "; ".join(projects)
    return (
        f"Name: {profile['name']}\n"
        f"Education: {profile['education']}\n"
        f"Role: {profile['role']}\n"
        f"Target: {profile['target']}\n"
        f"Projects: {projects}\n"
        f"Skills: {profile['skills']}\n"
        f"GitHub: {profile['github']}\n"
        f"LinkedIn: {profile['linkedin']}"
    )


def _search_opportunities(params: dict, context: dict, brain) -> dict:
    del params, context
    verdict, reason = brain.policy.check("network", "internshala.com")
    if verdict == "deny":
        logger.warning("search_opportunities DENIED: %s", reason)
        return {"success": False, "reason": reason}

    brain.policy.record("search")
    found = []
    skipped = 0

    try:
        from bs4 import BeautifulSoup

        for cat in INTERNSHALA_CATEGORIES[:4]:
            try:
                resp = _safe_get(cat["url"])
            except CircuitBreakerError as e:
                logger.warning("Career circuit open: %s", e)
                break
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all("div", attrs={"data-internship_id": True}) or soup.find_all(
                "div", class_=re.compile(r"individual_internship")
            )
            for card in cards[:8]:
                title_tag = card.find(class_=re.compile(r"profile|title|heading"))
                company_tag = card.find(class_=re.compile(r"company|employer"))
                link_tag = card.find("a", href=re.compile(r"/internship"))

                title = title_tag.get_text(strip=True) if title_tag else ""
                company = company_tag.get_text(strip=True) if company_tag else ""
                href = link_tag.get("href", "") if link_tag else ""
                link = f"https://internshala.com{href}" if href.startswith("/") else href

                if not title or len(title) < 5:
                    continue
                if link and brain.memory.has_link(link):
                    skipped += 1
                    continue

                opp = {
                    "title": title,
                    "company": company,
                    "link": link or cat["url"],
                    "source": "Internshala",
                    "category": cat["label"],
                }
                found.append(opp)
                brain.memory.observe(
                    f"{title} at {company} - {cat['label']}",
                    {
                        "source": "internshala",
                        "type": "opportunity",
                        "title": title,
                        "company": company,
                        "link": link or cat["url"],
                        "status": "new",
                    },
                )
            time.sleep(1.5)
    except ImportError:
        logger.warning("BeautifulSoup not installed - skipping Internshala scrape")
    except Exception as e:
        logger.error("Internshala search error: %s", e)

    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            for query in SEARCH_QUERIES[:5]:
                for result in list(ddgs.text(query, max_results=3)):
                    title = result.get("title", "")
                    link = result.get("href", "")
                    body = result.get("body", "")
                    if not title or not link:
                        continue
                    if brain.memory.has_link(link):
                        skipped += 1
                        continue

                    opp = {
                        "title": title,
                        "company": "",
                        "link": link,
                        "source": "search",
                        "category": "web",
                    }
                    found.append(opp)
                    brain.memory.observe(
                        f"{title} - {body[:100]}",
                        {
                            "source": "duckduckgo",
                            "type": "opportunity",
                            "title": title,
                            "link": link,
                            "status": "new",
                        },
                    )
    except Exception as e:
        logger.error("DuckDuckGo search error: %s", e)

    _save_to_csv(found)

    logger.info(
        "search_opportunities: found %d new, skipped %d duplicates",
        len(found),
        skipped,
    )
    return {
        "success": True,
        "found": len(found),
        "skipped": skipped,
        "summary": f"Found {len(found)} new opportunities ({skipped} duplicates skipped)",
    }


def _score_opportunity(params: dict, context: dict, brain) -> dict:
    del context
    title = params.get("title", "")
    company = params.get("company", "")
    description = params.get("description", "")

    if not title:
        return {"success": False, "error": "title required"}

    prompt = f"""Evaluate this opportunity for {_get_profile()['name']}.

PROFILE:
{_profile_str()}

OPPORTUNITY:
Title: {title}
Company: {company}
Description: {description[:400]}

Rate 1-10 and explain. Consider:
- Skill match (RAG, LLM, Python, AI/ML)
- Learning value for a 2nd year student
- Realistic chance of getting it
- Remote/India availability

Respond ONLY in JSON:
{{"score": 7, "fit": "HIGH/MEDIUM/LOW", "reason": "one sentence", "angle": "how to approach this"}}"""

    result = brain._infer(prompt)
    try:
        match = re.search(r"\{.*\}", result, re.DOTALL)
        if match:
            data = json.loads(match.group())
            if data.get("score", 0) >= 7:
                brain.memory.learn(
                    f"{title} {company} {description[:100]}",
                    "positive",
                    float(data.get("score", 5)) / 10,
                )
            return {"success": True, **data}
    except Exception:
        pass

    return {"success": True, "score": 5, "reason": result[:100]}


def _draft_outreach(params: dict, context: dict, brain) -> dict:
    del context
    verdict, reason = brain.policy.check("outreach")
    if verdict == "deny":
        logger.warning("draft_outreach DENIED: %s", reason)
        return {"success": False, "denied": True, "reason": reason}

    name = params.get("name", "Hiring Manager")
    company = params.get("company", "")
    role = params.get("role", "")
    opportunity = params.get("opportunity", "")

    identifier = params.get("linkedin_url", f"{name}_{company}")
    entity = brain.memory.entity_status(identifier)
    if entity.get("contacted") == "true":
        return {
            "success": False,
            "reason": f"Already contacted {name} at {company} - skipping",
        }

    prompt = f"""Draft a LinkedIn DM from {_get_profile()['name']} to {name} ({role} at {company}).

{_get_profile()['name'].upper()}'S PROFILE:
{_profile_str()}

OPPORTUNITY: {opportunity}

RULES:
- Max 5 sentences. No fluff.
- Mention ONE specific thing about their company
- Reference ONE of the sender's projects that matches
- End with a specific question, not "let me know"
- Do NOT say "I hope this message finds you well"
- Tone: confident, direct

Output ONLY the DM text."""

    dm = brain._infer(prompt)
    if not dm:
        return {"success": False, "error": "LLM returned empty response"}

    print("\n" + "=" * 55)
    print(f"  OUTREACH DRAFT - {name} @ {company}")
    print("=" * 55)
    print(f"\n{dm}\n")
    print("=" * 55)
    approve = input("  Approve? [y/n]: ").strip().lower()

    if approve == "y":
        brain.memory.remember_entity(
            name,
            "person",
            identifier,
            {
                "company": company,
                "role": role,
                "contacted": "true",
                "date_contacted": datetime.datetime.now().isoformat(),
            },
        )
        brain.memory.update_entity(identifier, {"contacted": "true"})
        brain.policy.record("outreach")
        brain.memory.log_action("outreach", identifier, dm, "approved")
        return {"success": True, "approved": True, "dm": dm}

    return {"success": True, "approved": False}


def _track_entity(params: dict, context: dict, brain) -> dict:
    del context
    name = params.get("name", "")
    etype = params.get("type", "person")
    identifier = params.get("identifier", name)
    metadata = {
        key: value
        for key, value in params.items()
        if key not in ("name", "type", "identifier")
    }

    if not name:
        return {"success": False, "error": "name required"}

    brain.memory.remember_entity(name, etype, identifier, metadata)
    return {"success": True, "tracked": name, "type": etype}


def _send_digest(params: dict, context: dict, brain) -> dict:
    del params, context
    gmail_user = os.environ.get("RAKBOT_GMAIL_EMAIL", "")
    gmail_pass = os.environ.get("RAKBOT_GMAIL_PASSWORD", "")

    if not gmail_user or not gmail_pass:
        return {
            "success": False,
            "error": "RAKBOT_GMAIL_EMAIL and RAKBOT_GMAIL_PASSWORD not set in .env",
        }

    recent = brain.memory.search("observations", "opportunity internship", n=10)
    today = datetime.datetime.now().strftime("%d %B %Y")

    if not recent:
        return {"success": False, "error": "No opportunities in memory yet"}

    cards = "".join(
        [
            f"""<div style="background:#f8f9ff;border-left:4px solid #667eea;
            border-radius:8px;padding:14px;margin:10px 0;">
            <h3 style="margin:0;color:#333;font-size:14px;">
            {r.get('title', 'Unknown')}</h3>
            <p style="margin:4px 0;color:#888;font-size:12px;">
            {r.get('company', '')} · {r.get('source', '')}</p>
            <a href="{r.get('link', '#')}"
            style="background:#667eea;color:white;padding:6px 14px;
            border-radius:6px;text-decoration:none;font-size:12px;">
            View</a></div>"""
            for r in recent
        ]
    )

    html = f"""<html><body style="font-family:Arial,sans-serif;
    background:#f0f2f5;padding:20px;">
    <div style="max-width:640px;margin:auto;">
    <div style="background:linear-gradient(135deg,#667eea,#764ba2);
    border-radius:12px 12px 0 0;padding:28px;text-align:center;">
    <h1 style="color:white;margin:0;">RKTM83 Digest</h1>
    <p style="color:rgba(255,255,255,0.8);margin:6px 0 0;">
    {today} · Autonomous Agent Report</p></div>
    <div style="background:white;padding:24px;border-radius:0 0 12px 12px;">
    <h2 style="font-size:16px;color:#333;">
    Recent Opportunities ({len(recent)})</h2>
    {cards}
    <p style="color:#888;font-size:11px;margin-top:20px;">
    RKTM83 · Autonomous Agent</p>
    </div></div></body></html>"""

    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"RKTM83: {len(recent)} opportunities · {today}"
        msg["From"] = gmail_user
        msg["To"] = gmail_user
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, gmail_user, msg.as_string())

        return {"success": True, "sent": len(recent)}
    except Exception as e:
        logger.error("Digest send failed: %s", e)
        return {"success": False, "error": str(e)}


def _save_to_csv(results: list):
    if not results:
        return
    csv_file = "internships_tracker.csv"
    fieldnames = ["date", "title", "company", "link", "source", "category", "status"]
    today = datetime.datetime.now().strftime("%d-%m-%Y")
    exists = os.path.exists(csv_file)
    try:
        with open(csv_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not exists:
                writer.writeheader()
            for result in results:
                writer.writerow(
                    {
                        "date": today,
                        "title": result.get("title", ""),
                        "company": result.get("company", ""),
                        "link": result.get("link", ""),
                        "source": result.get("source", ""),
                        "category": result.get("category", ""),
                        "status": "new",
                    }
                )
    except Exception as e:
        logger.error("CSV save error: %s", e)


def register(agent):
    agent.brain.register_tool(
        "search_opportunities",
        "Search Internshala and web for new AI/ML internship opportunities. "
        "Use when opportunities in memory are stale (>8 hours) or count is low.",
        _search_opportunities,
    )
    agent.brain.register_tool(
        "score_opportunity",
        "Deep evaluate a specific opportunity using LLM reasoning. "
        "Use on high-potential results before drafting outreach.",
        _score_opportunity,
    )
    agent.brain.register_tool(
        "draft_outreach",
        "Draft a personalized LinkedIn DM or email to a recruiter or hiring manager. "
        "Requires human approval before anything is sent.",
        _draft_outreach,
    )
    agent.brain.register_tool(
        "track_entity",
        "Store a person or company in agent memory for future reference.",
        _track_entity,
    )
    agent.brain.register_tool(
        "send_digest",
        "Send a summary email of recent opportunities. "
        "Use once per week or when explicitly requested.",
        _send_digest,
    )

    logger.info("Career skill registered: 5 tools")
    return agent
