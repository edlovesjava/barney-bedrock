"""run_command: a shell in the workdir with a timeout and an output cap."""

from __future__ import annotations

import os
import subprocess

from . import Tool, ToolContext, ToolError, truncate


def run_command(ctx: ToolContext, command: str, timeout_seconds: int = 0) -> str:
    timeout = min(timeout_seconds or ctx.max_tool_seconds, ctx.max_tool_seconds)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "PAGER": "cat", "CI": "1"}
    try:
        r = subprocess.run(
            ["bash", "-o", "pipefail", "-c", command],
            cwd=ctx.workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        raise ToolError(f"timed out after {timeout}s\n{truncate(out, ctx.max_output_chars)}") from e
    except OSError as e:
        raise ToolError(str(e)) from e
    body = r.stdout
    if r.stderr:
        body += ("\n--- stderr ---\n" if body else "") + r.stderr
    return f"exit code: {r.returncode}\n{truncate(body, ctx.max_output_chars)}"


TOOLS = [
    Tool(
        "run_command",
        "Run a bash command in the repo root and return exit code, stdout and stderr. Use it to build, "
        "test, and inspect. Long output is truncated in the middle. No interactive commands.",
        {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Bash command line"},
                "timeout_seconds": {"type": "integer", "description": "Optional timeout; capped by config"},
            },
            "required": ["command"],
        },
        run_command,
    ),
]
