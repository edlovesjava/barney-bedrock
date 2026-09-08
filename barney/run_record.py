"""Run record: everything needed to compare and reproduce a pass."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .llm import Usage

# USD per 1M tokens (input, output). Approximate; edit freely. Missing = cost null.
PRICES: dict[str, tuple[float, float]] = {
    "us.amazon.nova-2-lite-v1:0": (0.30, 2.50),
    "us.amazon.nova-pro-v1:0": (0.80, 3.20),
    "us.amazon.nova-lite-v1:0": (0.06, 0.24),
    "us.amazon.nova-micro-v1:0": (0.035, 0.14),
}


@dataclass
class Event:
    t: float
    kind: str  # model | tool | note | error
    data: dict[str, Any]


@dataclass
class RunRecord:
    role: str
    model: str
    harness: str
    repo: str
    target: str  # "issue:N" | "pr:N"
    pass_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started: float = field(default_factory=time.time)
    finished: float | None = None
    prompt_hash: str = ""
    image_digest: str = ""
    turns: int = 0
    tool_calls: int = 0
    usage: Usage = field(default_factory=Usage)
    outcome: str = "running"  # running | success | gave_up | cap:<name> | error
    summary: str = ""
    branch: str = ""
    head_sha: str = ""
    pr_url: str = ""
    events: list[Event] = field(default_factory=list)

    def log(self, kind: str, **data: Any) -> None:
        self.events.append(Event(time.time(), kind, data))

    @property
    def cost_usd(self) -> float | None:
        p = PRICES.get(self.model)
        if not p:
            return None
        return round((self.usage.input_tokens * p[0] + self.usage.output_tokens * p[1]) / 1e6, 4)

    @property
    def wall_s(self) -> float:
        return round((self.finished or time.time()) - self.started, 1)

    def finish(self, outcome: str, summary: str = "") -> None:
        self.finished = time.time()
        self.outcome = outcome
        if summary:
            self.summary = summary

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["cost_usd"] = self.cost_usd
        d["wall_s"] = self.wall_s
        return d

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, default=str))
        return path

    def summary_markdown(self) -> str:
        cost = f"${self.cost_usd:.4f}" if self.cost_usd is not None else "n/a"
        return (
            f"| role | model | harness | outcome | turns | tool calls | in tokens | out tokens | cost | wall |\n"
            f"|---|---|---|---|---|---|---|---|---|---|\n"
            f"| {self.role} | `{self.model}` | {self.harness} | {self.outcome} | {self.turns} | {self.tool_calls} "
            f"| {self.usage.input_tokens:,} | {self.usage.output_tokens:,} | {cost} | {self.wall_s}s |"
        )
