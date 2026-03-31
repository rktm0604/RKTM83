"""
browser_skill.py — Browser Automation Skill
Plugs into agent_brain.Agent via agent.load_skill(browser_skill)

Registers these tools with the agent:
  - browse_url       : open a URL, return page text
  - fill_form        : fill input fields and submit
  - click_element    : click buttons/links by text or selector
  - search_web       : Google search, return top results

Tech: Playwright (async, runs headless by default, set BROWSER_HEADLESS=false for visible)

Usage:
  First: playwright install chromium
  Enable in config.yaml:
    skills:
      - browser
"""

import os
import re
import json
import asyncio
import logging
import datetime

logger = logging.getLogger("agent.browser")

SKILL_NAME = "browser"

_CONFIG = None
_BROWSER = None
_PAGE = None


def set_config(full_config: dict):
    global _CONFIG
    _CONFIG = full_config


def _get_headless() -> bool:
    return os.environ.get("BROWSER_HEADLESS", "true").lower() != "false"


async def _ensure_browser():
    """Lazy-init: create browser + page on first use."""
    global _BROWSER, _PAGE
    if _PAGE is not None:
        return _PAGE

    from playwright.async_api import async_playwright
    pw = await async_playwright().start()
    _BROWSER = await pw.chromium.launch(headless=_get_headless())
    context = await _BROWSER.new_context(
        viewport={"width": 1280, "height": 720},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    )
    _PAGE = await context.new_page()
    logger.info("Browser launched (headless=%s)", _get_headless())
    return _PAGE


def _run_async(coro):
    """Run async coroutine from sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result(timeout=30)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ── TOOL HANDLERS ─────────────────────────────────────────────────────────────

def _browse_url(params: dict, context: dict, brain) -> dict:
    """
    Open a URL and return the page title + text content.
    params: {"url": str}
    """
    url = params.get("url", "")
    if not url:
        return {"success": False, "error": "url required"}
    if not url.startswith("http"):
        url = "https://" + url

    async def _go():
        page = await _ensure_browser()
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        title = await page.title()
        text = await page.inner_text("body")
        # Truncate to avoid memory overflow
        text = text[:3000] if text else ""
        return title, text

    try:
        title, text = _run_async(_go())
        brain.memory.observe(
            f"Browsed: {title} — {url}",
            {"source": "browser", "type": "page_visit", "url": url, "title": title}
        )
        logger.info("Browsed: %s", url)
        return {"success": True, "title": title, "text": text[:500], "url": url}
    except Exception as e:
        logger.error("browse_url error: %s", e)
        return {"success": False, "error": str(e)}


def _fill_form(params: dict, context: dict, brain) -> dict:
    """
    Fill form fields on the current page.
    params: {"fields": {"selector_or_label": "value", ...}, "submit": "selector"}
    """
    fields = params.get("fields", {})
    submit = params.get("submit", "")

    if not fields:
        return {"success": False, "error": "fields required"}

    async def _do():
        page = await _ensure_browser()
        filled = []
        for selector, value in fields.items():
            try:
                # Try as CSS selector first
                el = page.locator(selector).first
                if await el.count() > 0:
                    await el.fill(str(value))
                    filled.append(selector)
                    continue
            except Exception:
                pass
            try:
                # Try as label text
                el = page.get_by_label(selector).first
                await el.fill(str(value))
                filled.append(selector)
            except Exception:
                try:
                    # Try as placeholder
                    el = page.get_by_placeholder(selector).first
                    await el.fill(str(value))
                    filled.append(selector)
                except Exception:
                    logger.warning("Could not find field: %s", selector)

        if submit:
            try:
                await page.locator(submit).first.click()
            except Exception:
                try:
                    await page.get_by_role("button", name=submit).first.click()
                except Exception:
                    await page.get_by_text(submit).first.click()
            await page.wait_for_load_state("domcontentloaded", timeout=5000)

        return filled

    try:
        filled = _run_async(_do())
        logger.info("Filled %d fields", len(filled))
        return {"success": True, "filled": filled}
    except Exception as e:
        logger.error("fill_form error: %s", e)
        return {"success": False, "error": str(e)}


def _click_element(params: dict, context: dict, brain) -> dict:
    """
    Click a button or link on the current page.
    params: {"text": str} or {"selector": str}
    """
    text = params.get("text", "")
    selector = params.get("selector", "")

    if not text and not selector:
        return {"success": False, "error": "text or selector required"}

    async def _do():
        page = await _ensure_browser()
        if selector:
            await page.locator(selector).first.click()
        elif text:
            # Try button role first, then link, then any text
            try:
                await page.get_by_role("button", name=text).first.click(timeout=3000)
            except Exception:
                try:
                    await page.get_by_role("link", name=text).first.click(timeout=3000)
                except Exception:
                    await page.get_by_text(text).first.click(timeout=3000)
        await page.wait_for_load_state("domcontentloaded", timeout=5000)
        return await page.title()

    try:
        title = _run_async(_do())
        logger.info("Clicked: %s → %s", text or selector, title)
        return {"success": True, "page_title": title}
    except Exception as e:
        logger.error("click_element error: %s", e)
        return {"success": False, "error": str(e)}


def _search_web(params: dict, context: dict, brain) -> dict:
    """
    Search Google and return top results.
    params: {"query": str, "max_results": int (default 5)}
    """
    query = params.get("query", "")
    max_results = min(params.get("max_results", 5), 10)

    if not query:
        return {"success": False, "error": "query required"}

    async def _do():
        page = await _ensure_browser()
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        await page.goto(search_url, wait_until="domcontentloaded", timeout=15000)

        results = []
        links = await page.locator("div.g").all()
        for link in links[:max_results]:
            try:
                title_el = link.locator("h3").first
                title = await title_el.inner_text() if await title_el.count() > 0 else ""
                a_tag = link.locator("a").first
                href = await a_tag.get_attribute("href") if await a_tag.count() > 0 else ""
                snippet_el = link.locator("div[data-sncf]").first
                snippet = ""
                try:
                    snippet = await snippet_el.inner_text() if await snippet_el.count() > 0 else ""
                except Exception:
                    pass
                if title and href:
                    results.append({"title": title, "url": href, "snippet": snippet[:200]})
            except Exception:
                continue
        return results

    try:
        results = _run_async(_do())
        for r in results:
            brain.memory.observe(
                f"Search result: {r['title']}",
                {"source": "google", "type": "search_result",
                 "title": r["title"], "link": r["url"], "query": query}
            )
        logger.info("search_web: %d results for '%s'", len(results), query)
        return {"success": True, "results": results, "count": len(results)}
    except Exception as e:
        logger.error("search_web error: %s", e)
        return {"success": False, "error": str(e)}


# ── SKILL REGISTRATION ───────────────────────────────────────────────────────

def register(agent):
    """Called by agent.load_skill(browser_skill)."""
    agent.brain.register_tool(
        "browse_url",
        "Open a URL in the browser and return the page title and text content. "
        "Use to visit any website, read articles, check pages.",
        _browse_url
    )
    agent.brain.register_tool(
        "fill_form",
        "Fill form fields on the current browser page and optionally submit. "
        "Use to log in, fill applications, enter data.",
        _fill_form
    )
    agent.brain.register_tool(
        "click_element",
        "Click a button or link on the current browser page by text or CSS selector. "
        "Use to navigate, accept cookies, press buttons.",
        _click_element
    )
    agent.brain.register_tool(
        "search_web",
        "Search Google and return top results with titles, URLs, and snippets. "
        "Use to find information on any topic.",
        _search_web
    )

    logger.info("Browser skill registered: 4 tools")
    return agent
