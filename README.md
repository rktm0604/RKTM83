# RKTM83 — Personal Autonomous Agent

> "Running on an RTX 3050 and pure ambition."

A NemoClaw-inspired personal autonomous agent that runs forever,
decides its own next action every cycle, and learns from what it does.

## Architecture
- **PolicyEngine** — NemoClaw-style gateway, rate limits, guardrails
- **AgentMemory** — ChromaDB vector store, persists across runs
- **AgentBrain** — LLM decision engine (LLaMA 3.2 via Ollama)
- **Skills** — pluggable Python modules, drop in skills/ folder

## Run
```bash
pip install chromadb sentence-transformers requests pyyaml
python run_agent.py
```

## Add Your Own Skill
Copy `skills/custom_skill.py`, rename it, add tools, enable in `config.yaml`.

**Built by Raktim Banerjee** — BTech CSE, NIIT University 2024-28
