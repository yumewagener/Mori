"""
Tool registry and execution for mori-orchestrator.

Supported tool categories:
  - MCP tools  — forwarded to the MCP gateway (env MORI_MCP_URL)
  - web_search — SearXNG-backed web search
  - shell      — allow-listed shell commands
  - builtin    — utility functions (always available)

Tool schemas follow the OpenAI function-calling format so they can be
passed directly to litellm.acompletion as the ``tools`` parameter.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
from typing import Any, Optional

import aiohttp
import structlog

from .config import MoriConfig

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Tool schema definitions (OpenAI-compatible)
# ---------------------------------------------------------------------------

_BUILTIN_TOOL_SCHEMAS: dict[str, dict] = {
    "web_search": {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web via SearXNG and return the top results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results to return (1-10).",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    "shell": {
        "type": "function",
        "function": {
            "name": "shell",
            "description": "Run an allow-listed shell command and return stdout/stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Full shell command string (e.g. 'git status').",
                    },
                    "working_directory": {
                        "type": "string",
                        "description": "Directory to run the command in (optional).",
                    },
                },
                "required": ["command"],
            },
        },
    },
    "read_file": {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative path to the file.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    "write_file": {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file (creates or overwrites).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to write to.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Text content to write.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    "mcp": {
        "type": "function",
        "function": {
            "name": "mcp",
            "description": (
                "Call an MCP (Model Context Protocol) tool via the MCP gateway. "
                "Useful for Obsidian notes, calendar, and other integrations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": "Name of the MCP tool to invoke.",
                    },
                    "arguments": {
                        "type": "object",
                        "description": "Tool-specific arguments dict.",
                    },
                },
                "required": ["tool_name"],
            },
        },
    },
}


# ---------------------------------------------------------------------------
# ToolManager
# ---------------------------------------------------------------------------


class ToolManager:
    """
    Registry and executor for all tools available to agents.

    MCP tool definitions are fetched lazily from the MCP gateway on first use.
    """

    def __init__(self, config: MoriConfig) -> None:
        self.config = config
        self.mcp_url = os.environ.get("MORI_MCP_URL", "http://mcp-gateway:18810")
        self._mcp_tools_cache: Optional[list[dict]] = None
        self._session: Optional[aiohttp.ClientSession] = None

    # ------------------------------------------------------------------
    # HTTP session
    # ------------------------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=60),
                connector=aiohttp.TCPConnector(limit=10),
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # Schema registry
    # ------------------------------------------------------------------

    def get_tools_schema(self, tool_ids: list[str]) -> list[dict]:
        """
        Return the OpenAI-compatible tool schemas for the given *tool_ids*.

        Recognised IDs:
          - "web_search"  (requires tools.web_search.enabled)
          - "shell"       (requires tools.shell.enabled)
          - "read_file"   (always available)
          - "write_file"  (always available)
          - "mcp"         (requires MORI_MCP_URL to be reachable)
          - Any unknown ID is passed through as a generic mcp-routed tool.
        """
        schemas: list[dict] = []
        seen: set[str] = set()

        for tid in tool_ids:
            if tid in seen:
                continue
            seen.add(tid)

            if tid == "web_search":
                if not self.config.tools.web_search.enabled:
                    log.debug("tool_disabled", tool=tid)
                    continue
                schemas.append(_BUILTIN_TOOL_SCHEMAS["web_search"])

            elif tid == "shell":
                if not self.config.tools.shell.enabled:
                    log.debug("tool_disabled", tool=tid)
                    continue
                schemas.append(_BUILTIN_TOOL_SCHEMAS["shell"])

            elif tid in ("read_file", "write_file"):
                schemas.append(_BUILTIN_TOOL_SCHEMAS[tid])

            elif tid == "mcp":
                schemas.append(_BUILTIN_TOOL_SCHEMAS["mcp"])

            else:
                # Unknown tool IDs → expose as a generic MCP-routed tool
                schemas.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tid,
                            "description": f"MCP tool: {tid}",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "arguments": {
                                        "type": "object",
                                        "description": "Arguments for the tool.",
                                    }
                                },
                                "required": [],
                            },
                        },
                    }
                )

        return schemas

    # ------------------------------------------------------------------
    # Execution dispatcher
    # ------------------------------------------------------------------

    async def execute_tool_calls(self, tool_calls: list) -> list[dict]:
        """
        Execute a list of tool calls (as returned by the LLM) concurrently.

        Each call returns::

            {
                "tool_call_id": str,
                "name": str,
                "result": str,   # always a string for the LLM
            }
        """
        tasks = [self._execute_one(tc) for tc in tool_calls]
        return await asyncio.gather(*tasks)

    async def _execute_one(self, tool_call) -> dict:
        name: str = tool_call.function.name
        tool_call_id: str = tool_call.id

        # Parse arguments
        try:
            raw_args = tool_call.function.arguments
            arguments: dict = json.loads(raw_args) if raw_args else {}
        except (json.JSONDecodeError, TypeError) as exc:
            return {
                "tool_call_id": tool_call_id,
                "name": name,
                "result": f"Error: could not parse tool arguments — {exc}",
            }

        log.info("tool_call", name=name, tool_call_id=tool_call_id)

        try:
            result = await self._dispatch(name, arguments)
        except Exception as exc:
            log.warning("tool_execution_error", name=name, error=str(exc))
            result = f"Error executing {name}: {exc}"

        return {
            "tool_call_id": tool_call_id,
            "name": name,
            "result": str(result),
        }

    async def _dispatch(self, name: str, arguments: dict) -> str:
        if name == "web_search":
            return await self._web_search(**arguments)
        elif name == "shell":
            return await self._shell(**arguments)
        elif name == "read_file":
            return self._read_file(**arguments)
        elif name == "write_file":
            return self._write_file(**arguments)
        elif name == "mcp":
            return await self._mcp_call(
                arguments.get("tool_name", ""),
                arguments.get("arguments", {}),
            )
        else:
            # Try MCP gateway for any unknown tool
            return await self._mcp_call(name, arguments)

    # ------------------------------------------------------------------
    # Web search (SearXNG)
    # ------------------------------------------------------------------

    async def _web_search(self, query: str, num_results: int = 5) -> str:
        searxng_url = self.config.tools.web_search.searxng_url
        params = {
            "q": query,
            "format": "json",
            "engines": "google,bing,duckduckgo",
        }
        session = await self._get_session()
        try:
            async with session.get(
                f"{searxng_url}/search",
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return f"SearXNG returned HTTP {resp.status}"
                data = await resp.json()
        except asyncio.TimeoutError:
            return "Web search timed out."
        except Exception as exc:
            return f"Web search error: {exc}"

        results = data.get("results", [])[:num_results]
        if not results:
            return "No results found."

        lines = [f"Search results for: {query}\n"]
        for i, r in enumerate(results, 1):
            lines.append(
                f"{i}. {r.get('title', '')}\n"
                f"   URL: {r.get('url', '')}\n"
                f"   {r.get('content', '')[:300]}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Shell
    # ------------------------------------------------------------------

    async def _shell(
        self, command: str, working_directory: Optional[str] = None
    ) -> str:
        cfg = self.config.tools.shell
        if not cfg.enabled:
            return "Shell tool is disabled in config."

        # Validate the first token against the allow-list
        try:
            tokens = shlex.split(command)
        except ValueError as exc:
            return f"Invalid command: {exc}"

        if not tokens:
            return "Empty command."

        base_cmd = os.path.basename(tokens[0])
        if base_cmd not in cfg.allowed_commands:
            return (
                f"Command '{base_cmd}' is not in the allow-list: "
                f"{cfg.allowed_commands}"
            )

        cwd = working_directory if (working_directory and not cfg.working_directory_only) else None

        try:
            proc = await asyncio.create_subprocess_exec(
                *tokens,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        except asyncio.TimeoutError:
            return f"Command timed out after 120s: {command}"
        except Exception as exc:
            return f"Shell error: {exc}"

        out = stdout.decode(errors="replace")
        err = stderr.decode(errors="replace")
        parts = []
        if out:
            parts.append(f"STDOUT:\n{out}")
        if err:
            parts.append(f"STDERR:\n{err}")
        if proc.returncode != 0:
            parts.append(f"Exit code: {proc.returncode}")
        return "\n".join(parts) if parts else "(no output)"

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _read_file(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(50_000)  # cap at ~50 KB
            if len(content) == 50_000:
                content += "\n… (truncated)"
            return content
        except FileNotFoundError:
            return f"File not found: {path}"
        except Exception as exc:
            return f"Error reading {path}: {exc}"

    def _write_file(self, path: str, content: str) -> str:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Written {len(content)} characters to {path}"
        except Exception as exc:
            return f"Error writing {path}: {exc}"

    # ------------------------------------------------------------------
    # MCP gateway
    # ------------------------------------------------------------------

    async def _mcp_call(self, tool_name: str, arguments: dict) -> str:
        if not tool_name:
            return "Error: tool_name is required for MCP calls."

        payload = {"name": tool_name, "arguments": arguments}
        session = await self._get_session()
        try:
            async with session.post(
                f"{self.mcp_url}/tools/call",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                body = await resp.text()
                if resp.status != 200:
                    return f"MCP gateway returned HTTP {resp.status}: {body[:500]}"
                try:
                    data = json.loads(body)
                    # MCP response may be {content: [{type: "text", text: "..."}]}
                    if isinstance(data, dict):
                        if "content" in data:
                            parts = data["content"]
                            if isinstance(parts, list):
                                return "\n".join(
                                    p.get("text", str(p))
                                    for p in parts
                                    if p.get("type") == "text"
                                )
                        if "result" in data:
                            return str(data["result"])
                    return body
                except json.JSONDecodeError:
                    return body
        except asyncio.TimeoutError:
            return f"MCP tool '{tool_name}' timed out."
        except Exception as exc:
            return f"MCP call error for '{tool_name}': {exc}"

    # ------------------------------------------------------------------
    # MCP tool discovery (optional, for dynamic tool listing)
    # ------------------------------------------------------------------

    async def discover_mcp_tools(self) -> list[dict]:
        """
        Fetch available tool schemas from the MCP gateway (GET /tools).
        Results are cached for the lifetime of this process.
        """
        if self._mcp_tools_cache is not None:
            return self._mcp_tools_cache

        session = await self._get_session()
        try:
            async with session.get(
                f"{self.mcp_url}/tools",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    log.warning("mcp_discover_failed", status=resp.status)
                    return []
                data = await resp.json()
                tools = data if isinstance(data, list) else data.get("tools", [])
                self._mcp_tools_cache = tools
                log.info("mcp_tools_discovered", count=len(tools))
                return tools
        except Exception as exc:
            log.warning("mcp_discover_error", error=str(exc))
            return []
