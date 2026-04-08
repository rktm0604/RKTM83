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

import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("rktm83")

INFERENCE_TIMEOUT = 30


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
        self._config = {}
        logger.info("AgentBrain ready")

    def register_tool(self, name: str, description: str, handler):
        self._tools[name] = {"description": description, "handler": handler}
        logger.info("Tool: %s", name)

    def set_config(self, config: dict):
        """Set brain config from agent context."""
        self._config = config.get("brain", {})

    def _get_inference_config(self) -> dict:
        """Get LLM config from brain settings."""
        brain_cfg = self._config
        provider = brain_cfg.get("provider", "ollama")
        
        if provider == "gemini":
            return {
                "provider": "gemini",
                "model": brain_cfg.get("gemini_model", "gemini-2.0-flash"),
            }
        else:
            return {
                "provider": "ollama",
                "endpoint": os.environ.get("OLLAMA_URL", "http://localhost:11434"),
                "model": brain_cfg.get("ollama_model", "llama3.2:3b"),
            }

    def _infer(self, prompt: str) -> str:
        self.policy.record("llm")
        cfg = self._get_inference_config()
        
        if cfg["provider"] == "gemini":
            return self._call_gemini(prompt, cfg["model"])
        else:
            return self._call_ollama(prompt, cfg["endpoint"], cfg["model"])

    def _call_gemini(self, prompt: str, model: str) -> str:
        """Call Gemini API with fallback to Ollama."""
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            logger.warning("No GEMINI_API_KEY, falling back to Ollama")
            return self._call_ollama(prompt, "http://localhost:11434", "llama3.2:3b")
        
        try:
            import google.genai as genai
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model,
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
            )
            return response.text.strip() if response.text else ""
        except Exception as e:
            logger.warning("Gemini failed: %s, falling back to Ollama", e)
            fallback_cfg = self._config.get("fallback", True)
            if fallback_cfg:
                return self._call_ollama(prompt, "http://localhost:11434", "llama3.2:3b")
            return ""

    def _call_ollama(self, prompt: str, endpoint: str, model: str) -> str:
        """Call Ollama local API."""
        try:
            url = f"{endpoint}/api/generate"
            r = requests.post(
                url,
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=INFERENCE_TIMEOUT,
            )
            if r.status_code == 200:
                return r.json().get("response", "").strip()
        except Exception as e:
            logger.error("Ollama inference: %s", e)
        return ""

    def decide(self, context: dict) -> dict:
        if not self._tools:
            return {"tool": "wait", "params": {}, "reasoning": "no tools"}

        tools_str = "\n".join(f"- {n}: {i['description']}" for n, i in self._tools.items())

        # Build user command section first
        user_cmd = context.get("user_command", "")
        if user_cmd:
            # If it looks like a question or greeting → use chat tool
            chat_triggers = ("?", "what", "who", "how", "why", "hello", "hi ", "hey",
                            "can you", "tell me", "like your", "personality")
            is_question = any(t in user_cmd.lower() for t in chat_triggers)
            cmd_priority = "USE chat TOOL to reply to this message" if is_question else "highest priority — act on this now"
            user_cmd_section = f"USER COMMAND ({cmd_priority}): {user_cmd}\n"
        else:
            user_cmd_section = ""

        prompt = f"""{self.profile}

MEMORY: {json.dumps(self.memory.stats())}
POLICY: {json.dumps(self.policy.status())}
CONTEXT: {json.dumps({k: v for k, v in context.items() if k not in ("config","user_command")}, default=str)}

TOOLS:
{tools_str}

{user_cmd_section}Rules:
- If user_command is a question, greeting, or conversation → use "chat" tool
- If user_command is an action request ("search", "find", "send") → use the matching tool
- Do NOT pick the same tool as last_action
- When nothing to do → use "wait"

Reply ONLY in valid JSON with no extra text:
{{"tool": "name", "params": {{}}, "reasoning": "one line"}}"""

        text = self._infer(prompt)

        # ── Robust JSON extraction ─────────────────────────────────────────
        # LLM sometimes returns malformed JSON like {"params": {}
        # Strategy: try full match first, then progressively clean up
        decision = None
        if text:
            clean = re.sub(r'```(?:json)?|```', '', text).strip()

            # Try 1: direct parse of the whole response
            try:
                decision = json.loads(clean)
            except Exception:
                pass

            # Try 2: extract first {...} block (greedy)
            if not decision:
                try:
                    m = re.search(r'\{.*\}', clean, re.DOTALL)
                    if m:
                        decision = json.loads(m.group())
                except Exception:
                    pass

            # Try 3: extract tool name directly if JSON is broken
            if not decision:
                tool_match = re.search(r'"tool"\s*:\s*"([^"]+)"', clean)
                reason_match = re.search(r'"reasoning"\s*:\s*"([^"]+)"', clean)
                if tool_match:
                    decision = {
                        "tool":      tool_match.group(1),
                        "params":    {},
                        "reasoning": reason_match.group(1) if reason_match else "extracted from broken JSON",
                    }

        # Validate tool exists
        if decision and decision.get("tool") in self._tools:
            return decision

        # ── Fallback — pick anything that isn't last_action ────────────────
        last = context.get("last_action", "")
        reasoning = f"fallback — LLM said: {text[:60]}" if text else "fallback — no LLM response"
        for tool in self._tools:
            if tool != last:
                return {"tool": tool, "params": {}, "reasoning": reasoning}
        return {"tool": next(iter(self._tools)), "params": {}, "reasoning": reasoning}

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
        
        # Tools that need permission before running
        self.PERMISSION_REQUIRED = set()

        self.brain.register_tool("wait",   "Wait — nothing to do right now",          lambda p,c,b: {"success": True})

        def _chat(params, context, brain):
            """Generate a conversational reply to the user's message."""
            command = context.get("user_command", "")
            if not command:
                return {"success": False, "error": "no command to reply to"}

            prompt = f"""{brain.profile}

The user just said: "{command}"

Reply naturally in your personality. Be helpful, funny, and direct.
If they're asking what you can do, list your available tools: {list(brain._tools.keys())}
If they're asking you to do something specific, say you'll do it next cycle.
If they need permission for something, ask clearly.
Keep it under 3 sentences. No JSON — just plain conversational text."""

            reply = brain._infer(prompt)
            if reply:
                self._write_reply(reply, reply_type="chat")
                logger.info("[CHAT] replied to: %s", command[:50])
                return {"success": True, "replied": True}
            return {"success": False, "error": "LLM returned empty"}
        self.brain.register_tool("status", "Check and print agent memory and policy",  lambda p,c,b: self._status())
        self.brain.register_tool("chat",   "Reply conversationally to user messages — use when user_command is a question or greeting", _chat)
        logger.info("Agent '%s' ready", name)

    def _status(self):
        print(f"\n{'='*50}\n  {self.name} | Cycle {self.cycle}")
        print(f"  Memory : {self.memory.stats()}")
        print(f"  Policy : {self.policy.status()}\n{'='*50}\n")
        return {"success": True}

    REPLY_FILE = "agent_reply.json"

    # Tools that need permission before running
    PERMISSION_REQUIRED = set()  # populated by skills via agent.require_permission()

    def _write_reply(self, message: str, reply_type: str = "chat"):
        """Write a reply visible in the dashboard chat."""
        try:
            import json as _json
            with open(self.REPLY_FILE, "w") as f:
                _json.dump({
                    "message":   message,
                    "type":      reply_type,
                    "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                    "cycle":     self.cycle,
                }, f, indent=2)
        except Exception as e:
            logger.debug("Reply write failed: %s", e)

    def _ask_permission(self, tool: str, reasoning: str) -> bool:
        """
        Write a permission request to the reply file.
        Returns False — agent waits for user to approve via dashboard.
        """
        msg = (
            f"I want to run **{tool}** next.\n\n"
            f"Reason: *{reasoning}*\n\n"
            f"Type **yes** to approve or **no** to skip."
        )
        self._write_reply(msg, reply_type="permission")
        logger.info("[PERMISSION] Waiting for approval to run: %s", tool)
        return False

    def require_permission(self, tool_name: str):
        """Skills call this to mark a tool as requiring permission."""
        self.PERMISSION_REQUIRED.add(tool_name)
        logger.info("Permission required for tool: %s", tool_name)

    def _read_command(self) -> str:
        """Read a pending command from the dashboard. Returns empty string if none."""
        try:
            from pathlib import Path
            import json as _json
            cmd_file = Path("agent_command.json")
            if cmd_file.exists():
                with open(cmd_file) as f:
                    cmd = _json.load(f)
                if cmd.get("status") == "pending":
                    # Mark as read
                    cmd["status"] = "processing"
                    with open(cmd_file, "w") as f:
                        _json.dump(cmd, f, indent=2)
                    logger.info("[COMMAND] %s", cmd.get("command",""))
                    return cmd.get("command", "")
        except Exception:
            pass
        return ""

    def _mark_command_done(self):
        """Mark the current command as done."""
        try:
            from pathlib import Path
            import json as _json
            cmd_file = Path("agent_command.json")
            if cmd_file.exists():
                with open(cmd_file) as f:
                    cmd = _json.load(f)
                cmd["status"] = "done"
                with open(cmd_file, "w") as f:
                    _json.dump(cmd, f, indent=2)
        except Exception:
            pass

    def _write_log(self, decision: dict, result: dict):
        """Write current cycle state to agent_log.json for Web UI."""
        try:
            log_path = "agent_log.json"
            # Load existing log
            try:
                with open(log_path) as f:
                    log = json.load(f)
            except Exception:
                log = {"agent": self.name, "started": self.context.get("started",""), "cycles": []}

            # Add this cycle
            entry = {
                "cycle":     self.cycle,
                "time":      datetime.datetime.now().strftime("%H:%M:%S"),
                "tool":      decision.get("tool", ""),
                "reasoning": decision.get("reasoning", ""),
                "success":   result.get("success", False),
                "memory":    self.memory.stats(),
                "policy":    self.policy.status(),
            }
            log["cycles"].append(entry)
            log["cycles"] = log["cycles"][-50:]  # keep last 50 cycles
            log["latest"] = entry

            with open(log_path, "w") as f:
                json.dump(log, f, indent=2)
        except Exception as e:
            logger.debug("Log write failed: %s", e)

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

                # Check for user command from dashboard
                command = self._read_command()
                if command:
                    self.context["user_command"] = command
                    logger.info("[COMMAND RECEIVED] %s", command)
                else:
                    self.context.pop("user_command", None)

                decision = self.brain.decide(self.context)
                logger.info("[PLAN] %s — %s", decision.get("tool"), decision.get("reasoning"))
                result = self.brain.execute(decision, self.context)

                # Mark command done after execution
                if command:
                    self._mark_command_done()

                self.context["last_action"] = decision.get("tool")
                self.memory.observe(
                    f"cycle {self.cycle}: {decision.get('tool')}",
                    {"tool": decision.get("tool"), "cycle": str(self.cycle)}
                )

                # Write to agent_log.json for Web UI
                self._write_log(decision, result)

                if max_cycles and self.cycle >= max_cycles:
                    break
                time.sleep(cycle_sleep)

        except KeyboardInterrupt:
            print(f"\n  Stopped. Cycles: {self.cycle} | Memory: {self.memory.stats()}")
