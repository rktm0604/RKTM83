"""
RKTM83 core runtime.

Three layers:
- PolicyEngine
- AgentMemory
- AgentBrain
- Agent
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import re
import time

import chromadb
import requests
from chromadb.utils import embedding_functions

from resilience import (
    CircuitBreakerError,
    api_circuit_breaker,
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

try:
    from groq import Groq
except ImportError:  # pragma: no cover - dependency shim
    Groq = None

try:
    from google import genai
except ImportError:  # pragma: no cover - dependency shim
    genai = None


LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("rktm83")

try:
    _fh = logging.FileHandler("rktm83.log", encoding="utf-8")
    _fh.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(_fh)
except Exception:  # pragma: no cover - best-effort logging
    pass


INFERENCE_ENDPOINT = "http://localhost:11434/api/generate"
DEFAULT_OLLAMA_MODEL = "llama3.2:3b"
DEFAULT_GROQ_MODEL = "llama-3.1-70b-versatile"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
INFERENCE_TIMEOUT = 30


class PolicyEngine:
    ALLOW = "allow"
    ROUTE = "route"
    DENY = "deny"

    DEFAULT_LIMITS = {
        "outreach_per_day": 5,
        "outreach_per_week": 20,
        "llm_calls_per_day": 150,
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
            "outreach_today": 0,
            "outreach_week": 0,
            "llm_calls_today": 0,
            "search_calls_hour": 0,
            "last_day": datetime.date.today().isoformat(),
            "last_hour": now.strftime("%Y-%m-%d-%H"),
            "last_week": now.strftime("%Y-W%W"),
            "total": 0,
        }

    def _load_state(self) -> dict:
        if self._state_path and os.path.exists(self._state_path):
            try:
                with open(self._state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                logger.info("PolicyEngine: loaded state from %s", self._state_path)
                for key, value in self._default_state().items():
                    state.setdefault(key, value)
                return state
            except Exception as e:
                logger.warning("PolicyEngine: failed to load state: %s", e)
        return self._default_state()

    def _save_state(self):
        if not self._state_path:
            return
        try:
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2)
        except Exception as e:
            logger.debug("PolicyEngine: failed to save state: %s", e)

    def _reset(self):
        today = datetime.date.today().isoformat()
        hour = datetime.datetime.now().strftime("%Y-%m-%d-%H")
        week = datetime.datetime.now().strftime("%Y-W%W")

        if self._state["last_day"] != today:
            self._state.update(
                {"outreach_today": 0, "llm_calls_today": 0, "last_day": today}
            )
        if self._state["last_hour"] != hour:
            self._state.update({"search_calls_hour": 0, "last_hour": hour})
        if self._state.get("last_week") != week:
            self._state.update({"outreach_week": 0, "last_week": week})

    def check(self, action: str, target: str = "") -> tuple:
        del target
        self._reset()
        if action == "inference":
            if self._state["llm_calls_today"] >= self.limits["llm_calls_per_day"]:
                return self.DENY, "daily llm limit reached"
            return self.ROUTE, "routed"
        if action == "llm":
            if self._state["llm_calls_today"] >= self.limits["llm_calls_per_day"]:
                return self.DENY, "daily llm limit reached"
            return self.ALLOW, "ok"
        if action == "network":
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
            self._state["outreach_week"] += 1
        elif action == "llm":
            self._state["llm_calls_today"] += 1
        elif action == "search":
            self._state["search_calls_hour"] += 1
        self._state["total"] += 1
        self._save_state()

    def status(self) -> dict:
        self._reset()
        return {
            "outreach": f"{self._state['outreach_today']}/{self.limits['outreach_per_day']} today",
            "outreach_w": f"{self._state['outreach_week']}/{self.limits['outreach_per_week']} this week",
            "llm_calls": f"{self._state['llm_calls_today']}/{self.limits['llm_calls_per_day']} today",
            "searches": f"{self._state['search_calls_hour']}/{self.limits['search_calls_per_hour']} this hour",
            "total": self._state["total"],
        }


class AgentMemory:
    def __init__(self, path: str = "./rktm83_memory"):
        self.path = path
        self.client = chromadb.PersistentClient(path=path)
        ef = embedding_functions.DefaultEmbeddingFunction()
        self.observations = self.client.get_or_create_collection(
            "observations", embedding_function=ef
        )
        self.entities = self.client.get_or_create_collection(
            "entities", embedding_function=ef
        )
        self.actions = self.client.get_or_create_collection(
            "actions", embedding_function=ef
        )
        self.learned = self.client.get_or_create_collection(
            "learned", embedding_function=ef
        )
        logger.info("AgentMemory ready at %s", path)

    def _id(self, raw: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", str(raw))[:50]
        digest = hashlib.sha1(str(raw).encode("utf-8")).hexdigest()[:10]
        return f"{safe}_{digest}"

    def observe(self, content: str, meta: dict = None):
        meta = meta or {}
        try:
            self.observations.add(
                documents=[content],
                metadatas=[{**meta, "ts": datetime.datetime.now().isoformat()}],
                ids=[self._id(content[:40] + str(time.time()))],
            )
        except Exception as e:
            logger.debug("AgentMemory.observe error: %s", e)

    def remember(self, name: str, kind: str, uid: str, meta: dict = None):
        meta = meta or {}
        try:
            self.entities.upsert(
                documents=[f"{name} {kind}"],
                metadatas=[
                    {
                        "name": name,
                        "kind": kind,
                        "uid": uid,
                        "ts": datetime.datetime.now().isoformat(),
                        **meta,
                    }
                ],
                ids=[self._id(uid)],
            )
        except Exception as e:
            logger.debug("AgentMemory.remember error: %s", e)

    def log(self, tool: str, outcome: str, detail: str = ""):
        try:
            self.actions.add(
                documents=[f"{tool}: {detail}"],
                metadatas=[
                    {
                        "tool": tool,
                        "outcome": outcome,
                        "ts": datetime.datetime.now().isoformat(),
                    }
                ],
                ids=[self._id(f"{tool}_{time.time()}")],
            )
        except Exception as e:
            logger.debug("AgentMemory.log error: %s", e)

    def learn(self, pattern: str, signal: str, confidence: float = 1.0):
        try:
            self.learned.add(
                documents=[pattern],
                metadatas=[
                    {
                        "signal": signal,
                        "confidence": confidence,
                        "ts": datetime.datetime.now().isoformat(),
                    }
                ],
                ids=[self._id(f"learn_{pattern[:40]}")],
            )
        except Exception as e:
            logger.debug("AgentMemory.learn error: %s", e)

    def search(self, collection: str, query: str, n: int = 5) -> list:
        col = getattr(self, collection, self.observations)
        try:
            result = col.query(query_texts=[query], n_results=n)
            return result["metadatas"][0] if result["metadatas"] else []
        except Exception as e:
            logger.debug("AgentMemory.search error: %s", e)
            return []

    def stats(self) -> dict:
        return {
            "observations": self.observations.count(),
            "entities": self.entities.count(),
            "actions": self.actions.count(),
            "learned": self.learned.count(),
        }

    def remember_entity(self, name: str, kind: str, uid: str, meta: dict = None):
        return self.remember(name, kind, uid, meta)

    def entity_status(self, identifier: str) -> dict:
        try:
            result = self.entities.get(ids=[self._id(identifier)], include=["metadatas"])
            if result and result["metadatas"]:
                return result["metadatas"][0]
        except Exception as e:
            logger.debug("AgentMemory.entity_status error: %s", e)
        return {}

    def update_entity(self, identifier: str, updates: dict):
        try:
            existing = self.entity_status(identifier)
            if existing:
                merged = {
                    **existing,
                    **updates,
                    "ts": datetime.datetime.now().isoformat(),
                }
                self.entities.update(ids=[self._id(identifier)], metadatas=[merged])
        except Exception as e:
            logger.debug("AgentMemory.update_entity error: %s", e)

    def log_action(self, tool: str, identifier: str, detail: str = "", outcome: str = "ok"):
        return self.log(tool, outcome, f"{identifier}: {detail[:60]}")

    def has_link(self, link: str) -> bool:
        try:
            result = self.observations.get(
                where={"link": link},
                include=["metadatas"],
                limit=1,
            )
            return bool(result and result["metadatas"])
        except Exception:
            return False


class AgentBrain:
    def __init__(
        self,
        name: str,
        policy: PolicyEngine,
        memory: AgentMemory,
        profile: str = "",
        config: dict = None,
    ):
        self.name = name
        self.policy = policy
        self.memory = memory
        self.profile = profile
        self.config = config or {}
        self._tools = {}
        self._groq_client = None
        self._gemini_client = None
        logger.info("AgentBrain ready")

    def register_tool(self, name: str, description: str, handler):
        self._tools[name] = {"description": description, "handler": handler}
        logger.info("Tool: %s", name)

    def _brain_settings(self) -> dict:
        settings = self.config.get("brain", {})
        return {
            "provider": settings.get("provider", "gemini").lower(),
            "gemini_model": settings.get("gemini_model", DEFAULT_GEMINI_MODEL),
            "groq_model": settings.get("groq_model", DEFAULT_GROQ_MODEL),
            "ollama_model": settings.get("ollama_model", DEFAULT_OLLAMA_MODEL),
            "fallback": settings.get("fallback", True),
        }

    def _get_groq_client(self):
        if self._groq_client is not None:
            return self._groq_client

        api_key = os.environ.get("GROQ_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        if Groq is None:
            raise RuntimeError("groq package is not installed")

        self._groq_client = Groq(api_key=api_key)
        return self._groq_client

    @api_circuit_breaker("groq_api", logger=logger)
    @retry(
        wait=wait_exponential(min=1, max=30),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(Exception),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _call_groq(self, prompt: str, model: str) -> str:
        client = self._get_groq_client()
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return (response.choices[0].message.content or "").strip()

    @api_circuit_breaker("ollama_api", logger=logger)
    @retry(
        wait=wait_exponential(min=1, max=30),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(Exception),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _call_ollama(self, prompt: str, model: str) -> str:
        response = requests.post(
            INFERENCE_ENDPOINT,
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=INFERENCE_TIMEOUT,
        )
        response.raise_for_status()
        return response.json().get("response", "").strip()

    def _get_gemini_client(self):
        if self._gemini_client is not None:
            return self._gemini_client

        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        if genai is None:
            raise RuntimeError("google-genai package is not installed")

        self._gemini_client = genai.Client(api_key=api_key)
        return self._gemini_client

    @api_circuit_breaker("gemini_api", logger=logger)
    @retry(
        wait=wait_exponential(min=1, max=30),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(Exception),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _call_gemini(self, prompt: str, model: str) -> str:
        client = self._get_gemini_client()
        response = client.models.generate_content(
            model=model,
            contents=prompt,
        )
        return (response.text or "").strip()

    def _infer(self, prompt: str) -> str:
        verdict, reason = self.policy.check("inference")
        if verdict == self.policy.DENY:
            logger.warning("Inference blocked: %s", reason)
            return ""

        self.policy.record("llm")

        settings = self._brain_settings()
        provider = settings["provider"]

        # Build fallback chain
        providers = [provider]
        if settings["fallback"]:
            for fb in ["gemini", "groq", "ollama"]:
                if fb not in providers:
                    providers.append(fb)

        for candidate in providers:
            try:
                if candidate == "gemini":
                    return self._call_gemini(prompt, settings["gemini_model"])
                elif candidate == "groq":
                    return self._call_groq(prompt, settings["groq_model"])
                else:
                    return self._call_ollama(prompt, settings["ollama_model"])
            except CircuitBreakerError as e:
                logger.warning("%s circuit open: %s", candidate, e)
            except Exception as e:
                logger.warning("%s inference failed: %s", candidate, e)

            if len(providers) > 1:
                next_idx = providers.index(candidate) + 1
                if next_idx < len(providers):
                    logger.info("Falling back to %s", providers[next_idx])

        return ""

    _call_inference = _infer

    def decide(self, context: dict) -> dict:
        if not self._tools:
            return {"tool": "wait", "params": {}, "reasoning": "no tools"}

        tools_str = "\n".join(
            f"- {name}: {info['description']}" for name, info in self._tools.items()
        )

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
            clean = re.sub(r"```(?:json)?", "", text).strip()
            match = re.search(r"\{.*\}", clean, re.DOTALL)
            if match:
                decision = json.loads(match.group())
                if decision.get("tool") in self._tools:
                    return decision
        except Exception:
            pass

        last = context.get("last_action", "")
        for tool in self._tools:
            if tool != last:
                return {"tool": tool, "params": {}, "reasoning": "fallback"}
        return {"tool": next(iter(self._tools)), "params": {}, "reasoning": "fallback"}

    def execute(self, decision: dict, context: dict) -> dict:
        tool = decision.get("tool", "wait")
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
    def __init__(
        self,
        name: str = "RKTM83",
        profile: str = "",
        memory_path: str = "./rktm83_memory",
        policy_overrides: dict = None,
        state_path: str = "policy_state.json",
        config: dict = None,
        agent_state_path: str = "agent_state.json",
    ):
        policy_overrides = policy_overrides or {}
        self.config = config or {}
        self.name = name
        self.cycle = 0
        self.consecutive_failures = 0
        self.agent_state_path = agent_state_path
        self.context = {"agent": name, "cycle": 0, "last_action": "startup"}

        self.policy = PolicyEngine(policy_overrides, state_path=state_path)
        self.memory = AgentMemory(memory_path)
        self.brain = AgentBrain(name, self.policy, self.memory, profile, config=self.config)

        self.brain.register_tool(
            "wait",
            "Wait - nothing to do right now",
            lambda p, c, b: {"success": True},
        )
        self.brain.register_tool(
            "status",
            "Check and print agent memory and policy",
            lambda p, c, b: self._status(),
        )
        self._load_agent_state()
        logger.info("Agent '%s' ready", name)

    def _status(self):
        print(f"\n{'=' * 50}\n  {self.name} | Cycle {self.cycle}")
        print(f"  Memory : {self.memory.stats()}")
        print(f"  Policy : {self.policy.status()}\n{'=' * 50}\n")
        return {"success": True}

    def load_skill(self, skill_module):
        try:
            skill_module.register(self)
            logger.info("Skill: %s", getattr(skill_module, "SKILL_NAME", "?"))
        except Exception as e:
            logger.error("Skill failed: %s", e)

    def _load_agent_state(self):
        if not self.agent_state_path or not os.path.exists(self.agent_state_path):
            return
        try:
            with open(self.agent_state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            self.cycle = int(state.get("cycle_count", 0))
            self.context["last_action"] = state.get(
                "last_action", self.context["last_action"]
            )
            self.context["resumed_at"] = datetime.datetime.now().isoformat()
            logger.info(
                "Resumed agent state from %s (cycle=%s, last_action=%s)",
                self.agent_state_path,
                self.cycle,
                self.context["last_action"],
            )
        except Exception as e:
            logger.warning("Failed to load agent state: %s", e)

    def _save_agent_state(self, extra: dict = None):
        if not self.agent_state_path:
            return

        state = {
            "last_action": self.context.get("last_action", "startup"),
            "cycle_count": self.cycle,
            "timestamp": datetime.datetime.now().isoformat(),
        }
        if extra:
            state.update(extra)

        try:
            with open(self.agent_state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save agent state: %s", e)

    def _notifications_config(self) -> dict:
        return self.config.get("notifications", {})

    def _notification_enabled(self, event: str) -> bool:
        cfg = self._notifications_config()
        if not cfg.get("enabled", False):
            return False
        if event == "success":
            return cfg.get("on_success", True)
        if event == "error":
            return cfg.get("on_error", True)
        return False

    def _summarize_result(self, result: dict) -> str:
        if not isinstance(result, dict):
            return str(result)[:120]
        if result.get("error"):
            return str(result["error"])[:120]

        parts = []
        for key, value in result.items():
            if key == "success" or value in (None, "", []):
                continue
            if isinstance(value, list):
                parts.append(f"{key}={len(value)} items")
            elif isinstance(value, dict):
                parts.append(f"{key}=updated")
            else:
                parts.append(f"{key}={str(value)[:60]}")
            if len(parts) == 2:
                break

        return "; ".join(parts)[:120] or "Completed successfully"

    def _send_notification(self, event: str, tool_name: str, result: dict):
        if tool_name == "notify" or not self._notification_enabled(event):
            return

        notify_tool = self.brain._tools.get("notify")
        if not notify_tool:
            return

        title = f"{self.name} - {tool_name}"
        prefix = "Success" if event == "success" else "Error"
        message = f"{prefix}: {self._summarize_result(result)}"
        try:
            notify_tool["handler"](
                {"title": title, "message": message},
                self.context,
                self.brain,
            )
        except Exception as e:
            logger.warning("Notification failed: %s", e)

    def run(self, max_cycles: int = 0, cycle_sleep: int = 300):
        print(f"\n{'=' * 50}")
        print(f"  {self.name} - Autonomous Agent")
        print(f"  Tools  : {list(self.brain._tools.keys())}")
        print(f"  Memory : {self.memory.path}")
        print(f"  Sleep  : {cycle_sleep}s per cycle")
        print("  Ctrl+C to stop")
        print(f"{'=' * 50}\n")

        try:
            while True:
                try:
                    self.cycle += 1
                    self.context.update(
                        {
                            "cycle": self.cycle,
                            "time": datetime.datetime.now().isoformat(),
                            "memory": self.memory.stats(),
                            "policy": self.policy.status(),
                            "cycle_sleep": cycle_sleep,
                        }
                    )

                    logger.info("Cycle %d", self.cycle)
                    decision = self.brain.decide(self.context)
                    logger.info(
                        "[PLAN] %s - %s",
                        decision.get("tool"),
                        decision.get("reasoning"),
                    )
                    result = self.brain.execute(decision, self.context)

                    self.context["last_action"] = decision.get("tool")
                    self.memory.observe(
                        f"cycle {self.cycle}: {decision.get('tool')}",
                        {"tool": decision.get("tool"), "cycle": str(self.cycle)},
                    )
                    self._save_agent_state()

                    if result.get("success"):
                        self.consecutive_failures = 0
                        self._send_notification(
                            "success", decision.get("tool", "tool"), result
                        )
                    else:
                        self._send_notification(
                            "error", decision.get("tool", "tool"), result
                        )

                    if max_cycles and self.cycle >= max_cycles:
                        break
                    time.sleep(cycle_sleep)
                except Exception as e:
                    self.consecutive_failures += 1
                    logger.exception("Cycle %d crashed: %s", self.cycle, e)
                    self._save_agent_state({"last_error": str(e)})
                    self._send_notification("error", "agent_cycle", {"error": str(e)})
                    if self.consecutive_failures > 5:
                        logger.warning(
                            "More than 5 consecutive failures. Sleeping for 5 minutes."
                        )
                        time.sleep(300)
                        self.consecutive_failures = 0
                    else:
                        time.sleep(10)
        except KeyboardInterrupt:
            print(f"\n  Stopped. Cycles: {self.cycle} | Memory: {self.memory.stats()}")
