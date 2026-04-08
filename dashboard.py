"""
dashboard.py — RKTM83 Gradio Dashboard
A simple web UI to monitor the agent's memory, policy, and recent actions.

Run:
  python dashboard.py

Opens at http://localhost:7860
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
import re

_AGENT = None


def get_agent():
    """Initialize or return the global Agent instance."""
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


def load_config():
    """Load config.yaml."""
    try:
        with open("config.yaml") as f:
            return yaml.safe_load(f)
    except Exception as e:
        return {"error": str(e)}


def load_policy():
    """Load current policy state."""
    try:
        cfg = load_config()
        overrides = {k: v for k, v in cfg.get("policy", {}).items()
                     if k != "search_interval_hours"}
        policy = PolicyEngine(overrides)
        return policy.status()
    except Exception as e:
        return {"error": str(e)}


def load_memory():
    """Load memory instance."""
    cfg = load_config()
    path = cfg.get("agent", {}).get("memory_path", "./rktm83_memory")
    return AgentMemory(path)


# ── TAB: Status ──────────────────────────────────────────────────────────────

def get_status():
    """Get full agent status as formatted text."""
    try:
        cfg = load_config()
        mem = load_memory()
        policy = load_policy()

        agent_name = cfg.get("agent", {}).get("name", "RKTM83")
        catchphrase = cfg.get("personality", {}).get("catchphrase", "")

        lines = [
            f"# {agent_name}",
            f'> "{catchphrase}"',
            "",
            "## Memory Stats",
            f"| Collection | Count |",
            f"|---|---|",
        ]
        for k, v in mem.stats().items():
            lines.append(f"| {k} | {v} |")

        lines += [
            "",
            "## Policy Status",
            f"| Metric | Value |",
            f"|---|---|",
        ]
        for k, v in policy.items():
            lines.append(f"| {k} | {v} |")

        lines += [
            "",
            f"*Last checked: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
        ]

        return "\n".join(lines)
    except Exception as e:
        return f"Error loading status: {e}"


# ── TAB: Memory Search ──────────────────────────────────────────────────────

def search_memory(collection: str, query: str, n: int):
    """Search agent memory by collection and query."""
    try:
        mem = load_memory()
        n = max(1, min(int(n), 20))
        results = mem.search(collection, query, n=n)
        if not results:
            return "No results found."

        lines = ["| # | Key | Value |", "|---|---|---|"]
        for i, r in enumerate(results, 1):
            for k, v in r.items():
                lines.append(f"| {i} | {k} | {str(v)[:80]} |")
            lines.append("|---|---|---|")

        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


# ── TAB: Recent Actions ─────────────────────────────────────────────────────

def get_recent_actions():
    """Get last 20 actions from memory."""
    try:
        mem = load_memory()
        results = mem.search("actions", "tool action", n=20)
        if not results:
            return "No actions recorded yet."

        lines = ["| # | Tool | Outcome | Time |", "|---|---|---|---|"]
        for i, r in enumerate(results, 1):
            tool = r.get("tool", "?")
            outcome = r.get("outcome", "?")
            ts = r.get("ts", "?")
            if isinstance(ts, str) and len(ts) > 16:
                ts = ts[:16]
            lines.append(f"| {i} | {tool} | {outcome} | {ts} |")

        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


# ── TAB: Config ──────────────────────────────────────────────────────────────

def get_config():
    """Display current config.yaml contents."""
    try:
        with open("config.yaml") as f:
            return f.read()
    except Exception as e:
        return f"Error reading config: {e}"


# ── CHAT SESSION STATE ─────────────────────────────────────────────────────

_chat_history = []  # Session memory for conversation context
_max_history = 10   # Keep last 10 exchanges


# ── TAB: Chat / Command ─────────────────────────────────────────────────────

def chat_with_agent(message, history):
    """ChatGPT-style chat interface - natural conversation."""
    global _chat_history

    try:
        agent = get_agent()
    except Exception as e:
        return f"Sorry, I encountered an error: {str(e)}"

    user_input = message.strip()
    if not user_input:
        return "Please type a message."

    # Build conversation context from history
    conversation = ""
    for role, msg in _chat_history[-_max_history:]:
        conversation += f"{role}: {msg}\n"

    # Current context
    current_time = datetime.datetime.now().strftime("%I:%M %p")
    context_str = f"""CURRENT TIME: {current_time}
MEMORY: {agent.memory.stats()}
TOOLS AVAILABLE: {', '.join(agent.brain._tools.keys())}"""

    # Smart prompt - let LLM decide what to do
    prompt = f"""{agent.brain.profile}

CONVERSATION SO FAR:
{conversation}

CURRENT CONTEXT:
{context_str}

USER'S LATEST MESSAGE: "{user_input}"

INSTRUCTIONS:
1. If the user is just chatting/greeting/asking questions - respond naturally and conversationally like a helpful assistant
2. If the user is asking you to DO something (search, list files, send email, open apps, etc.) - use a tool
3. If you use a tool, include it at the END of your response in this exact format:
   ACTION: open_app
   PARAMS: {{"app": "Microsoft Word", "file_path": "C:/Users/Raktim/Downloads/project proposal.docx"}}
4. Keep your main response conversational and helpful
5. After your response, include ACTION and PARAMS if you used a tool
6. Do NOT include any code blocks around the action/params

Remember: You are RKTM83, a personal AI assistant. Be friendly, helpful, and natural!"""

    # Get LLM response
    response = agent.brain._infer(prompt)

    # Debug: print raw response
    print(f"[DEBUG] Raw response: {response[:500]}")

    # Check if LLM wants to use a tool - more robust parsing
    response_lower = response.lower()
    tool_name = None
    tool_params = {}
    
    try:
        action_idx = response_lower.find("action:")
        params_idx = response_lower.find("params:")
        if action_idx != -1 and params_idx != -1 and params_idx > action_idx:
            action_line = response[action_idx + 8:params_idx].strip()
            params_line = response[params_idx + 8:].strip()
            
            # Try to parse as JSON
            if params_line.strip().startswith("{"):
                import ast
                try:
                    tool_params = ast.literal_eval(params_line.split("}")[0] + "}")
                except:
                    import json
                    try:
                        tool_params = json.loads(params_line.split("}")[0] + "}")
                    except:
                        pass
            tool_name = action_line.strip()
            
            # Remove the action/params from the displayed response
            response = response[:action_idx].strip()
    except Exception as e:
        print(f"Tool parse error: {e}")

    final_response = response

    # If tool requested, execute it
    if tool_name and tool_name in agent.brain._tools:
        # Clean up response to just be the conversational part
        final_response = response.split("TOOL:")[0].strip()
        
        # Execute tool and check actual result
        try:
            result = agent.brain.execute({"tool": tool_name, "params": tool_params}, agent.context)

            # Add tool result to response - be honest about success/failure
            if result.get("success"):
                # Extract relevant info and add naturally
                if tool_name == "list_files":
                    if result.get("count", 0) > 0:
                        items = result.get("items", [])[:5]
                        files = ", ".join([i.get("name", "?") for i in items])
                        final_response += f"\n\nI found {result.get('count', 0)} items. Here's what's there: {files}"
                    else:
                        final_response += "\n\nThe folder appears to be empty."
                elif tool_name == "search_web":
                    if result.get("results"):
                        # Format search results nicely
                        results = result.get("results", [])
                        if results:
                            formatted = "\n\n**Search Results:**\n"
                            for i, r in enumerate(results[:5], 1):
                                title = r.get("title", "Untitled")[:60]
                                url = r.get("url", "")
                                snippet = r.get("snippet", "")[:100]
                                source = r.get("source", "")
                                formatted += f"{i}. **{title}**\n   {snippet}... \n   {url} ({source})\n"
                            final_response += formatted
                        else:
                            final_response += "\n\nI didn't find any results for that search."
                    else:
                        final_response += "\n\nI didn't find any results for that search."
                elif tool_name == "open_app":
                    app = tool_params.get("app", "the app")
                    file_info = tool_params.get("file_path", "")
                    if file_info:
                        final_response = f"Opened {file_info} with {app}!"
                    else:
                        final_response = f"Launched {app} for you!"
                elif tool_name == "browse_url":
                    if result.get("title"):
                        title = result.get("title", "Untitled")
                        text = result.get("text", "")[:500]
                        url = result.get("url", "")
                        final_response += f"\n\n**Page: {title}**\n{text}...\n\n[View full page]({url})"
                    else:
                        final_response += "\n\nI couldn't access that page."
                else:
                    # Generic success handling
                    if result.get("message"):
                        final_response += f"\n\n{result.get('message')}"
            else:
                # Tool failed - be honest!
                error_msg = result.get("error", "unknown error")
                final_response += f"\n\n(Actually, that didn't work: {error_msg})"
        except Exception as e:
            final_response += f"\n\n(Tried to run that but got an error: {str(e)})"

    # Update conversation history
    _chat_history.append(("User", user_input))
    _chat_history.append(("RKTM83", final_response))

    # Record in agent memory
    agent.memory.observe(
        f"chat: {user_input[:50]}",
        {"source": "chat", "response": final_response[:100]}
    )

    return final_response


# ── BUILD DASHBOARD ─────────────────────────────────────────────────────────

def build_dashboard():
    """Build the Gradio dashboard."""

    with gr.Blocks(
        title="RKTM83 Dashboard",
        theme=gr.themes.Default(
            primary_hue="purple",
            secondary_hue="blue",
        ),
        css="""
        .gradio-container { max-width: 900px !important; }
        h1 { text-align: center; }
        """
    ) as app:

        gr.Markdown("# 🤖 RKTM83 — Agent Dashboard")
        gr.Markdown("*Personal Autonomous Agent · NemoClaw-inspired*")

        with gr.Tabs():

            # ── Chat Tab
            with gr.Tab("💬 Command Center"):
                gr.ChatInterface(
                    fn=chat_with_agent,
                    examples=["Hello!", "What time is it?", "List files in my downloads"]
                )

            # ── Status Tab
            with gr.Tab("📊 Status"):
                status_output = gr.Markdown(value=get_status())
                gr.Button("🔄 Refresh").click(fn=get_status, outputs=status_output)

            # ── Memory Search Tab
            with gr.Tab("🧠 Memory"):
                with gr.Row():
                    collection = gr.Dropdown(
                        choices=["observations", "entities", "actions", "learned"],
                        value="observations",
                        label="Collection"
                    )
                    query = gr.Textbox(
                        value="opportunity internship",
                        label="Search Query"
                    )
                    n_results = gr.Slider(
                        minimum=1, maximum=20, value=5, step=1,
                        label="Results"
                    )
                memory_output = gr.Markdown()
                gr.Button("🔍 Search").click(
                    fn=search_memory,
                    inputs=[collection, query, n_results],
                    outputs=memory_output
                )

            # ── Recent Actions Tab
            with gr.Tab("📋 Actions"):
                actions_output = gr.Markdown(value=get_recent_actions())
                gr.Button("🔄 Refresh").click(
                    fn=get_recent_actions,
                    outputs=actions_output
                )

            # ── Config Tab
            with gr.Tab("⚙️ Config"):
                config_output = gr.Code(
                    value=get_config(),
                    language="yaml",
                    label="config.yaml"
                )
                gr.Button("🔄 Reload").click(fn=get_config, outputs=config_output)

    return app


if __name__ == "__main__":
    app = build_dashboard()
    app.launch(share=False, inbrowser=True)