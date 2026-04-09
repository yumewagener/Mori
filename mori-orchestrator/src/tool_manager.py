"""
Tool registry and execution for mori-orchestrator.

Supported tool categories:
  - MCP tools  — forwarded to the MCP gateway (env MORI_MCP_URL)
  - web_search — SearXNG-backed web search
  - shell      — allow-listed shell commands
  - browser    — Playwright-based browser automation (requires tools.browser.enabled)
  - code       — sandboxed Python code execution (requires tools.shell.enabled)
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
import time
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
    "code_execute": {
        "type": "function",
        "function": {
            "name": "code_execute",
            "description": "Execute Python code in a sandboxed environment and return the output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute.",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Execution timeout in seconds (default 30).",
                        "default": 30,
                    },
                },
                "required": ["code"],
            },
        },
    },
}

_BROWSER_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Navegar a una URL en el navegador",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "URL a visitar"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_get_text",
            "description": "Obtener el texto visible de la página actual",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Hacer click en un elemento CSS selector",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string"}},
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_fill",
            "description": "Rellenar un campo de formulario",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["selector", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Tomar un screenshot de la página actual",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


# ---------------------------------------------------------------------------
# BrowserTool
# ---------------------------------------------------------------------------


class BrowserTool:
    """Playwright-based browser tool. Only active when tools.browser.enabled=True."""

    def __init__(self, config: MoriConfig) -> None:
        self.config = config
        self._browser = None
        self._page = None

    @property
    def enabled(self) -> bool:
        return self.config.tools.browser.enabled

    async def _ensure_browser(self) -> None:
        if self._browser is None:
            from playwright.async_api import async_playwright

            pw = await async_playwright().start()
            self._browser = await pw.chromium.launch(
                headless=self.config.tools.browser.headless
            )
        if self._page is None or self._page.is_closed():
            self._page = await self._browser.new_page()

    async def navigate(self, url: str) -> str:
        await self._ensure_browser()
        await self._page.goto(url, wait_until="networkidle", timeout=30000)
        title = await self._page.title()
        return f"Navegado a: {url} (título: {title})"

    async def get_text(self) -> str:
        if not self._page:
            return "Error: no hay página activa"
        text = await self._page.inner_text("body")
        return text[:3000]  # limit

    async def click(self, selector: str) -> str:
        await self._ensure_browser()
        await self._page.click(selector, timeout=10000)
        return f"Click en: {selector}"

    async def fill(self, selector: str, value: str) -> str:
        await self._ensure_browser()
        await self._page.fill(selector, value)
        return f"Relleno: {selector} = {value}"

    async def screenshot(self) -> str:
        if not self._page:
            return "Error: no hay página activa"
        path = f"/tmp/mori_screenshot_{int(time.time())}.png"
        await self._page.screenshot(path=path)
        return f"Screenshot guardado: {path}"

    async def evaluate(self, js: str) -> str:
        await self._ensure_browser()
        result = await self._page.evaluate(js)
        return str(result)[:1000]

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
            self._browser = None
            self._page = None


# ---------------------------------------------------------------------------
# CodeInterpreter
# ---------------------------------------------------------------------------


class CodeInterpreter:
    """Sandboxed Python code execution with timeout."""

    def __init__(self, config: MoriConfig) -> None:
        self.config = config

    @property
    def enabled(self) -> bool:
        # Available when shell tool is enabled
        return self.config.tools.shell.enabled

    async def execute(self, code: str, timeout: int = 30) -> str:
        """Execute Python code in a restricted environment."""
        import sys
        import tempfile

        # Write code to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            tmp_path = f.name

        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    sys.executable,
                    tmp_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=timeout,
            )
            stdout, stderr = await proc.communicate()
            output = stdout.decode()[:2000]
            errors = stderr.decode()[:500]
            if errors:
                return f"Output:\n{output}\nErrors:\n{errors}"
            return output or "(sin output)"
        except asyncio.TimeoutError:
            return f"Error: timeout después de {timeout}s"
        except Exception as e:
            return f"Error: {e}"
        finally:
            os.unlink(tmp_path)


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
        self.browser_tool = BrowserTool(config)
        self.code_interpreter = CodeInterpreter(config)

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
        await self.browser_tool.close()

    # ------------------------------------------------------------------
    # Schema registry
    # ------------------------------------------------------------------

    def get_tools_schema(self, tool_ids: list[str]) -> list[dict]:
        """
        Return the OpenAI-compatible tool schemas for the given *tool_ids*.

        Recognised IDs:
          - "web_search"       (requires tools.web_search.enabled)
          - "shell"            (requires tools.shell.enabled)
          - "read_file"        (always available)
          - "write_file"       (always available)
          - "mcp"              (requires MORI_MCP_URL to be reachable)
          - "code_execute"     (requires tools.shell.enabled)
          - "browser_navigate" / "browser_*"  (requires tools.browser.enabled)
          - Any unknown ID is passed through as a generic mcp-routed tool.
        """
        schemas: list[dict] = []
        seen: set[str] = set()

        # Browser tool IDs (injected when browser is enabled)
        browser_tool_names = {s["function"]["name"] for s in _BROWSER_TOOL_SCHEMAS}

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

            elif tid == "code_execute":
                if not self.code_interpreter.enabled:
                    log.debug("tool_disabled", tool=tid)
                    continue
                schemas.append(_BUILTIN_TOOL_SCHEMAS["code_execute"])

            elif tid in browser_tool_names:
                # Skip individual browser tool IDs when browser is disabled
                if not self.browser_tool.enabled:
                    log.debug("tool_disabled", tool=tid)
                    continue
                # Find matching schema from browser schemas list
                for s in _BROWSER_TOOL_SCHEMAS:
                    if s["function"]["name"] == tid:
                        schemas.append(s)
                        break

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

        # Browser tools (only when enabled) — append ALL browser schemas
        # if "browser" (wildcard) was listed as a tool ID
        if "browser" in tool_ids and self.browser_tool.enabled:
            for s in _BROWSER_TOOL_SCHEMAS:
                name = s["function"]["name"]
                if name not in seen:
                    seen.add(name)
                    schemas.append(s)

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
        elif name == "code_execute":
            return await self.code_interpreter.execute(
                arguments.get("code", ""),
                arguments.get("timeout", 30),
            )
        elif name == "browser_navigate":
            return await self.browser_tool.navigate(arguments.get("url", ""))
        elif name == "browser_get_text":
            return await self.browser_tool.get_text()
        elif name == "browser_click":
            return await self.browser_tool.click(arguments.get("selector", ""))
        elif name == "browser_fill":
            return await self.browser_tool.fill(
                arguments.get("selector", ""), arguments.get("value", "")
            )
        elif name == "browser_screenshot":
            return await self.browser_tool.screenshot()
        else:
            # Try MCP gateway for any unknown tool
            return await self._mcp_call(name, arguments)

    # ------------------------------------------------------------------
    # Shell (public wrapper for testing)
    # ------------------------------------------------------------------

    async def execute_shell(self, command: str, working_directory: Optional[str] = None) -> str:
        """Public wrapper around _shell — used by tests and external callers."""
        return await self._shell(command=command, working_directory=working_directory)

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
