from pathlib import Path

import pytest

from barney.tools import ToolContext, ToolError
from barney.tools.fs import edit_file, grep, list_files, read_file, write_file
from barney.tools.git import git_commit, git_diff, git_status, protected_paths
from barney.tools.shell import run_command


def ctx(repo: Path, **kw) -> ToolContext:
    return ToolContext(workdir=repo, **kw)


def test_read_write_edit(repo):
    c = ctx(repo)
    assert "1\tdef add" in read_file(c, "src/a.py")
    assert read_file(c, "src/a.py", start_line=2, end_line=2).strip().startswith("2\t")
    assert "created" in write_file(c, "src/new/b.py", "x = 1\n")
    assert (repo / "src/new/b.py").read_text() == "x = 1\n"
    assert edit_file(c, "src/a.py", "a + b", "a - b") == "edited src/a.py"
    assert "a - b" in (repo / "src/a.py").read_text()
    with pytest.raises(ToolError, match="not found"):
        edit_file(c, "src/a.py", "nope", "x")
    (repo / "dup.txt").write_text("zz zz")
    with pytest.raises(ToolError, match="2 times"):
        edit_file(c, "dup.txt", "zz", "y")


def test_path_sandbox(repo):
    c = ctx(repo)
    with pytest.raises(PermissionError):
        read_file(c, "../outside.txt")
    with pytest.raises(PermissionError):
        write_file(c, "/etc/passwd", "x")
    # symlink escape
    (repo.parent / "outside.txt").write_text("secret")
    (repo / "link").symlink_to(repo.parent)
    with pytest.raises(PermissionError):
        read_file(c, "link/outside.txt")


def test_protected_paths(repo):
    c = ctx(repo)
    with pytest.raises(ToolError, match="refusing"):
        write_file(c, ".github/workflows/evil.yml", "x")
    with pytest.raises(ToolError, match="refusing"):
        edit_file(c, ".github/workflows/ci.yml", "ci", "evil")
    assert protected_paths([".github/workflows/a.yml", "src/a.py", ".github/other"]) == [".github/workflows/a.yml"]


def test_list_and_grep(repo):
    c = ctx(repo)
    (repo / "debug.log").write_text("ignored")
    (repo / "untracked.py").write_text("hello = 1")
    files = list_files(c)
    assert "src/a.py" in files and "untracked.py" in files and "debug.log" not in files
    assert "src/a.py:1:" in grep(c, "def add")
    assert grep(c, "nomatchzzz") == "(no matches)"
    with pytest.raises(ToolError, match="bad regex"):
        grep(c, "(")


def test_run_command(repo):
    c = ctx(repo, max_tool_seconds=5)
    out = run_command(c, "echo hi; echo err >&2; exit 3")
    assert out.startswith("exit code: 3") and "hi" in out and "err" in out
    with pytest.raises(ToolError, match="timed out"):
        run_command(c, "sleep 3", timeout_seconds=1)
    assert "exit code: 0" in run_command(c, "pwd") and str(repo) in run_command(c, "pwd")


def test_output_truncation(repo):
    c = ctx(repo, max_output_chars=200)
    out = run_command(c, "seq 1 10000")
    assert "truncated" in out and len(out) < 400


def test_git_commit_refuses_protected(repo):
    c = ctx(repo)
    (repo / ".github/workflows/ci.yml").write_text("changed\n")
    (repo / "src/a.py").write_text("ok\n")
    with pytest.raises(ToolError, match="protected"):
        git_commit(c, "msg")
    # the protected file was unstaged, the good one is still staged
    assert "ci.yml" in git_status(c) and "A" not in git_status(c).split("ci.yml")[0][-3:]
    (repo / ".github/workflows/ci.yml").write_text("name: ci\n")  # revert
    assert git_commit(c, "msg").startswith("committed")
    assert git_diff(c) == "(no changes)"
    assert git_commit(c, "again") == "nothing to commit"
