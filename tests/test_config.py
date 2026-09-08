from pathlib import Path

import pytest

from barney.config import DEFAULTS, load


def test_defaults_without_target():
    cfg = load(None, env={})
    assert cfg.coder.model == DEFAULTS.coder.model
    assert cfg.reviewer.max_turns == 20
    assert cfg.region == "us-east-1"
    assert cfg.loop.rounds == 0


def test_toml_env_cli_precedence(tmp_path: Path):
    (tmp_path / "barney.toml").write_text(
        '[coder]\nmodel = "zai.glm-5"\nmax_turns = 7\n[reviewer]\nmodel = "x"\n'
        '[loop]\nrounds = 2\n[runtime]\nimage = "img:1"\n[aws]\nregion = "us-west-2"\n'
    )
    cfg = load(tmp_path, env={})
    assert cfg.coder.model == "zai.glm-5" and cfg.coder.max_turns == 7
    assert cfg.reviewer.model == "x" and cfg.reviewer.max_turns == 20  # untouched default
    assert cfg.loop.rounds == 2 and cfg.runtime.image == "img:1" and cfg.region == "us-west-2"

    cfg = load(tmp_path, env={"BARNEY_CODER_MODEL": "from-env", "BARNEY_REVIEWER_MAX_USD": "0.5"})
    assert cfg.coder.model == "from-env" and cfg.reviewer.max_usd == 0.5

    cfg = load(tmp_path, env={"BARNEY_CODER_MODEL": "from-env"}, overrides={"coder": {"model": "cli"}})
    assert cfg.coder.model == "cli"
    assert cfg.coder.max_turns == 7  # toml value survives when env/cli don't touch it


def test_unknown_key_rejected(tmp_path: Path):
    (tmp_path / "barney.toml").write_text("[coder]\nmodle = 'typo'\n")
    with pytest.raises(ValueError, match="unknown role keys"):
        load(tmp_path, env={})


def test_region_fallback_chain():
    assert load(None, env={"AWS_REGION": "eu-west-1"}).region == "eu-west-1"
    assert load(None, env={"AWS_REGION": "eu-west-1", "BARNEY_AWS_REGION": "us-east-2"}).region == "us-east-2"
