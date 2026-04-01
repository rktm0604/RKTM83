<div align="center">

<br>

<img src="https://img.shields.io/badge/RKTM83-AI_Agent-blueviolet?style=for-the-badge&labelColor=0d1117" alt="RKTM83" height="36"/>

<br><br>

# ⚡ RKTM83

### Modular AI Agent with Multi-Skill Execution Framework

<br>

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e?style=flat-square)](LICENSE)
[![Status](https://img.shields.io/badge/status-active-brightgreen?style=flat-square)]()
[![Contributions Welcome](https://img.shields.io/badge/contributions-welcome-f97316?style=flat-square)](CONTRIBUTING.md)
[![Skills](https://img.shields.io/badge/skills-10_modules-8b5cf6?style=flat-square)]()
[![Tools](https://img.shields.io/badge/tools-22+-06b6d4?style=flat-square)]()

<br>

> *An autonomous agent system that thinks, acts, and remembers — powered by LLMs, built with pluggable skills, and designed to run on your own hardware.*

<br>

[Overview](#-overview) · [Features](#-features) · [Skills](#-skills) · [How It Works](#-how-it-works) · [Installation](#-installation) · [Usage](#-usage) · [Contributing](#-contributing)

<br>

---

</div>

<br>

## 📖 Overview

**RKTM83** is a modular AI agent system built on a skill-based execution architecture. Instead of a monolithic AI that tries to do everything, RKTM83 uses **independent skill modules** that the agent dynamically selects and executes based on context.

The agent operates in two modes — **autonomous** (runs continuously, decides its own actions) and **interactive** (chat-based, responds to your commands). Under the hood, a policy engine enforces guardrails, a vector memory store persists everything the agent learns, and an LLM brain decides what to do next.

Built with a **NemoClaw-inspired** three-layer architecture. Runs locally on consumer GPUs.

<br>

## ✨ Features

<table>
<tr>
<td width="50%" valign="top">

#### 🧩 Multi-Skill Architecture
Plug-and-play skill system — enable, disable, or create skills without touching core code.

#### 🧠 Intelligent Decision Engine
LLM-powered brain (Groq / Ollama) that selects the right tool for the right job, every cycle.

#### 💬 Dual Interaction Modes
Autonomous background agent *or* interactive chat — switch with a single flag.

</td>
<td width="50%" valign="top">

#### 🔒 Policy & Safety Layer
Rate limits, human approval gates, execution sandboxing, and configurable guardrails.

#### 📦 Persistent Vector Memory
ChromaDB-backed memory across four collections — observations, entities, actions, and learned patterns.

#### ⚙️ Zero-Code Configuration
Everything controlled through `config.yaml` — identity, personality, skills, policy limits, and more.

</td>
</tr>
</table>

<br>

## 📁 Project Structure

```
RKTM83/
│
├── agent_brain.py              # Core engine — PolicyEngine, AgentMemory, AgentBrain, Agent
├── run_agent.py                # Launcher — autonomous / --chat / --status / --test-skills
├── config.yaml                 # All configuration — the only file you edit
├── dashboard.py                # Gradio web dashboard (4 tabs)
├── supervisor.py               # Process supervisor — auto-restarts on crash
├── resilience.py               # Circuit breaker + tenacity retry wrappers
├── requirements.txt            # Dependencies
├── env.example                 # Environment variable template
│
├── skills/
│   ├── browser_skill.py        # 🌐 Playwright browser automation
│   ├── desktop_skill.py        # 🖥️ Desktop control (pyautogui)
│   ├── filesystem_skill.py     # 📁 File operations
│   ├── email_skill.py          # 📧 Gmail send / read / reply
│   ├── executor_skill.py       # ⚡ LLM-generated code execution
│   ├── research_skill.py       # 🔬 Academic research (Semantic Scholar)
│   ├── github_skill.py         # 🐙 GitHub repos & issues
│   ├── notify_skill.py         # 🔔 Windows toast notifications
│   ├── career_skill.py         # 💼 Opportunity hunting (optional)
│   └── custom_skill.py         # 🧪 Template for your own skills
│
├── tests/
│   ├── test_policy.py          # PolicyEngine unit tests
│   ├── test_memory.py          # AgentMemory unit tests
│   ├── test_executor.py        # Executor safety tests
│   ├── test_filesystem.py      # Filesystem operation tests
│   └── test_career.py          # Career skill logic tests
│
├── docs/
│   └── RKTM83_DOCS.md          # Comprehensive documentation
│
└── .github/
    └── workflows/              # CI/CD pipeline
```

<br>

## 🧩 Skills

> Each skill is a self-contained Python module. Enable or disable any combination in `config.yaml`.

<br>

| | Skill | Tools | What It Does |
|:--|:------|:------|:-------------|
| 🌐 | **Browser** | `browse_url` · `fill_form` · `click_element` · `search_web` | Navigate websites, fill forms, click buttons, search Google |
| 🖥️ | **Desktop** | `open_app` · `type_text` · `screenshot` · `hotkey` | Launch applications, type text, capture screen, keyboard shortcuts |
| 📁 | **Filesystem** | `list_files` · `read_file` · `move_file` · `organize_folder` | Browse, read, rename, and auto-organize files by type |
| 📧 | **Email** | `send_email` · `read_inbox` · `reply_email` | Gmail integration with configurable approval gate |
| ⚡ | **Executor** | `execute_task` · `run_code` | Describe a task in English → LLM writes Python → sandboxed execution |
| 🔬 | **Research** | `search_professors` · `search_papers` · `track_lab` | Semantic Scholar + web search for papers, professors, and labs |
| 🐙 | **GitHub** | `search_repos` · `find_issues` · `track_contribution` | Discover repos, find good-first-issues, track contributions |
| 🔔 | **Notify** | `notify` | Windows desktop toast notifications |
| 💼 | **Career** | `search_opportunities` · `score_opportunity` · `draft_outreach` + 2 | Opportunity discovery with LLM-powered scoring (optional) |
| 🧪 | **Custom** | *Your tools* | Template — build your own skill module |

<details>
<summary><strong>🛠️ Create a custom skill</strong></summary>

<br>

1. Copy `skills/custom_skill.py` → `skills/my_skill.py`
2. Define your tool handler functions
3. Register them in `register(agent)`
4. Add `my` to the `skills:` list in `config.yaml`
5. Restart the agent

</details>

<br>

## 🔄 How It Works

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│              │     │              │     │              │     │              │     │              │
│  User Input  │────▶│  Agent Brain │────▶│    Skill     │────▶│  Execution   │────▶│    Output    │
│  or Timer    │     │  (LLM)       │     │  Selection   │     │  + Memory    │     │  + Learning  │
│              │     │              │     │              │     │              │     │              │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                            │                                         │
                            ▼                                         ▼
                     ┌──────────────┐                          ┌──────────────┐
                     │   Policy     │                          │   ChromaDB   │
                     │   Engine     │                          │   Memory     │
                     │  (Guardrails)│                          │  (Persisted) │
                     └──────────────┘                          └──────────────┘
```

**Each cycle:**

1. **Wake** — Agent reads memory, policy state, and current time
2. **Think** — LLM brain evaluates context and available tools
3. **Decide** — Selects the best tool with parameters and reasoning
4. **Check** — Policy engine enforces rate limits (ALLOW / DENY)
5. **Execute** — Skill handler runs the tool
6. **Remember** — Result stored in ChromaDB vector memory
7. **Repeat** — Sleep, then loop

<br>

## 🚀 Installation

```bash
# Clone the repository
git clone https://github.com/rktm0604/RKTM83.git
cd RKTM83

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser (for browser skill)
playwright install chromium

# Pull the LLM model (if using local Ollama)
ollama pull llama3.2:3b
```

<br>

## ▶️ Usage

```bash
# Interactive chat mode — talk to the agent
python run_agent.py --chat

# Autonomous mode — runs continuously
python run_agent.py

# Limited test run
python run_agent.py --cycles 5 --cycle-sleep 10

# Check agent status
python run_agent.py --status

# Verify all skills load correctly
python run_agent.py --test-skills

# Launch the web dashboard
python dashboard.py

# Run with auto-restart on crash
python supervisor.py
```

<br>

## 🔐 Environment Setup

Copy the template and fill in your credentials:

```bash
cp env.example .env
```

| Variable | Required | Description |
|:---------|:---------|:------------|
| `GROQ_API_KEY` | Recommended | Free API key from [console.groq.com](https://console.groq.com) |
| `RAKBOT_GMAIL_EMAIL` | For email skill | Your Gmail address |
| `RAKBOT_GMAIL_PASSWORD` | For email skill | Gmail [app password](https://myaccount.google.com/apppasswords) (not your real password) |
| `GITHUB_TOKEN` | Optional | GitHub [personal access token](https://github.com/settings/tokens) for higher API limits |

> **Note:** The `.env` file is gitignored. Never commit credentials.

<br>

## ⚙️ Configuration

All behavior is controlled via `config.yaml` — no code changes needed:

```yaml
skills:
  - browser          # enable / disable any skill
  - desktop
  - filesystem
  - email
  - executor
  - research
  - github
  - notify

brain:
  provider: "groq"               # "groq" or "ollama"
  groq_model: "llama-3.1-70b-versatile"
  fallback: true                 # fall back to local Ollama if Groq fails

email:
  require_approval: true         # human must approve before sending

executor:
  allow_dangerous: false         # sandbox restrictions
  timeout: 10                    # max seconds per execution

policy:
  llm_calls_per_day: 150
  search_calls_per_hour: 10
```

<br>

## 🤝 Contributing

Contributions are welcome! Please see the [Contributing Guide](CONTRIBUTING.md) for guidelines.

```
Fork → Branch → Code → Test → Pull Request
```

<br>

---

<div align="center">

<br>

Built by [**Raktim Banerjee**](https://github.com/rktm0604) · BTech CSE, NIIT University

Architecture inspired by [NVIDIA NemoClaw](https://developer.nvidia.com/blog/building-agentic-ai-applications-with-nvidia-nemoclaw/)

<br>

<sub>If this agent becomes sentient, I take full responsibility. 🤖</sub>

<br>

</div>
