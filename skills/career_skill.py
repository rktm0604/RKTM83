"""
career_skill.py — Career Intelligence Skill
Plugs into agent_brain.Agent via agent.load_skill(career_skill)

Registers these tools with the agent:
  - search_opportunities   : discover new opportunities from all sources
  - score_opportunity      : deep evaluate a specific opportunity
  - draft_outreach         : write personalized DM or email
  - track_entity           : store a person or company in agent memory
  - send_digest            : send weekly email summary

The agent decides autonomously when to use each tool.
This file contains zero scheduling logic — that belongs to the agent loop.

Usage:
  import career_skill
  agent.load_skill(career_skill)
"""

import os
import re
import csv
import json
import time
import datetime
import logging
import requests
import webbrowser

logger = logging.getLogger("agent.career")

SKILL_NAME = "career"

# ── PROFILE ───────────────────────────────────────────────────────────────────
# Loaded once at skill registration — injected into outreach prompts

PROFILE = {
    "name":       "Raktim Banerjee",
    "education":  "2nd year BTech CSE, NIIT University (2024-2028)",
    "role":       "Microsoft Student Ambassador",
    "target":     "AI/ML internship, Summer 2026, India or remote",
    "projects": [
        "RAG Study Assistant — ChromaDB + Gradio, streaming, OCR fallback, "
        "pytest suite, 90%+ accuracy on RTX 3050",
        "AI Code Review Assistant — LLaMA 3.2, 7 languages",
        "RakBot v9 — Autonomous career agent (NemoClaw-inspired)",
        "FachuBot v6 — Cold email automation",
    ],
    "skills": "Python, LLMs, RAG, ChromaDB, NLP, Gradio, Node.js, Azure",
    "github":   "github.com/rktm0604",
    "linkedin": "linkedin.com/in/raktim-banerjee4421b6322",
}

# ── INTERNSHALA CATEGORIES ────────────────────────────────────────────────────

INTERNSHALA_CATEGORIES = [
    {"label": "AI & ML",      "url": "https://internshala.com/internships/artificial-intelligence-internship/"},
    {"label": "ML",           "url": "https://internshala.com/internships/machine-learning-internship/"},
    {"label": "Python",       "url": "https://internshala.com/internships/python-internship/"},
    {"label": "Data Science", "url": "https://internshala.com/internships/data-science-internship/"},
    {"label": "WFH AI",       "url": "https://internshala.com/internships/work-from-home-artificial-intelligence-internship/"},
    {"label": "WFH Python",   "url": "https://internshala.com/internships/work-from-home-python-internship/"},
    {"label": "Deep Learning","url": "https://internshala.com/internships/deep-learning-internship/"},
    {"label": "NLP",          "url": "https://internshala.com/internships/natural-language-processing-internship/"},
]

SEARCH_QUERIES = [
    "remote AI ML internship 2026 India stipend",
    "LLM RAG internship 2026 India remote",
    "IIT summer research internship 2026 CS AI",
    "Microsoft Research India internship 2026",
    "Google internship India 2026 AI ML student",
    "Nvidia internship India 2026 AI",
    "AMD internship India 2026 software",
]

SCRAPE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Referer': 'https://internshala.com/',
}

# ── HELPERS ───────────────────────────────────────────────────────────────────

def _safe_get(url: str, timeout: int = 15):
    for attempt in range(3):
        try:
            from bs4 import BeautifulSoup
            resp = requests.get(url, headers=SCRAPE_HEADERS, timeout=timeout)
            return resp
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
    return None

def _profile_str() -> str:
    p = PROFILE
    return (
        f"Name: {p['name']}\n"
        f"Education: {p['education']}\n"
        f"Role: {p['role']}\n"
        f"Target: {p['target']}\n"
        f"Projects: {'; '.join(p['projects'])}\n"
        f"Skills: {p['skills']}\n"
        f"GitHub: {p['github']}\n"
        f"LinkedIn: {p['linkedin']}"
    )

# ── TOOL HANDLERS ─────────────────────────────────────────────────────────────

def _search_opportunities(params: dict, context: dict, brain) -> dict:
    """
    Discover new opportunities from Internshala and DuckDuckGo.
    Stores each result in agent memory as an observation.
    Returns count of new opportunities found.
    """
    # Policy check before any network calls
    verdict, reason = brain.policy.check("network", "internshala.com")
    if verdict == "deny":
        logger.warning("search_opportunities DENIED: %s", reason)
        return {"success": False, "reason": reason}

    brain.policy.record("search")
    found = []

    # ── Internshala ──────────────────────────────────────────────────────────
    logger.info("Searching Internshala...")
    try:
        from bs4 import BeautifulSoup
        for cat in INTERNSHALA_CATEGORIES[:4]:   # limit for rate control
            resp = _safe_get(cat["url"])
            if not resp or resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, 'html.parser')
            cards = (
                soup.find_all('div', attrs={'data-internship_id': True}) or
                soup.find_all('div', class_=re.compile(r'individual_internship'))
            )
            for card in cards[:8]:
                title_tag   = card.find(class_=re.compile(r'profile|title|heading'))
                company_tag = card.find(class_=re.compile(r'company|employer'))
                link_tag    = card.find('a', href=re.compile(r'/internship'))

                title   = title_tag.get_text(strip=True)   if title_tag   else ''
                company = company_tag.get_text(strip=True) if company_tag else ''
                href    = link_tag.get('href', '')          if link_tag    else ''
                link    = f"https://internshala.com{href}" if href.startswith('/') else href

                if not title or len(title) < 5:
                    continue

                opp = {
                    "title":   title,
                    "company": company,
                    "link":    link or cat["url"],
                    "source":  "Internshala",
                    "category": cat["label"],
                }
                found.append(opp)

                # Store in agent memory
                brain.memory.observe(
                    f"{title} at {company} — {cat['label']}",
                    {
                        "source":   "internshala",
                        "type":     "opportunity",
                        "title":    title,
                        "company":  company,
                        "link":     link or cat["url"],
                        "status":   "new",
                    }
                )
            time.sleep(1.5)
    except ImportError:
        logger.warning("BeautifulSoup not installed — skipping Internshala scrape")
    except Exception as e:
        logger.error("Internshala search error: %s", e)

    # ── DuckDuckGo ───────────────────────────────────────────────────────────
    logger.info("Searching DuckDuckGo...")
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            for query in SEARCH_QUERIES[:5]:
                for r in list(ddgs.text(query, max_results=3)):
                    title = r.get('title', '')
                    link  = r.get('href', '')
                    body  = r.get('body', '')
                    if not title or not link:
                        continue
                    opp = {
                        "title":   title,
                        "company": "",
                        "link":    link,
                        "source":  "search",
                        "category": "web",
                    }
                    found.append(opp)
                    brain.memory.observe(
                        f"{title} — {body[:100]}",
                        {
                            "source":  "duckduckgo",
                            "type":    "opportunity",
                            "title":   title,
                            "link":    link,
                            "status":  "new",
                        }
                    )
    except Exception as e:
        logger.error("DuckDuckGo search error: %s", e)

    # Save to CSV for compatibility with v8 workflow
    _save_to_csv(found)

    logger.info("search_opportunities: found %d results", len(found))
    return {
        "success": True,
        "found":   len(found),
        "summary": f"Found {len(found)} opportunities across Internshala and web search",
    }


def _score_opportunity(params: dict, context: dict, brain) -> dict:
    """
    Deep evaluate a specific opportunity using LLM reasoning.
    params: {"title": str, "company": str, "description": str}
    """
    title       = params.get("title", "")
    company     = params.get("company", "")
    description = params.get("description", "")

    if not title:
        return {"success": False, "error": "title required"}

    prompt = f"""Evaluate this opportunity for {PROFILE['name']}.

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

    result = brain._call_inference(prompt)
    try:
        match = re.search(r'\{.*\}', result, re.DOTALL)
        if match:
            data = json.loads(match.group())
            # Store learned pattern in memory
            if data.get("score", 0) >= 7:
                brain.memory.learn(
                    f"{title} {company} {description[:100]}",
                    "positive",
                    float(data.get("score", 5)) / 10
                )
            return {"success": True, **data}
    except Exception:
        pass

    return {"success": True, "score": 5, "reason": result[:100]}


def _draft_outreach(params: dict, context: dict, brain) -> dict:
    """
    Draft a personalized LinkedIn DM or cold email.
    params: {"name": str, "company": str, "role": str, "opportunity": str}
    Requires human approval before anything is sent.
    """
    # Policy check
    verdict, reason = brain.policy.check("outreach")
    if verdict == "deny":
        logger.warning("draft_outreach DENIED: %s", reason)
        return {"success": False, "denied": True, "reason": reason}

    name        = params.get("name", "Hiring Manager")
    company     = params.get("company", "")
    role        = params.get("role", "")
    opportunity = params.get("opportunity", "")

    # Check memory — never contact same person twice
    identifier = params.get("linkedin_url", f"{name}_{company}")
    entity     = brain.memory.entity_status(identifier)
    if entity.get("contacted") == "true":
        return {
            "success": False,
            "reason": f"Already contacted {name} at {company} — skipping"
        }

    prompt = f"""Draft a LinkedIn DM from Raktim to {name} ({role} at {company}).

RAKTIM'S PROFILE:
{_profile_str()}

OPPORTUNITY: {opportunity}

RULES:
- Max 5 sentences. No fluff.
- Mention ONE specific thing about their company
- Reference ONE of Raktim's projects that matches
- End with a specific question, not "let me know"
- Do NOT say "I hope this message finds you well"
- Tone: confident, direct — smart student not desperate applicant

Output ONLY the DM text."""

    dm = brain._call_inference(prompt)

    if not dm:
        return {"success": False, "error": "LLM returned empty response"}

    # Human approval gate — agent NEVER sends without approval
    print("\n" + "="*55)
    print(f"  OUTREACH DRAFT — {name} @ {company}")
    print("="*55)
    print(f"\n{dm}\n")
    print("="*55)
    approve = input("  Approve? [y/n]: ").strip().lower()

    if approve == 'y':
        # Record in memory — mark as contacted
        brain.memory.remember_entity(
            name, "person", identifier,
            {"company": company, "role": role, "contacted": "true",
             "date_contacted": datetime.datetime.now().isoformat()}
        )
        brain.memory.update_entity(identifier, {"contacted": "true"})
        brain.policy.record("outreach")
        brain.memory.log_action("outreach", identifier, dm, "approved")
        logger.info("Outreach approved and logged: %s @ %s", name, company)
        return {"success": True, "approved": True, "dm": dm}
    else:
        logger.info("Outreach declined by operator: %s @ %s", name, company)
        return {"success": True, "approved": False}


def _track_entity(params: dict, context: dict, brain) -> dict:
    """
    Store a person or company in agent memory.
    params: {"name": str, "type": "person"/"company", "identifier": str, ...}
    """
    name       = params.get("name", "")
    etype      = params.get("type", "person")
    identifier = params.get("identifier", name)
    metadata   = {k: v for k, v in params.items()
                  if k not in ("name", "type", "identifier")}

    if not name:
        return {"success": False, "error": "name required"}

    brain.memory.remember_entity(name, etype, identifier, metadata)
    logger.info("Entity tracked: %s (%s)", name, etype)
    return {
        "success": True,
        "tracked": name,
        "type":    etype,
    }


def _send_digest(params: dict, context: dict, brain) -> dict:
    """
    Send a summary email of recent opportunities.
    Pulls from agent memory — no CSV dependency.
    """
    gmail_user = os.environ.get("RAKBOT_GMAIL_EMAIL", "")
    gmail_pass = os.environ.get("RAKBOT_GMAIL_PASSWORD", "")

    if not gmail_user or not gmail_pass:
        return {
            "success": False,
            "error": "RAKBOT_GMAIL_EMAIL and RAKBOT_GMAIL_PASSWORD not set in .env"
        }

    # Pull recent opportunities from memory
    recent = brain.memory.search("observations", "opportunity internship", n=10)
    today  = datetime.datetime.now().strftime("%d %B %Y")

    if not recent:
        return {"success": False, "error": "No opportunities in memory yet"}

    cards = "".join([
        f"""<div style="background:#f8f9ff;border-left:4px solid #667eea;
        border-radius:8px;padding:14px;margin:10px 0;">
        <h3 style="margin:0;color:#333;font-size:14px;">
        {r.get('title','Unknown')}</h3>
        <p style="margin:4px 0;color:#888;font-size:12px;">
        {r.get('company','')} · {r.get('source','')}</p>
        <a href="{r.get('link','#')}"
        style="background:#667eea;color:white;padding:6px 14px;
        border-radius:6px;text-decoration:none;font-size:12px;">
        View</a></div>"""
        for r in recent
    ])

    html = f"""<html><body style="font-family:Arial,sans-serif;
    background:#f0f2f5;padding:20px;">
    <div style="max-width:640px;margin:auto;">
    <div style="background:linear-gradient(135deg,#667eea,#764ba2);
    border-radius:12px 12px 0 0;padding:28px;text-align:center;">
    <h1 style="color:white;margin:0;">RakBot v9 Digest</h1>
    <p style="color:rgba(255,255,255,0.8);margin:6px 0 0;">
    {today} · Autonomous Agent Report</p></div>
    <div style="background:white;padding:24px;border-radius:0 0 12px 12px;">
    <h2 style="font-size:16px;color:#333;">
    Recent Opportunities ({len(recent)})</h2>
    {cards}
    <p style="color:#888;font-size:11px;margin-top:20px;">
    RakBot v9 · NemoClaw-inspired Autonomous Agent</p>
    </div></div></body></html>"""

    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"RakBot v9: {len(recent)} opportunities · {today}"
        msg['From']    = gmail_user
        msg['To']      = gmail_user
        msg.attach(MIMEText(html, 'html'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, gmail_user, msg.as_string())

        logger.info("Digest sent: %d opportunities", len(recent))
        return {"success": True, "sent": len(recent)}

    except Exception as e:
        logger.error("Digest send failed: %s", e)
        return {"success": False, "error": str(e)}


def _save_to_csv(results: list):
    """Save opportunities to CSV — keeps v8 compatibility."""
    if not results:
        return
    csv_file   = "internships_tracker.csv"
    fieldnames = ['date', 'title', 'company', 'link', 'source', 'category', 'status']
    today      = datetime.datetime.now().strftime("%d-%m-%Y")
    exists     = os.path.exists(csv_file)
    try:
        with open(csv_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not exists:
                writer.writeheader()
            for r in results:
                writer.writerow({
                    'date':     today,
                    'title':    r.get('title', ''),
                    'company':  r.get('company', ''),
                    'link':     r.get('link', ''),
                    'source':   r.get('source', ''),
                    'category': r.get('category', ''),
                    'status':   'new',
                })
    except Exception as e:
        logger.error("CSV save error: %s", e)


# ── SKILL REGISTRATION ────────────────────────────────────────────────────────

def register(agent):
    """
    Called by agent.load_skill(career_skill).
    Registers all career tools with the agent brain.
    Also adds career-specific allowed hosts to policy.
    """
    # Register tools
    agent.brain.register_tool(
        "search_opportunities",
        "Search Internshala and web for new AI/ML internship opportunities. "
        "Use when opportunities in memory are stale (>8 hours) or count is low.",
        _search_opportunities
    )
    agent.brain.register_tool(
        "score_opportunity",
        "Deep evaluate a specific opportunity using LLM reasoning. "
        "Use on high-potential results before drafting outreach.",
        _score_opportunity
    )
    agent.brain.register_tool(
        "draft_outreach",
        "Draft a personalized LinkedIn DM or email to a recruiter or hiring manager. "
        "Requires human approval before anything is sent. "
        "Check policy outreach limits before using.",
        _draft_outreach
    )
    agent.brain.register_tool(
        "track_entity",
        "Store a person or company in agent memory for future reference.",
        _track_entity
    )
    agent.brain.register_tool(
        "send_digest",
        "Send a summary email of recent opportunities. "
        "Use once per week or when explicitly requested.",
        _send_digest
    )

    logger.info("Career skill registered: 5 tools")
    return agent
