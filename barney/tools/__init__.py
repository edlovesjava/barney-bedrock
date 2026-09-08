"""Tool surface exposed to the model.

A ``Tool`` is a name, a description, a flat JSON schema, and a callable that
receives a ``ToolContext`` plus the model's arguments and returns a string.
Schemas are linted at registration so every tool works on every Bedrock
provider (Nova is the strictest: top-level object with only ``type``,
``properties``, ``required``; primitive property types).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PRIMITIVES = {"string", "integer", "number", "boolean"}
ALLOWED_TOP = {"type", "properties", "required"}
ALLOWED_PROP = {"type", "description"}


class SchemaError(ValueError):
    pass


def lint_schema(name: str, schema: dict[str, Any]) -> None:
    if schema.get("type") != "object":
        raise SchemaError(f"{name}: top-level type must be 'object'")
    extra = set(schema) - ALLOWED_TOP
    if extra:
        raise SchemaError(f"{name}: top-level keys not allowed: {sorted(extra)}")
    props = schema.get("properties", {})
    if not isinstance(props, dict):
        raise SchemaError(f"{name}: properties must be an object")
    for pname, p in props.items():
        if not isinstance(p, dict):
            raise SchemaError(f"{name}.{pname}: property must be an object")
        extra = set(p) - ALLOWED_PROP
        if extra:
            raise SchemaError(f"{name}.{pname}: keys not allowed: {sorted(extra)}")
        if p.get("type") not in PRIMITIVES:
            raise SchemaError(f"{name}.{pname}: type must be one of {sorted(PRIMITIVES)}")
    req = schema.get("required", [])
    if not isinstance(req, list) or any(r not in props for r in req):
        raise SchemaError(f"{name}: required must list existing properties")


@dataclass
class ToolContext:
    workdir: Path
    max_tool_seconds: int = 300
    max_output_chars: int = 20_000
    # Free-form bag for tools that need to hand state back to the harness
    # (e.g. the ``finish`` tool records its arguments here).
    state: dict[str, Any] = field(default_factory=dict)

    def resolve(self, rel: str) -> Path:
        """Resolve a model-supplied path inside the workdir, or raise."""
        root = self.workdir.resolve()
        p = (root / rel).resolve() if not Path(rel).is_absolute() else Path(rel).resolve()
        if p != root and root not in p.parents:
            raise PermissionError(f"path escapes the workdir: {rel}")
        return p


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict[str, Any]
    fn: Callable[..., str]
    # Tools that only read may run concurrently with each other.
    read_only: bool = False

    def __post_init__(self) -> None:
        lint_schema(self.name, self.schema)

    def call(self, ctx: ToolContext, args: dict[str, Any]) -> str:
        return self.fn(ctx, **args)


class ToolError(Exception):
    """Raised by a tool to return an error result to the model (is_error)."""


def truncate(text: str, limit: int, where: str = "tail") -> str:
    if len(text) <= limit:
        return text
    marker = f"\n... [truncated {len(text) - limit} chars] ...\n"
    if where == "head":
        return text[:limit] + marker
    half = limit // 2
    return text[:half] + marker + text[-half:]


def to_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, default=str)
