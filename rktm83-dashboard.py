"""
rktm83 Dashboard - Production-Ready UI
Full-width, modern design, professional look
FIXED VERSION - Forces actual tool execution
"""

import json
import datetime
import logging

logger = logging.getLogger("rktm83.dashboard")

try:
    import gradio as gr
except ImportError:
    print("ERROR: gradio not installed. Run: pip install gradio")
    raise

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed. Run: pip install pyyaml")
    raise

from agent_brain import AgentMemory, PolicyEngine, Agent
from run_agent import build_profile, load_skills, CONFIG

_AGENT = None


def get_agent():
    global _AGENT
    if _AGENT is not None:
        return _AGENT

    cfg = CONFIG.get("agent", {})
    overrides = {k: v for k, v in CONFIG.get("policy", {}).items() if k != "search_interval_hours"}

    _AGENT = Agent(
        name=cfg.get("name", "RKTM83"),
        profile=build_profile(CONFIG),
        memory_path=cfg.get("memory_path", "./rktm83_memory"),
        policy_overrides=overrides,
    )
    _AGENT.context["config"] = CONFIG
    _AGENT.brain.set_config(CONFIG)
    load_skills(_AGENT, CONFIG)
    return _AGENT


# ── CHAT SESSION STATE ─────────────────────────────────────────────────────
_chat_history = []

# Action keyword → tool mapping (forced execution)
ACTION_KEYWORDS = {
    # Browsing
    ("go to", "visit", "browse to", "navigate to"): "browse_url",
    ("search for", "search", "find", "look for", "google"): "search_web",
    
    # Files
    ("list files", "show files", "what files", "list my files"): "list_files",
    ("read file", "show content"): "read_file",
    ("move file", "copy file"): "move_file",
    
    # Desktop
    ("open app", "launch", "start", "open notepad", "open calculator", "open word", "open excel"): "open_app",
    ("take screenshot", "screenshot", "capture screen"): "screenshot",
    
    # Email
    ("send email", "send mail"): "send_email",
    ("check email", "read emails", "inbox"): "read_inbox",
    
    # Career/Jobs
    ("find jobs", "search jobs", "search internships", "internship", "job search"): "search_opportunities",
    ("find papers", "search papers", "papers on"): "find_papers",
    ("find issues", "github issues"): "find_issues",
    ("trending repos", "popular repos"): "find_trending",
    
    # GitHub
    ("github", "repo", "repository"): "find_trending",
    
    # Research
    ("professor", "research programs"): "find_professors",
}


def detect_and_execute_tool(user_input: str, agent) -> dict:
    """Detect action keywords and execute the appropriate tool."""
    user_lower = user_input.lower().strip()
    
    for keywords, tool_name in ACTION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in user_lower:
                params = _build_params_for_tool(tool_name, user_input, user_lower)
                try:
                    result = agent.brain.execute(
                        {"tool": tool_name, "params": params},
                        agent.context
                    )
                    return {"tool": tool_name, "params": params, "result": result, "matched": keyword}
                except Exception as e:
                    return {"tool": tool_name, "error": str(e), "matched": keyword}
    
    return {"tool": None}


def _build_params_for_tool(tool_name: str, user_input: str, user_lower: str) -> dict:
    """Build parameters for the tool based on user input."""
    params = {}
    import re
    
    if tool_name == "browse_url":
        urls = re.findall(r'(https?://)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})[/\w.-]*', user_input)
        if urls:
            url = urls[0][1]
            if not url.startswith('http'):
                url = 'https://' + url
            params['url'] = url
        else:
            for domain in ['github.com', 'linkedin.com', 'google.com', 'wikipedia.org']:
                if domain in user_lower:
                    params['url'] = 'https://' + domain
                    break
    
    elif tool_name in ["search_web", "search_opportunities"]:
        query_match = re.search(r'(?:search for|find|search|look for)\s+(?:about\s+)?(.+)', user_lower)
        if query_match:
            params['query'] = query_match.group(1).strip()
            params['max_results'] = 10
        else:
            params['query'] = user_input.strip()
            params['max_results'] = 10
    
    elif tool_name == "open_app":
        apps = {
            'notepad': 'notepad', 'calculator': 'calculator', 'word': 'microsoft word',
            'excel': 'microsoft excel', 'chrome': 'chrome', 'browser': 'chrome',
            'vscode': 'vscode', 'code': 'code',
        }
        for app_key, app_name in apps.items():
            if app_key in user_lower:
                params['app'] = app_name
                break
    
    elif tool_name == "list_files":
        folder_match = re.search(r'(?:in|on|from)\s+(?:my\s+)?(\w+)', user_lower)
        if folder_match:
            path = folder_match.group(1)
            if path in ['downloads', 'desktop', 'documents']:
                params['path'] = f"~/{path}"
            else:
                params['path'] = path
    
    return params


def chat_with_agent(message, history):
    """ChatGPT-style chat interface - forces actual tool execution."""
    global _chat_history

    try:
        agent = get_agent()
    except Exception as e:
        return f"Error: {str(e)}"

    user_input = message.strip()
    if not user_input:
        return "Please type a message."

    # FIRST: Auto-detect and execute tools BEFORE LLM response
    tool_result = detect_and_execute_tool(user_input, agent)
    
    tool_executed = False
    tool_output = ""
    
    if tool_result.get("tool"):
        result_data = tool_result.get("result", {})
        
        if result_data.get("success"):
            tool_executed = True
            tool_output = _format_tool_result(tool_result["tool"], result_data)
        else:
            tool_executed = True
            tool_output = f"[{tool_result['tool']} failed: {result_data.get('error', 'unknown')}]"

    # Build prompt for LLM
    conversation = ""
    for role, msg in _chat_history[-10:]:
        conversation += f"{role}: {msg}\n"

    current_time = datetime.datetime.now().strftime("%I:%M %p")
    tools_list = ', '.join(agent.brain._tools.keys())

    prompt = f"""{agent.brain.profile}

You are RKTM83 - an AI agent that ACTUALLY DOES THINGS.

CONVERSATION:
{conversation}

TIME: {current_time}
TOOLS: {tools_list}

USER: {user_input}

IMPORTANT: If user asks to DO something (search, find, open, list, etc), you MUST execute a tool!
The tool has ALREADY been executed automatically if detected.

Show the results in your response naturally.

If you need to use a tool, respond:
ACTION: tool_name
PARAMS: {{"param": "value"}}"""

    response = agent.brain._infer(prompt)

    # Check if LLM also tries to use a tool
    tool_name = None
    tool_params = {}
    response_lower = response.lower()

    if "action:" in response_lower and "params:" in response_lower:
        try:
            action_idx = response_lower.find("action:")
            params_idx = response_lower.find("params:")
            action_line = response[action_idx + 8:params_idx].strip()
            params_line = response[params_idx + 8:].strip()
            
            if params_line.strip().startswith("{"):
                import ast
                try:
                    tool_params = ast.literal_eval(params_line.split("}")[0] + "}")
                except:
                    import json as json_mod
                    try:
                        tool_params = json_mod.loads(params_line.split("}")[0] + "}")
                    except:
                        pass
            tool_name = action_line.strip()
            response = response[:action_idx].strip()
            
            # Execute if tool not already executed
            if tool_name and tool_name in agent.brain._tools and not tool_executed:
                result = agent.brain.execute({"tool": tool_name, "params": tool_params}, agent.context)
                if result.get("success"):
                    tool_output = _format_tool_result(tool_name, result)
                tool_executed = True
        except:
            pass

    final_response = response

    # If we executed a tool, show the result
    if tool_executed and tool_output:
        if final_response:
            final_response = f"{final_response}\n\n{tool_output}"
        else:
            final_response = tool_output

    _chat_history.append(("User", user_input))
    _chat_history.append(("RKTM83", final_response))

    agent.memory.observe(f"chat: {user_input[:50]}", {"source": "chat"})

    return final_response


def _format_tool_result(tool_name: str, result: dict) -> str:
    """Format tool execution result nicely."""
    if not result.get("success"):
        return f"❌ Error: {result.get('error', 'unknown')}"
    
    if tool_name == "search_web" and result.get("results"):
        results = result.get("results", [])
        formatted = "**Search Results:**\n"
        for i, r in enumerate(results[:5], 1):
            formatted += f"{i}. **{r.get('title', 'Untitled')}**\n"
            formatted += f"   {r.get('url', '')}\n"
            formatted += f"   {r.get('snippet', '')[:80]}...\n\n"
        return formatted
    
    elif tool_name == "browse_url" and result.get("title"):
        return f"**🌐 Opened:** {result.get('title')}\n\n{result.get('text', '')[:300]}..."
    
    elif tool_name == "list_files" and result.get("items"):
        items = result.get("items", [])[:15]
        files = "\n".join([f"• {i.get('name', '?')}" for i in items])
        return f"**📁 Files ({result.get('count', 0)} total):**\n{files}"
    
    elif tool_name == "search_opportunities" and result.get("results"):
        results = result.get("results", [])[:5]
        formatted = "**💼 Opportunities Found:**\n"
        for r in results:
            formatted += f"• {r.get('title', 'Untitled')}\n"
        return formatted
    
    elif tool_name == "open_app":
        return f"**✅ Opened:** {result.get('app', 'application')}"
    
    elif tool_name == "find_papers" and result.get("papers"):
        papers = result.get("papers", [])[:5]
        formatted = "**🔬 Papers Found:**\n"
        for p in papers:
            formatted += f"• {p.get('title', 'Untitled')}\n"
        return formatted
    
    elif result.get("message"):
        return f"**Result:** {result.get('message')}"
    
    return f"**Done!** {str(result)[:200]}"


# ── BUILD DASHBOARD ─────────────────────────────────────────────────────────
def build_dashboard():
    """Build a production-ready, full-width dashboard."""

    custom_css = """
    .gradio-container { max-width: 100% !important; width: 100% !important; padding: 0 !important; }
    .header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; padding: 20px; text-align: center; margin-bottom: 20px; }
    .header h1 { font-size: 2.5rem; font-weight: 700; margin: 0; background: linear-gradient(90deg, #00d4ff, #7c3aed); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .header p { color: #9ca3af; font-size: 1rem; margin-top: 8px; }
    .status-card { background: #1e293b; border-radius: 12px; padding: 16px; margin: 8px; border: 1px solid #334155; }
    """

    with gr.Blocks(title="RKTM83 - Personal AI Agent", css=custom_css,
                   theme=gr.themes.Soft(primary_hue="blue", secondary_hue="purple")) as app:

        gr.HTML("""
        <div class="header">
            <h1>🤖 RKTM83</h1>
            <p>Personal AI Agent • Running on RTX 3050</p>
        </div>
        """)

        with gr.Tabs():
            with gr.Tab("💬 Chat"):
                gr.ChatInterface(fn=chat_with_agent, examples=[
                    "Hello!", "Search for AI internships", "Go to github.com",
                    "List files in downloads", "Find papers on RAG"
                ])

            with gr.Tab("📊 Status"):
                gr.HTML("""
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; padding: 20px;">
                    <div class="status-card">
                        <h3 style="color: #00d4ff; margin: 0 0 10px 0;">🧠 Memory</h3>
                        <p style="color: #9ca3af; font-size: 2rem; margin: 0;">""" + str(get_agent().memory.stats().get('observations', 0)) + """</p>
                        <p style="color: #6b7280; margin: 0;">Observations</p>
                    </div>
                    <div class="status-card">
                        <h3 style="color: #7c3aed; margin: 0 0 10px 0;">🔧 Tools</h3>
                        <p style="color: #9ca3af; font-size: 2rem; margin: 0;">""" + str(len(get_agent().brain._tools)) + """</p>
                        <p style="color: #6b7280; margin: 0;">Available</p>
                    </div>
                </div>
                """)

            with gr.Tab("🛠️ Tools"):
                gr.HTML("""
                <div style="padding: 20px;">
                    <h2 style="color: #e2e8f0; margin-bottom: 20px;">Available Tools</h2>
                    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px;">
                        <div class="status-card"><h4 style="color: #00d4ff;">🌐 Browser</h4><p style="color: #9ca3af;">search_web, browse_url, fill_form, click_element</p></div>
                        <div class="status-card"><h4 style="color: #7c3aed;">💻 Desktop</h4><p style="color: #9ca3af;">open_app, type_text, hotkey, screenshot</p></div>
                        <div class="status-card"><h4 style="color: #10b981;">📁 Filesystem</h4><p style="color: #9ca3af;">list_files, read_file, move_file</p></div>
                        <div class="status-card"><h4 style="color: #f59e0b;">📧 Email</h4><p style="color: #9ca3af;">send_email, read_inbox, reply_email</p></div>
                        <div class="status-card"><h4 style="color: #ef4444;">🔬 Research</h4><p style="color: #9ca3af;">find_papers, find_professors</p></div>
                        <div class="status-card"><h4 style="color: #3b82f6;">🐙 GitHub</h4><p style="color: #9ca3af;">find_issues, find_trending</p></div>
                    </div>
                </div>
                """)

            with gr.Tab("⚙️ Config"):
                try:
                    with open("config.yaml") as f:
                        config_content = f.read()
                except:
                    config_content = "Error loading config"
                gr.Code(value=config_content, language="yaml", label="config.yaml", lines=30)

    return app


if __name__ == "__main__":
    app = build_dashboard()
    app.launch(share=False, inbrowser=True, server_name="0.0.0.0", server_port=7860)