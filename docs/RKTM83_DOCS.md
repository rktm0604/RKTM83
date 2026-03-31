# RKTM83 — Personal Autonomous Agent
## Complete Documentation

> "Running on an RTX 3050 and pure ambition."

---

## What Is RKTM83

RKTM83 is a personal autonomous agent that runs on your laptop.
You start it once. It runs forever. It decides what to do on its own.

It is NOT a chatbot. It does NOT wait for you to ask it something.
It thinks every N seconds, picks an action, executes it, remembers
the result, and repeats.

Built on the same architecture as NVIDIA NemoClaw — three layers:
policy enforcement, vector memory, and LLM decision engine.

---

## Tech Stack

```
LAYER           TECHNOLOGY          WHAT IT DOES
─────────────   ─────────────────   ──────────────────────────────
LLM Inference   Ollama + LLaMA      The agent's brain — decides
                3.2:3b (GPU)        what to do each cycle
                                    Runs 100% on your RTX 3050

Vector Memory   ChromaDB            Remembers everything forever
                (embedded)          Semantic search over past actions,
                                    observations, entities, patterns

Policy Engine   Pure Python         Guardrails — rate limits,
                (NemoClaw-          action caps, request logging
                inspired)           Prevents agent going rogue

Config          YAML                You control everything here
                                    No code changes ever needed

Skills          Python modules      Pluggable domain logic
                in skills/ folder   Drop a .py file → agent gets
                                    new capabilities

Launcher        run_agent.py        The only file you run
```

---

## Folder Structure

```
RKTM83/
├── agent_brain.py          ← NEVER TOUCH — the core engine
├── run_agent.py            ← ONLY FILE YOU RUN
├── config.yaml             ← ONLY FILE YOU EDIT
├── dashboard.py            ← Gradio web dashboard
├── requirements.txt        ← Dependencies
├── policy_state.json       ← auto-created, tracks rate limits
├── rktm83_memory/          ← ChromaDB database, grows over time
├── skills/
│   ├── research_skill.py   ← academic research (papers, professors)
│   ├── github_skill.py     ← open source (repos, issues)
│   ├── career_skill.py     ← internship hunting (optional)
│   ├── custom_skill.py     ← your blank template
│   └── yourname_skill.py   ← add your own skills here
└── tests/
    ├── test_policy.py      ← PolicyEngine unit tests
    └── test_memory.py      ← AgentMemory unit tests
```

---

## How It Works — One Cycle

Every cycle RKTM83 does exactly this:

```
1. WAKE UP
   Reads memory stats, policy limits, last action, current time

2. THINK (LLM call ~2-3 seconds on your RTX 3050)
   Sends context + available tools to LLaMA 3.2
   LLM picks the best next action and explains why

3. POLICY CHECK
   Gateway checks if action is allowed
   Rate limits enforced automatically

4. EXECUTE
   Runs the chosen tool handler
   Tool does its work (search, score, draft, etc.)

5. REMEMBER
   Result stored in ChromaDB
   Full audit trail maintained

6. SLEEP
   Waits cycle_sleep seconds

7. REPEAT FOREVER
```

---

## The Three Layers

### Layer 1 — PolicyEngine (Guardrails)

Inspired by NemoClaw's OpenShell gateway.
Every action passes through here first.

Three outcomes for every action:
- ALLOW — go ahead
- ROUTE — forward to inference gateway (all LLM calls)
- DENY  — blocked, logged, agent told why

Default limits (change in config.yaml):
```
outreach_per_day:      5     ← max DMs/emails per day
outreach_per_week:     20    ← max DMs/emails per week
llm_calls_per_day:     150   ← max inference calls
search_calls_per_hour: 10    ← max searches per hour
```

### Layer 2 — AgentMemory (ChromaDB)

Four collections, all searchable by meaning not just keywords:

```
observations  → everything the agent has ever seen
entities      → people, companies, anything named
actions       → full audit trail of every tool call
learned       → patterns from feedback (what worked)
```

Persists forever. Restart the agent — it remembers everything.

### Layer 3 — AgentBrain (LLM Decision Engine)

Reads context every cycle. Decides the next action.
Does NOT know what tools exist until skills register them.
This is what makes it an agent instead of a script.

---

## How To Use It

### Start the agent
```powershell
cd C:\Users\RAKTIM\rakbot
python run_agent.py
```

### Run for a fixed number of cycles (testing)
```powershell
python run_agent.py --cycles 5 --cycle-sleep 10
```

### Check status without running
```powershell
python run_agent.py --status
```

### Change cycle speed without editing config
```powershell
python run_agent.py --cycle-sleep 30
```

### Stop the agent
```
Ctrl+C
```

---

## Cycle Speed Guide

```
SCENARIO                    RECOMMENDED CYCLE SLEEP
──────────────────────────  ────────────────────────
Testing / watching it work  10–30 seconds
Active development          60 seconds
Normal daily use            300 seconds (5 min)
Overnight / background      600 seconds (10 min)
```

Change in config.yaml:
```yaml
agent:
  cycle_sleep: 30
```

Or override at runtime:
```powershell
python run_agent.py --cycle-sleep 30
```

---

## How To Customize — config.yaml

This is the ONLY file you need to edit.

### Change your identity
```yaml
identity:
  name: "Your Name"
  education: "Your course"
  skills: "Your skills"
  goals:
    - "Your goal 1"
    - "Your goal 2"
```

### Change personality
```yaml
personality:
  tone: "humorous"
  traits:
    - "Add your own traits here"
    - "The LLM reads these and reasons in this style"
  catchphrase: "Your catchphrase"
```

### Change cycle speed
```yaml
agent:
  cycle_sleep: 60   # seconds
```

### Enable/disable skills
```yaml
skills:
  - career        # comment out to disable
  # - research    # uncomment to enable
  - custom        # your own skill
```

### Change policy limits
```yaml
policy:
  outreach_per_day: 10
  llm_calls_per_day: 200
```

---

## How To Add Your Own Skill

1. Copy `skills/custom_skill.py`
2. Rename it `skills/yourname_skill.py`
3. Add your tool functions inside
4. Add `yourname` to skills list in config.yaml
5. Restart the agent

Skill template structure:
```python
SKILL_NAME = "yourname"

def _my_tool(params, context, brain):
    # params   — what LLM passes in
    # context  — current agent state
    # brain    — access to memory, policy, inference
    
    # Do whatever you want here
    result = brain._infer("Your prompt here")
    brain.memory.observe("something happened", {"source": "mytool"})
    
    return {"success": True, "data": result}

def register(agent):
    agent.brain.register_tool(
        "my_tool",
        "Description the LLM reads to decide when to use this",
        _my_tool
    )
```

---

## Currently Implemented Skills

### research_skill.py

```
search_professors   Find professors and labs offering research internships
search_papers       Search Semantic Scholar + web for recent AI/ML papers
track_lab           Store a professor or lab in memory for follow-up
```

### github_skill.py

```
search_repos         Find AI/ML repos to contribute to on GitHub
find_issues          Find good-first-issue / help-wanted issues
track_contribution   Store a contribution opportunity in memory
```

### career_skill.py (optional)

```
search_opportunities  Search Internshala + web for internships
score_opportunity     LLM-powered fit analysis (score 1-10)
draft_outreach        Write personalized DMs (human approval required)
track_entity          Store a person or company in memory
send_digest           Email summary of recent opportunities
```

---

## What RKTM83 Is NOT

```
❌ Not a chatbot — it does not wait for your input
❌ Not hardcoded to one domain — add any skill
❌ Not sending anything without your approval
❌ Not storing your passwords in code (use .env file)
```

---

## .env File (Required for email)

Create a file called `.env` in your rakbot folder:
```
RAKBOT_GMAIL_EMAIL=your@gmail.com
RAKBOT_GMAIL_PASSWORD=your_app_password
```

Get an app password at: myaccount.google.com/apppasswords

---

## Roadmap

```
DONE     Core engine + 3 skills + dashboard + tests ✅

NEXT     Port to AMD Developer Cloud
         → ROCm instead of Ollama
         → AMD portfolio project

THEN     Wrap in NemoClaw sandbox
         → real policy.yaml enforcement
         → NemoClaw contribution

FUTURE   More skills — monitoring, automation, alerts
         → whatever you build, just drop it in skills/
```

---

## Quick Reference

```powershell
# Run forever (production)
python run_agent.py

# Run 5 cycles, 10s sleep (testing)
python run_agent.py --cycles 5 --cycle-sleep 10

# Check status
python run_agent.py --status

# Run with faster cycles
python run_agent.py --cycle-sleep 30
```

---

Built by Raktim Banerjee | NIIT University | March 2026
Architecture inspired by NVIDIA NemoClaw / OpenShell
