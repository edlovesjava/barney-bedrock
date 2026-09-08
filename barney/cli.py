"""barney command line."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .config import load
from .harness.native import NativeHarness
from .llm.converse import ConverseAdapter
from .roles.coder import run_coder
from .run_record import RunRecord
from .tools.github import GitHub, PatTokenProvider


def _harness(name: str, model: str, region: str, thinking: str):
    if name == "native":
        return NativeHarness(ConverseAdapter(model, region, thinking=thinking))
    raise SystemExit(f"harness {name!r} not implemented yet (Phase 4)")


def cmd_code(a: argparse.Namespace) -> int:
    workdir = Path(a.workdir).resolve()
    overrides = {"coder": {k: v for k, v in (("model", a.model), ("harness", a.harness)) if v}}
    if a.region:
        overrides["aws"] = {"region": a.region}
    cfg = load(workdir, overrides=overrides)
    rc = cfg.coder

    if a.issue_file:
        issue = json.loads(Path(a.issue_file).read_text())
        gh = None
    else:
        gh = GitHub(a.repo, PatTokenProvider())
        issue = gh.issue(a.issue)
    if a.dry_run:
        gh_for_writes = None
    else:
        gh_for_writes = gh

    record = RunRecord(role="coder", model=rc.model, harness=rc.harness, repo=a.repo, target=f"issue:{issue['number']}")
    logging.info("coder: model=%s harness=%s workdir=%s dry_run=%s", rc.model, rc.harness, workdir, a.dry_run)

    harness = _harness(rc.harness, rc.model, cfg.region, rc.thinking)
    base = a.base or (gh.default_branch() if gh else "main")
    result = run_coder(
        harness=harness,
        cfg=rc,
        workdir=workdir,
        issue=issue,
        gh=gh_for_writes,
        repo=a.repo,
        record=record,
        dry_run=a.dry_run,
        base_branch=base,
    )

    out = record.save(Path(a.record))
    print(record.summary_markdown())
    print(f"branch: {result.branch}  head: {record.head_sha[:8]}  pr: {result.pr_url or '-'}")
    print(f"record: {out}")
    return 0 if result.outcome.status == "success" else 1


def cmd_review(a: argparse.Namespace) -> int:
    raise SystemExit("barney review arrives in Phase 3")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="barney", description="Autonomous coding agent on AWS Bedrock")
    p.add_argument("--version", action="version", version=f"barney {__version__}")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("code", help="implement an issue and open a PR")
    c.add_argument("--repo", required=True, help="owner/name")
    g = c.add_mutually_exclusive_group(required=True)
    g.add_argument("--issue", type=int, help="issue number")
    g.add_argument("--issue-file", help="local JSON with number/title/body (offline testing)")
    c.add_argument("--workdir", default=".", help="path to the target checkout")
    c.add_argument("--base", help="base branch (default: repo default branch)")
    c.add_argument("--model", help="override coder model")
    c.add_argument("--harness", help="override coder harness")
    c.add_argument("--region", help="override AWS region")
    c.add_argument("--dry-run", action="store_true", help="no GitHub writes, no push")
    c.add_argument("--record", default="barney-run.json", help="where to write the run record")
    c.set_defaults(fn=cmd_code)

    r = sub.add_parser("review", help="review a PR (Phase 3)")
    r.add_argument("--repo", required=True)
    r.add_argument("--pr", type=int, required=True)
    r.set_defaults(fn=cmd_review)

    a = p.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if a.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
