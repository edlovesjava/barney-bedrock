# Specification: Bedrock autonomous coding agent ("barney")

Status: **draft v1, for review**. Everything here is a proposal until the
reviewer (Ed) signs off. Open questions are collected at the end.

## 1. Goal

An autonomous agent, running on AWS Bedrock models, that turns a GitHub issue
into a pull request on a target repository, with a second agent posting a code
review on that PR. A human merges.

The system is an **experimentation platform**, so the design optimises for
swapping parts rather than for polish:

- swap the **model** (Claude, Nova, Llama, Mistral, DeepSeek, ...) with a flag
- swap the **harness** (our own Converse loop first, then Claude Code on
  Bedrock, Strands Agents, others) behind one interface
- grow from single agent to **multi-agent orchestration** without rewriting
  the tool layer or the GitHub integration
- work on **any target stack**. The first proof of concept is PlatformIO and
  ESP32 firmware, but the same agent must handle a Java REST service or a
  React and TypeScript front end with no change to agent code, only to the
  runtime image and the target's `CLAUDE.md`

## 2. Non-goals (for the first working version)

- Merging PRs. Never. A human merges.
- Addressing review comments in a loop. Coder opens PR, reviewer reviews once,
  human merges. The review loop is a later phase.
- Running on hardware. The first target is firmware, but verification in v1
  is compile plus native unit tests, not flashing a board.
- Non-firmware targets in v1. The design must not preclude them (see 5.5 and
  5.6), but the first PR is on aiotp1.
- Cost optimisation, prompt caching tuning, evals. Later.
- Security hardening beyond the guardrails in section 8. This is a personal
  account and a throwaway target repo.

## 3. Actors and repositories

| Actor | Where | Identity |
|---|---|---|
| Coder agent | GitHub Actions job in the **target** repo, or local CLI | GitHub App "barney-coder" (fine-grained PAT allowed in Phase 1) |
| Reviewer agent | GitHub Actions job in the target repo, or local CLI | GitHub App "barney-reviewer" (distinct identity so it can review the coder's PR) |
| Human | GitHub UI | Ed |
| Bedrock | us-east-1 | IAM role assumed via GitHub OIDC (Actions) or local AWS profile (CLI) |

| Repo | Role |
|---|---|
| `edlovesjava/barney-bedrock` | This repo. Agent code, prompts, infra-as-code, workflows to copy into targets, docs. |
| `edlovesjava/aiotp1` | Target. ESP32-S3 voice node firmware (see its `docs/product-spec.md`). Throwaway. |

The agent code never modifies its own repo during a run. A broken run can only
damage the target.

## 4. End-to-end flow (v1)

1. Ed opens an issue on the target repo and adds the label `agent`.
2. Workflow `agent-code.yml` fires. It checks out the target, assumes the AWS
   role via OIDC, installs barney, and runs `barney code --issue N`.
3. Coder agent:
   1. reads the issue and the repo's `CLAUDE.md` / `AGENTS.md` if present
   2. writes a short **refined spec and plan** as an issue comment
      (acceptance criteria, files it expects to touch, how it will verify)
   3. creates branch `agent/issue-N-<slug>`
   4. loops: read, edit, run build and tests, until acceptance criteria pass or
      a cap is hit
   5. commits with a descriptive message, pushes, opens a PR that links the
      issue and reports what it verified and what it could not
   6. if it gave up: still pushes the branch, opens a **draft** PR, and
      explains what blocked it
4. Workflow `agent-review.yml` fires on `pull_request: opened` when the author
   is the coder identity. Reviewer agent reads the diff, the issue, and the
   CI result, then submits one review: inline comments plus a summary with a
   verdict of `approve`, `comment`, or `request_changes`.
5. Ed reads both, merges or closes.

Every run writes a **run record** (JSON) as a workflow artifact: model id,
harness, token usage, tool calls, wall time, cost estimate, outcome. This is
the data that makes model and harness comparisons possible later.

## 5. Components

```
barney/
  config.py     run configuration: model, region, caps, harness name
  llm/          model adapters behind one interface
    converse.py Bedrock Converse API (model-agnostic; tool use, streaming)
  harness/      agent loops behind one interface
    native.py   our own loop over llm + tools (v1)
    claude_code.py  shell out to Claude Code CLI on Bedrock (Phase 4)
    strands.py  Strands Agents SDK (Phase 4)
  tools/        the tool surface exposed to the model
    fs.py       read_file, write_file, edit_file, list_files, grep
    shell.py    run_command in the checkout with timeout and output cap
    git.py      status, diff, commit, push, create_branch
    github.py   issue read/comment, PR create, review submit
  roles/
    coder.py    system prompt + tool subset + stop conditions
    reviewer.py system prompt + tool subset + stop conditions
  run_record.py usage, cost, and event logging
  cli.py        barney code | barney review | barney models
infra/
  iam/          CloudFormation: OIDC provider + role for the target repo
.github/workflows/   templates copied into the target repo
scripts/
  check_model_access.py
```

### 5.1 Model adapter (`llm`)

One interface: `complete(system, messages, tools) -> assistant_message` with
tool-use blocks normalised to a small internal type. The Converse API already
gives a single schema across Bedrock providers, so v1 is one adapter. The
model id is a **cross-region inference profile** (`us.anthropic...`,
`us.amazon.nova...`, `us.meta.llama...`) chosen by flag or env var.

Why Converse and not the Anthropic SDK: model-agnostic is a primary goal. The
Anthropic Bedrock client remains an option for a Claude-only adapter if we want
Claude-specific features (adaptive thinking, effort, 1M context) that Converse
exposes only through `additionalModelRequestFields`.

### 5.2 Harness (`harness`)

Interface: `run(task, tools, budget) -> Outcome`. The native harness is a
plain loop: call model, execute tool calls (in parallel when independent),
append results, repeat until the model stops or a cap trips. Later harnesses
wrap external agents but must emit the same run record.

### 5.3 Tools

Deliberately small. The model gets a shell, so most capability comes from
`run_command`. Dedicated file tools exist because they are cheaper and safer
than `sed` for edits. Tools run in the checkout directory only. Paths outside
the checkout are rejected. `run_command` has a per-call timeout and truncated
output.

Tool input schemas are kept deliberately simple: top-level `object`, only
`type`, `properties`, `required`, flat property types, no `$defs`, `anyOf`,
`default`, or nested objects. Amazon Nova rejects anything richer, and the
simpler shape helps every other model too. A schema linter in the tool layer
enforces this at import time.

### 5.4 GitHub integration

Via the GitHub REST API. Auth is a **token provider** interface with two
implementations: fine-grained PAT (Phases 1 and 2) and GitHub App installation
token (from Phase 3, when a second identity is required for the reviewer).
The default Actions `GITHUB_TOKEN` is never used, because PRs it opens do not
trigger other workflows, which would stop the reviewer from firing. The agent uses `git` over HTTPS with that token for push. Required
permissions: contents read/write, issues read/write, pull requests read/write,
metadata read. The reviewer app additionally needs pull requests write to
submit reviews. No admin, no actions, no secrets.

### 5.5 Verification inside the target

The agent does not decide what "verified" means. The target repo declares it
in `CLAUDE.md` under a `## Verification` heading: the exact commands to build,
lint and test. For aiotp1 that is `pio run` for firmware compile and
`pio test -e native` for host unit tests; for a Java service it would be
`./mvnw verify`; for a React app `npm ci && npm test && npm run build`. The
agent never hard-codes any of these. The coder must run them before opening
a non-draft PR and report the results in the PR body.

### 5.6 Runtime and images

Barney runs inside a container image, everywhere: locally with `docker run`,
in GitHub Actions as a `container:` job, and later on ECS Fargate. One image
per target stack, all sharing a base:

| Image | Contents | For |
|---|---|---|
| `ghcr.io/edlovesjava/barney:<tag>` | `python:3.12-slim`, git, barney, AWS CLI | base; pure-Python or shell targets |
| `ghcr.io/edlovesjava/barney-platformio:<tag>` | base + PlatformIO + `espressif32` platform and toolchains pre-installed | aiotp1 and other firmware targets |
| `ghcr.io/edlovesjava/barney-jdk:<tag>` | base + Temurin JDK 21 + Maven and Gradle | Java / REST targets (later) |
| `ghcr.io/edlovesjava/barney-node:<tag>` | base + Node 22 + pnpm | React / TypeScript targets (later) |

The target's `barney.toml` names its image under `[runtime] image = ...`. The
Actions workflow template reads that value, so adding a new stack is a new
Dockerfile in this repo plus one line in the target. Images are built and
pushed to GHCR by a workflow in this repo on every push to `main`, tagged
with the short SHA and `latest`. The run record stores the image digest.

Hosted runner specs for public repos are 4 vCPU, 16 GB RAM, 14 GB disk,
which is ample. The VM is the sandbox; the image is for reproducibility and
parity, not isolation.

## 6. Configuration

Configuration is **per role**. The coder and the reviewer are independent
agents that happen to share a codebase: each has its own model, harness,
prompt, tool subset, and caps. Nothing forces them to match, and the run
record captures both so a "GLM-5 coder reviewed by Qwen3 Coder Next" run is
distinguishable from any other pairing.

Precedence, lowest to highest: built-in defaults, `barney.toml` in the
**target** repo (so each target can pin its own pairing), environment
variables, CLI flags.

```toml
# barney.toml in the target repo (all keys optional)
[coder]
model   = "zai.glm-5"
harness = "native"            # native | claude_code | strands (Phase 4)
max_turns = 60
max_usd   = 5.00

[reviewer]
model   = "qwen.qwen3-coder-next"
harness = "native"
max_turns = 20
max_usd   = 1.00

[runtime]
image = "ghcr.io/edlovesjava/barney-platformio:latest"

[aws]
region = "us-east-1"
```

Environment variables are namespaced by role: `BARNEY_CODER_MODEL`,
`BARNEY_CODER_HARNESS`, `BARNEY_REVIEWER_MODEL`, and so on. CLI flags are
`--model` and `--harness` on the `barney code` and `barney review`
subcommands, which only ever apply to the role being run.

| Setting (per role) | Coder default | Reviewer default |
|---|---|---|
| `model` | `us.amazon.nova-2-lite-v1:0` while debugging, then `zai.glm-5` | `qwen.qwen3-coder-next` |
| `harness` | `native` | `native` |
| `max_turns` | 60 | 20 |
| `max_tool_seconds` | 300 per call | 300 per call |
| `max_input_tokens` | 3,000,000 cumulative | 1,000,000 cumulative |
| `max_usd` | 5.00 | 1.00 |
| `thinking` | provider default (off) | provider default (off) |

Shared settings: `aws.region` (`us-east-1`), GitHub auth (section 5.4).

The account inventory (`my-models.json`, analysed in `docs/models.md`) shows
GLM-5, Kimi K2.5, Qwen3 Coder Next, Devstral 2, DeepSeek V3.2 and MiniMax
M2.5 served on demand in us-east-1. Nova 2 Pro is not offered in the region.
GLM-5 is the intended production coder; Nova 2 Lite is for harness debugging.

## 7. Prompts

Prompts are files under `barney/roles/prompts/`, versioned with the code, and
the run record stores a hash of the prompt used. The coder prompt covers:
read before writing, small commits, run the verification commands, never
force-push, never touch `.github/workflows`, never modify CI to make it pass,
stop and open a draft PR when stuck. The reviewer prompt covers: review the
diff against the issue's acceptance criteria and the repo conventions, run
the verification commands yourself, cite file and line, be specific, do not
approve if tests were not run.

## 8. Guardrails

- Never merge. The apps do not receive permission to merge.
- Never push to the default branch. Branch protection on the target enforces
  it independently of the prompt.
- Never edit `.github/workflows/**` (enforced in the `git` tool, not only in
  the prompt), so the agent cannot widen its own permissions.
- Hard caps on turns, tokens, dollars, and per-command time. Exceeding any cap
  ends the run with a draft PR and an explanation.
- Bedrock IAM role is scoped to `bedrock:InvokeModel*` on the allowed model
  and inference-profile ARNs in us-east-1, nothing else.
- Actions workflow has a job timeout (60 min) as the outer limit.
- Every run is reproducible from its run record: model, prompt hash, issue
  snapshot, commit SHA.

## 9. Observability

- Run record JSON uploaded as an Actions artifact and summarised in the job
  summary (tokens, cost, turns, outcome).
- Agent posts a final comment on the issue with the same summary.
- Later: CloudWatch or a small results table for cross-run comparison.

## 10. Success criteria for "something working"

1. An `agent`-labelled issue on aiotp1 produces a PR from the coder identity
   within one Actions run, with a passing `pio run` recorded in the PR body.
2. The reviewer identity posts a review on that PR with at least one
   substantive inline comment.
3. Swapping `BARNEY_MODEL` to a non-Anthropic model (Nova Pro or Llama) and
   rerunning the same issue produces a PR, even if a worse one.
4. Both runs have complete run records with cost.

## 11. Open questions

1. ~~GitHub App vs PAT~~ Decided: PAT for Phases 1 and 2, Apps from Phase 3 (decision 14).
2. Should the coder be allowed network access beyond GitHub and Bedrock during
   a run (PlatformIO downloads toolchains and libraries from its registry)?
   Proposal: yes for now, since the target build needs it.
3. Reviewer verdict: should `request_changes` be allowed, or `comment` only so
   a bad reviewer cannot block? Proposal: allow all three, human merges anyway.
4. Do you want the refined spec and plan comment to be a **gate** (agent waits
   for a thumbs-up before coding) in v1, or fully autonomous? Proposal: fully
   autonomous in v1, gate as an option later.
