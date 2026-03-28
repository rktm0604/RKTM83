"""
agent_brain.py — RKTM83 Core
Three layers: PolicyEngine, AgentMemory, AgentBrain, Agent.
Domain-agnostic. Skills plug in via agent.load_skill(module).
"""

import json
import re
import time
import datetime
import logging
import requests
import chromadb
from chromadb.utils import embedding_functions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("rktm83")

INFERENCE_ENDPOINT = "http://localhost:11434/api/generate"
INFERENCE_MODEL    = "llama3.2:3b"
INFERENCE_TIMEOUT  = 30


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

    def __init__(self, overrides: dict = {}):
        self.limits = {**self.DEFAULT_LIMITS, **overrides}
        self._state = {
            "outreach_today":    0,
            "outreach_week":     0,
            "llm_calls_today":   0,
            "search_calls_hour": 0,
            "last_day":  datetime.date.today().isoformat(),
            "last_hour": datetime.datetime.now().strftime("%Y-%m-%d-%H"),
            "total":     0,
        }
        logger.info("PolicyEngine ready")

    def _reset(self):
        today = datetime.date.today().isoformat()
        hour  = datetime.datetime.now().strftime("%Y-%m-%d-%H")
        if self._state["last_day"] != today:
            self._state.update({"outreach_today": 0, "llm_calls_today": 0, "last_day": today})
        if self._state["last_hour"] != hour:
            self._state.update({"search_calls_hour": 0, "last_hour": hour})

    def check(self, action: str) -> tuple:
        self._reset()
        if action == "inference":
            return self.ROUTE, "routed"
        if action == "outreach":
            if self._state["outreach_today"] >= self.limits["outreach_per_day"]:
                return self.DENY, "daily outreach limit reached"
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

    def status(self) -> dict:
        self._reset()
        return {
            "outreach":   f"{self._state['outreach_today']}/{self.limits['outreach_per_day']} today",
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

    def observe(self, content: str, meta: dict = {}):
        try:
            self.observations.add(
                documents=[content],
                metadatas=[{**meta, "ts": datetime.datetime.now().isoformat()}],
                ids=[self._id(content[:40] + str(time.time()))]
            )
        except Exception:
            pass

    def remember(self, name: str, kind: str, uid: str, meta: dict = {}):
        try:
            self.entities.add(
                documents=[f"{name} {kind}"],
                metadatas=[{"name": name, "kind": kind, "uid": uid,
                            "ts": datetime.datetime.now().isoformat(), **meta}],
                ids=[self._id(uid)]
            )
        except Exception:
            pass

    def log(self, tool: str, outcome: str, detail: str = ""):
        try:
            self.actions.add(
                documents=[f"{tool}: {detail}"],
                metadatas=[{"tool": tool, "outcome": outcome,
                            "ts": datetime.datetime.now().isoformat()}],
                ids=[self._id(f"{tool}_{time.time()}")]
            )
        except Exception:
            pass

    def learn(self, pattern: str, signal: str):
        try:
            self.learned.add(
                documents=[pattern],
                metadatas=[{"signal": signal, "ts": datetime.datetime.now().isoformat()}],
                ids=[self._id(f"learn_{pattern[:40]}")]
            )
        except Exception:
            pass

    def search(self, collection: str, query: str, n: int = 5) -> list:
        col = getattr(self, collection, self.observations)
        try:
            r = col.query(query_texts=[query], n_results=n)
            return r["metadatas"][0] if r["metadatas"] else []
        except Exception:
            return []

    def stats(self) -> dict:
        return {
            "observations": self.observations.count(),
            "entities":     self.entities.count(),
            "actions":      self.actions.count(),
            "learned":      self.learned.count(),
        }


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
        self.policy.record("llm")
        try:
            r = requests.post(
                INFERENCE_ENDPOINT,
                json={"model": INFERENCE_MODEL, "prompt": prompt, "stream": False},
                timeout=INFERENCE_TIMEOUT,
            )
            if r.status_code == 200:
                return r.json().get("response", "").strip()
        except Exception as e:
            logger.error("Inference: %s", e)
        return ""

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
                 policy_overrides: dict = {}):

        self.name    = name
        self.cycle   = 0
        self.context = {"agent": name, "cycle": 0, "last_action": "startup"}

        self.policy = PolicyEngine(policy_overrides)
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
