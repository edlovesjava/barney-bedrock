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
| [docs/models.md](docs/models.md) | Model shortlist for this account and region, derived from `my-models.json` |

## Quick start (Phase 0)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r scripts/requirements.txt
AWS_PROFILE=personal python scripts/check_model_access.py --region us-east-1
```

That prints, for each candidate model, whether your account is authorized,
entitled, and regionally able to invoke it, and optionally runs a one-token
smoke call with `--smoke`.
