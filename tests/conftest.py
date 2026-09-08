import subprocess
from pathlib import Path

import pytest


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A tiny git repo with one commit on main."""
    d = tmp_path / "target"
    d.mkdir()
    git(d, "init", "-q", "-b", "main")
    git(d, "config", "user.email", "t@example.com")
    git(d, "config", "user.name", "t")
    (d / "README.md").write_text("# target\n")
    (d / "src").mkdir()
    (d / "src" / "a.py").write_text("def add(a, b):\n    return a + b\n")
    (d / ".github" / "workflows").mkdir(parents=True)
    (d / ".github" / "workflows" / "ci.yml").write_text("name: ci\n")
    (d / ".gitignore").write_text("*.log\n")
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "init")
    return d
