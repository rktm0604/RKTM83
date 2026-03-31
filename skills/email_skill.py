"""
email_skill.py — Email Skill
Plugs into agent_brain.Agent via agent.load_skill(email_skill)

Registers these tools with the agent:
  - send_email    : send an email (configurable approval)
  - read_inbox    : fetch and summarize recent emails
  - reply_email   : draft and send a reply

Tech: smtplib (send) + imaplib (read)

Requires .env:
  RAKBOT_GMAIL_EMAIL=your@gmail.com
  RAKBOT_GMAIL_PASSWORD=your_app_password

Usage:
  Enable in config.yaml:
    skills:
      - email
    email:
      require_approval: true   # set false for fully autonomous
"""

import os
import re
import json
import email
import imaplib
import smtplib
import logging
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger("agent.email")

SKILL_NAME = "email"

_CONFIG = None


def set_config(full_config: dict):
    global _CONFIG
    _CONFIG = full_config


def _get_credentials() -> tuple:
    """Get email credentials from environment."""
    user = os.environ.get("RAKBOT_GMAIL_EMAIL", "")
    pwd  = os.environ.get("RAKBOT_GMAIL_PASSWORD", "")
    return user, pwd


def _require_approval() -> bool:
    """Check if email sending requires human approval."""
    if _CONFIG:
        return _CONFIG.get("email", {}).get("require_approval", True)
    return True


# ── TOOL HANDLERS ─────────────────────────────────────────────────────────────

def _send_email(params: dict, context: dict, brain) -> dict:
    """
    Send an email.
    params: {"to": str, "subject": str, "body": str, "html": bool (default false)}
    """
    verdict, reason = brain.policy.check("outreach")
    if verdict == "deny":
        return {"success": False, "reason": reason}

    to      = params.get("to", "")
    subject = params.get("subject", "")
    body    = params.get("body", "")
    is_html = params.get("html", False)

    if not to or not subject or not body:
        return {"success": False, "error": "to, subject, and body required"}

    gmail_user, gmail_pass = _get_credentials()
    if not gmail_user or not gmail_pass:
        return {"success": False, "error": "Email credentials not set in .env"}

    # Human approval gate (configurable)
    if _require_approval():
        print(f"\n{'='*55}")
        print(f"  EMAIL DRAFT")
        print(f"{'='*55}")
        print(f"  To:      {to}")
        print(f"  Subject: {subject}")
        print(f"\n{body}\n")
        print(f"{'='*55}")
        approve = input("  Send this email? [y/n]: ").strip().lower()
        if approve != "y":
            logger.info("Email declined by operator")
            return {"success": True, "sent": False, "reason": "declined by operator"}

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = gmail_user
        msg["To"]      = to
        msg.attach(MIMEText(body, "html" if is_html else "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, to, msg.as_string())

        brain.policy.record("outreach")
        brain.memory.observe(
            f"Email sent to {to}: {subject}",
            {"source": "email", "type": "email_sent", "to": to, "subject": subject}
        )
        logger.info("Email sent to %s: %s", to, subject)
        return {"success": True, "sent": True, "to": to, "subject": subject}

    except Exception as e:
        logger.error("send_email error: %s", e)
        return {"success": False, "error": str(e)}


def _read_inbox(params: dict, context: dict, brain) -> dict:
    """
    Read recent emails from inbox.
    params: {"max_emails": int (default 10), "folder": str (default "INBOX")}
    """
    max_emails = min(int(params.get("max_emails", 10)), 30)
    folder     = params.get("folder", "INBOX")

    gmail_user, gmail_pass = _get_credentials()
    if not gmail_user or not gmail_pass:
        return {"success": False, "error": "Email credentials not set in .env"}

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(gmail_user, gmail_pass)
        mail.select(folder, readonly=True)

        _, message_ids = mail.search(None, "ALL")
        ids = message_ids[0].split()
        recent_ids = ids[-max_emails:] if ids else []

        emails = []
        for eid in reversed(recent_ids):
            _, msg_data = mail.fetch(eid, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            subject = str(email.header.decode_header(msg["Subject"])[0][0] or "")
            if isinstance(subject, bytes):
                subject = subject.decode("utf-8", errors="replace")
            sender = msg.get("From", "")
            date = msg.get("Date", "")

            # Extract body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = payload.decode("utf-8", errors="replace")[:500]
                        break
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    body = payload.decode("utf-8", errors="replace")[:500]

            emails.append({
                "subject": subject,
                "from":    sender,
                "date":    date,
                "preview": body[:200],
                "id":      eid.decode(),
            })

        mail.logout()

        brain.memory.observe(
            f"Read inbox: {len(emails)} emails",
            {"source": "email", "type": "inbox_read", "count": str(len(emails))}
        )
        logger.info("Read %d emails from %s", len(emails), folder)
        return {"success": True, "count": len(emails), "emails": emails}

    except Exception as e:
        logger.error("read_inbox error: %s", e)
        return {"success": False, "error": str(e)}


def _reply_email(params: dict, context: dict, brain) -> dict:
    """
    Draft and send a reply to an email.
    params: {"to": str, "subject": str, "original": str, "reply": str}
    Uses LLM to draft if reply is not provided.
    """
    to       = params.get("to", "")
    subject  = params.get("subject", "")
    original = params.get("original", "")
    reply    = params.get("reply", "")

    if not to:
        return {"success": False, "error": "to address required"}

    # If no reply text provided, use LLM to draft one
    if not reply and original:
        prompt = f"""Draft a brief, professional reply to this email.

ORIGINAL EMAIL:
From: {to}
Subject: {subject}
{original[:500]}

RULES:
- Keep it under 3 sentences
- Be helpful and direct
- Don't be overly formal

Output ONLY the reply text."""

        reply = brain._infer(prompt)
        if not reply:
            return {"success": False, "error": "LLM failed to generate reply"}

    if not reply:
        return {"success": False, "error": "reply text required or provide original email for auto-draft"}

    # Use send_email with Re: subject
    re_subject = subject if subject.startswith("Re:") else f"Re: {subject}"
    return _send_email(
        {"to": to, "subject": re_subject, "body": reply},
        context, brain
    )


# ── SKILL REGISTRATION ───────────────────────────────────────────────────────

def register(agent):
    """Called by agent.load_skill(email_skill)."""
    agent.brain.register_tool(
        "send_email",
        "Send an email to someone. Requires approval by default "
        "(set email.require_approval=false in config for autonomous sending). "
        "Needs RAKBOT_GMAIL_EMAIL and RAKBOT_GMAIL_PASSWORD in .env.",
        _send_email
    )
    agent.brain.register_tool(
        "read_inbox",
        "Read recent emails from your Gmail inbox. "
        "Returns subject, sender, date, and preview for each email.",
        _read_inbox
    )
    agent.brain.register_tool(
        "reply_email",
        "Reply to an email. Can auto-draft using LLM if given the original email. "
        "Respects the same approval setting as send_email.",
        _reply_email
    )

    logger.info("Email skill registered: 3 tools")
    return agent
