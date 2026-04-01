<div align="center">

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://img.shields.io/badge/%E2%9A%A1_RKTM83-Autonomous_AI_Agent-blueviolet?style=for-the-badge&labelColor=0d1117&color=8b5cf6">
  <img src="https://img.shields.io/badge/%E2%9A%A1_RKTM83-Autonomous_AI_Agent-blueviolet?style=for-the-badge&labelColor=f0f0f0&color=7c3aed" alt="RKTM83" height="40"/>
</picture>

<br><br>

### A configurable, skill-based autonomous agent that runs locally on your machine — think of it like a personal JARVIS for automation, research, and productivity.

<br>

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-22c55e?style=flat-square)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=flat-square)]()
[![Skills](https://img.shields.io/badge/Skills-10_Modules-8b5cf6?style=flat-square)]()
[![Tools](https://img.shields.io/badge/Tools-22+-06b6d4?style=flat-square)]()

</div>

---

## 📖 Overview

- **RKTM83** is a local autonomous agent designed to run on your computer.
- It uses a modular skill system, a reasoning LLM (Gemini by default), and persistent vector memory (ChromaDB).
- **Think of it like JARVIS:** provide high-level requests, and the agent plans, selects tools, executes tasks, and remembers results.

---

## ✨ Key features

### Architecture
- **Modular skill-based design** — add or remove skills without touching core code.
- **Runs locally** with cloud LLMs (Gemini) or fully local models (Ollama).
- **Persistent semantic memory** with ChromaDB.

### Safety & control
- **Policy engine** with allow/deny rules and rate limits.
- **Human approval gates** for sensitive actions (e.g., sending email).
- **Sandboxed dynamic Python execution** (timeouts and process isolation).

### Developer experience
- **Zero-code configuration** — tune behavior via `config.yaml`.
- **Pluggable skill template** for fast custom tool creation.
- **Built-in tests** and a Gradio dashboard for inspection and chat.

---

## 🛠️ Capabilities

- **📁 Filesystem**
  - Read, list, move, and organize files.
  - Automate Downloads sorting, backups, and cleanup.
- **🌐 Browser**
  - Headless/headed browsing with Playwright.
  - Search, navigate, fill forms, click elements, and scrape structured data.
- **🐙 GitHub**
  - Search repositories and issues, discover contribution opportunities.
  - Optional Personal Access Token improves API limits and reliability.
- **📧 Email**
  - Read, draft, and prepare emails (Gmail support).
  - Sends only after explicit approval when enabled.
- **🔬 Academic research**
  - Query Semantic Scholar + web search for papers, authors, and labs.
  - Summarize papers and track new publications.
- **⚡ Dynamic Python execution**
  - LLM generates Python code; executor runs it in a sandboxed subprocess.
  - Useful for data-processing tasks, small automation scripts, and prototyping.

---

## 🔄 How it works

**High-level flow:**
`User (or timer) → Gemini (LLM) → Skill selector → Policy check → Skill executes → Memory stores observation → Agent replies`

**Cycle steps:**
1. Wake (user input or timer)
2. Load recent memory and context
3. LLM plans and picks the best skill + parameters
4. Policy engine approves or denies (rate-limits, approval gates)
5. Skill executes, result saved to ChromaDB
6. Agent returns output and waits for next cycle

---

## 📂 Project structure

```text
RKTM83/
├── agent_brain.py       # Core engine (PolicyEngine, AgentMemory, AgentBrain)
├── run_agent.py         # Entry point (interactive & autonomous)
├── config.yaml          # Zero-code configuration
├── requirements.txt     # Python dependencies
├── env.example          # .env template
├── dashboard.py         # Gradio dashboard
├── supervisor.py        # Auto-restart supervisor
├── skills/              # Skill modules
│   ├── browser_skill.py
│   ├── desktop_skill.py
│   ├── filesystem_skill.py
│   ├── email_skill.py
│   ├── executor_skill.py
│   ├── research_skill.py
│   ├── github_skill.py
│   └── custom_skill.py
├── tests/               # Unit tests
└── docs/                # Extended documentation
```

---

## 🚀 Installation

**1. Clone the repository**
```bash
git clone https://github.com/rktm0604/RKTM83.git
cd RKTM83
```

**2. (Recommended) Create & activate a virtual environment**
```bash
python -m venv .venv
# macOS / Linux
source .venv/bin/activate    
# Windows (PowerShell)
.\.venv\Scripts\activate     
```

**3. Install dependencies**
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**4. Install Playwright browsers (for browser skill)**
```bash
playwright install chromium
```

**5. Optional: Pull a local Ollama model for offline operation**
```bash
ollama pull llama3.2:3b
```

---

## ⚙️ Setup — .env & GEMINI_API_KEY

Copy the example environment file:
```bash
cp env.example .env
```

**Important variables:**
- `GEMINI_API_KEY` — API key for Google Gemini (recommended). If you want fully local operation, switch `brain.provider` to `ollama` in `config.yaml` and install local models.
- `GITHUB_TOKEN` — Optional: Personal Access Token for higher GitHub API limits.
- `RAKBOT_GMAIL_EMAIL` / `RAKBOT_GMAIL_PASSWORD` — For Gmail: use an app-specific password and secure storage.

> **Security Note:** `.env` is gitignored. Never commit secrets.

---

## 💻 Usage

**Interactive Web Chat:**
```bash
python dashboard.py
```
*(Opens a local Gradio dashboard at http://localhost:7860)*

**Interactive Terminal (chat) mode:**
```bash
python run_agent.py --chat
```

**Autonomous (continuous background cycles):**
```bash
python run_agent.py
```

**Common flags:**
- `--cycles N` (run N cycles then exit for testing)
- `--cycle-sleep S` (seconds between cycles)
- `--status` (show agent status)
- `--test-skills` (validate configured skills)

---

## 📝 Example commands (real use cases)

- **Organize downloads:**
  *"Organize my Downloads folder by file type and move images to Pictures."*
- **Research summary:**
  *"Find recent papers on retrieval-augmented generation and summarize the top 5."*
- **GitHub discovery:**
  *"Find good-first-issues for projects about semantic search."*
- **Email draft (approval required):**
  *"Draft an outreach email to Dr. Smith about collaboration on X."*
- **Code execution:**
  *"Generate a Python script that reads data.csv and plots a histogram, then run it."*

---

## 🗺️ Roadmap

Planned improvements:
- Docker-based executor sandbox for extra isolation
- Voice interface and speech-to-text
- Multi-agent orchestration and task delegation
- Mobile companion app and improved web dashboard
- Additional skills: calendar, Slack/Teams, richer notifications

---

## 🤝 Contributing

**Workflow:** `Fork → branch → implement → test → open PR`
- Please add tests for new features and run existing tests.
- See `CONTRIBUTING.md` for coding conventions and PR expectations.

---

Built and maintained by **[Raktim Banerjee (rktm0604)](https://github.com/rktm0604)**
