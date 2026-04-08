"""
career_skill.py — Career Intelligence Skill
No input() calls — fully web-dashboard compatible.

Approval flow for outreach:
  1. Agent calls draft_outreach → returns draft text, stores in memory
  2. Agent uses chat tool to show draft to user in dashboard
  3. User types "yes send it" / "looks good" / "approved"
  4. Agent calls send_outreach with approved_by_user: true

Tools registered:
  - search_opportunities   : find AI/ML internships
  - score_opportunity      : evaluate fit with LLM
  - draft_outreach         : write DM/email, ask user via chat
  - send_outreach          : actually log/send after user approves
  - send_digest            : weekly email summary
"""

import os
import re
import csv
import json
import time
import datetime
import logging
import requests

logger = logging.getLogger("agent.career")

SKILL_NAME = "career"

SCRAPE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/121.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Referer': 'https://internshala.com/',
}

INTERNSHALA_CATEGORIES = [
    {"label": "AI & ML",      "url": "https://internshala.com/internships/artificial-intelligence-internship/"},
    {"label": "ML",           "url": "https://internshala.com/internships/machine-learning-internship/"},
    {"label": "Python",       "url": "https://internshala.com/internships/python-internship/"},
    {"label": "Data Science", "url": "https://internshala.com/internships/data-science-internship/"},
    {"label": "WFH AI",       "url": "https://internshala.com/internships/work-from-home-artificial-intelligence-internship/"},
    {"label": "Deep Learning","url": "https://internshala.com/internships/deep-learning-internship/"},
]

SEARCH_QUERIES = [
    "remote AI ML internship 2026 India stipend undergraduate",
    "LLM RAG internship 2026 India remote paid",
    "IIT summer research internship 2026 CS AI ML",
    "Microsoft Research India internship 2026",
    "Google internship India 2026 AI ML student",
    "Nvidia AMD Intel internship India 2026 software",
]


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _safe_get(url: str, timeout: int = 15):
    """Safe HTTP GET with retries — no external library needed."""
    for attempt in range(3):
        try:
            return requests.get(url, headers=SCRAPE_HEADERS, timeout=timeout)
        except Exception:
            if attempt < 2:
                time.sleep(2 ** attempt)
    return None


def _search_web(query: str, max_results: int = 5) -> list:
    """
    Lightweight web search using DuckDuckGo HTML endpoint.
    Uses BeautifulSoup + requests — no duckduckgo-search library.
    Falls back to empty list gracefully.
    """
    results = []
    try:
        from bs4 import BeautifulSoup
        url  = "https://html.duckduckgo.com/html/"
        resp = requests.post(
            url,
            data={"q": query},
            headers={"User-Agent": SCRAPE_HEADERS["User-Agent"]},
            timeout=15,
        )
        if resp.status_code != 200:
            return results

        soup  = BeautifulSoup(resp.text, "html.parser")
        links = soup.select(".result__title a")
        snips = soup.select(".result__snippet")

        for i, link in enumerate(links[:max_results]):
            href = link.get("href", "")
            # DuckDuckGo wraps URLs — extract the real one
            if "uddg=" in href:
                from urllib.parse import unquote, parse_qs, urlparse
                parsed = parse_qs(urlparse(href).query)
                href   = parsed.get("uddg", [href])[0]
                href   = unquote(href)
            results.append({
                "title": link.get_text(strip=True),
                "link":  href,
                "body":  snips[i].get_text(strip=True) if i < len(snips) else "",
            })
    except Exception as e:
        logger.warning("Web search error: %s", e)
    return results


# ── TOOL HANDLERS ─────────────────────────────────────────────────────────────

def _search_opportunities(params: dict, context: dict, brain) -> dict:
    """
    Search Internshala + web for AI/ML opportunities.
    Stores everything in agent memory.
    No input() — safe for web dashboard.
    """
    verdict, reason = brain.policy.check("search")
    if verdict == "deny":
        return {"success": False, "reason": reason}

    brain.policy.record("search")
    found = []

    # ── Internshala scrape ────────────────────────────────────────────────
    logger.info("Scraping Internshala...")
    try:
        from bs4 import BeautifulSoup
        for cat in INTERNSHALA_CATEGORIES[:3]:
            resp = _safe_get(cat["url"])
            if not resp or resp.status_code != 200:
                continue
            soup  = BeautifulSoup(resp.text, "html.parser")
            cards = (
                soup.find_all("div", attrs={"data-internship_id": True}) or
                soup.find_all("div", class_=re.compile(r"individual_internship"))
            )
            for card in cards[:8]:
                title_tag   = card.find(class_=re.compile(r"profile|title|heading"))
                company_tag = card.find(class_=re.compile(r"company|employer"))
                link_tag    = card.find("a", href=re.compile(r"/internship"))

                title   = title_tag.get_text(strip=True)   if title_tag   else ""
                company = company_tag.get_text(strip=True) if company_tag else ""
                href    = link_tag.get("href", "")          if link_tag    else ""
                link    = f"https://internshala.com{href}" if href.startswith("/") else href

                if not title or len(title) < 5:
                    continue

                opp = {"title": title, "company": company,
                       "link": link or cat["url"], "source": "Internshala",
                       "category": cat["label"]}
                found.append(opp)
                brain.memory.observe(
                    f"{title} at {company}",
                    {"source": "internshala", "type": "opportunity",
                     "title": title, "company": company, "link": opp["link"]}
                )
            time.sleep(1.5)
    except ImportError:
        logger.warning("BeautifulSoup not installed — skipping Internshala")
    except Exception as e:
        logger.error("Internshala error: %s", e)

    # ── Web search ────────────────────────────────────────────────────────
    logger.info("Searching web...")
    for query in SEARCH_QUERIES[:3]:
        for r in _search_web(query, max_results=3):
            title = r.get("title", "")
            link  = r.get("link", "")
            body  = r.get("body", "")
            if not title or not link:
                continue
            if not any(k in (title + body).lower()
                       for k in ["intern", "fellowship", "research", "stipend"]):
                continue
            opp = {"title": title, "company": "", "link": link,
                   "source": "web", "category": "web"}
            found.append(opp)
            brain.memory.observe(
                f"{title} — {body[:100]}",
                {"source": "web_search", "type": "opportunity",
                 "title": title, "link": link}
            )
        time.sleep(1)

    _save_to_csv(found)
    logger.info("search_opportunities: found %d results", len(found))
    return {"success": True, "found": len(found),
            "summary": f"Found {len(found)} opportunities"}


def _score_opportunity(params: dict, context: dict, brain) -> dict:
    """Evaluate an opportunity with LLM reasoning."""
    title       = params.get("title", "")
    company     = params.get("company", "")
    description = params.get("description", "")

    if not title:
        return {"success": False, "error": "title required"}

    prompt = f"""You are evaluating an internship for the agent's owner.

Owner profile: BTech CSE 2nd year, skills in Python/LLMs/RAG/ChromaDB.
Target: AI/ML internship Summer 2026, India or remote.

Opportunity: {title} at {company}
Details: {description[:300]}

Rate 1-10 and give a one-line reason.
Reply ONLY in JSON: {{"score": 7, "fit": "HIGH", "reason": "one sentence"}}"""

    result = brain._infer(prompt)
    try:
        m    = re.search(r'\{.*\}', result, re.DOTALL)
        data = json.loads(m.group()) if m else {}
        if data.get("score", 0) >= 7:
            brain.memory.learn(f"{title} {company}", "positive",
                               float(data.get("score", 5)) / 10)
        return {"success": True, **data}
    except Exception:
        return {"success": True, "score": 5, "reason": result[:100]}


def _draft_outreach(params: dict, context: dict, brain) -> dict:
    """
    Draft a personalized DM or email.

    NO input() — completely web-safe.

    Flow:
      1. This tool writes the draft to memory + reply file
      2. Agent uses chat tool to show it to user in dashboard
      3. User types "yes" / "send it" / "approved"
      4. Agent calls send_outreach with approved_by_user: true
    """
    name        = params.get("name", "Hiring Manager")
    company     = params.get("company", "")
    role        = params.get("role", "")
    opportunity = params.get("opportunity", "")

    prompt = f"""Draft a LinkedIn DM from Raktim to {name} ({role} at {company}).

Raktim's profile:
- 2nd year BTech CSE, NIIT University
- Microsoft Student Ambassador
- Projects: RAG Study Assistant (ChromaDB+Gradio), AI Code Review tool, RKTM83 agent
- Skills: Python, LLMs, RAG, ChromaDB, NLP
- Goal: AI/ML internship Summer 2026

Opportunity: {opportunity}

Rules:
- Max 5 sentences. No fluff.
- Mention ONE specific thing about their company
- Reference ONE of Raktim's projects that fits
- End with a specific question
- No "I hope this message finds you well"
- Tone: confident, direct, smart student not desperate applicant

Output ONLY the DM text."""

    dm = brain._infer(prompt)
    if not dm:
        return {"success": False, "error": "LLM returned empty response"}

    # Store draft in memory — send_outreach will retrieve it
    draft_key = f"draft_{company}_{name}".replace(" ", "_")[:60]
    brain.memory.observe(
        f"OUTREACH DRAFT for {name} @ {company}:\n{dm}",
        {"source": "career_skill", "type": "outreach_draft",
         "name": name, "company": company, "draft_key": draft_key,
         "dm": dm, "status": "pending_approval"}
    )

    logger.info("Draft created for %s @ %s — awaiting user approval", name, company)

    # Write to reply file so dashboard shows it immediately
    try:
        with open("agent_reply.json", "w") as f:
            json.dump({
                "message": (
                    f"I've drafted a message to **{name}** at **{company}**:\n\n"
                    f"---\n{dm}\n---\n\n"
                    f"Type **'send it'** or **'yes'** to approve, "
                    f"or **'skip'** to discard."
                ),
                "type":      "permission",
                "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                "cycle":     context.get("cycle", 0),
            }, f, indent=2)
    except Exception:
        pass

    return {
        "success":      True,
        "draft":        dm,
        "draft_key":    draft_key,
        "name":         name,
        "company":      company,
        "needs_approval": True,
        "message":      f"Draft ready for {name} @ {company}. Showing to user for approval.",
    }


def _send_outreach(params: dict, context: dict, brain) -> dict:
    """
    Log outreach after user approves via dashboard chat.

    params:
      approved_by_user: bool  — MUST be true to proceed
      name:             str
      company:          str
      dm:               str   — the draft text (optional, uses memory if missing)

    If approved_by_user is false, tells agent to ask user first.
    No input() anywhere.
    """
    approved = params.get("approved_by_user", False)
    name     = params.get("name", "")
    company  = params.get("company", "")

    if not approved:
        return {
            "success": False,
            "error":   "User approval required. Use draft_outreach first, "
                       "then ask user via chat. Only call send_outreach "
                       "after user says yes/approved/send it.",
        }

    # Policy check
    verdict, reason = brain.policy.check("outreach")
    if verdict == "deny":
        return {"success": False, "reason": reason}

    brain.policy.record("outreach")

    # Log to memory
    uid = f"{name}_{company}".replace(" ", "_")
    brain.memory.remember(
        name, "person", uid,
        {"company": company, "contacted": "true",
         "date": datetime.datetime.now().isoformat()}
    )
    brain.memory.log_action = getattr(brain.memory, "log", lambda *a: None)

    logger.info("Outreach logged for %s @ %s (approved by user)", name, company)

    return {
        "success":  True,
        "approved": True,
        "logged":   True,
        "message":  f"Outreach to {name} @ {company} logged. "
                    f"Open LinkedIn and send the drafted message manually.",
    }


def _send_digest(params: dict, context: dict, brain) -> dict:
    """Send weekly email digest of recent opportunities."""
    gmail_user = os.environ.get("RAKBOT_GMAIL_EMAIL", "")
    gmail_pass = os.environ.get("RAKBOT_GMAIL_PASSWORD", "")

    if not gmail_user or not gmail_pass:
        return {"success": False,
                "error": "Set RAKBOT_GMAIL_EMAIL and RAKBOT_GMAIL_PASSWORD in .env"}

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
        <a href="{r.get('link','#')}" style="background:#667eea;color:white;
        padding:6px 14px;border-radius:6px;text-decoration:none;font-size:12px;">
        View</a></div>"""
        for r in recent
    ])

    html = f"""<html><body style="font-family:Arial,sans-serif;background:#f0f2f5;padding:20px;">
    <div style="max-width:640px;margin:auto;">
    <div style="background:linear-gradient(135deg,#667eea,#764ba2);
    border-radius:12px 12px 0 0;padding:28px;text-align:center;">
    <h1 style="color:white;margin:0;">RKTM83 Weekly Digest</h1>
    <p style="color:rgba(255,255,255,0.8);margin:6px 0 0;">{today}</p>
    </div>
    <div style="background:white;padding:24px;border-radius:0 0 12px 12px;">
    <h2 style="font-size:16px;color:#333;">Recent Opportunities ({len(recent)})</h2>
    {cards}
    </div></div></body></html>"""

    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"RKTM83: {len(recent)} opportunities · {today}"
        msg["From"]    = gmail_user
        msg["To"]      = gmail_user
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, gmail_user, msg.as_string())
        logger.info("Digest sent: %d opportunities", len(recent))
        return {"success": True, "sent": len(recent)}
    except Exception as e:
        logger.error("Digest send failed: %s", e)
        return {"success": False, "error": str(e)}


def _save_to_csv(results: list):
    """Save to CSV for backward compatibility."""
    if not results:
        return
    csv_file   = "internships_tracker.csv"
    fieldnames = ["date", "title", "company", "link", "source", "category", "status"]
    today      = datetime.datetime.now().strftime("%d-%m-%Y")
    exists     = os.path.exists(csv_file)
    try:
        with open(csv_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not exists:
                writer.writeheader()
            for r in results:
                writer.writerow({
                    "date":     today,
                    "title":    r.get("title", ""),
                    "company":  r.get("company", ""),
                    "link":     r.get("link", ""),
                    "source":   r.get("source", ""),
                    "category": r.get("category", ""),
                    "status":   "new",
                })
    except Exception as e:
        logger.error("CSV save error: %s", e)


# ── REGISTRATION ──────────────────────────────────────────────────────────────

def register(agent):
    agent.brain.register_tool(
        "search_opportunities",
        "Search Internshala and web for new AI/ML internship opportunities. "
        "Use when memory has no recent opportunities or when user asks to search.",
        _search_opportunities
    )
    agent.brain.register_tool(
        "score_opportunity",
        "Evaluate a specific opportunity for fit using LLM reasoning. "
        "Use after finding opportunities to identify the best ones.",
        _score_opportunity
    )
    agent.brain.register_tool(
        "draft_outreach",
        "Draft a personalized LinkedIn DM or email to a recruiter. "
        "Shows the draft to the user in the dashboard chat for approval. "
        "NEVER sends anything automatically — always waits for user to say yes.",
        _draft_outreach
    )
    agent.brain.register_tool(
        "send_outreach",
        "Log approved outreach after user confirms via dashboard chat. "
        "Only call this if approved_by_user is true. "
        "If user has not approved yet, use draft_outreach first.",
        _send_outreach
    )
    agent.brain.register_tool(
        "send_digest",
        "Send weekly email digest of recent opportunities. "
        "Use once per week or when user explicitly requests it.",
        _send_digest
    )
    logger.info("Career skill loaded: 5 tools, no input() calls")
