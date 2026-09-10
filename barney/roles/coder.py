"""Coder role: issue -> committed branch -> PR."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import RoleConfig
from ..harness import Harness, Outcome, Task
from ..run_record import RunRecord
from ..tools import Tool, ToolContext, fs, git, shell
from ..tools.github import GitHub
from . import load_prompt, read_conventions

log = logging.getLogger(__name__)


def slugify(title: str, n: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:n].rstrip("-") or "work"


def _plan_tool(gh: GitHub | None, issue_number: int, dry_run: bool) -> Tool:
    def post_plan(ctx: ToolContext, plan: str) -> str:
        ctx.state["plan"] = plan
        if gh is None or dry_run:
            log.info("PLAN (not posted):\n%s", plan)
            return "plan recorded (dry run, not posted)"
        gh.comment(issue_number, f"### barney plan\n\n{plan}\n\n<!-- barney:plan -->")
        return "plan posted to the issue"

    return Tool(
        "post_plan",
        "Post your implementation plan to the issue before starting work. Call exactly once, first.",
        {
            "type": "object",
            "properties": {"plan": {"type": "string", "description": "Markdown plan"}},
            "required": ["plan"],
        },
        post_plan,
    )


def _finish_tool() -> Tool:
    def finish(
        ctx: ToolContext, summary: str, verification: str, pr_title: str, pr_body: str, gave_up: bool = False
    ) -> str:
        ctx.state["finish"] = {
            "summary": summary,
            "verification": verification,
            "pr_title": pr_title,
            "pr_body": pr_body,
            "gave_up": gave_up,
        }
        return "finished"

    return Tool(
        "finish",
        "End the task. Call when the work is committed and verified, or when you are blocked (gave_up=true).",
        {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "What you did, in a few sentences"},
                "verification": {"type": "string", "description": "Commands run and their outcomes"},
                "pr_title": {"type": "string", "description": "Proposed PR title"},
                "pr_body": {"type": "string", "description": "Proposed PR body in markdown"},
                "gave_up": {"type": "boolean", "description": "True if you could not complete the task"},
            },
            "required": ["summary", "verification", "pr_title", "pr_body"],
        },
        finish,
    )


def build_prompt(issue: dict[str, Any], conventions: str) -> str:
    body = issue.get("body") or "(no description)"
    return (
        f"# Issue #{issue['number']}: {issue['title']}\n\n{body}\n\n"
        f"---\n\n## Repository conventions\n\n{conventions}\n\n"
        f"---\n\nImplement this issue. Start by calling post_plan."
    )


class PreflightError(RuntimeError):
    pass


@dataclass
class CoderResult:
    outcome: Outcome
    branch: str
    pr_url: str = ""


def run_coder(
    *,
    harness: Harness,
    cfg: RoleConfig,
    workdir: Path,
    issue: dict[str, Any],
    gh: GitHub | None,
    repo: str,
    record: RunRecord,
    dry_run: bool = False,
    base_branch: str = "main",
    allow_dirty: bool = False,
) -> CoderResult:
    number = issue["number"]
    branch = f"agent/issue-{number}-{slugify(issue['title'])}"

    # Pre-flight: a new pass must start from a clean tree on the base branch. Reusing a dirty
    # checkout (e.g. a previous aborted run) would silently fold stale edits into this pass.
    if git.has_uncommitted(workdir):
        if not allow_dirty:
            raise PreflightError(
                f"{workdir} has uncommitted changes; commit, stash or `git checkout -- .` first "
                "(or pass allow_dirty to fold them in)"
            )
        record.log("note", preflight="dirty worktree allowed")
    base_ref = git.resolve_base(workdir, base_branch)
    git.create_branch(workdir, branch, base_ref)
    record.branch = branch
    record.log("note", base=base_ref, base_sha=git.head_sha(workdir))

    system, phash = load_prompt("coder")
    record.prompt_hash = phash
    ctx = ToolContext(workdir=workdir, max_tool_seconds=cfg.max_tool_seconds)
    tools = [*fs.TOOLS, *shell.TOOLS, *git.TOOLS, _plan_tool(gh, number, dry_run), _finish_tool()]
    task = Task(system=system, prompt=build_prompt(issue, read_conventions(workdir)), tools=tools, ctx=ctx)

    outcome = harness.run(task, cfg, record)
    fin = outcome.finish_args

    # Refuse to ship workflow changes however they got there: committed via run_command,
    # or left dirty in the worktree.
    protected = git.protected_paths(git.dirty_paths(workdir))
    if git.has_uncommitted(workdir) and not protected:
        try:
            git.git_commit(ctx, fin.get("summary") or f"WIP for issue #{number}")
        except Exception as e:  # noqa: BLE001
            record.log("note", uncommitted=str(e))
    record.head_sha = git.head_sha(workdir)
    changed = git.changed_files_vs(workdir, base_branch)
    protected += git.protected_paths(changed)
    if protected:
        record.log("error", where="protected", files=sorted(set(protected)))
        outcome = Outcome(
            "error", final_text=f"protected paths changed, not pushing: {sorted(set(protected))}", finish_args=fin
        )

    if dry_run or gh is None or outcome.status == "error":
        record.finish(outcome.status, fin.get("summary", outcome.final_text))
        return CoderResult(outcome, branch)

    if changed:
        git.push(workdir, gh.clone_url, branch, gh.tokens.token())
        draft = outcome.status != "success"
        title = fin.get("pr_title") or f"{issue['title']} (#{number})"
        body = _pr_body(fin, outcome, record, number)
        existing = gh.pulls_for_branch(branch)
        pr = existing[0] if existing else gh.create_pull(title, body, branch, base_branch, draft=draft)
        record.pr_url = pr["html_url"]
        gh.comment(number, f"barney opened {pr['html_url']} ({outcome.status}).\n\n{record.summary_markdown()}")
    else:
        gh.comment(number, f"barney made no changes ({outcome.status}): {outcome.final_text[:1500]}")

    record.finish(outcome.status, fin.get("summary", outcome.final_text))
    return CoderResult(outcome, branch, record.pr_url)


def _pr_body(fin: dict[str, Any], outcome: Outcome, record: RunRecord, issue_number: int) -> str:
    parts = [fin.get("pr_body") or fin.get("summary") or outcome.final_text or "(no description)"]
    parts.append(f"\n\nCloses #{issue_number}")
    if fin.get("verification"):
        parts.append(f"\n\n## Verification\n\n{fin['verification']}")
    if outcome.status != "success":
        parts.append(f"\n\n> **Draft:** run ended with `{outcome.status}`. {outcome.final_text[:1000]}")
    parts.append(f"\n\n<!-- barney:pass id={record.pass_id} role=coder model={record.model} -->")
    return "".join(parts)
