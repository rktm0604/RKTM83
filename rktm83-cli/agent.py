"""
rktm83-cli/agent.py - Python backend for TypeScript CLI
Provides a simple API for the TypeScript CLI to interact with the agent
"""

import sys
import json
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from run_agent import build_profile, load_skills, CONFIG
from agent_brain import Agent, PolicyEngine


def create_agent():
    """Create an agent instance"""
    cfg = CONFIG.get("agent", {})
    overrides = {k: v for k, v in CONFIG.get("policy", {}).items() 
                 if k != "search_interval_hours"}

    agent = Agent(
        name=cfg.get("name", "RKTM83"),
        profile=build_profile(CONFIG),
        memory_path=cfg.get("memory_path", "./rktm83_memory"),
        policy_overrides=overrides,
    )
    agent.context["config"] = CONFIG
    agent.brain.set_config(CONFIG)
    load_skills(agent, CONFIG)
    return agent


def handle_chat(message: str) -> str:
    """Handle chat command"""
    agent = create_agent()
    agent.context["user_command"] = message
    
    # Build prompt for the agent
    tools_str = "\n".join(f"- {n}: {i['description']}" for n, i in agent.brain._tools.items())
    prompt = f"""{agent.brain.profile}

USER: {message}

AVAILABLE TOOLS:
{tools_str}

Respond naturally. If you need to use a tool, respond in format:
ACTION: tool_name
PARAMS: {{"param": "value"}}

Otherwise, just respond as a helpful assistant."""

    # Get LLM response
    response = agent.brain._infer(prompt)
    
    # Check for tool usage
    if "ACTION:" in response and "PARAMS:" in response:
        try:
            import re
            action_match = re.search(r'ACTION:\s*(\w+)', response)
            params_match = re.search(r'PARAMS:\s*(\{.*?\})', response)
            
            if action_match and params_match:
                tool_name = action_match.group(1)
                tool_params = json.loads(params_match.group(1))
                
                result = agent.brain.execute(
                    {"tool": tool_name, "params": tool_params},
                    agent.context
                )
                
                if result.get("success"):
                    response = response.split("ACTION:")[0].strip()
                    response += f"\n\n[Tool executed: {tool_name}]"
                    if result.get("message"):
                        response += f"\n{result.get('message')}"
                else:
                    response += f"\n\n(Error: {result.get('error', 'unknown')})"
        except Exception as e:
            response += f"\n\n(Tool execution error: {str(e)})"
    
    return response


def handle_browse(url: str) -> str:
    """Handle browse command"""
    agent = create_agent()
    result = agent.brain.execute(
        {"tool": "browse_url", "params": {"url": url}},
        agent.context
    )
    
    if result.get("success"):
        return f"Opened: {result.get('title', 'Unknown')}\nURL: {result.get('url', url)}\n\nContent preview:\n{result.get('text', '')[:500]}"
    else:
        return f"Error: {result.get('error', 'Unknown error')}"


def handle_search(query: str) -> str:
    """Handle search command"""
    agent = create_agent()
    result = agent.brain.execute(
        {"tool": "search_web", "params": {"query": query, "max_results": 10}},
        agent.context
    )
    
    if result.get("success"):
        results = result.get("results", [])
        output = f"Found {len(results)} results for '{query}':\n\n"
        for i, r in enumerate(results, 1):
            output += f"{i}. {r.get('title', 'Untitled')}\n"
            output += f"   {r.get('url', '')}\n"
            output += f"   {r.get('snippet', '')[:100]}...\n\n"
        return output
    else:
        return f"Error: {result.get('error', 'Unknown error')}"


def handle_status() -> str:
    """Handle status command"""
    agent = create_agent()
    mem_stats = agent.memory.stats()
    policy_status = agent.policy.status()
    tools_count = len(agent.brain._tools)
    
    output = f"""╔════════════════════════════════════╗
║  🤖 RKTM83 - Status Report         ║
╚════════════════════════════════════╝

📊 Memory:
   Observations: {mem_stats.get('observations', 0)}
   Entities:    {mem_stats.get('entities', 0)}
   Actions:     {mem_stats.get('actions', 0)}

🔧 Tools: {tools_count} tools loaded
   • Browser (search, browse, fill forms)
   • Desktop (open apps, type, screenshot)
   • Filesystem (list, read, move files)
   • Email (send, read, reply)
   • Research (papers, professors)
   • GitHub (issues, trending)
   • Career (job search, outreach)
   • And more...

⚙️ Policy:
   LLM calls today: {policy_status.get('llm_calls', 0)}
   Search calls: {policy_status.get('search_calls', 0)}

🖥️ Config:
   Model: {CONFIG.get('brain', {}).get('ollama_model', 'llama3.2:3b')}
   Provider: {CONFIG.get('brain', {}).get('provider', 'ollama')}
"""
    return output


def handle_exec(tool: str, params: list) -> str:
    """Handle exec command - execute specific tool"""
    agent = create_agent()
    
    # Parse params
    tool_params = {}
    for param in params:
        if '=' in param:
            key, value = param.split('=', 1)
            tool_params[key] = value
    
    result = agent.brain.execute(
        {"tool": tool, "params": tool_params},
        agent.context
    )
    
    return json.dumps(result, indent=2)


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: agent.py <command> [args...]")
        sys.exit(1)
    
    command = sys.argv[1]
    
    try:
        if command == 'chat':
            message = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else "hello"
            print(handle_chat(message))
        
        elif command == 'browse':
            url = sys.argv[2] if len(sys.argv) > 2 else "example.com"
            print(handle_browse(url))
        
        elif command == 'search':
            query = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else "test"
            print(handle_search(query))
        
        elif command == 'status':
            print(handle_status())
        
        elif command == 'exec':
            tool = sys.argv[2] if len(sys.argv) > 2 else ""
            params = sys.argv[3:] if len(sys.argv) > 3 else []
            print(handle_exec(tool, params))
        
        else:
            print(f"Unknown command: {command}")
            print("Available: chat, browse, search, status, exec")
    
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()