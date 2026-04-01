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
        state_path="policy_state.json",
        config=CONFIG,
        agent_state_path="agent_state.json",
    )
    _AGENT.context["config"] = CONFIG
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
        policy = PolicyEngine(overrides, state_path="policy_state.json")
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


# ── TAB: Chat / Command ──────────────────────────────────────────────────────

def chat_with_agent(message, history):
    """Gradio ChatInterface handler to execute an agent cycle."""
    try:
        agent = get_agent()
    except Exception as e:
        return f"❌ Failed to load agent: {str(e)}"
        
    user_input = message.strip()
    if not user_input:
        return "Please enter a command."

    # Build context
    agent.context.update({
        "time": datetime.datetime.now().isoformat(),
        "memory": agent.memory.stats(),
        "policy": agent.policy.status(),
        "user_request": user_input,
    })

    tools_str = "\n".join(f"- {n}: {i['description']}" for n, i in agent.brain._tools.items())
    prompt = f"{agent.brain.profile}\n\nUSER REQUEST: {user_input}\n\nTOOLS:\n{tools_str}\n\nPick the BEST tool for this request.\nReply ONLY in JSON: {{\"tool\": \"name\", \"params\": {{}}, \"reasoning\": \"one line\"}}"

    response = agent.brain._infer(prompt)

    # Parse JSON
    decision = None
    try:
        clean = re.sub(r'```(?:json)?', '', response).strip()
        m = re.search(r'\{.*\}', clean, re.DOTALL)
        if m:
            d = json.loads(m.group())
            if d.get("tool") in agent.brain._tools:
                decision = d
    except Exception:
        pass

    if not decision:
        return f"❌ **Agent couldn't decide.** Raw LLM response:\n```\n{response[:300]}\n```"

    tool = decision.get("tool")
    params = decision.get("params", {})
    reasoning = decision.get("reasoning", "")

    # Output log
    out = f"**💭 Reasoning:** {reasoning}\n\n**🛠️ Selected Tool:** `{tool}`\n\n```json\n{json.dumps(params, indent=2)}\n```\n\n"

    # Execute
    result = agent.brain.execute(decision, agent.context)

    # Display result
    out += "### Result\n"
    if result.get("success"):
        out += "✅ **Success**\n\n"
        for k, v in result.items():
            if k == "success":
                continue
            v_str = str(v)
            if len(v_str) > 500:
                v_str = v_str[:500] + "..."
            out += f"- **{k}**: {v_str}\n"
    else:
        out += f"❌ **Failed**: {result.get('error', 'unknown error')}"

    # Record Memory
    agent.memory.observe(
        f"chat: {user_input[:60]} → {tool}",
        {"tool": tool, "source": "chat"}
    )
    agent.context["last_action"] = tool

    return out


# ── BUILD DASHBOARD ─────────────────────────────────────────────────────────

def build_dashboard():
    """Build the Gradio dashboard."""

    with gr.Blocks(
        title="RKTM83 Dashboard",
        theme=gr.themes.Soft(
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
                    examples=["List files in my downloads folder", "What time is it?", "Check my recent memory for keywords"],
                    type="messages"
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
