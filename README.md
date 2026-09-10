# barney-bedrock

Autonomous coding agent on **AWS Bedrock** that takes a GitHub issue from
specification to a reviewed pull request. Built as a testbed for comparing
models, agent harnesses, and (later) multi-agent orchestration.

Target repo for experiments: [edlovesjava/aiotp1](https://github.com/edlovesjava/aiotp1)
(an ESP32-S3 voice-controlled ESP-NOW node, see its `docs/product-spec.md`).

| Doc | Purpose |
|---|---|
| [docs/spec.md](docs/spec.md) | What the system is and is not, roles, interfaces, guardrails |
| [docs/plan.md](docs/plan.md) | Phased implementation plan with a verification gate per phase |
| [docs/decisions.md](docs/decisions.md) | Decisions made so far and why |
| [images/](images/) | Dockerfiles: `barney` base and `barney-platformio`, published to GHCR by `images.yml` |
| [infra/iam/github-oidc.yaml](infra/iam/github-oidc.yaml) | CloudFormation: GitHub OIDC provider + Bedrock role for Actions |
| [workflows/agent-code.yml](workflows/agent-code.yml) | Workflow template to copy into a target repo |
| [docs/models.md](docs/models.md) | Model shortlist for this account and region, derived from `my-models.json` |

## Status

Phase 1 in progress: native Converse harness, sandboxed tools, per-role
config, coder role, `barney code` CLI. Reviewer and passes come in Phase 3.

## Run the coder locally (Phase 1)

In the devcontainer (or any shell with Python 3.11+):

```bash
pip install -e '.[dev]'
source scripts/aws_login.sh              # SSO -> AWS_PROFILE
export BARNEY_GITHUB_TOKEN=github_pat_...  # fine-grained PAT scoped to the target repo

# Offline dry run: no GitHub reads or writes, no push. Needs only Bedrock.
barney code --repo edlovesjava/aiotp1 --issue-file examples/issue-hello.json \
            --workdir ../aiotp1 --dry-run

# Real issue, still no writes to GitHub:
barney code --repo edlovesjava/aiotp1 --issue 1 --workdir ../aiotp1 --dry-run

# The real thing: posts the plan comment, pushes a branch, opens the PR.
barney code --repo edlovesjava/aiotp1 --issue 1 --workdir ../aiotp1
```

`--model`, `--harness` and `--region` override the coder role for one run.
`-v` turns on debug output on the console; a full DEBUG log always goes to
`barney-run.log` (change with `--log PATH`, disable with `--log ''`).
`--allow-dirty` lets a run start on a checkout with uncommitted changes.
The target's `barney.toml` and `BARNEY_CODER_*` env vars are the other two
layers (see `docs/spec.md` section 6). Every run writes `barney-run.json`.

## Development

```bash
ruff check . && ruff format --check . && pytest -q
```

## Phase 0: model access

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r scripts/requirements.txt
AWS_PROFILE=personal python scripts/check_model_access.py --region us-east-1
```

That prints, for each candidate model, whether your account is authorized,
entitled, and regionally able to invoke it, and optionally runs a one-token
smoke call with `--smoke`.
