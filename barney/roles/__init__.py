"""Roles: coder and reviewer. Each is a prompt, a tool subset, and a driver around the harness."""

from __future__ import annotations

import hashlib
from pathlib import Path

PROMPTS = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> tuple[str, str]:
    text = (PROMPTS / f"{name}.md").read_text()
    return text, hashlib.sha256(text.encode()).hexdigest()[:12]


def read_conventions(workdir: Path) -> str:
    """CLAUDE.md / AGENTS.md from the target, if any."""
    for name in ("CLAUDE.md", "AGENTS.md"):
        p = workdir / name
        if p.is_file():
            return f"# {name}\n\n{p.read_text()}"
    return "(the repository has no CLAUDE.md or AGENTS.md)"
