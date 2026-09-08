"""Harness interface: run a task with tools under a budget, produce an Outcome."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..config import RoleConfig
from ..run_record import RunRecord
from ..tools import Tool, ToolContext


@dataclass
class Task:
    system: str
    prompt: str
    tools: list[Tool]
    ctx: ToolContext
    finish_tool: str = "finish"  # tool whose call ends the loop


@dataclass
class Outcome:
    status: str  # success | gave_up | cap:<name> | error
    final_text: str = ""
    finish_args: dict[str, Any] = field(default_factory=dict)


class Harness(Protocol):
    name: str

    def run(self, task: Task, cfg: RoleConfig, record: RunRecord) -> Outcome: ...
