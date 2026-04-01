# RKTM83 — Personal Autonomous Agent

[![Tests](https://github.com/rktm0604/RKTM83/actions/workflows/test.yml/badge.svg)](https://github.com/rktm0604/RKTM83/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Groq](https://img.shields.io/badge/Brain-Groq%20LLaMA%203.1%2070B-00A67E?style=for-the-badge)](https://groq.com)
[![Ollama](https://img.shields.io/badge/Fallback-Ollama-111111?style=for-the-badge)](https://ollama.ai)
[![ChromaDB](https://img.shields.io/badge/Memory-ChromaDB-4285F4?style=for-the-badge)](https://www.trychroma.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![NemoClaw](https://img.shields.io/badge/Architecture-NemoClaw--inspired-76B900?style=for-the-badge)](https://github.com/NVIDIA/NemoClaw)

> *"Running on an RTX 3050 and pure ambition."*

A local-first personal autonomous agent that runs on your machine, makes decisions every cycle, executes tools, remembers everything, and recovers from failure without starting from zero.

Inspired by [NVIDIA NemoClaw](https://github.com/NVIDIA/NemoClaw) — three-layer architecture: policy enforcement, vector memory, LLM decision engine.

[Quick Start](#quick-start) · [Capabilities](#capabilities) · [Architecture](#architecture) · [Add a Skill](#add-a-skill) · [Configuration](#configuration)

---

## Why RKTM83

Most AI assistants are cloud-first, expensive, and forget everything between sessions. RKTM83 runs entirely on your laptop:

- **Groq-first** with Ollama fallback — fast cloud inference or fully local
- **Persistent vector memory** — ChromaDB remembers everything across restarts
- **Skill-based** — add capabilities by dropping a `.py` file in `skills/`
- **Policy-governed** — rate limits, permission gates, no runaway API calls
- **Chat + autonomous modes** — talk to it or let it run in the background
- **Crash recovery** — supervisor process restarts it, state is saved

---

## Quick Start

```bash
git clone https://github.com/rktm0604/RKTM83.git
cd RKTM83
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add your credentials:

```bash
cp .env.example .env
# Add your GROQ_API_KEY at minimum
```

Run:

```bash
# Autonomous mode — runs forever, decides its own actions
python run_agent.py

# Faster cycles for testing
python run_agent.py --cycle-sleep 15

# Run for a fixed number of cycles
python run_agent.py --cycles 5

# Check status without running
python run_agent.py --status

# Keep alive as a service (restarts on crash)
python supervisor.py
```

Open the dashboard at **http://localhost:7860**:

```bash
python dashboard.py
```

---

## Capabilities

| Skill | What It Does | Status |
|---|---|---|
| `career` | Search Internshala + web for AI/ML opportunities, score and draft outreach | ✅ Working |
| `research` | Find papers on arXiv, professors at IITs/IISc, summer research programs | ✅ Working |
| `github` | Find beginner issues, track repos, discover trending AI/ML projects | ✅ Working |
| `filesystem` | List, read, move, and organize local files | ✅ Working |
| `executor` | Generate and run Python in a subprocess sandbox | ✅ Working |
| `email` | Read inbox, draft and send replies via Gmail | ⚙️ Requires credentials |
| `browser` | Open pages, search, click, fill forms via Playwright | ⚙️ Requires Playwright install |
| `desktop` | Open apps, type text, take screenshots via PyAutoGUI | ⚙️ Windows only |
| `notify` | Windows toast notifications on completion/error | ⚙️ Windows only |
| `custom` | Blank template — build your own | 📄 Template |

Enable any skill in `config.yaml`:

```yaml
skills:
  - career
  - research
  - github
  # - filesystem
  # - executor
```

---

## Architecture

```
run_agent.py
└── Agent
    ├── PolicyEngine     ← NemoClaw-inspired gateway (ALLOW/ROUTE/DENY)
    │   ├── Rate limits  (outreach, LLM calls, searches)
    │   └── Permission gates (ask before running restricted tools)
    ├── AgentMemory      ← ChromaDB, 4 collections, persists across runs
    │   ├── observations (everything perceived)
    │   ├── entities     (people, companies, repos)
    │   ├── actions      (full audit trail)
    │   └── learned      (patterns from feedback)
    ├── AgentBrain       ← LLM decision engine (domain-agnostic)
    │   ├── Groq primary (llama-3.1-70b)
    │   └── Ollama fallback (llama3.2:3b)
    └── Skills           ← pluggable Python modules
        └── Each skill registers tools with the brain
```

Every cycle:
1. Agent reads memory + policy state + pending user commands
2. LLM decides the best next action
3. PolicyEngine checks rate limits and permissions
4. Tool executes, result stored in ChromaDB
5. `agent_log.json` updated for dashboard
6. Sleep, repeat

---

## Add a Skill

```bash
cp skills/custom_skill.py skills/myskill_skill.py
```

Minimal skill structure:

```python
SKILL_NAME = "myskill"

def _my_tool(params, context, brain):
    result = brain._infer("Do something useful")
    brain.memory.observe("it happened", {"source": "myskill"})
    return {"success": True, "data": result}

def register(agent):
    agent.brain.register_tool(
        "my_tool",
        "Description the LLM reads to decide when to use this",
        _my_tool
    )
```

Enable in `config.yaml` and restart. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide.

---

## Configuration

Everything is in `config.yaml` — no code changes needed:

```yaml
agent:
  name: "RKTM83"
  cycle_sleep: 30        # seconds between cycles

brain:
  provider: "groq"       # or "ollama" for fully local
  groq_model: "llama-3.1-70b-versatile"
  ollama_model: "llama3.2:3b"

skills:
  - career
  - research
  - github

policy:
  outreach_per_day: 5
  llm_calls_per_day: 150
  search_calls_per_hour: 10
```

---

## Project Structure

```
RKTM83/
├── agent_brain.py          ← core engine (never needs editing)
├── run_agent.py            ← launcher
├── dashboard.py            ← Gradio web UI
├── supervisor.py           ← restart-on-crash service
├── resilience.py           ← retry + circuit breaker helpers
├── config.yaml             ← all configuration
├── requirements.txt        ← dependencies
├── .env.example            ← credential template
├── CONTRIBUTING.md         ← how to add skills
├── skills/
│   ├── career_skill.py     ← internship hunting
│   ├── research_skill.py   ← papers, professors, programs
│   ├── github_skill.py     ← repos, issues, trending
│   ├── filesystem_skill.py ← local file management
│   ├── executor_skill.py   ← Python subprocess sandbox
│   ├── email_skill.py      ← Gmail read/send
│   ├── browser_skill.py    ← Playwright web automation
│   ├── desktop_skill.py    ← PyAutoGUI desktop control
│   ├── notify_skill.py     ← Windows toast notifications
│   └── custom_skill.py     ← blank template
├── tests/
│   ├── test_policy.py
│   ├── test_memory.py
│   └── test_career.py
└── docs/
    └── RKTM83_DOCS.md
```

---

## Open Source Contributions

RKTM83 has contributed to the NemoClaw ecosystem:

- **[PR #1047](https://github.com/NVIDIA/NemoClaw/pull/1047)** on NVIDIA/NemoClaw — Ollama local inference policy preset
- **Recipe** on [awesome-nemoclaw](https://github.com/VoltAgent/awesome-nemoclaw) — personal agent pattern

---

## Roadmap

- [x] Groq-first inference with Ollama fallback
- [x] Persistent ChromaDB vector memory
- [x] Skill-based architecture
- [x] Web dashboard with chat interface
- [x] Permission gate system
- [x] Crash recovery and supervisor
- [x] GitHub Actions CI
- [ ] HuggingFace Spaces deployment
- [ ] AMD ROCm inference backend
- [ ] NemoClaw sandbox integration
- [ ] Scheduled recurring jobs
- [ ] Multi-agent collaboration

---

Built by [Raktim Banerjee](https://github.com/rktm0604) — BTech CSE, NIIT University 2024-28 · Microsoft Student Ambassador

MIT License
