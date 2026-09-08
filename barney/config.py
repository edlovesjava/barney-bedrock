"""Per-role configuration.

Precedence, lowest to highest: built-in defaults, ``barney.toml`` in the
target repo, environment variables (``BARNEY_<ROLE>_<KEY>``), CLI overrides.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any

ROLES = ("coder", "reviewer")


@dataclass(frozen=True)
class RoleConfig:
    model: str
    harness: str = "native"
    max_turns: int = 60
    max_tool_seconds: int = 300
    max_input_tokens: int = 3_000_000
    max_output_tokens: int = 8192  # per model call
    max_usd: float = 5.0
    thinking: str = "off"  # off | provider default; per-provider mapping lives in the adapter


@dataclass(frozen=True)
class LoopConfig:
    rounds: int = 0
    max_passes: int = 10


@dataclass(frozen=True)
class RuntimeConfig:
    image: str = "ghcr.io/edlovesjava/barney:latest"


@dataclass(frozen=True)
class Config:
    coder: RoleConfig
    reviewer: RoleConfig
    loop: LoopConfig = field(default_factory=LoopConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    region: str = "us-east-1"

    def role(self, name: str) -> RoleConfig:
        if name not in ROLES:
            raise ValueError(f"unknown role {name!r}, expected one of {ROLES}")
        return getattr(self, name)


DEFAULTS = Config(
    coder=RoleConfig(model="us.amazon.nova-2-lite-v1:0"),
    reviewer=RoleConfig(model="qwen.qwen3-coder-next", max_turns=20, max_input_tokens=1_000_000, max_usd=1.0),
)

_ROLE_FIELD_TYPES = {f.name: f.type for f in fields(RoleConfig)}


def _coerce(name: str, value: Any) -> Any:
    t = _ROLE_FIELD_TYPES[name]
    if t in ("int", int):
        return int(value)
    if t in ("float", float):
        return float(value)
    return str(value)


def _apply_role(base: RoleConfig, values: dict[str, Any], source: str) -> RoleConfig:
    unknown = set(values) - set(_ROLE_FIELD_TYPES)
    if unknown:
        raise ValueError(f"{source}: unknown role keys {sorted(unknown)}")
    return replace(base, **{k: _coerce(k, v) for k, v in values.items()})


def _env_role_values(role: str, env: dict[str, str]) -> dict[str, Any]:
    prefix = f"BARNEY_{role.upper()}_"
    return {k[len(prefix) :].lower(): v for k, v in env.items() if k.startswith(prefix)}


def load(
    target_dir: Path | None,
    env: dict[str, str] | None = None,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> Config:
    """Build the effective Config.

    ``overrides`` is ``{role: {key: value}}`` from CLI flags, plus optional
    ``{"aws": {"region": ...}}``.
    """
    env = os.environ if env is None else env
    overrides = overrides or {}
    cfg = DEFAULTS

    toml: dict[str, Any] = {}
    if target_dir is not None:
        p = Path(target_dir) / "barney.toml"
        if p.is_file():
            toml = tomllib.loads(p.read_text())

    roles = {}
    for role in ROLES:
        rc = cfg.role(role)
        rc = _apply_role(rc, toml.get(role, {}), f"barney.toml [{role}]")
        rc = _apply_role(rc, _env_role_values(role, env), f"env BARNEY_{role.upper()}_*")
        rc = _apply_role(rc, overrides.get(role, {}), f"cli --{role}")
        roles[role] = rc

    loop = LoopConfig(**{**toml.get("loop", {})})
    runtime = RuntimeConfig(**{**toml.get("runtime", {})})
    region = (
        overrides.get("aws", {}).get("region")
        or env.get("BARNEY_AWS_REGION")
        or toml.get("aws", {}).get("region")
        or env.get("AWS_REGION")
        or DEFAULTS.region
    )
    return Config(coder=roles["coder"], reviewer=roles["reviewer"], loop=loop, runtime=runtime, region=region)
