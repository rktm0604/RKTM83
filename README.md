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
[![Tools](https://img.shields.io/badge/Tools-40+-06b6d4?style=flat-square)]()
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-ff9900?style=flat-square)]()

</div>

---

## 📖 Overview

**RKTM83** is a production-ready autonomous AI agent that runs locally on your machine. Inspired by NVIDIA NemoClaw, it's your personal AI assistant that can:

- 🌐 **Browse websites** (with visible browser window!)
- 🔍 **Search the web** (DuckDuckGo → Google → Bing)
- 📁 **Manage files** (list, read, move, organize)
- 📧 **Handle emails** (read, send, draft)
- 💻 **Execute code** (Python in sandbox)
- 🔬 **Research papers** (Semantic Scholar)
- 🐙 **GitHub integration** (issues, trending)
- 💼 **Job search** (internships, opportunities)
- 💻 **Control desktop** (open apps, type, screenshot)

---

## ✨ Key Features

### 🎯 Smart Tool Execution
- **Forced execution** - Agent actually performs actions, not just talks about them
- **Auto-detection** - Detects action keywords and executes appropriate tools
- **Multiple fallback** - Search engines, tools all have backups

### 🌐 Browser Automation
- **Visible mode** - See the browser window open!
- **Auto-scroll, screenshot, form filling**
- **Multi-step automation workflows**
- **CSS selector content extraction**

### 🧠 Memory System
- **Vector memory** (ChromaDB) - Semantic storage
- **Conversation history** - Remembers context
- **Action logging** - Tracks all activities

### 🔒 Safety Features
- **Policy engine** - Rate limits, approvals
- **Human approval gates** - For sensitive actions
- **Sandboxed code execution** - Safe Python runs

---

## 📂 Project Structure

```
RKTM83/
├── rktm83-dashboard.py     # NEW! Production dashboard (recommended)
├── rktm83-cli/              # NEW! TypeScript CLI wrapper
│   ├── src/index.ts       # CLI commands
│   ├── agent.py           # Python backend
│   └── package.json
├── agent_brain.py         # Core engine
├── run_agent.py           # Entry point
├── config.yaml            # Configuration
├── dashboard.py          # Legacy dashboard
├── skills/                # Skill modules (40+ tools)
│   ├── browser_skill.py  # 10 browser tools
│   ├── desktop_skill.py  # 4 desktop tools
│   ├── filesystem_skill.py
│   ├── email_skill.py
│   ├── executor_skill.py
│   ├── research_skill.py
│   ├── github_skill.py
│   ├── notify_skill.py
│   └── career_skill.py
├── requirements.txt
├── .env                   # Environment variables
└── README.md
```

---

## 🚀 Quick Start

### Option 1: Web Dashboard (RECOMMENDED)
```bash
# Start the dashboard
python rktm83-dashboard.py

# Open in browser
# http://localhost:7860
```

### Option 2: Terminal Chat Mode
```bash
python run_agent.py --chat
# Then type your commands
```

### Option 3: TypeScript CLI (Advanced)
```bash
cd rktm83-cli
npm install
npm run build
npm link
rktm83 --help
```

---

## 🛠️ Available Tools

### 🌐 Browser (10 tools)
| Tool | Description |
|------|-------------|
| `search_web` | Web search with fallback (DDG → Google → Bing) |
| `browse_url` | Open URL in visible browser |
| `screenshot` | Capture page screenshot |
| `scroll_page` | Scroll up/down |
| `scrape_content` | Extract with CSS selectors |
| `fill_form` | Fill forms with templates |
| `click_element` | Click buttons/links |
| `get_page_state` | Debug page info |
| `automation_workflow` | Multi-step automation |

### 💻 Desktop (4 tools)
| Tool | Description |
|------|-------------|
| `open_app` | Open applications |
| `type_text` | Type into active window |
| `hotkey` | Keyboard shortcuts |
| `screenshot` | Screen capture |

### 📁 Filesystem (4 tools)
| Tool | Description |
|------|-------------|
| `list_files` | List directory contents |
| `read_file` | Read file content |
| `move_file` | Move/copy files |
| `organize_folder` | Auto-organize |

### 📧 Email (3 tools)
| Tool | Description |
|------|-------------|
| `send_email` | Send emails (requires approval) |
| `read_inbox` | Read recent emails |
| `reply_email` | Reply to emails |

### 🔬 Research (3 tools)
| Tool | Description |
|------|-------------|
| `find_papers` | Search academic papers |
| `find_professors` | Find researchers |
| `find_research_programs` | Find research programs |

### 🐙 GitHub (3 tools)
| Tool | Description |
|------|-------------|
| `find_issues` | Search GitHub issues |
| `find_trending` | Trending repositories |
| `track_repo` | Track repositories |

### 💼 Career (5 tools)
| Tool | Description |
|------|-------------|
| `search_opportunities` | Job/internship search |
| `score_opportunity` | Rate opportunities |
| `draft_outreach` | Draft outreach messages |
| `send_outreach` | Send messages |
| `send_digest` | Daily digest |

---

## 💬 Test Commands

After starting the dashboard, try these:

| Command | Expected Result |
|---------|------------------|
| `"Hello"` | Conversational response |
| `"go to github.com"` | Browser opens, shows page |
| `"search for AI internships"` | Shows search results |
| `"list files in downloads"` | Lists files |
| `"find papers on RAG"` | Shows academic papers |
| `"open notepad"` | Opens Notepad app |
| `"find trending repos"` | Shows GitHub trending |

---

## ⚙️ Configuration

### config.yaml
```yaml
agent:
  name: "RKTM83"
  version: "2.0"
  memory_path: "./rktm83_memory"

brain:
  provider: "ollama"  # or "gemini"
  ollama_model: "llama3.2:3b"

browser:
  headless: false  # Set to false for visible browser
  visible: true
  timeout: 20

skills:
  - browser
  - desktop
  - filesystem
  - email
  - executor
  - research
  - github
  - notify
  - career
```

### .env
```env
GEMINI_API_KEY=your_key_here
BROWSER_HEADLESS=false  # Make browser visible
GITHUB_TOKEN=your_token_here
RAKBOT_GMAIL_EMAIL=your_email
RAKBOT_GMAIL_PASSWORD=app_password
```

---

## 🔧 Installation

```bash
# 1. Clone
git clone https://github.com/rktm0604/RKTM83.git
cd RKTM83

# 2. Virtual environment
python -m venv .venv
.\.venv\Scripts\activate  # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright
playwright install chromium

# 5. Start Ollama (optional, for local models)
ollama serve
ollama pull llama3.2:3b

# 6. Run!
python rktm83-dashboard.py
```

---

## 🎯 How It Works

1. **User Input** → Dashboard receives command
2. **Auto-Detection** → System detects action keywords (search, go to, open, etc.)
3. **Tool Execution** → Automatically executes appropriate tool
4. **LLM Response** → Gets response from Ollama/Gemini
5. **Result Display** → Shows actual tool results in chat
6. **Memory** → Saves to ChromaDB for context

---

## 🔄 Action → Tool Mapping

The system automatically maps your words to tools:

| You say... | Tool executes... |
|------------|------------------|
| "go to github.com" | `browse_url` |
| "search for jobs" | `search_web` / `search_opportunities` |
| "open notepad" | `open_app` |
| "list files" | `list_files` |
| "find papers on X" | `find_papers` |
| "check email" | `read_inbox` |
| "take screenshot" | `screenshot` |

---

## 🗺️ Roadmap

- [ ] Production API server (FastAPI)
- [ ] Multi-agent orchestration  
- [ ] Voice interface
- [ ] Docker sandbox (like NemoClaw)
- [ ] Mobile companion app
- [ ] Plugin system

---

## 🤝 Contributing

```bash
# Fork → Branch → Implement → Test → PR
git checkout -b feature/my-feature
# ... make changes ...
git commit -m "Add feature"
git push origin main
```

---

## 📝 License

MIT License - See LICENSE file.

---

## 👨‍💻 Built By

**Raktim Banerjee** (raktim0604)
- 2nd Year BTech CSE, NIIT University
- Microsoft Student Ambassador
- Building autonomous AI agents 🚀

---

## ⭐ Show Your Support

If RKTM83 helps you, give it a ⭐ on GitHub!
