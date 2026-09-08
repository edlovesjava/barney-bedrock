from pathlib import Path

from barney.config import RoleConfig
from barney.harness import Task
from barney.harness.native import NativeHarness
from barney.llm import Completion, Message, ToolCall, Usage
from barney.run_record import RunRecord
from barney.tools import Tool, ToolContext
from barney.tools.fs import TOOLS as FS_TOOLS


class ScriptedAdapter:
    """Returns pre-scripted completions; records what it was sent."""

    model_id = "fake"

    def __init__(self, script):
        self.script = list(script)
        self.seen = []

    def complete(self, system, messages, tools, max_tokens):
        self.seen.append([m for m in messages])
        text, calls, stop = self.script.pop(0)
        msg = Message(
            role="assistant", text=text, tool_calls=[ToolCall(f"id{i}", n, a) for i, (n, a) in enumerate(calls)]
        )
        return Completion(msg, stop, Usage(10, 5), 0.01)


def finish_tool():
    def finish(ctx: ToolContext, summary: str) -> str:
        ctx.state["finish"] = {"summary": summary}
        return "finished"

    return Tool(
        "finish",
        "done",
        {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]},
        finish,
    )


def make_task(repo: Path, tools):
    return Task(system="s", prompt="p", tools=tools, ctx=ToolContext(workdir=repo))


def test_loop_runs_tools_then_finishes(repo):
    ad = ScriptedAdapter(
        [
            ("look", [("read_file", {"path": "src/a.py"}), ("list_files", {})], "tool_use"),
            ("bad", [("read_file", {"path": "missing.py"}), ("nope", {})], "tool_use"),
            ("done", [("finish", {"summary": "did it"})], "tool_use"),
        ]
    )
    rec = RunRecord("coder", "fake", "native", "o/r", "issue:1")
    out = NativeHarness(ad).run(make_task(repo, [*FS_TOOLS, finish_tool()]), RoleConfig(model="fake"), rec)
    assert out.status == "success" and out.finish_args == {"summary": "did it"}
    assert rec.turns == 3 and rec.tool_calls == 5
    assert rec.usage.input_tokens == 30
    # tool results were fed back, in one user message, with errors flagged
    results = ad.seen[2][-1].tool_results
    assert len(results) == 2 and results[0].is_error and results[1].is_error
    assert "unknown tool" in results[1].content
    # both read-only calls in turn 1 produced results in order
    r1 = ad.seen[1][-1].tool_results
    assert r1[0].tool_call_id == "id0" and "def add" in r1[0].content and "src/a.py" in r1[1].content


def test_nudge_then_gave_up(repo):
    ad = ScriptedAdapter([("i think i'm done", [], "end_turn"), ("still no tool", [], "end_turn")])
    rec = RunRecord("coder", "fake", "native", "o/r", "issue:1")
    out = NativeHarness(ad).run(make_task(repo, [finish_tool()]), RoleConfig(model="fake"), rec)
    assert out.status == "gave_up" and "finish" in ad.seen[1][-1].text.lower()


def test_turn_cap(repo):
    ad = ScriptedAdapter([("x", [("list_files", {})], "tool_use")] * 3)
    rec = RunRecord("coder", "fake", "native", "o/r", "issue:1")
    out = NativeHarness(ad).run(make_task(repo, [*FS_TOOLS]), RoleConfig(model="fake", max_turns=3), rec)
    assert out.status == "cap:turns" and rec.turns == 3


def test_token_cap(repo):
    ad = ScriptedAdapter([("x", [("list_files", {})], "tool_use")] * 5)
    rec = RunRecord("coder", "fake", "native", "o/r", "issue:1")
    out = NativeHarness(ad).run(make_task(repo, [*FS_TOOLS]), RoleConfig(model="fake", max_input_tokens=25), rec)
    assert out.status == "cap:input_tokens" and rec.turns == 3
