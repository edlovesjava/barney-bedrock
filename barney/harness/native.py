"""The native harness: a plain model/tool loop over the Converse adapter."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor

from ..config import RoleConfig
from ..llm import Message, ModelAdapter, ToolResult, ToolSpec
from ..llm.converse import ModelError
from ..run_record import RunRecord
from ..tools import Tool, ToolError, truncate
from . import Outcome, Task

log = logging.getLogger(__name__)

NUDGE = (
    "You stopped without calling the finish tool. If the task is complete, call finish now with a "
    "summary. Otherwise continue working."
)


class NativeHarness:
    name = "native"

    def __init__(self, adapter: ModelAdapter) -> None:
        self.adapter = adapter

    def run(self, task: Task, cfg: RoleConfig, record: RunRecord) -> Outcome:
        tools_by_name: dict[str, Tool] = {t.name: t for t in task.tools}
        specs = [ToolSpec(t.name, t.description, t.schema) for t in task.tools]
        messages: list[Message] = [Message(role="user", text=task.prompt)]
        nudged = False
        last_text = ""

        for turn in range(1, cfg.max_turns + 1):
            record.turns = turn
            try:
                comp = self.adapter.complete(task.system, messages, specs, cfg.max_output_tokens)
            except ModelError as e:
                record.log("error", where="model", code=e.code, message=str(e))
                return Outcome("error", final_text=str(e))
            record.usage = record.usage + comp.usage
            record.log(
                "model",
                turn=turn,
                stop=comp.stop_reason,
                latency_s=round(comp.latency_s, 2),
                in_tokens=comp.usage.input_tokens,
                out_tokens=comp.usage.output_tokens,
                tool_calls=[tc.name for tc in comp.message.tool_calls],
                text=truncate(comp.message.text, 2000),
            )
            messages.append(comp.message)
            last_text = comp.message.text or last_text
            log.info("turn %d stop=%s tools=%s", turn, comp.stop_reason, [tc.name for tc in comp.message.tool_calls])
            if comp.message.text:
                log.info("assistant: %s", truncate(comp.message.text, 500))

            # Budget checks (after accounting for this call).
            if record.usage.input_tokens > cfg.max_input_tokens:
                return Outcome("cap:input_tokens", final_text=last_text)
            if record.cost_usd is not None and record.cost_usd > cfg.max_usd:
                return Outcome("cap:usd", final_text=last_text)

            if comp.message.tool_calls:
                results, finished = self._execute(task, tools_by_name, comp.message, record)
                messages.append(Message(role="user", tool_results=results))
                if finished is not None:
                    return Outcome(
                        "success" if not finished.get("gave_up") else "gave_up",
                        final_text=last_text,
                        finish_args=finished,
                    )
                continue

            if comp.stop_reason == "max_tokens":
                messages.append(Message(role="user", text="Your last message was cut off. Continue."))
                continue

            # No tool calls and not truncated: the model thinks it is done.
            if not nudged:
                nudged = True
                messages.append(Message(role="user", text=NUDGE))
                continue
            return Outcome("gave_up", final_text=last_text)

        return Outcome("cap:turns", final_text=last_text)

    def _execute(self, task: Task, tools: dict[str, Tool], msg: Message, record: RunRecord):
        """Run all tool calls from one assistant turn; return (results, finish_args | None)."""
        finished = None
        calls = msg.tool_calls
        record.tool_calls += len(calls)

        def one(tc):
            tool = tools.get(tc.name)
            if tool is None:
                return ToolResult(tc.id, f"unknown tool {tc.name!r}", is_error=True)
            try:
                out = tool.call(task.ctx, tc.input)
                return ToolResult(tc.id, out)
            except ToolError as e:
                return ToolResult(tc.id, str(e), is_error=True)
            except TypeError as e:  # bad/missing arguments
                return ToolResult(tc.id, f"bad arguments for {tc.name}: {e}", is_error=True)
            except Exception as e:  # noqa: BLE001 - surface to the model, keep the loop alive
                log.exception("tool %s crashed", tc.name)
                return ToolResult(tc.id, f"{type(e).__name__}: {e}", is_error=True)

        # Read-only tools may run concurrently; anything that writes runs serially, in order.
        results: list[ToolResult] = []
        parallel = all(tools.get(tc.name) and tools[tc.name].read_only for tc in calls) and len(calls) > 1
        if parallel:
            with ThreadPoolExecutor(max_workers=min(8, len(calls))) as ex:
                results = list(ex.map(one, calls))
        else:
            for tc in calls:
                results.append(one(tc))

        for tc, res in zip(calls, results, strict=True):
            record.log(
                "tool",
                name=tc.name,
                args=truncate(json.dumps(tc.input, default=str), 1000),
                error=res.is_error,
                result=truncate(res.content, 1000),
            )
            log.info(
                "tool %s(%s) -> %s%s",
                tc.name,
                truncate(json.dumps(tc.input, default=str), 200),
                "ERROR " if res.is_error else "",
                truncate(res.content, 200).replace("\n", " "),
            )
            if tc.name == task.finish_tool and not res.is_error:
                finished = task.ctx.state.get("finish", {})
        return results, finished
