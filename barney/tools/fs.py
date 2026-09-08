"""File tools: read, write, edit, list, grep. All paths are sandboxed to the workdir."""

from __future__ import annotations

import re
import subprocess

from . import Tool, ToolContext, ToolError, truncate

PROTECTED = (".github/workflows",)


def _check_writable(ctx: ToolContext, rel: str) -> None:
    p = ctx.resolve(rel)
    relp = p.relative_to(ctx.workdir.resolve()).as_posix()
    for prot in PROTECTED:
        if relp == prot or relp.startswith(prot + "/"):
            raise ToolError(f"refusing to write under {prot}: the agent may not change CI or its own permissions")


def read_file(ctx: ToolContext, path: str, start_line: int = 1, end_line: int = 0) -> str:
    p = ctx.resolve(path)
    if not p.is_file():
        raise ToolError(f"not a file: {path}")
    try:
        lines = p.read_text(errors="replace").splitlines()
    except OSError as e:
        raise ToolError(str(e)) from e
    start = max(1, start_line)
    end = len(lines) if end_line <= 0 else min(end_line, len(lines))
    if start > len(lines):
        return f"(file has {len(lines)} lines; start_line {start} is past the end)"
    out = "\n".join(f"{i:>6}\t{lines[i - 1]}" for i in range(start, end + 1))
    return truncate(out, ctx.max_output_chars, where="head")


def write_file(ctx: ToolContext, path: str, content: str) -> str:
    _check_writable(ctx, path)
    p = ctx.resolve(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    existed = p.exists()
    p.write_text(content)
    return f"{'overwrote' if existed else 'created'} {path} ({len(content)} chars)"


def edit_file(ctx: ToolContext, path: str, old_string: str, new_string: str) -> str:
    _check_writable(ctx, path)
    p = ctx.resolve(path)
    if not p.is_file():
        raise ToolError(f"not a file: {path}")
    text = p.read_text()
    n = text.count(old_string)
    if n == 0:
        raise ToolError("old_string not found; read the file and copy the exact text including whitespace")
    if n > 1:
        raise ToolError(f"old_string occurs {n} times; include more surrounding context so it is unique")
    p.write_text(text.replace(old_string, new_string, 1))
    return f"edited {path}"


def list_files(ctx: ToolContext, path: str = ".", max_entries: int = 500) -> str:
    """Tracked plus untracked-but-not-ignored files under path, via git."""
    p = ctx.resolve(path)
    if not p.exists():
        raise ToolError(f"no such path: {path}")
    try:
        r = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", str(p)],
            cwd=ctx.workdir,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ToolError(str(e)) from e
    if r.returncode != 0:
        # Not a git repo (yet): fall back to a plain walk.
        entries = sorted(str(x.relative_to(ctx.workdir)) for x in p.rglob("*") if x.is_file() and ".git" not in x.parts)
    else:
        entries = sorted(set(r.stdout.split()))
    total = len(entries)
    entries = entries[:max_entries]
    tail = f"\n... {total - len(entries)} more" if total > len(entries) else ""
    return "\n".join(entries) + tail if entries else "(no files)"


def grep(ctx: ToolContext, pattern: str, path: str = ".", glob: str = "") -> str:
    """Regex search with line numbers. Uses git grep when available."""
    p = ctx.resolve(path)
    try:
        re.compile(pattern)
    except re.error as e:
        raise ToolError(f"bad regex: {e}") from e
    cmd = ["git", "grep", "-n", "-I", "-E", "--untracked", "-e", pattern, "--", str(p)]
    if glob:
        cmd.append(f":(glob){glob}" if p == ctx.workdir.resolve() else glob)
    try:
        r = subprocess.run(cmd, cwd=ctx.workdir, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ToolError(str(e)) from e
    if r.returncode == 1:
        return "(no matches)"
    if r.returncode not in (0, 1):
        raise ToolError(r.stderr.strip() or f"git grep exited {r.returncode}")
    return truncate(r.stdout, ctx.max_output_chars, where="head")


TOOLS = [
    Tool(
        "read_file",
        "Read a text file with line numbers. Use start_line/end_line for a range (1-based, inclusive; "
        "end_line 0 means to the end).",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to the repo root"},
                "start_line": {"type": "integer", "description": "First line, default 1"},
                "end_line": {"type": "integer", "description": "Last line, default 0 = end of file"},
            },
            "required": ["path"],
        },
        read_file,
        read_only=True,
    ),
    Tool(
        "write_file",
        "Create or overwrite a whole file. Prefer edit_file for changes to existing files.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to the repo root"},
                "content": {"type": "string", "description": "Full file content"},
            },
            "required": ["path", "content"],
        },
        write_file,
    ),
    Tool(
        "edit_file",
        "Replace one exact occurrence of old_string with new_string in a file. old_string must match "
        "exactly and be unique in the file.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to the repo root"},
                "old_string": {"type": "string", "description": "Exact text to replace"},
                "new_string": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "old_string", "new_string"],
        },
        edit_file,
    ),
    Tool(
        "list_files",
        "List files under a path (tracked and untracked, ignoring .gitignore'd files).",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory relative to repo root, default '.'"},
                "max_entries": {"type": "integer", "description": "Cap on entries returned, default 500"},
            },
            "required": [],
        },
        list_files,
        read_only=True,
    ),
    Tool(
        "grep",
        "Search file contents with an extended regex; returns path:line:text matches.",
        {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Extended regular expression"},
                "path": {"type": "string", "description": "Directory or file to search, default '.'"},
                "glob": {"type": "string", "description": "Optional pathspec glob, e.g. '*.cpp'"},
            },
            "required": ["pattern"],
        },
        grep,
        read_only=True,
    ),
]
