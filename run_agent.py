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
            agent.load_skill(mod)
            loaded.append(name)
        except Exception as e:
            print(f"  [ERROR] {name}: {e}")
    return loaded

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles",      type=int, default=0)
    parser.add_argument("--cycle-sleep", type=int, default=None)
    parser.add_argument("--status",      action="store_true")
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
    )

    if args.status:
        agent._status()
        sys.exit(0)

    loaded = load_skills(agent, CONFIG)
    print(f"  Skills : {loaded or 'none — add to skills/ folder'}")
    print(f"  Sleep  : {cycle_sleep}s\n")

    agent.run(max_cycles=args.cycles, cycle_sleep=cycle_sleep)
