"""
agent_brain.py — RKTM83 Core
Three layers: PolicyEngine, AgentMemory, AgentBrain, Agent.
Domain-agnostic. Skills plug in via agent.load_skill(module).
"""

import json
import os
import re
import time
import datetime
import logging
import requests
import chromadb
from chromadb.utils import embedding_functions

# ── LOGGING: Console + File ──────────────────────────────────────────────────

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("rktm83")

# Add file handler so logs persist across runs
try:
    _fh = logging.FileHandler("rktm83.log", encoding="utf-8")
    _fh.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(_fh)
except Exception:
    pass

INFERENCE_ENDPOINT = "http://localhost:11434/api/generate"
INFERENCE_MODEL    = "llama3.2:3b"
INFERENCE_TIMEOUT  = 30
INFERENCE_RETRIES  = 3


class PolicyEngine:
    ALLOW = "allow"
    ROUTE = "route"
    DENY  = "deny"

    DEFAULT_LIMITS = {
        "outreach_per_day":      5,
        "outreach_per_week":     20,
        "llm_calls_per_day":     150,
        "search_calls_per_hour": 10,
    }

    def __init__(self, overrides: dict = None, state_path: str = "policy_state.json"):
        overrides = overrides or {}
        self.limits = {**self.DEFAULT_LIMITS, **overrides}
        self._state_path = state_path
        self._state = self._load_state()
        logger.info("PolicyEngine ready (state: %s)", state_path)

    def _default_state(self) -> dict:
        now = datetime.datetime.now()
        return {
            "outreach_today":    0,
            "outreach_week":     0,
            "llm_calls_today":   0,
            "search_calls_hour": 0,
            "last_day":   datetime.date.today().isoformat(),
            "last_hour":  now.strftime("%Y-%m-%d-%H"),
            "last_week":  now.strftime("%Y-W%W"),
            "total":      0,
        }

    def _load_state(self) -> dict:
        """Load persisted state from JSON, or create fresh."""
        if self._state_path and os.path.exists(self._state_path):
            try:
                with open(self._state_path, "r") as f:
                    state = json.load(f)
                logger.info("PolicyEngine: loaded state from %s", self._state_path)
                # Ensure all keys exist (forward compat)
                for k, v in self._default_state().items():
                    state.setdefault(k, v)
                return state
            except Exception as e:
                logger.warning("PolicyEngine: failed to load state: %s", e)
        return self._default_state()

    def _save_state(self):
        """Persist state to JSON."""
        if not self._state_path:
            return
        try:
            with open(self._state_path, "w") as f:
                json.dump(self._state, f, indent=2)
        except Exception as e:
            logger.debug("PolicyEngine: failed to save state: %s", e)

    def _reset(self):
        today = datetime.date.today().isoformat()
        hour  = datetime.datetime.now().strftime("%Y-%m-%d-%H")
        week  = datetime.datetime.now().strftime("%Y-W%W")

        if self._state["last_day"] != today:
            self._state.update({
                "outreach_today": 0, "llm_calls_today": 0, "last_day": today
            })
        if self._state["last_hour"] != hour:
            self._state.update({"search_calls_hour": 0, "last_hour": hour})
        if self._state.get("last_week") != week:
            self._state.update({"outreach_week": 0, "last_week": week})

    def check(self, action: str, target: str = "") -> tuple:
        """Check if an action is allowed. Accepts optional target for compatibility."""
        self._reset()
        if action == "inference":
            return self.ROUTE, "routed"
        if action == "network":
            # Network requests — check search limits
            if self._state["search_calls_hour"] >= self.limits["search_calls_per_hour"]:
                return self.DENY, "hourly search limit reached"
            return self.ALLOW, "ok"
        if action == "outreach":
            if self._state["outreach_today"] >= self.limits["outreach_per_day"]:
                return self.DENY, "daily outreach limit reached"
            if self._state["outreach_week"] >= self.limits["outreach_per_week"]:
                return self.DENY, "weekly outreach limit reached"
            return self.ALLOW, "ok"
        if action == "search":
            if self._state["search_calls_hour"] >= self.limits["search_calls_per_hour"]:
                return self.DENY, "hourly search limit reached"
            return self.ALLOW, "ok"
        return self.ALLOW, "ok"

    def record(self, action: str):
        self._reset()
        if action == "outreach":
            self._state["outreach_today"] += 1
            self._state["outreach_week"]  += 1
        elif action == "llm":
            self._state["llm_calls_today"] += 1
        elif action == "search":
            self._state["search_calls_hour"] += 1
        self._state["total"] += 1
        self._save_state()

    def status(self) -> dict:
        self._reset()
        return {
            "outreach":   f"{self._state['outreach_today']}/{self.limits['outreach_per_day']} today",
            "outreach_w": f"{self._state['outreach_week']}/{self.limits['outreach_per_week']} this week",
            "llm_calls":  f"{self._state['llm_calls_today']}/{self.limits['llm_calls_per_day']} today",
            "searches":   f"{self._state['search_calls_hour']}/{self.limits['search_calls_per_hour']} this hour",
            "total":      self._state["total"],
        }


class AgentMemory:
    def __init__(self, path: str = "./rktm83_memory"):
        self.path   = path
        self.client = chromadb.PersistentClient(path=path)
        ef          = embedding_functions.DefaultEmbeddingFunction()
        self.observations = self.client.get_or_create_collection("observations", embedding_function=ef)
        self.entities     = self.client.get_or_create_collection("entities",     embedding_function=ef)
        self.actions      = self.client.get_or_create_collection("actions",      embedding_function=ef)
        self.learned      = self.client.get_or_create_collection("learned",      embedding_function=ef)
        logger.info("AgentMemory ready at %s", path)

    def _id(self, raw: str) -> str:
        return re.sub(r'[^a-zA-Z0-9_-]', '_', str(raw))[:50] + "_" + str(abs(hash(raw)))[-6:]

    # ── Core Methods ─────────────────────────────────────────────────────────

    def observe(self, content: str, meta: dict = None):
        meta = meta or {}
        try:
            self.observations.add(
                documents=[content],
                metadatas=[{**meta, "ts": datetime.datetime.now().isoformat()}],
                ids=[self._id(content[:40] + str(time.time()))]
            )
        except Exception as e:
            logger.debug("AgentMemory.observe error: %s", e)

    def remember(self, name: str, kind: str, uid: str, meta: dict = None):
        meta = meta or {}
        try:
            self.entities.upsert(
                documents=[f"{name} {kind}"],
                metadatas=[{"name": name, "kind": kind, "uid": uid,
                            "ts": datetime.datetime.now().isoformat(), **meta}],
                ids=[self._id(uid)]
            )
        except Exception as e:
            logger.debug("AgentMemory.remember error: %s", e)

    def log(self, tool: str, outcome: str, detail: str = ""):
        try:
            self.actions.add(
                documents=[f"{tool}: {detail}"],
                metadatas=[{"tool": tool, "outcome": outcome,
                            "ts": datetime.datetime.now().isoformat()}],
                ids=[self._id(f"{tool}_{time.time()}")]
            )
        except Exception as e:
            logger.debug("AgentMemory.log error: %s", e)

    def learn(self, pattern: str, signal: str, confidence: float = 1.0):
        try:
            self.learned.add(
                documents=[pattern],
                metadatas=[{"signal": signal, "confidence": confidence,
                            "ts": datetime.datetime.now().isoformat()}],
                ids=[self._id(f"learn_{pattern[:40]}")]
            )
        except Exception as e:
            logger.debug("AgentMemory.learn error: %s", e)

    def search(self, collection: str, query: str, n: int = 5) -> list:
        col = getattr(self, collection, self.observations)
        try:
            r = col.query(query_texts=[query], n_results=n)
            return r["metadatas"][0] if r["metadatas"] else []
        except Exception as e:
            logger.debug("AgentMemory.search error: %s", e)
            return []

    def stats(self) -> dict:
        return {
            "observations": self.observations.count(),
            "entities":     self.entities.count(),
            "actions":      self.actions.count(),
            "learned":      self.learned.count(),
        }

    # ── Aliases for career_skill.py compatibility ────────────────────────────

    def remember_entity(self, name: str, kind: str, uid: str, meta: dict = None):
        """Alias for remember() — used by career_skill.py."""
        return self.remember(name, kind, uid, meta)

    def entity_status(self, identifier: str) -> dict:
        """Look up an entity by its uid. Returns its metadata or empty dict."""
        try:
            result = self.entities.get(
                ids=[self._id(identifier)],
                include=["metadatas"]
            )
            if result and result["metadatas"]:
                return result["metadatas"][0]
        except Exception as e:
            logger.debug("AgentMemory.entity_status error: %s", e)
        return {}

    def update_entity(self, identifier: str, updates: dict):
        """Update metadata on an existing entity."""
        try:
            existing = self.entity_status(identifier)
            if existing:
                merged = {**existing, **updates, "ts": datetime.datetime.now().isoformat()}
                self.entities.update(
                    ids=[self._id(identifier)],
                    metadatas=[merged]
                )
        except Exception as e:
            logger.debug("AgentMemory.update_entity error: %s", e)

    def log_action(self, tool: str, identifier: str, detail: str = "", outcome: str = "ok"):
        """Alias for log() — used by career_skill.py."""
        return self.log(tool, outcome, f"{identifier}: {detail[:60]}")

    def has_link(self, link: str) -> bool:
        """Check if an opportunity link already exists in observations."""
        try:
            r = self.observations.get(
                where={"link": link},
                include=["metadatas"],
                limit=1
            )
            return bool(r and r["metadatas"])
        except Exception:
            # ChromaDB might not support where filter on non-indexed field
            # Fall back to False (allow the insert)
            return False


class AgentBrain:
    def __init__(self, name: str, policy: PolicyEngine,
                 memory: AgentMemory, profile: str = ""):
        self.name    = name
        self.policy  = policy
        self.memory  = memory
        self.profile = profile
        self._tools  = {}
        logger.info("AgentBrain ready")

    def register_tool(self, name: str, description: str, handler):
        self._tools[name] = {"description": description, "handler": handler}
        logger.info("Tool: %s", name)

    def _infer(self, prompt: str) -> str:
        """Call LLM with retry + exponential backoff."""
        self.policy.record("llm")
        for attempt in range(INFERENCE_RETRIES):
            try:
                r = requests.post(
                    INFERENCE_ENDPOINT,
                    json={"model": INFERENCE_MODEL, "prompt": prompt, "stream": False},
                    timeout=INFERENCE_TIMEOUT,
                )
                if r.status_code == 200:
                    return r.json().get("response", "").strip()
                logger.warning("Inference HTTP %d (attempt %d/%d)",
                               r.status_code, attempt + 1, INFERENCE_RETRIES)
            except Exception as e:
                logger.error("Inference error (attempt %d/%d): %s",
                             attempt + 1, INFERENCE_RETRIES, e)
            if attempt < INFERENCE_RETRIES - 1:
                time.sleep(2 ** attempt)
        return ""

    # Alias so career_skill.py's brain._call_inference() works
    _call_inference = _infer

    def decide(self, context: dict) -> dict:
        if not self._tools:
            return {"tool": "wait", "params": {}, "reasoning": "no tools"}

        tools_str = "\n".join(f"- {n}: {i['description']}" for n, i in self._tools.items())

        prompt = f"""{self.profile}

MEMORY: {json.dumps(self.memory.stats())}
POLICY: {json.dumps(self.policy.status())}
CONTEXT: {json.dumps({k: v for k, v in context.items() if k != "config"}, default=str)}

TOOLS:
{tools_str}

What is the best next action? Do NOT pick the same tool as last_action.
Reply ONLY in JSON: {{"tool": "name", "params": {{}}, "reasoning": "one line"}}"""

        text = self._infer(prompt)
        try:
            clean = re.sub(r'```(?:json)?', '', text).strip()
            m = re.search(r'\{.*\}', clean, re.DOTALL)
            if m:
                d = json.loads(m.group())
                if d.get("tool") in self._tools:
                    return d
        except Exception:
            pass

        # Fallback — pick anything that isn't last_action
        last = context.get("last_action", "")
        for tool in self._tools:
            if tool != last:
                return {"tool": tool, "params": {}, "reasoning": "fallback"}
        return {"tool": next(iter(self._tools)), "params": {}, "reasoning": "fallback"}

    def execute(self, decision: dict, context: dict) -> dict:
        tool   = decision.get("tool", "wait")
        params = decision.get("params", {})
        if tool not in self._tools:
            return {"success": False, "error": f"unknown: {tool}"}
        try:
            logger.info("[RUN] %s", tool)
            result = self._tools[tool]["handler"](params, context, self)
            self.memory.log(tool, "ok", str(result)[:80])
            return result or {"success": True}
        except Exception as e:
            logger.error("[FAIL] %s: %s", tool, e)
            self.memory.log(tool, "error", str(e))
            return {"success": False, "error": str(e)}


class Agent:
    def __init__(self, name: str = "RKTM83", profile: str = "",
                 memory_path: str = "./rktm83_memory",
                 policy_overrides: dict = None,
                 state_path: str = "policy_state.json"):

        policy_overrides = policy_overrides or {}
        self.name    = name
        self.cycle   = 0
        self.context = {"agent": name, "cycle": 0, "last_action": "startup"}

        self.policy = PolicyEngine(policy_overrides, state_path=state_path)
        self.memory = AgentMemory(memory_path)
        self.brain  = AgentBrain(name, self.policy, self.memory, profile)

        self.brain.register_tool("wait",   "Wait — nothing to do right now",          lambda p,c,b: {"success": True})
        self.brain.register_tool("status", "Check and print agent memory and policy",  lambda p,c,b: self._status())
        logger.info("Agent '%s' ready", name)

    def _status(self):
        print(f"\n{'='*50}\n  {self.name} | Cycle {self.cycle}")
        print(f"  Memory : {self.memory.stats()}")
        print(f"  Policy : {self.policy.status()}\n{'='*50}\n")
        return {"success": True}

    def load_skill(self, skill_module):
        try:
            skill_module.register(self)
            logger.info("Skill: %s", getattr(skill_module, 'SKILL_NAME', '?'))
        except Exception as e:
            logger.error("Skill failed: %s", e)

    def run(self, max_cycles: int = 0, cycle_sleep: int = 300):
        print(f"\n{'='*50}")
        print(f"  {self.name} — Autonomous Agent")
        print(f"  Tools  : {list(self.brain._tools.keys())}")
        print(f"  Memory : {self.memory.path}")
        print(f"  Sleep  : {cycle_sleep}s per cycle")
        print(f"  Ctrl+C to stop")
        print(f"{'='*50}\n")

        try:
            while True:
                self.cycle += 1
                self.context.update({
                    "cycle":       self.cycle,
                    "time":        datetime.datetime.now().isoformat(),
                    "memory":      self.memory.stats(),
                    "policy":      self.policy.status(),
                    "cycle_sleep": cycle_sleep,
                })

                logger.info("─── Cycle %d ───", self.cycle)
                decision = self.brain.decide(self.context)
                logger.info("[PLAN] %s — %s", decision.get("tool"), decision.get("reasoning"))
                result = self.brain.execute(decision, self.context)

                self.context["last_action"] = decision.get("tool")
                self.memory.observe(
                    f"cycle {self.cycle}: {decision.get('tool')}",
                    {"tool": decision.get("tool"), "cycle": str(self.cycle)}
                )

                if max_cycles and self.cycle >= max_cycles:
                    break
                time.sleep(cycle_sleep)

        except KeyboardInterrupt:
            print(f"\n  Stopped. Cycles: {self.cycle} | Memory: {self.memory.stats()}")
