#!/usr/bin/env python3
"""
MCP CLI Client
A simple command-line interface to interact with your Selenium MCP server.

Usage:
    python mcp_client.py --url http://localhost:8001/mcp/invoke
"""

import argparse
import glob
import json
import requests
import sys
from urllib.parse import urljoin
import re
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime
import os

LOG_FILE = os.path.join(os.getcwd(), "session_log.txt")
TOOL_CHAINING_ENABLED = True  # Set False to disable automatic chaining
MAX_CHAIN_STEPS = 3
_last_tool = None
_chain_depth = 0

# ─────────────────────────────────────────────
# Log file settings — automatically versioned in Downloads
# ─────────────────────────────────────────────
LOG_DIR = os.path.expanduser("~/Downloads")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(
    LOG_DIR,
    f"session_log_{datetime.now():%Y%m%d_%H%M%S}.txt"
)

# ────────────────────────────────────────────────────────────────
# Helper functions
# ────────────────────────────────────────────────────────────────

# _____________________________________________
# GPT-based natural language interpreter
# _____________________________________________
def interpret_command(nl_input: str):
    """
    Uses a GPT model to interpret a natural language instruction and map it
    to one of the available Selenium MCP tools with appropriate arguments.
    """
    client = OpenAI()   # assumes OPENAI_API_KEY is in your environment

    prompt = f"""
    You are an intent parser for a Selenium Model Context Protocol (MCP) client.

    Available tools and their required arguments:
      1. selenium_open_page(url)
         - Opens a web page in Selenium.
      2. selenium_click(selector)
         - Clicks an element using a CSS selector.
      3. selenium_get_text(selector)
         - Retrieves visible text content of an element.
      4. selenium_screenshot(filename)
         - Takes a screenshot and saves to a file.

    Instruction: "{nl_input}"

    Output only a valid JSON object with this structure:
    {{
      "tool": "<tool_name>",
      "arguments": {{ "<arg_name>": "<value>", ... }}
    }}

    Choose the tool that best fulfills the instruction.
    If information is missing, make a sensible default guess (e.g., "body" selector,
    "screenshot.png" filename, or "https://example.com" URL).
    Do not include explanations or prose—output JSON only.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )

        raw_text = response.choices[0].message.content.strip()
        parsed = json.loads(raw_text)
        return parsed.get("tool"), parsed.get("arguments", {})

    except Exception as e:
        print(f"❌ LLM interpretation failed: {e}")
        return None, {}

# _____________________________________________
# Chaining Function
# _____________________________________________
def suggest_next_tool(previous_tool, previous_result):
    """Ask GPT to suggest the next MCP tool and arguments, given the previous result."""
    if not TOOL_CHAINING_ENABLED:
        return None, None

    try:
        from openai import OpenAI
        client = OpenAI()

        prompt = f"""
        You are an automation planner. The last MCP tool executed was '{previous_tool}'.
        Its JSON result was:
        {json.dumps(previous_result, indent=2)}

        The available tools are:
        - selenium_open_page(url)
        - selenium_click(selector)
        - selenium_get_text(selector)
        - selenium_screenshot(filename)

        Suggest the next logical tool to call (if any) and its arguments
        as a compact JSON: {{ "tool": ..., "arguments": ... }}.
        If no next action makes sense, respond with null.
        """

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            max_output_tokens=200,
        )

        content = response.output_text.strip()
        suggestion = json.loads(content) if content and "null" not in content else None

        if suggestion:
            tool = suggestion.get("tool")
            args = suggestion.get("arguments", {})
            return tool, args
        else:
            return None, None

    except Exception as e:
        print(f"⚠️  Tool chaining suggestion failed: {e}")
        return None, None

# ─────────────────────────────────────────────
# Helper to pretty-print JSON
# ─────────────────────────────────────────────
def print_json(data):
    print(json.dumps(data, indent=2))

# ─────────────────────────────────────────────
# Logging helper
# ─────────────────────────────────────────────
def log_session_entry(command, tool, args, response):
    """Append a timestamped record of command, interpretation, and result to session_log.txt."""
    try:
        with open(LOG_FILE, "a") as f:
            f.write("──────────────────────────────────────────────\n")
            f.write(f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"💬 Command: {command}\n")
            if tool:
                f.write(f"🧠 Interpreted Tool: {tool}\n")
                f.write(f"🔸 Arguments: {json.dumps(args, indent=2)}\n")
            if response:
                f.write(f"✅ Response:\n{json.dumps(response, indent=2)}\n")
            f.write("\n")
    except Exception as e:
        print(f"⚠️ Could not write to log: {e}")

def cleanup_old_logs(directory, keep=10):
    """Keep only the most recent N log files in the given directory."""
    try:
        logs = sorted(
            glob.glob(os.path.join(directory, "session_log_*.txt")),
            key=os.path.getmtime,
            reverse=True
        )
        if len(logs) > keep:
            old_logs = logs[keep:]
            for old_log in old_logs:
                os.remove(old_log)
            print(f"🧹 Cleaned up {len(old_logs)} old log(s), keeping {keep} most recent.")
    except Exception as e:
        print(f"⚠️  Log cleanup failed: {e}")


# ─────────────────────────────────────────────
# Function that sends the invocation request
# ─────────────────────────────────────────────
def invoke_mcp(base_url, tool, arguments, original_cmd=None):
    """Send a tool invocation request to the MCP server and log the result."""
    try:
        payload = {"tool": tool, "arguments": arguments}
        print(f"🔹 Invoking MCP tool: {tool}")
        print(f"🔸 Arguments: {arguments}\n")

        r = requests.post(base_url, json=payload, timeout=20)

        # --- safer request + JSON parsing ---
        try:
            r.raise_for_status()
            try:
                result_json = r.json()
            except ValueError:
                print(f"⚠️  Non-JSON or empty response:\n{r.text[:500]}")
                result_json = {"status": "error", "error": "Empty or invalid JSON"}
        except requests.exceptions.RequestException as e:
            print(f"❌ HTTP error: {e}")
            print(f"⚙️  Raw response:\n{getattr(e.response, 'text', '(no body)')}")
            result_json = {"status": "error", "error": str(e)}

        print("✅ MCP Response:")
        print_json(result_json)

        # Log successful transaction
        log_session_entry(original_cmd or tool, tool, arguments, result_json)

        # Attempt automatic chaining based on GPT reasoning
        global _last_tool, _chain_depth
        if TOOL_CHAINING_ENABLED:
            _chain_depth += 1
            if _chain_depth > MAX_CHAIN_STEPS:
                print(f"🛑 Reached max chain depth ({MAX_CHAIN_STEPS}). Stopping.")
                _chain_depth = 0
                return

            next_tool, next_args = suggest_next_tool(tool, result_json)
            if next_tool:
                if next_tool == _last_tool:
                    print(f"🛑 Detected repetitive tool suggestion '{next_tool}'. Stopping chain.")
                    _chain_depth = 0
                    return
                _last_tool = next_tool
                print(f"🤖 GPT suggests next tool: {next_tool} → {next_args}")
                invoke_mcp(base_url, next_tool, next_args, original_cmd=f"[AUTOCHAIN] {next_tool}")
            else:
                print("✅ No further tool suggested. Chain complete.")
                _chain_depth = 0

    except requests.exceptions.RequestException as e:
        print(f"❌ HTTP error: {e}")
        # Log failure
        log_session_entry(original_cmd or tool, tool, arguments, {"error": str(e)})

    finally:
        # Always clean up old logs — success or error
        cleanup_old_logs(LOG_DIR, keep=10)


def interactive_loop(base_url):
    """Interactive shell that auto-discovers available MCP tools."""
    print("\n=== Selenium MCP CLI Client ===")
    print(f"Connected to: {base_url}")

    # ── fetch /mcp/schema once ────────────────────────────────────────────────
    schema_url = base_url.replace("/invoke", "/schema")
    try:
        r = requests.get(schema_url, timeout=10)
        r.raise_for_status()
        schema = r.json()
        tools = [t["function"]["name"] for t in schema.get("tools", [])]
        print(f"Discovered tools: {', '.join(tools)}")
    except Exception as e:
        print(f"⚠️  Could not fetch schema automatically: {e}")
        tools = []

    print("Type 'help' for options, 'exit' to quit.\n")

    # ── main loop ─────────────────────────────────────────────────────────────
    while True:
        try:
            cmd = input("mcp> ").strip()
            if not cmd:
                continue
            if cmd.lower() in {"exit", "quit"}:
                print("👋 Exiting MCP CLI. Goodbye!")
                break
            if cmd.lower() == "help":
                print("Available commands:")
                for name in tools:
                    print(f"  {name}")
                print("  schema   → re-fetch schema")
                print("  exit     → quit\n")
                print("  nl:<instruction> → natural language mode")
                continue
            if cmd.lower() == "schema":
                r = requests.get(schema_url, timeout=10)
                print_json(r.json())
                continue

            # ── Natural-language mode (prefix “nl:”) ─────────────────────────────
            if cmd.lower().startswith("nl:"):
                nl_input = cmd[3:].strip()
                tool, args = interpret_command(nl_input)
                if tool:
                    print(f"🧠 Interpreted as {tool} with args {args}")
                    invoke_mcp(base_url, tool, args)
                else:
                    print("❓ Sorry, I couldn't interpret that instruction.")
                continue

            # ── invoke any discovered tool ───────────────────────────────────────
            if cmd in tools:
                args = {}
                # read parameter schema from the cached definition
                tool_def = next(t for t in schema["tools"] if t["function"]["name"] == cmd)
                params = tool_def["function"]["parameters"]["properties"]
                for p, info in params.items():
                    val = input(f"{p} ({info.get('description','')}): ").strip()
                    args[p] = val
                invoke_mcp(base_url, cmd, args)
            else:
                # ── Attempt GPT-based interpretation for any unknown command ─────────────
                print(f"🤖 Interpreting as natural language: {cmd}")
                tool, args = interpret_command(cmd)
                if tool:
                    print(f"🧠 Interpreted as {tool} with args {args}")
                    invoke_mcp(base_url, tool, args)
                else:
                    print("❓ Sorry, I couldn't interpret that instruction.")

        except KeyboardInterrupt:
            print("\n🛑 Interrupted by user.")
            break
        except EOFError:
            print("\n👋 Exiting.")
            break

# ────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Command-line client for the Selenium MCP server."
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://localhost:8001/mcp/invoke",
        help="Base MCP invoke URL (default: http://localhost:8001/mcp/invoke)",
    )
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    interactive_loop(base_url)


if __name__ == "__main__":
    main()
