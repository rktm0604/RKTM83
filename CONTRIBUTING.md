# Contributing to RKTM83

Thanks for your interest. RKTM83 is designed to be extended.
The most useful contributions are new skills, bug fixes, and documentation.

---

## How to Add a Skill

A skill is a single Python file in the `skills/` folder with a `register(agent)` function.

### 1. Copy the template

```bash
cp skills/custom_skill.py skills/yourname_skill.py
```

### 2. Write your tools

```python
SKILL_NAME = "yourname"

def _my_tool(params: dict, context: dict, brain) -> dict:
    """
    params   — dict the LLM passes in
    context  — current agent state (cycle, time, last_action, memory, policy)
    brain    — access to brain._infer(), brain.memory, brain.policy
    """
    # Do your thing here
    result = brain._infer("Your prompt here")
    brain.memory.observe("something happened", {"source": "yourname_skill"})
    return {"success": True, "data": result}

def register(agent):
    agent.brain.register_tool(
        "my_tool",
        "One sentence the LLM reads to decide when to use this tool.",
        _my_tool
    )
```

### 3. Enable in config.yaml

```yaml
skills:
  - yourname    # loads skills/yourname_skill.py
```

### 4. Test it

```bash
python run_agent.py --test-skills --cycles 2 --cycle-sleep 5
```

---

## Tool Handler Rules

- Always return a dict with at least `{"success": True}` or `{"success": False, "error": "..."}`
- Use `brain._infer(prompt)` for LLM calls — never call Ollama/Groq directly
- Use `brain.memory.observe(content, metadata)` to store anything the agent learns
- Use `brain.policy.check("search")` before web calls — respect rate limits
- Handle all exceptions — a crashing tool crashes the agent cycle

---

## What Makes a Good Skill

- **Focused** — one skill does one thing well
- **Graceful degradation** — if a dependency is missing, warn and skip, don't crash
- **Observable** — store results in memory so other tools and future cycles can use them
- **Respects policy** — check limits before network calls

---

## Pull Request Checklist

- [ ] Skill file is in `skills/` folder
- [ ] `SKILL_NAME` constant defined at top
- [ ] `register(agent)` function present
- [ ] All tools return `{"success": bool, ...}`
- [ ] No hardcoded credentials (use `os.environ.get()`)
- [ ] Graceful import handling for optional deps
- [ ] Brief description added to README capabilities table

---

## Bug Reports

Open an issue with:
- What you ran
- What you expected
- What actually happened
- Python version and OS

---

## Code Style

- Python 3.10+
- No type annotations required but welcome
- Keep functions under 50 lines where possible
- Log with `logger.info/warning/error` — never `print()` in skills

---

Built by [Raktim Banerjee](https://github.com/rktm0604) · MIT License
