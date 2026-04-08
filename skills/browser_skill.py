"""
browser_skill.py — Enhanced Browser Automation Skill
Plugs into agent_brain.Agent via agent.load_skill(browser_skill)

Enhanced Features:
  - Visible/headless mode toggle
  - Screenshot capture
  - Page scrolling
  - Content extraction with CSS selectors
  - Enhanced form filling with templates
  - Multi-step automation workflows
  - Session persistence

Tech: Playwright (sync)

Usage:
  First: playwright install chromium
  Set BROWSER_HEADLESS=false for visible mode
  Enable in config.yaml:
    skills:
      - browser
"""

import os
import re
import json
import logging
import datetime
import base64
from pathlib import Path

logger = logging.getLogger("agent.browser")

SKILL_NAME = "browser"

_CONFIG = None
_PLAYWRIGHT = None
_BROWSER = None
_PAGE = None

# Form templates for common scenarios
FORM_TEMPLATES = {
    "job_application": {
        "full_name": "name",
        "first_name": "firstName",
        "last_name": "lastName", 
        "email": "email",
        "phone": "phone",
        "resume": "resume",
        "cover_letter": "coverLetter",
        "linkedin": "linkedin",
        "github": "github",
        "portfolio": "portfolio",
        "location": "location",
        "experience": "experience",
        "education": "education"
    },
    "contact_form": {
        "name": "name",
        "email": "email",
        "subject": "subject",
        "message": "message"
    },
    "login_form": {
        "username": "username",
        "email": "email", 
        "password": "password"
    },
    "signup_form": {
        "name": "name",
        "email": "email",
        "password": "password",
        "confirm_password": "confirmPassword"
    }
}

# Pre-built automation workflows
AUTOMATION_WORKFLOWS = {
    "job_search": {
        "description": "Search for jobs and extract listings",
        "steps": [
            {"action": "search", "query": "{query}"},
            {"action": "scroll", "pixels": 500},
            {"action": "extract", "selectors": {"titles": "h2", "companies": ".company", "locations": ".location"}}
        ]
    },
    "company_research": {
        "description": "Research a company website",
        "steps": [
            {"action": "browse", "url": "https://{domain}"},
            {"action": "extract", "selectors": {"about": "#about", "team": "#team", "contact": "#contact"}},
            {"action": "screenshot"}
        ]
    }
}


def set_config(full_config: dict):
    global _CONFIG
    _CONFIG = full_config


def _get_headless() -> bool:
    """Check if browser should run headless. Can be overridden via params."""
    return os.environ.get("BROWSER_HEADLESS", "true").lower() != "false"


def _ensure_browser(params: dict = None) -> any:
    """Lazy-init: create browser + page on first use securely."""
    global _PLAYWRIGHT, _BROWSER, _PAGE
    
    # Allow override via params
    headless = True
    if params and params.get("headless") is not None:
        headless = params.get("headless")
    elif _CONFIG and _CONFIG.get("browser"):
        headless = _CONFIG.get("browser", {}).get("headless", True)
    
    if _PAGE is not None:
        try:
            _PAGE.title()
            return _PAGE
        except Exception:
            _PAGE = None
            _BROWSER = None
            _PLAYWRIGHT = None

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return None

    try:
        _PLAYWRIGHT = sync_playwright().start()
        
        # Launch browser (visible if headless=False)
        launch_args = []
        if not headless:
            launch_args.append("--start-maximized")
            logger.info("Browser will run in VISIBLE mode")
        
        _BROWSER = _PLAYWRIGHT.chromium.launch(
            headless=headless,
            args=launch_args
        )
        
        context = _BROWSER.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        _PAGE = context.new_page()
        logger.info("Browser launched (headless=%s, visible=%s)", headless, not headless)
        return _PAGE
    except Exception as e:
        logger.error("Failed to launch browser: %s", e)
        return None


def _close_browser():
    """Close browser and cleanup."""
    global _PLAYWRIGHT, _BROWSER, _PAGE
    try:
        if _PAGE:
            _PAGE.close()
        if _BROWSER:
            _BROWSER.close()
        if _PLAYWRIGHT:
            _PLAYWRIGHT.stop()
    except Exception as e:
        logger.warning("Error closing browser: %s", e)
    finally:
        _PAGE = None
        _BROWSER = None
        _PLAYWRIGHT = None


# ── TOOL HANDLERS ─────────────────────────────────────────────────────────────

def _browse_url(params: dict, context: dict, brain) -> dict:
    """
    Open a URL and return the page title + text content.
    params: {"url": str, "headless": bool (optional), "wait": int (optional seconds)}
    """
    url = params.get("url", "")
    if not url:
        return {"success": False, "error": "url required"}
    if not url.startswith("http"):
        url = "https://" + url

    wait_time = params.get("wait", 2)
    
    try:
        page = _ensure_browser(params)
        if not page:
            return {"success": False, "error": "Browser not available"}
        
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        
        # Wait for dynamic content
        if wait_time > 0:
            page.wait_for_timeout(wait_time * 1000)
        
        title = page.title()
        url_current = page.url
        
        # Get main content more intelligently
        try:
            text = page.inner_text("main") or page.inner_text("article") or page.inner_text("body")
        except:
            text = page.inner_text("body")
        
        text = text[:5000] if text else ""

        brain.memory.observe(
            f"Browsed: {title} — {url}",
            {"source": "browser", "type": "page_visit", "url": url, "title": title}
        )
        logger.info("Browsed: %s", url)
        return {
            "success": True, 
            "title": title, 
            "text": text[:1500], 
            "url": url_current, 
            "full_text_length": len(text)
        }
    except Exception as e:
        logger.error("browse_url error: %s", e)
        return {"success": False, "error": str(e)}


def _screenshot(params: dict, context: dict, brain) -> dict:
    """
    Take a screenshot of the current page.
    params: {"save_path": str (optional), "full_page": bool (optional)}
    """
    save_path = params.get("save_path", "screenshot.png")
    full_page = params.get("full_page", False)
    
    try:
        page = _ensure_browser(params)
        if not page:
            return {"success": False, "error": "Browser not available"}
        
        # Ensure directory exists
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        
        page.screenshot(path=save_path, full_page=full_page)
        
        brain.memory.observe(
            f"Screenshot saved: {save_path}",
            {"source": "browser", "type": "screenshot", "path": save_path}
        )
        logger.info("Screenshot saved: %s", save_path)
        return {"success": True, "path": save_path, "full_page": full_page}
    except Exception as e:
        logger.error("screenshot error: %s", e)
        return {"success": False, "error": str(e)}


def _scroll_page(params: dict, context: dict, brain) -> dict:
    """
    Scroll the page.
    params: {"pixels": int (default 500), "direction": str ("down"/"up")}
    """
    pixels = params.get("pixels", 500)
    direction = params.get("direction", "down")
    
    try:
        page = _ensure_browser(params)
        if not page:
            return {"success": False, "error": "Browser not available"}
        
        if direction == "up":
            pixels = -pixels
        
        # Scroll smoothly
        for _ in range(3):
            page.evaluate(f"window.scrollBy(0, {pixels // 3})")
            page.wait_for_timeout(300)
        
        title = page.title()
        logger.info("Scrolled %d pixels %s on %s", pixels, direction, title)
        return {"success": True, "pixels": pixels, "direction": direction, "page_title": title}
    except Exception as e:
        logger.error("scroll_page error: %s", e)
        return {"success": False, "error": str(e)}


def _scrape_content(params: dict, context: dict, brain) -> dict:
    """
    Extract specific content from current page using CSS selectors.
    params: {"selectors": {"key": "css_selector", ...}}
    """
    selectors = params.get("selectors", {})
    
    if not selectors:
        return {"success": False, "error": "selectors required"}
    
    try:
        page = _ensure_browser(params)
        if not page:
            return {"success": False, "error": "Browser not available"}
        
        results = {}
        for key, selector in selectors.items():
            try:
                elements = page.locator(selector).all()
                texts = [el.inner_text().strip() for el in elements if el.inner_text().strip()]
                results[key] = texts[:10]  # Limit to 10 results
            except Exception as e:
                results[key] = [f"Error: {str(e)}"]
        
        logger.info("Extracted content with selectors: %s", list(selectors.keys()))
        return {"success": True, "extracted": results, "selectors": list(selectors.keys())}
    except Exception as e:
        logger.error("scrape_content error: %s", e)
        return {"success": False, "error": str(e)}


def _fill_form(params: dict, context: dict, brain) -> dict:
    """
    Fill form fields on the current page with enhanced support.
    params: {
        "url": str (optional - navigate to URL first),
        "fields": {"label": "value", ...},
        "template": str (optional - use template like "job_application"),
        "data": dict (optional - data for template),
        "submit": str (optional - button text to click)
    }
    """
    # Optional: navigate to URL first
    url = params.get("url", "")
    if url:
        if not url.startswith("http"):
            url = "https://" + url
        try:
            page = _ensure_browser(params)
            if page:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(1000)
        except Exception as e:
            return {"success": False, "error": f"Failed to navigate to URL: {e}"}
    
    # Get fields to fill
    fields = params.get("fields", {})
    
    # Handle template
    template_name = params.get("template", "")
    if template_name and template_name in FORM_TEMPLATES:
        template = FORM_TEMPLATES[template_name]
        data = params.get("data", {})
        # Map data to template fields
        fields = {}
        for key, selector in template.items():
            if key in data:
                fields[selector] = data[key]
    
    if not fields:
        return {"success": False, "error": "fields or template+data required"}
    
    submit = params.get("submit", "")
    
    try:
        page = _ensure_browser(params)
        if not page:
            return {"success": False, "error": "Browser not available"}
        
        filled = []
        failed = []
        
        for label, value in fields.items():
            # Try multiple methods to find the field
            filled_field = False
            
            # Method 1: Try as CSS selector
            try:
                el = page.locator(label).first
                if el.count() > 0:
                    el.fill(str(value))
                    filled.append(label)
                    filled_field = True
                    continue
            except:
                pass
            
            # Method 2: Try as label text
            try:
                el = page.get_by_label(label, exact=False).first
                if el.count() > 0:
                    el.fill(str(value))
                    filled.append(label)
                    filled_field = True
                    continue
            except:
                pass
            
            # Method 3: Try as placeholder
            try:
                el = page.get_by_placeholder(label, exact=False).first
                if el.count() > 0:
                    el.fill(str(value))
                    filled.append(label)
                    filled_field = True
                    continue
            except:
                pass
            
            # Method 4: Try as name/id attribute
            try:
                el = page.locator(f'[name="{label}"], [id="{label}"]').first
                if el.count() > 0:
                    el.fill(str(value))
                    filled.append(label)
                    filled_field = True
                    continue
            except:
                pass
            
            if not filled_field:
                failed.append(label)
        
        # Submit if requested
        submitted = False
        if submit:
            try:
                page.get_by_role("button", name=submit).first.click(timeout=3000)
                page.wait_for_load_state("domcontentloaded", timeout=5000)
                submitted = True
            except:
                try:
                    page.get_by_text(submit).first.click(timeout=3000)
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                    submitted = True
                except:
                    pass
        
        result = {
            "success": True,
            "filled": filled,
            "failed": failed,
            "submitted": submitted
        }
        
        logger.info("Filled %d fields, %d failed, submitted=%s", len(filled), len(failed), submitted)
        return result
        
    except Exception as e:
        logger.error("fill_form error: %s", e)
        return {"success": False, "error": str(e)}


def _click_element(params: dict, context: dict, brain) -> dict:
    """
    Click a button or link on the current page.
    params: {"text": str, "selector": str, "index": int (optional)}
    """
    text = params.get("text", "")
    selector = params.get("selector", "")
    index = params.get("index", 0)
    
    if not text and not selector:
        return {"success": False, "error": "text or selector required"}
    
    try:
        page = _ensure_browser(params)
        if not page:
            return {"success": False, "error": "Browser not available"}
        
        if selector:
            page.locator(selector).nth(index).click(timeout=5000)
        elif text:
            # Try multiple strategies
            try:
                page.get_by_role("button", name=text).nth(index).click(timeout=3000)
            except:
                try:
                    page.get_by_role("link", name=text).nth(index).click(timeout=3000)
                except:
                    page.get_by_text(text, exact=False).nth(index).click(timeout=3000)
        
        page.wait_for_load_state("domcontentloaded", timeout=5000)
        title = page.title()
        url = page.url
        
        logger.info("Clicked: %s → %s (%s)", text or selector, title, url)
        return {"success": True, "page_title": title, "url": url}
    except Exception as e:
        logger.error("click_element error: %s", e)
        return {"success": False, "error": str(e)}


def _get_page_state(params: dict, context: dict, brain) -> dict:
    """
    Get current page state for debugging.
    params: {}
    """
    try:
        page = _ensure_browser(params)
        if not page:
            return {"success": False, "error": "Browser not available"}
        
        return {
            "success": True,
            "url": page.url,
            "title": page.title(),
            "loaded": True
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _automation_workflow(params: dict, context: dict, brain) -> dict:
    """
    Execute a multi-step automation workflow.
    params: {
        "workflow": str (name of pre-built workflow),
        "steps": [{"action": "...", ...}] (custom steps),
        "params": {} (parameters for workflow)
    }
    """
    workflow_name = params.get("workflow", "")
    custom_steps = params.get("steps", [])
    params_dict = params.get("params", {})
    
    # Get workflow steps
    steps = []
    if workflow_name and workflow_name in AUTOMATION_WORKLOWS:
        workflow = AUTOMATION_WORKLOWS[workflow_name]
        raw_steps = workflow.get("steps", [])
        # Replace placeholders with params
        for step in raw_steps:
            step_copy = step.copy()
            for key, value in step_copy.items():
                if isinstance(value, str):
                    for p_key, p_val in params_dict.items():
                        value = value.replace(f"{{{p_key}}}", str(p_val))
                step_copy[key] = value
            steps.append(step_copy)
    elif custom_steps:
        steps = custom_steps
    
    if not steps:
        return {"success": False, "error": "No workflow or steps provided"}
    
    try:
        page = _ensure_browser(params)
        if not page:
            return {"success": False, "error": "Browser not available"}
        
        results = []
        
        for i, step in enumerate(steps):
            action = step.get("action", "")
            logger.info(f"Workflow step {i+1}/{len(steps)}: {action}")
            
            try:
                if action == "search":
                    query = step.get("query", "")
                    # Use search_web tool internally
                    search_result = _search_web({"query": query, "max_results": 5}, context, brain)
                    results.append({"step": i+1, "action": "search", "result": search_result})
                    
                elif action == "browse":
                    url = step.get("url", "")
                    if not url.startswith("http"):
                        url = "https://" + url
                    page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    results.append({"step": i+1, "action": "browse", "url": url, "title": page.title()})
                    
                elif action == "click":
                    text = step.get("text", "")
                    selector = step.get("selector", "")
                    _click_element({"text": text, "selector": selector}, context, brain)
                    results.append({"step": i+1, "action": "click", "target": text or selector})
                    
                elif action == "scroll":
                    pixels = step.get("pixels", 500)
                    _scroll_page({"pixels": pixels}, context, brain)
                    results.append({"step": i+1, "action": "scroll", "pixels": pixels})
                    
                elif action == "extract":
                    selectors = step.get("selectors", {})
                    extracted = _scrape_content({"selectors": selectors}, context, brain)
                    results.append({"step": i+1, "action": "extract", "data": extracted.get("extracted", {})})
                    
                elif action == "screenshot":
                    path = step.get("path", f"workflow_step_{i+1}.png")
                    _screenshot({"save_path": path}, context, brain)
                    results.append({"step": i+1, "action": "screenshot", "path": path})
                    
                elif action == "fill":
                    fields = step.get("fields", {})
                    template = step.get("template", "")
                    data = step.get("data", {})
                    submit = step.get("submit", "")
                    _fill_form({"fields": fields, "template": template, "data": data, "submit": submit}, context, brain)
                    results.append({"step": i+1, "action": "fill", "filled": list(fields.keys())})
                    
            except Exception as step_error:
                logger.error(f"Workflow step {i+1} failed: {step_error}")
                results.append({"step": i+1, "action": action, "error": str(step_error)})
        
        return {"success": True, "workflow": workflow_name or "custom", "steps_completed": len(results), "results": results}
        
    except Exception as e:
        logger.error("automation_workflow error: %s", e)
        return {"success": False, "error": str(e)}


def _search_web(params: dict, context: dict, brain) -> dict:
    """
    Search the web and return top results.
    params: {"query": str, "max_results": int (default 5)}
    """
    query = params.get("query", "")
    max_results = min(params.get("max_results", 5), 10)

    if not query:
        return {"success": False, "error": "query required"}

    results = []
    errors = []

    # Try DuckDuckGo first
    try:
        import requests
        from bs4 import BeautifulSoup
        
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}", 
                           headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        for result_div in soup.find_all("div", class_="result")[:max_results]:
            try:
                a_tag = result_div.find("a", class_="result__url")
                title_tag = result_div.find("h2", class_="result__title")
                snippet_tag = result_div.find("a", class_="result__snippet")
                
                title = title_tag.text.strip() if title_tag else ""
                href = a_tag.get("href") if a_tag else ""
                snippet = snippet_tag.text.strip() if snippet_tag else ""
                
                if href and href.startswith("//"):
                    import urllib.parse
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    href = parsed.get("uddg", [href])[0]
                
                if title and href:
                    results.append({"title": title, "url": href, "snippet": snippet[:200], "source": "DuckDuckGo"})
            except Exception:
                continue
        
        if results:
            logger.info("search_web (DuckDuckGo): %d results for '%s'", len(results), query)
    except Exception as e:
        errors.append(f"DuckDuckGo failed: {e}")
        logger.warning("DuckDuckGo search failed: %s", e)

    # Fallback to Google if no results
    if not results:
        try:
            resp = requests.get(
                f"https://www.google.com/search?q={query.replace(' ', '+')}&num={max_results}",
                headers=headers, timeout=10
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            
            for div in soup.find_all("div", class_="g")[:max_results]:
                try:
                    title_tag = div.find("h3")
                    link_tag = div.find("a")
                    snippet_tag = div.find("div", class_="VwiC3b")
                    
                    title = title_tag.text.strip() if title_tag else ""
                    href = link_tag.get("href", "") if link_tag else ""
                    snippet = snippet_tag.text.strip() if snippet_tag else ""
                    
                    if title and href and href.startswith("http"):
                        results.append({"title": title, "url": href, "snippet": snippet[:200], "source": "Google"})
                except Exception:
                    continue
            
            if results:
                logger.info("search_web (Google fallback): %d results for '%s'", len(results), query)
        except Exception as e:
            errors.append(f"Google failed: {e}")
            logger.warning("Google search failed: %s", e)

    # Final fallback to Bing
    if not results:
        try:
            resp = requests.get(
                f"https://www.bing.com/search?q={query.replace(' ', '+')}&count={max_results}",
                headers=headers, timeout=10
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            
            for li in soup.find_all("li", class_="b_algo")[:max_results]:
                try:
                    title_tag = li.find("h2")
                    link_tag = title_tag.find("a") if title_tag else None
                    snippet_tag = li.find("p")
                    
                    title = title_tag.text.strip() if title_tag else ""
                    href = link_tag.get("href", "") if link_tag else ""
                    snippet = snippet_tag.text.strip() if snippet_tag else ""
                    
                    if title and href:
                        results.append({"title": title, "url": href, "snippet": snippet[:200], "source": "Bing"})
                except Exception:
                    continue
            
            if results:
                logger.info("search_web (Bing fallback): %d results for '%s'", len(results), query)
        except Exception as e:
            errors.append(f"Bing failed: {e}")
            logger.warning("Bing search failed: %s", e)

    if not results:
        logger.error("search_web: All search engines failed. Errors: %s", errors)
        return {"success": False, "error": f"All search engines failed. Try a different query.", "details": errors}

    # Store in memory
    for r in results:
        brain.memory.observe(
            f"Search result: {r['title']}",
            {"source": "browser", "type": "search_result",
             "title": r["title"], "link": r["url"], "query": query, "source": r.get("source")}
        )
    
    return {"success": True, "results": results, "count": len(results), "query": query}


# ── SKILL REGISTRATION ───────────────────────────────────────────────────────

def register(agent_or_brain):
    """Called by agent.load_skill(browser_skill). Accepts Agent or AgentBrain."""
    # Handle both Agent and AgentBrain
    if hasattr(agent_or_brain, 'brain'):
        brain = agent_or_brain.brain
    else:
        brain = agent_or_brain
    
    brain.register_tool(
        "search_web",
        "Search the web and return top results. "
        "Params: {'query': 'search term', 'max_results': 5}. "
        "Use to find information, jobs, research.",
        _search_web
    )
    brain.register_tool(
        "browse_url",
        "Open a URL in the browser and return the page title and text content. "
        "Params: {'url': 'https://...', 'headless': false}. "
        "Use to visit websites, read articles.",
        _browse_url
    )
    brain.register_tool(
        "screenshot",
        "Take a screenshot of the current browser page. "
        "Params: {'save_path': 'filename.png', 'full_page': true/false}. "
        "Use to capture what's visible.",
        _screenshot
    )
    brain.register_tool(
        "scroll_page",
        "Scroll the browser page up or down. "
        "Params: {'pixels': 500, 'direction': 'down'/'up'}. "
        "Use to load more content or navigate.",
        _scroll_page
    )
    brain.register_tool(
        "scrape_content",
        "Extract specific content from page using CSS selectors. "
        "Params: {'selectors': {'title': 'h1', 'links': 'a'}}. "
        "Use to extract structured data from websites.",
        _scrape_content
    )
    brain.register_tool(
        "fill_form",
        "Fill form fields on a page. "
        "Params: {'url': '...', 'fields': {'email': 'test@...'}, 'template': 'job_application', 'data': {...}, 'submit': 'Submit'}. "
        "Supports templates: job_application, contact_form, login_form, signup_form. "
        "Use to fill applications, contact forms, login.",
        _fill_form
    )
    brain.register_tool(
        "click_element",
        "Click a button or link on the current page. "
        "Params: {'text': 'Apply Now', 'selector': '#submit', 'index': 0}. "
        "Use to navigate, accept, press buttons.",
        _click_element
    )
    brain.register_tool(
        "get_page_state",
        "Get current page URL and title. "
        "Params: {}. Use for debugging.",
        _get_page_state
    )
    brain.register_tool(
        "automation_workflow",
        "Execute multi-step automation workflow. "
        "Params: {'workflow': 'job_search', 'steps': [...], 'params': {...}}. "
        "Use for complex multi-step tasks.",
        _automation_workflow
    )
    
    # Register permission requirement for browser tools
    if hasattr(agent_or_brain, 'require_permission'):
        agent_or_brain.require_permission('browse_url')
        agent_or_brain.require_permission('fill_form')
        agent_or_brain.require_permission('automation_workflow')

    logger.info("Browser skill registered: 10 tools (enhanced)")
    return agent_or_brain