"""
run_agent.py — RKTM83 Launcher
Edit config.yaml to change everything.
Add skills to the skills/ folder.
Run: python run_agent.py
"""

import os, sys, logging, importlib, argparse
from pathlib import Path

try:
    import yaml
except ImportError:
    os.system("pip install pyyaml -q")
    import yaml

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

if not Path("config.yaml").exists():
    print("ERROR: config.yaml not found.")
    sys.exit(1)

with open("config.yaml") as f:
    CONFIG = yaml.safe_load(f)

logging.basicConfig(
    level=getattr(logging, CONFIG["agent"].get("log_level", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

def build_profile(cfg):
    p = cfg.get("personality", {})
    i = cfg.get("identity", {})
    traits   = "\n".join(f"  - {t}" for t in p.get("traits", []))
    goals    = "\n".join(f"  - {g}" for g in i.get("goals", []))
    projects = "\n".join(f"  - {x}" for x in i.get("projects", []))
    return f"""You are {cfg['agent']['name']}, a personal autonomous agent.

PERSONALITY ({p.get('tone','helpful')}):
{traits}
Catchphrase: "{p.get('catchphrase','')}"

OWNER: {i.get('name','')} | {i.get('education','')}
Skills: {i.get('skills','')}
Projects: {projects}
Goals: {goals}

RULES:
  - Never pick the same tool as last_action
  - Reason in your personality — one punchy line max
  - When nothing urgent: wait
"""

def load_skills(agent, cfg):
    skills_dir = Path("skills")
    skills_dir.mkdir(exist_ok=True)
    sys.path.insert(0, str(skills_dir))
    loaded = []
    for name in cfg.get("skills", []):
        f = skills_dir / f"{name}_skill.py"
        if not f.exists():
            print(f"  [WARN] skills/{name}_skill.py not found")
            continue
        try:
            mod = importlib.import_module(f"{name}_skill")
            # Pass config to skill if it accepts it
            if hasattr(mod, 'set_config'):
                mod.set_config(cfg)
            agent.load_skill(mod)
            loaded.append(name)
        except Exception as e:
            print(f"  [ERROR] {name}: {e}")
    return loaded

def test_skills(agent, cfg):
    """Health-check: load all skills, report tool registration status."""
    loaded = load_skills(agent, cfg)
    tools = list(agent.brain._tools.keys())
    print(f"\n{'='*52}")
    print(f"  SKILL HEALTH CHECK")
    print(f"{'='*52}")
    print(f"  Skills loaded : {loaded or 'none'}")
    print(f"  Tools active  : {tools}")
    print(f"  Total tools   : {len(tools)}")
    print(f"{'='*52}")

    # Quick test: call each tool's handler with empty params
    errors = []
    for name, info in agent.brain._tools.items():
        if name in ("wait", "status"):
            continue
        try:
            # Just check handler is callable
            assert callable(info["handler"]), f"{name}: handler not callable"
            print(f"  ✓ {name}: OK (callable)")
        except Exception as e:
            errors.append(f"  ✗ {name}: {e}")
            print(f"  ✗ {name}: {e}")

    if errors:
        print(f"\n  {len(errors)} tool(s) failed health check")
    else:
        print(f"\n  All tools passed health check ✓")
    print(f"{'='*52}\n")
    return not errors

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RKTM83 — Personal Autonomous Agent")
    parser.add_argument("--cycles",      type=int, default=0, help="Max cycles (0 = infinite)")
    parser.add_argument("--cycle-sleep", type=int, default=None, help="Seconds between cycles")
    parser.add_argument("--status",      action="store_true", help="Print status and exit")
    parser.add_argument("--test-skills", action="store_true", help="Test skill loading and exit")
    parser.add_argument("--chat",        action="store_true", help="Interactive chat mode")
    args = parser.parse_args()

    from agent_brain import Agent

    cfg         = CONFIG["agent"]
    cycle_sleep = args.cycle_sleep or cfg.get("cycle_sleep", 300)
    overrides   = {k: v for k, v in CONFIG.get("policy", {}).items()
                   if k != "search_interval_hours"}

    print(f"\n{'='*52}")
    print(f"  {cfg['name']} — Personal Autonomous Agent")
    print(f"  \"{CONFIG['personality'].get('catchphrase','')}\"")
    print(f"{'='*52}\n")

    agent = Agent(
        name             = cfg["name"],
        profile          = build_profile(CONFIG),
        memory_path      = cfg.get("memory_path", "./rktm83_memory"),
        policy_overrides = overrides,
        state_path       = "policy_state.json",
    )

    # Store full config in context so skills can access it
    agent.context["config"] = CONFIG

    if args.status:
        agent._status()
        sys.exit(0)

    if args.test_skills:
        ok = test_skills(agent, CONFIG)
        sys.exit(0 if ok else 1)

    loaded = load_skills(agent, CONFIG)
    print(f"  Skills : {loaded or 'none — add to skills/ folder'}")

    # ── CHAT MODE ─────────────────────────────────────────────────────────
    if args.chat:
        import json as _json
        print(f"  Mode   : Interactive Chat")
        print(f"  Tools  : {list(agent.brain._tools.keys())}")
        print(f"\n  Type a command. The agent will pick the best tool and execute it.")
        print(f"  Type 'quit' or 'exit' to stop. Type 'status' for agent status.\n")

        while True:
            try:
                user_input = input(f"  [{cfg['name']}] > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  Goodbye!")
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                print("  Goodbye!")
                break
            if user_input.lower() == "status":
                agent._status()
                continue
            if user_input.lower() == "tools":
                for name, info in agent.brain._tools.items():
                    print(f"    {name}: {info['description'][:70]}")
                print()
                continue
            if user_input.lower() == "memory":
                print(f"  {agent.memory.stats()}\n")
                continue

            # Build context with user's request
            agent.context.update({
                "time":    __import__("datetime").datetime.now().isoformat(),
                "memory":  agent.memory.stats(),
                "policy":  agent.policy.status(),
                "user_request": user_input,
            })

            # Ask the brain to decide what tool to use
            tools_str = "\n".join(
                f"- {n}: {i['description']}"
                for n, i in agent.brain._tools.items()
            )
            prompt = f"""{agent.brain.profile}

USER REQUEST: {user_input}

TOOLS:
{tools_str}

Pick the BEST tool for this request.
Reply ONLY in JSON: {{"tool": "name", "params": {{}}, "reasoning": "one line"}}"""

            response = agent.brain._infer(prompt)

            # Parse the decision
            decision = None
            try:
                import re as _re
                clean = _re.sub(r'```(?:json)?', '', response).strip()
                m = _re.search(r'\{.*\}', clean, _re.DOTALL)
                if m:
                    d = _json.loads(m.group())
                    if d.get("tool") in agent.brain._tools:
                        decision = d
            except Exception:
                pass

            if not decision:
                print(f"\n  Agent couldn't decide. Raw response:\n  {response[:200]}\n")
                continue

            tool = decision["tool"]
            params = decision.get("params", {})
            reasoning = decision.get("reasoning", "")

            print(f"\n  → Tool: {tool}")
            print(f"  → Why:  {reasoning}")
            if params:
                print(f"  → Params: {_json.dumps(params, indent=2)}")

            # Execute
            result = agent.brain.execute(decision, agent.context)

            # Display result
            if result.get("success"):
                print(f"  ✓ Success")
                for k, v in result.items():
                    if k == "success":
                        continue
                    v_str = str(v)
                    if len(v_str) > 200:
                        v_str = v_str[:200] + "..."
                    print(f"    {k}: {v_str}")
            else:
                print(f"  ✗ Failed: {result.get('error', 'unknown')}")

            # Remember
            agent.memory.observe(
                f"chat: {user_input[:60]} → {tool}",
                {"tool": tool, "source": "chat"}
            )
            agent.context["last_action"] = tool
            print()

        sys.exit(0)

    # ── AUTONOMOUS MODE ───────────────────────────────────────────────────
    print(f"  Sleep  : {cycle_sleep}s\n")
    agent.run(max_cycles=args.cycles, cycle_sleep=cycle_sleep)
