"""
Agent execution loop with LiteLLM tool-calling support.

The Executor drives a single agent through as many conversation turns as
needed (up to *max_turns*).  On each turn it:
  1. Calls the LLM (optionally streaming).
  2. If the model returned tool calls, executes them via ToolManager.
  3. Appends tool results to the conversation and loops.
  4. If the model returned plain text (no tool calls), returns.

Fallback model retry is attempted once if the primary model raises.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

import litellm
import structlog

from .config import AgentConfig, MoriConfig
from .model_registry import ModelRegistry

if TYPE_CHECKING:
    from .stream import StreamManager
    from .tool_manager import ToolManager

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class AgentResult:
    content: str
    success: bool
    turns_used: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    error: Optional[str] = None
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


class Executor:
    def __init__(
        self,
        config: MoriConfig,
        db,  # Database — typed as Any to avoid circular import
        tool_manager: "ToolManager",
        stream: "StreamManager",
    ) -> None:
        self.config = config
        self.db = db
        self.tool_manager = tool_manager
        self.stream = stream
        self.model_registry = ModelRegistry(config)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def execute(
        self,
        task: dict,
        agent: AgentConfig,
        context: str = "",
        run_id: Optional[str] = None,
        max_turns: int = 20,
    ) -> AgentResult:
        """
        Run agent on *task* and return an AgentResult.

        If the primary model fails and agent.fallback_model is set,
        retries once with the fallback model.
        """
        start = time.monotonic()
        try:
            result = await self._execute_with_model(
                task=task,
                agent=agent,
                model_id=agent.model,
                context=context,
                run_id=run_id,
                max_turns=max_turns,
            )
        except Exception as exc:
            if agent.fallback_model:
                log.warning(
                    "primary_model_failed_trying_fallback",
                    agent_id=agent.id,
                    model_id=agent.model,
                    fallback=agent.fallback_model,
                    error=str(exc),
                )
                try:
                    result = await self._execute_with_model(
                        task=task,
                        agent=agent,
                        model_id=agent.fallback_model,
                        context=context,
                        run_id=run_id,
                        max_turns=max_turns,
                    )
                except Exception as exc2:
                    result = AgentResult(
                        content="",
                        success=False,
                        turns_used=0,
                        error=f"Primary: {exc}; Fallback: {exc2}",
                    )
            else:
                result = AgentResult(
                    content="",
                    success=False,
                    turns_used=0,
                    error=str(exc),
                )

        result.duration_seconds = time.monotonic() - start
        return result

    # ------------------------------------------------------------------
    # Internal execution with a specific model
    # ------------------------------------------------------------------

    async def _execute_with_model(
        self,
        task: dict,
        agent: AgentConfig,
        model_id: str,
        context: str,
        run_id: Optional[str],
        max_turns: int,
    ) -> AgentResult:
        model_config = self.model_registry.get_model(model_id)
        litellm_kwargs = self.model_registry.build_litellm_kwargs(model_config)

        # Build OpenAI-compatible tool schemas if the model supports tools
        tools_schema: Optional[list] = None
        if model_config.supports_tools and agent.tools:
            tools_schema = self.tool_manager.get_tools_schema(agent.tools)

        # Build system prompt (inject memory context if provided)
        system_prompt = agent.system_prompt
        if context:
            system_prompt += f"\n\nCONTEXTO RELEVANTE DEL SISTEMA:\n{context}"

        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self._build_task_prompt(task)},
        ]

        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_cost = 0.0

        for turn in range(max_turns):
            log.debug(
                "executor_turn",
                run_id=run_id,
                agent_id=agent.id,
                model=model_config.litellm_model_string,
                turn=turn + 1,
            )

            try:
                response = await litellm.acompletion(
                    **litellm_kwargs,
                    messages=messages,
                    tools=tools_schema if tools_schema else litellm.NOT_GIVEN,
                    stream=self.config.orchestrator.stream_output,
                    timeout=agent.timeout_seconds,
                )
            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"Agent '{agent.id}' timed out after {agent.timeout_seconds}s "
                    f"on turn {turn + 1}"
                )

            # ---- Handle response (streaming or not) -----------------
            if self.config.orchestrator.stream_output:
                content, tool_calls, usage = await self._consume_stream(
                    response, run_id
                )
                if usage:
                    total_prompt_tokens += usage.get("prompt_tokens", 0)
                    total_completion_tokens += usage.get("completion_tokens", 0)
            else:
                choice = response.choices[0]
                content = choice.message.content or ""
                tool_calls = getattr(choice.message, "tool_calls", None)
                if hasattr(response, "usage") and response.usage:
                    total_prompt_tokens += getattr(response.usage, "prompt_tokens", 0) or 0
                    total_completion_tokens += getattr(response.usage, "completion_tokens", 0) or 0

            # Estimate cost from model config (rough: per-1k prices)
            total_cost += (
                total_prompt_tokens / 1000 * model_config.cost_per_1k_input
                + total_completion_tokens / 1000 * model_config.cost_per_1k_output
            )

            # Append assistant turn
            assistant_msg: dict = {"role": "assistant", "content": content}
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ]
            messages.append(assistant_msg)

            # ---- No tool calls → final answer -----------------------
            if not tool_calls:
                return AgentResult(
                    content=content,
                    success=True,
                    turns_used=turn + 1,
                    prompt_tokens=total_prompt_tokens,
                    completion_tokens=total_completion_tokens,
                    cost_usd=total_cost,
                )

            # ---- Execute tool calls ---------------------------------
            tool_results = await self.tool_manager.execute_tool_calls(tool_calls)
            for tr in tool_results:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tr["tool_call_id"],
                        "content": tr["result"],
                    }
                )
                if run_id:
                    await self.stream.push_tool_result(
                        run_id, tr["name"], tr["result"]
                    )

        # Max turns reached — return whatever the last assistant said
        last_content = ""
        for m in reversed(messages):
            if m["role"] == "assistant":
                last_content = m.get("content", "") or ""
                break

        return AgentResult(
            content=last_content,
            success=True,
            turns_used=max_turns,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            cost_usd=total_cost,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_task_prompt(self, task: dict) -> str:
        parts = [f"# Tarea: {task.get('title', '(sin título)')}"]
        if task.get("description"):
            parts.append(f"\n{task['description']}")
        if task.get("tags"):
            tags = task["tags"] if isinstance(task["tags"], list) else []
            parts.append(f"\nTags: {', '.join(tags)}")
        if task.get("area"):
            parts.append(f"Área: {task['area']}")
        if task.get("priority"):
            parts.append(f"Prioridad: {task['priority']}")
        return "\n".join(parts)

    async def _consume_stream(
        self, response, run_id: Optional[str]
    ) -> tuple[str, Optional[list], Optional[dict]]:
        """
        Drain a streaming response, collecting content and tool calls.

        Returns (content, tool_calls_or_none, usage_dict_or_none).
        """
        content = ""
        tool_call_chunks: dict[int, dict] = {}  # index → partial tool call
        usage: Optional[dict] = None

        try:
            async for chunk in response:
                if not chunk.choices:
                    # Some providers send usage-only final chunks
                    if hasattr(chunk, "usage") and chunk.usage:
                        usage = {
                            "prompt_tokens": getattr(chunk.usage, "prompt_tokens", 0),
                            "completion_tokens": getattr(chunk.usage, "completion_tokens", 0),
                        }
                    continue

                delta = chunk.choices[0].delta

                if delta.content:
                    content += delta.content
                    if run_id:
                        await self.stream.push(run_id, delta.content)

                # Accumulate tool call chunks (streamed in pieces)
                if delta.tool_calls:
                    for tc_chunk in delta.tool_calls:
                        idx = tc_chunk.index
                        if idx not in tool_call_chunks:
                            tool_call_chunks[idx] = {
                                "id": tc_chunk.id or "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        existing = tool_call_chunks[idx]
                        if tc_chunk.id:
                            existing["id"] = tc_chunk.id
                        if tc_chunk.function:
                            if tc_chunk.function.name:
                                existing["function"]["name"] += tc_chunk.function.name
                            if tc_chunk.function.arguments:
                                existing["function"]["arguments"] += tc_chunk.function.arguments
        except Exception as exc:
            log.warning("stream_consume_error", error=str(exc), run_id=run_id)

        if not tool_call_chunks:
            return content, None, usage

        # Reconstruct tool_calls as pseudo-objects that match non-streaming API
        class _FunctionCall:
            def __init__(self, name: str, arguments: str) -> None:
                self.name = name
                self.arguments = arguments

        class _ToolCall:
            def __init__(self, id: str, function: _FunctionCall) -> None:
                self.id = id
                self.function = function

        tool_calls = [
            _ToolCall(
                id=tc["id"],
                function=_FunctionCall(
                    name=tc["function"]["name"],
                    arguments=tc["function"]["arguments"],
                ),
            )
            for tc in sorted(tool_call_chunks.values(), key=lambda x: list(tool_call_chunks.values()).index(x))
        ]

        return content, tool_calls, usage
