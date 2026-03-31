<div align="center">

# 🤖 RKTM83

### Personal Autonomous Agent

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Ollama](https://img.shields.io/badge/Ollama-LLaMA_3.2-FF6F00?style=for-the-badge&logo=meta&logoColor=white)](https://ollama.ai)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector_Memory-4285F4?style=for-the-badge&logo=google-cloud&logoColor=white)](https://www.trychroma.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

<br>

*"Running on an RTX 3050 and pure ambition."*

**A NemoClaw-inspired autonomous agent with full computer-use capabilities.**<br>
**It can control your browser, desktop, filesystem, emails — and think for itself.**

<br>

[Quick Start](#-quick-start) · [Skills](#-skills) · [Chat Mode](#-two-modes) · [Architecture](#-architecture) · [Config](#-configuration)

---

</div>

<br>

## ✨ What Is This

RKTM83 is an **autonomous agent** that runs on your laptop. You start it once — it runs forever.

It is **not a chatbot**. It doesn't wait for you to ask it something.
It thinks every cycle, picks an action, executes it, remembers the result, and repeats.

But it *can* also talk to you when you want (`--chat` mode).

> **9 pluggable skills** · **22 tools** · **Persistent vector memory** · **Policy guardrails**

<br>

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      run_agent.py                        │
│            --chat (interactive) │ autonomous              │
├─────────────────────────────────────────────────────────┤
│                                                          │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│   │ PolicyEngine │  │ AgentMemory  │  │  AgentBrain  │  │
│   │              │  │              │  │              │  │
│   │ Rate limits  │  │  ChromaDB    │  │  LLaMA 3.2   │  │
│   │ Guardrails   │  │  4 vector    │  │  via Ollama  │  │
│   │ ALLOW / DENY │  │  collections │  │  on your GPU │  │
│   └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                          │
├─────────────────────────────────────────────────────────┤
│                    Skills (Pluggable)                     │
│                                                          │
│  🌐 browser  │ 🖥 desktop  │ 📁 filesystem │ 📧 email   │
│  ⚡ executor │ 🔬 research │ 🐙 github     │ 💼 career  │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

**Three layers** inspired by [NVIDIA NemoClaw](https://developer.nvidia.com/blog/building-agentic-ai-applications-with-nvidia-nemoclaw/):

| Layer | What It Does |
|:------|:-------------|
| **PolicyEngine** | Guardrails — rate limits, ALLOW/ROUTE/DENY gating on every action |
| **AgentMemory** | ChromaDB vector store — observations, entities, actions, learned patterns |
| **AgentBrain** | LLM decision engine — picks the best tool, formats params, explains reasoning |

<br>

## 🚀 Quick Start

```bash
# Clone
git clone https://github.com/rktm0604/RKTM83.git
cd RKTM83

# Install dependencies
pip install -r requirements.txt
playwright install chromium        # for browser skill

# Pull the LLM model
ollama pull llama3.2:3b

# 💬 Chat mode — talk to the agent
python run_agent.py --chat

# 🔄 Autonomous mode — runs forever
python run_agent.py

# 🧪 Other commands
python run_agent.py --cycles 5 --cycle-sleep 10    # test run
python run_agent.py --status                        # check status
python run_agent.py --test-skills                   # verify skills
python dashboard.py                                 # web dashboard
```

<br>

## 💬 Two Modes

<table>
<tr>
<td width="50%">

### 🗣 Chat Mode
```
python run_agent.py --chat
```

You type → agent picks tool → executes → responds

```
[RKTM83] > open notepad
→ Tool: open_app
→ Why:  User wants to launch Notepad
✓ Success
  app: notepad

[RKTM83] > list files on my desktop  
→ Tool: list_files
✓ Success
  count: 23

[RKTM83] > search google for AI agents
→ Tool: search_web
✓ Success
  results: [...]
```

</td>
<td width="50%">

### 🔄 Autonomous Mode
```
python run_agent.py
```

Runs forever. Zero input needed.

```
Cycle 1: search_papers
  → Found 12 papers

Cycle 2: find_issues
  → Found 5 good-first-issues

Cycle 3: search_repos
  → Found 8 repos to contribute to

Cycle 4: wait
  → Nothing urgent, sleeping...
```

</td>
</tr>
</table>

<br>

## 🧩 Skills

> **9 skills · 22 tools · Fully pluggable** — enable/disable any combination in `config.yaml`

| Skill | Tools | Description |
|:------|:------|:------------|
| 🌐 **browser** | `browse_url` · `fill_form` · `click_element` · `search_web` | Playwright — browse any site, fill forms, click buttons, Google search |
| 🖥 **desktop** | `open_app` · `type_text` · `screenshot` · `hotkey` | Open apps, type text, screenshots, keyboard shortcuts |
| 📁 **filesystem** | `list_files` · `read_file` · `move_file` · `organize_folder` | Read files, move/rename, auto-sort Downloads by type |
| 📧 **email** | `send_email` · `read_inbox` · `reply_email` | Gmail send/read/reply with configurable approval |
| ⚡ **executor** | `execute_task` · `run_code` | Describe any task in English → LLM writes Python → runs it |
| 🔬 **research** | `search_professors` · `search_papers` · `track_lab` | Semantic Scholar + web search for papers and labs |
| 🐙 **github** | `search_repos` · `find_issues` · `track_contribution` | Find repos, good-first-issues, track contributions |
| 💼 **career** | `search_opportunities` · `score_opportunity` · `draft_outreach` + 2 more | Internship hunting with LLM scoring (optional) |
| 🔧 **custom** | *Your tools here* | Template — copy, rename, add your own tools |

<details>
<summary><b>📝 How to add your own skill</b></summary>

<br>

1. Copy `skills/custom_skill.py` → `skills/yourname_skill.py`
2. Add tool handler functions
3. Register tools in the `register(agent)` function
4. Add `yourname` to `config.yaml` skills list
5. Restart the agent

</details>

<br>

## ⚙️ Configuration

Everything is controlled via `config.yaml` — **no code changes needed**:

```yaml
agent:
  name: "RKTM83"
  cycle_sleep: 30

identity:
  name: "Your Name"
  skills: "Python, AI, ML"
  goals:
    - "Your goal here"

skills:                         # comment out to disable any
  - browser
  - desktop
  - filesystem
  - email
  - executor
  - research
  - github

email:
  require_approval: true        # false = fully autonomous

executor:
  allow_dangerous: false        # true = allows os.system, subprocess
  timeout: 10

policy:
  llm_calls_per_day: 150
  search_calls_per_hour: 10
```

<br>

## 📂 Project Structure

```
RKTM83/
├── 🧠 agent_brain.py           ← Core engine (PolicyEngine, AgentMemory, AgentBrain, Agent)
├── 🚀 run_agent.py             ← Launcher (--chat / autonomous / --status / --test-skills)
├── ⚙️ config.yaml              ← Configuration (the only file you edit)
├── 📊 dashboard.py             ← Gradio web dashboard
├── 📦 requirements.txt         ← Dependencies
│
├── 🧩 skills/
│   ├── browser_skill.py        ← Playwright browser automation
│   ├── desktop_skill.py        ← pyautogui desktop control
│   ├── filesystem_skill.py     ← File operations
│   ├── email_skill.py          ← Gmail send/read/reply
│   ├── executor_skill.py       ← LLM code execution
│   ├── research_skill.py       ← Academic research
│   ├── github_skill.py         ← Open source
│   ├── career_skill.py         ← Internship hunting (optional)
│   └── custom_skill.py         ← Your template
│
├── 🧪 tests/
│   ├── test_policy.py          ← PolicyEngine tests (14 tests)
│   └── test_memory.py          ← AgentMemory tests (21 tests)
│
└── 📚 docs/
    └── RKTM83_DOCS.md          ← Full documentation
```

<br>

## 🔒 Safety

| Layer | Protection |
|:------|:-----------|
| **Policy Engine** | Rate limits on all actions (outreach, LLM calls, searches) |
| **Human Approval** | Email and outreach require `y/n` confirmation by default |
| **Executor Sandbox** | Dangerous patterns blocked (`os.system`, `subprocess`, `eval`, etc.) |
| **Memory Isolation** | Each agent instance has its own ChromaDB database |
| **Config Control** | All limits configurable via YAML — no code needed |

<br>

## 🛠 Requirements

| Component | Requirement |
|:----------|:------------|
| **Python** | 3.10+ |
| **LLM** | [Ollama](https://ollama.ai/) with `llama3.2:3b` |
| **GPU** | NVIDIA (tested on RTX 3050) |
| **Browser** | Playwright Chromium (for browser skill) |

<br>

## 🗺 Roadmap

- [x] Core engine — PolicyEngine, AgentMemory, AgentBrain
- [x] 9 pluggable skills with 22 tools
- [x] Interactive chat mode
- [x] Gradio web dashboard
- [x] 35 unit tests
- [ ] Groq/GPT-4o API support (smarter brain)
- [ ] Windows service auto-restart
- [ ] Desktop notifications
- [ ] GitHub Actions CI/CD
- [ ] Subprocess sandbox for executor

<br>

---

<div align="center">

**Built by [Raktim Banerjee](https://github.com/rktm0604)** · BTech CSE, NIIT University (2024-28)

Architecture inspired by [NVIDIA NemoClaw](https://developer.nvidia.com/blog/building-agentic-ai-applications-with-nvidia-nemoclaw/)

<br>

*If this agent becomes sentient, I take full responsibility.* 🤖

</div>
