"""Git tools the model may call, plus helpers the harness uses around the loop.

The model gets status, diff and commit. Branching, pushing and PR creation
belong to the harness, not the model.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from . import Tool, ToolContext, ToolError, truncate
from .fs import PROTECTED


def _git(workdir: Path, *args: str, check: bool = True, env: dict[str, str] | None = None) -> str:
    r = subprocess.run(
        ["git", *args],
        cwd=workdir,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **(env or {})},
        timeout=300,
    )
    if check and r.returncode != 0:
        raise ToolError(f"git {' '.join(args[:2])} failed: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def protected_paths(paths: list[str]) -> list[str]:
    return [p for p in paths if any(p == prot or p.startswith(prot + "/") for prot in PROTECTED)]


def git_status(ctx: ToolContext) -> str:
    return _git(ctx.workdir, "status", "--short", "--branch") or "(clean)"


def git_diff(ctx: ToolContext, staged: bool = False, path: str = "") -> str:
    args = ["diff", "--stat", "-p"]
    if staged:
        args.append("--cached")
    if path:
        args += ["--", str(ctx.resolve(path))]
    out = _git(ctx.workdir, *args)
    return truncate(out, ctx.max_output_chars) if out else "(no changes)"


def git_commit(ctx: ToolContext, message: str) -> str:
    _git(ctx.workdir, "add", "-A")
    staged = _git(ctx.workdir, "diff", "--cached", "--name-only").split()
    bad = protected_paths(staged)
    if bad:
        _git(ctx.workdir, "reset", "-q", "--", *bad)
        raise ToolError(f"unstaged and refused to commit protected paths: {bad}")
    if not staged:
        return "nothing to commit"
    _git(ctx.workdir, "commit", "-q", "-m", message)
    sha = _git(ctx.workdir, "rev-parse", "--short", "HEAD").strip()
    return f"committed {sha}: {len(staged)} file(s)"


TOOLS = [
    Tool(
        "git_status",
        "Show working tree status.",
        {"type": "object", "properties": {}, "required": []},
        git_status,
        read_only=True,
    ),
    Tool(
        "git_diff",
        "Show the diff of uncommitted changes (or staged changes).",
        {
            "type": "object",
            "properties": {
                "staged": {"type": "boolean", "description": "Show staged changes instead of unstaged"},
                "path": {"type": "string", "description": "Limit to a path"},
            },
            "required": [],
        },
        git_diff,
        read_only=True,
    ),
    Tool(
        "git_commit",
        "Stage all changes and commit with a message. Commit small, coherent steps.",
        {
            "type": "object",
            "properties": {"message": {"type": "string", "description": "Commit message"}},
            "required": ["message"],
        },
        git_commit,
    ),
]


# --- harness-side helpers -------------------------------------------------


def current_branch(workdir: Path) -> str:
    return _git(workdir, "rev-parse", "--abbrev-ref", "HEAD").strip()


def head_sha(workdir: Path) -> str:
    return _git(workdir, "rev-parse", "HEAD").strip()


def resolve_base(workdir: Path, base_branch: str) -> str:
    """Prefer the remote-tracking base (fresh after a fetch), else the local branch, else HEAD."""
    for ref in (f"origin/{base_branch}", base_branch):
        r = subprocess.run(["git", "rev-parse", "--verify", "-q", ref], cwd=workdir, capture_output=True, text=True)
        if r.returncode == 0:
            return ref
    return "HEAD"


def create_branch(workdir: Path, name: str, base: str | None = None) -> None:
    args = ["checkout", "-q", "-B", name]
    if base:
        args.append(base)
    _git(workdir, *args)


def has_uncommitted(workdir: Path) -> bool:
    return bool(_git(workdir, "status", "--porcelain").strip())


def dirty_paths(workdir: Path) -> list[str]:
    """Paths with uncommitted changes (staged, unstaged or untracked)."""
    out = []
    for line in _git(workdir, "status", "--porcelain", "--untracked-files=all").splitlines():
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        out.append(path)
    return out


def changed_files_vs(workdir: Path, base_ref: str) -> list[str]:
    out = _git(workdir, "diff", "--name-only", f"{base_ref}...HEAD", check=False)
    return out.split()


def push(workdir: Path, remote_url: str, branch: str, token: str) -> str:
    """Push using a one-shot credential helper so the token never appears in argv or config."""
    helper = '!f() { echo username=x-access-token; echo "password=$BARNEY_PUSH_TOKEN"; }; f'
    return _git(
        workdir,
        "-c",
        f"credential.helper={helper}",
        "push",
        "-u",
        remote_url,
        f"HEAD:refs/heads/{branch}",
        env={"BARNEY_PUSH_TOKEN": token, "GIT_TERMINAL_PROMPT": "0"},
    )
