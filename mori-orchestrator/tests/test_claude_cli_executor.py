"""
Tests for the claude-cli provider in Executor.

These tests mock asyncio.create_subprocess_exec so no real Claude CLI
is needed to run the suite.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import AgentConfig, ModelConfig, MoriConfig, OrchestratorConfig
from src.executor import AgentResult, Executor
from src.model_registry import ModelRegistry


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_config(model_cfg: ModelConfig) -> MoriConfig:
    return MoriConfig(
        orchestrator=OrchestratorConfig(),
        models=[model_cfg],
        agents=[],
        pipelines=[],
    )


def _make_cli_model(**kwargs) -> ModelConfig:
    defaults = dict(
        id="claude-max",
        provider="claude-cli",
        model="claude-sonnet-4-5",
        cli_path="claude",
        allowed_tools=["Read", "Edit", "Bash"],
        max_turns=10,
    )
    defaults.update(kwargs)
    return ModelConfig(**defaults)


def _make_agent(model_id: str = "claude-max") -> AgentConfig:
    return AgentConfig(
        id="test-agent",
        name="Test Agent",
        model=model_id,
        role="executor",
        system_prompt="You are a test agent.",
    )


def _make_task(title: str = "Test task", description: str = "") -> dict:
    return {"id": "task-1", "title": title, "description": description}


def _make_executor(model_cfg: ModelConfig) -> Executor:
    config = _make_config(model_cfg)
    stream = MagicMock()
    stream.push = AsyncMock()
    stream.push_tool_result = AsyncMock()
    tool_manager = MagicMock()
    tool_manager.get_tools_schema = MagicMock(return_value=[])
    return Executor(config=config, db=None, tool_manager=tool_manager, stream=stream)


# ---------------------------------------------------------------------------
# Fake subprocess
# ---------------------------------------------------------------------------


@dataclass
class _FakeProcess:
    """Simulates asyncio.subprocess.Process with pre-baked stdout lines."""

    lines: list[bytes] = field(default_factory=list)
    returncode: int = 0
    _stderr_data: bytes = b""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def wait(self):
        return self.returncode

    async def kill(self):
        pass

    @property
    def stdout(self):
        return _AsyncIterLines(self.lines)

    @property
    def stderr(self):
        return _FakeStderr(self._stderr_data)


@dataclass
class _FakeStderr:
    data: bytes

    async def read(self):
        return self.data


class _AsyncIterLines:
    """Async iterable that yields bytes lines."""

    def __init__(self, lines: list[bytes]) -> None:
        self._iter = iter(lines)

    def __aiter__(self):
        return self

    async def __anext__(self) -> bytes:
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


# ---------------------------------------------------------------------------
# Model config tests
# ---------------------------------------------------------------------------


class TestModelConfig:
    def test_is_cli_provider_true(self):
        m = _make_cli_model()
        assert m.is_cli_provider is True

    def test_is_cli_provider_false_for_anthropic(self):
        m = ModelConfig(id="x", provider="anthropic", model="claude-sonnet-4-5")
        assert m.is_cli_provider is False

    def test_default_cli_path(self):
        m = _make_cli_model()
        assert m.cli_path == "claude"

    def test_custom_cli_path(self):
        m = _make_cli_model(cli_path="/usr/local/bin/claude")
        assert m.cli_path == "/usr/local/bin/claude"

    def test_allowed_tools_default(self):
        m = ModelConfig(id="x", provider="claude-cli", model="claude-sonnet-4-5")
        assert "Read" in m.allowed_tools

    def test_max_turns_default(self):
        m = ModelConfig(id="x", provider="claude-cli", model="claude-sonnet-4-5")
        assert m.max_turns == 20


# ---------------------------------------------------------------------------
# Model registry tests
# ---------------------------------------------------------------------------


class TestModelRegistryCLI:
    def test_build_litellm_kwargs_raises_for_cli(self):
        m = _make_cli_model()
        config = _make_config(m)
        registry = ModelRegistry(config)
        with pytest.raises(ValueError, match="claude-cli provider does not use LiteLLM"):
            registry.build_litellm_kwargs(m)

    def test_get_model_returns_cli_model(self):
        m = _make_cli_model()
        config = _make_config(m)
        registry = ModelRegistry(config)
        assert registry.get_model("claude-max") is m


# ---------------------------------------------------------------------------
# Executor routing tests
# ---------------------------------------------------------------------------


class TestExecutorRoutesToCLI:
    @pytest.mark.asyncio
    async def test_execute_routes_to_cli_when_provider_is_claude_cli(self):
        model = _make_cli_model()
        executor = _make_executor(model)
        agent = _make_agent()
        task = _make_task()

        # Patch _execute_claude_cli to verify it's called
        called = {}

        async def fake_cli(*args, **kwargs):
            called["yes"] = True
            return AgentResult(content="ok", success=True, turns_used=1)

        executor._execute_claude_cli = fake_cli  # type: ignore

        result = await executor.execute(task, agent, run_id="run-1")
        assert called.get("yes") is True
        assert result.success is True


# ---------------------------------------------------------------------------
# _execute_claude_cli tests
# ---------------------------------------------------------------------------


class TestExecuteClaudeCLI:
    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def _make_stream_json_lines(self, events: list[dict]) -> list[bytes]:
        return [json.dumps(e).encode() + b"\n" for e in events]

    @pytest.mark.asyncio
    async def test_success_extracts_text_from_assistant_event(self):
        model = _make_cli_model()
        executor = _make_executor(model)
        agent = _make_agent()
        task = _make_task(title="Write hello world")

        lines = self._make_stream_json_lines([
            {"type": "system", "subtype": "init"},
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "Hello, world!"}]
                },
            },
            {"type": "result", "subtype": "success", "num_turns": 1, "result": ""},
        ])

        fake_proc = _FakeProcess(lines=lines, returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=fake_proc):
            result = await executor._execute_claude_cli(
                task=task, agent=agent, context="", run_id="run-1", max_turns=10
            )

        assert result.success is True
        assert "Hello, world!" in result.content
        assert result.turns_used == 1

    @pytest.mark.asyncio
    async def test_tool_use_block_emits_indicator(self):
        model = _make_cli_model()
        executor = _make_executor(model)
        agent = _make_agent()
        task = _make_task()

        lines = self._make_stream_json_lines([
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "Read", "input": {"path": "/app/main.py"}},
                    ]
                },
            },
            {"type": "result", "subtype": "success", "num_turns": 1, "result": ""},
        ])

        fake_proc = _FakeProcess(lines=lines, returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=fake_proc):
            result = await executor._execute_claude_cli(
                task=task, agent=agent, context="", run_id="run-1", max_turns=10
            )

        # stream.push should have been called with tool indicator
        calls = [str(c) for c in executor.stream.push.call_args_list]
        assert any("Read" in c for c in calls)

    @pytest.mark.asyncio
    async def test_error_event_returns_failure(self):
        model = _make_cli_model()
        executor = _make_executor(model)
        agent = _make_agent()
        task = _make_task()

        lines = self._make_stream_json_lines([
            {"type": "result", "subtype": "error", "error": "Rate limit exceeded"},
        ])

        fake_proc = _FakeProcess(lines=lines, returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=fake_proc):
            result = await executor._execute_claude_cli(
                task=task, agent=agent, context="", run_id=None, max_turns=10
            )

        assert result.success is False
        assert "Rate limit" in (result.error or "")

    @pytest.mark.asyncio
    async def test_nonzero_exit_code_marks_failure(self):
        model = _make_cli_model()
        executor = _make_executor(model)
        agent = _make_agent()
        task = _make_task()

        lines = self._make_stream_json_lines([
            {"type": "result", "subtype": "success", "num_turns": 2, "result": "done"},
        ])

        fake_proc = _FakeProcess(lines=lines, returncode=1, _stderr_data=b"CLI crash")

        with patch("asyncio.create_subprocess_exec", return_value=fake_proc):
            result = await executor._execute_claude_cli(
                task=task, agent=agent, context="", run_id=None, max_turns=10
            )

        assert result.success is False
        assert "Exit code 1" in (result.error or "")

    @pytest.mark.asyncio
    async def test_file_not_found_returns_helpful_error(self):
        model = _make_cli_model(cli_path="/nonexistent/claude")
        executor = _make_executor(model)
        agent = _make_agent()
        task = _make_task()

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            result = await executor._execute_claude_cli(
                task=task, agent=agent, context="", run_id=None, max_turns=10
            )

        assert result.success is False
        assert "npm install" in (result.error or "")

    @pytest.mark.asyncio
    async def test_context_injected_into_prompt(self):
        model = _make_cli_model()
        executor = _make_executor(model)
        agent = _make_agent()
        task = _make_task(title="My task")

        lines = self._make_stream_json_lines([
            {"type": "result", "subtype": "success", "num_turns": 1, "result": "ok"},
        ])
        fake_proc = _FakeProcess(lines=lines, returncode=0)

        captured_cmd = {}

        async def fake_create(*args, **kwargs):
            captured_cmd["args"] = args
            return fake_proc

        with patch("asyncio.create_subprocess_exec", side_effect=fake_create):
            await executor._execute_claude_cli(
                task=task,
                agent=agent,
                context="IMPORTANT CONTEXT",
                run_id=None,
                max_turns=10,
            )

        # The prompt (second arg after 'claude -p') should contain context
        prompt_arg = captured_cmd["args"][2]  # [claude, -p, PROMPT, ...]
        assert "IMPORTANTE CONTEXT" in prompt_arg or "CONTEXT" in prompt_arg

    @pytest.mark.asyncio
    async def test_max_turns_capped_by_model_config(self):
        model = _make_cli_model(max_turns=5)
        executor = _make_executor(model)
        agent = _make_agent()
        task = _make_task()

        lines = self._make_stream_json_lines([
            {"type": "result", "subtype": "success", "num_turns": 3, "result": "done"},
        ])
        fake_proc = _FakeProcess(lines=lines, returncode=0)

        captured_cmd = {}

        async def fake_create(*args, **kwargs):
            captured_cmd["args"] = args
            return fake_proc

        with patch("asyncio.create_subprocess_exec", side_effect=fake_create):
            # Pass max_turns=20, but model caps at 5
            await executor._execute_claude_cli(
                task=task, agent=agent, context="", run_id=None, max_turns=20
            )

        # Find --max-turns in args
        args = list(captured_cmd["args"])
        idx = args.index("--max-turns")
        assert args[idx + 1] == "5"

    @pytest.mark.asyncio
    async def test_result_fallback_to_result_field(self):
        """When no assistant text blocks, use the 'result' field from result event."""
        model = _make_cli_model()
        executor = _make_executor(model)
        agent = _make_agent()
        task = _make_task()

        lines = self._make_stream_json_lines([
            {"type": "result", "subtype": "success", "num_turns": 1, "result": "Final answer here"},
        ])
        fake_proc = _FakeProcess(lines=lines, returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=fake_proc):
            result = await executor._execute_claude_cli(
                task=task, agent=agent, context="", run_id=None, max_turns=10
            )

        assert result.success is True
        assert "Final answer here" in result.content

    @pytest.mark.asyncio
    async def test_plain_text_fallback_for_non_json_lines(self):
        model = _make_cli_model()
        executor = _make_executor(model)
        agent = _make_agent()
        task = _make_task()

        # Mix of JSON and plain text lines
        lines = [
            b"some plain text line\n",
            json.dumps({"type": "result", "subtype": "success", "num_turns": 1, "result": ""}).encode() + b"\n",
        ]
        fake_proc = _FakeProcess(lines=lines, returncode=0)

        with patch("asyncio.create_subprocess_exec", return_value=fake_proc):
            result = await executor._execute_claude_cli(
                task=task, agent=agent, context="", run_id="run-1", max_turns=10
            )

        assert result.success is True
        assert "some plain text line" in result.content
