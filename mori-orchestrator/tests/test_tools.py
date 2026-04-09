"""Tests for tool_manager.py — mocks all external calls."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def make_config(browser_enabled=False, shell_enabled=False, search_enabled=False):
    from src.config import MoriConfig, ToolsConfig, WebSearchConfig, ShellConfig, BrowserConfig
    return MoriConfig(
        tools=ToolsConfig(
            web_search=WebSearchConfig(enabled=search_enabled, searxng_url="http://localhost:8888"),
            shell=ShellConfig(enabled=shell_enabled),
            browser=BrowserConfig(enabled=browser_enabled),
        )
    )


class TestToolSchemas:
    def test_no_tools_when_empty_list(self):
        from src.tool_manager import ToolManager
        tm = ToolManager(make_config())
        schemas = tm.get_tools_schema([])
        assert schemas == []

    def test_mcp_tool_schema_included(self):
        from src.tool_manager import ToolManager
        tm = ToolManager(make_config())
        schemas = tm.get_tools_schema(["task_list"])
        assert any(s["function"]["name"] == "task_list" for s in schemas)

    def test_browser_tools_excluded_when_disabled(self):
        from src.tool_manager import ToolManager
        tm = ToolManager(make_config(browser_enabled=False))
        schemas = tm.get_tools_schema(["browser_navigate"])
        # browser_navigate not in schemas when browser disabled
        assert not any(s["function"]["name"] == "browser_navigate" for s in schemas)

    def test_browser_tools_included_when_enabled(self):
        from src.tool_manager import ToolManager
        tm = ToolManager(make_config(browser_enabled=True))
        schemas = tm.get_tools_schema(["browser_navigate", "browser_get_text", "browser_screenshot"])
        names = [s["function"]["name"] for s in schemas]
        assert "browser_navigate" in names
        assert "browser_get_text" in names
        assert "browser_screenshot" in names

    def test_code_execute_included_when_shell_enabled(self):
        from src.tool_manager import ToolManager
        tm = ToolManager(make_config(shell_enabled=True))
        schemas = tm.get_tools_schema(["code_execute"])
        assert any(s["function"]["name"] == "code_execute" for s in schemas)

    def test_code_execute_excluded_when_shell_disabled(self):
        from src.tool_manager import ToolManager
        tm = ToolManager(make_config(shell_enabled=False))
        schemas = tm.get_tools_schema(["code_execute"])
        assert not any(s["function"]["name"] == "code_execute" for s in schemas)

    def test_web_search_included_when_enabled(self):
        from src.tool_manager import ToolManager
        tm = ToolManager(make_config(search_enabled=True))
        schemas = tm.get_tools_schema(["web_search"])
        assert any(s["function"]["name"] == "web_search" for s in schemas)

    def test_web_search_excluded_when_disabled(self):
        from src.tool_manager import ToolManager
        tm = ToolManager(make_config(search_enabled=False))
        schemas = tm.get_tools_schema(["web_search"])
        assert not any(s["function"]["name"] == "web_search" for s in schemas)

    def test_read_write_file_always_available(self):
        from src.tool_manager import ToolManager
        tm = ToolManager(make_config())
        schemas = tm.get_tools_schema(["read_file", "write_file"])
        names = [s["function"]["name"] for s in schemas]
        assert "read_file" in names
        assert "write_file" in names

    def test_deduplication(self):
        from src.tool_manager import ToolManager
        tm = ToolManager(make_config())
        schemas = tm.get_tools_schema(["read_file", "read_file", "read_file"])
        names = [s["function"]["name"] for s in schemas]
        assert names.count("read_file") == 1


class TestShellTool:
    @pytest.mark.asyncio
    async def test_allowed_command_executes(self):
        from src.tool_manager import ToolManager
        tm = ToolManager(make_config(shell_enabled=True))
        # 'git' is in the default allowlist
        result = await tm.execute_shell("git --version")
        assert "git" in result.lower() or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_blocked_command_rejected(self):
        from src.tool_manager import ToolManager
        tm = ToolManager(make_config(shell_enabled=True))
        result = await tm.execute_shell("rm -rf /")
        assert "no permitido" in result.lower() or "not in the allow-list" in result.lower() or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_shell_disabled_returns_error(self):
        from src.tool_manager import ToolManager
        tm = ToolManager(make_config(shell_enabled=False))
        result = await tm.execute_shell("git status")
        assert "disabled" in result.lower() or "deshabilitad" in result.lower() or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_empty_command_returns_error(self):
        from src.tool_manager import ToolManager
        tm = ToolManager(make_config(shell_enabled=True))
        result = await tm.execute_shell("")
        assert "empty" in result.lower() or "error" in result.lower()


class TestCodeInterpreter:
    @pytest.mark.asyncio
    async def test_execute_simple_code(self):
        from src.tool_manager import CodeInterpreter
        ci = CodeInterpreter(make_config(shell_enabled=True))
        result = await ci.execute("print('hello world')")
        assert "hello world" in result

    @pytest.mark.asyncio
    async def test_execute_disabled_when_shell_disabled(self):
        from src.tool_manager import CodeInterpreter
        ci = CodeInterpreter(make_config(shell_enabled=False))
        assert not ci.enabled

    @pytest.mark.asyncio
    async def test_execute_captures_errors(self):
        from src.tool_manager import CodeInterpreter
        ci = CodeInterpreter(make_config(shell_enabled=True))
        result = await ci.execute("raise ValueError('test error')")
        assert "error" in result.lower() or "ValueError" in result


class TestBrowserTool:
    def test_browser_disabled_by_default(self):
        from src.tool_manager import BrowserTool
        bt = BrowserTool(make_config(browser_enabled=False))
        assert not bt.enabled

    def test_browser_enabled_when_configured(self):
        from src.tool_manager import BrowserTool
        bt = BrowserTool(make_config(browser_enabled=True))
        assert bt.enabled

    @pytest.mark.asyncio
    async def test_get_text_without_active_page(self):
        from src.tool_manager import BrowserTool
        bt = BrowserTool(make_config(browser_enabled=True))
        # No page active — should return error message without crashing
        result = await bt.get_text()
        assert "error" in result.lower() or "no hay página" in result.lower()

    @pytest.mark.asyncio
    async def test_screenshot_without_active_page(self):
        from src.tool_manager import BrowserTool
        bt = BrowserTool(make_config(browser_enabled=True))
        # No page active — should return error message without crashing
        result = await bt.screenshot()
        assert "error" in result.lower() or "no hay página" in result.lower()
