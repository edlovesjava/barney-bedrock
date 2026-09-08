# Implementation plan

Each phase ends with a verification gate that must pass before the next phase
starts. Phases are small on purpose: the point is a working loop early, then
widening.

## Phase 0: Enablement (manual, ~1 hour)

Work in the AWS console and GitHub settings. Nothing here is code except the
check script.

- [ ] AWS: pick or create an IAM user or SSO profile for local runs
      (`AWS_PROFILE=personal`).
- [ ] AWS: run `python scripts/check_model_access.py --region us-east-1
      --smoke`. Record which Claude, Nova, Llama, Mistral profiles are
      `AUTHORIZED` + `AVAILABLE`. Submit the Anthropic use-case form once if
      Claude shows `NOT_AUTHORIZED` (console: Bedrock > Model catalog > any
      Anthropic model > Request access, or the CLI shown by the script).
- [ ] AWS: deploy `infra/iam/github-oidc.yaml` (Phase 2 writes it; can wait).
- [ ] GitHub: create a fine-grained PAT scoped to `aiotp1` with contents,
      issues, pull requests read/write. Store as `BARNEY_GITHUB_TOKEN` locally.
- [ ] GitHub: on `aiotp1`, protect `main` (require PR, no force push).
- [ ] Decide open questions 1 to 4 in `docs/spec.md`.

**Gate:** check script shows at least one Claude and one non-Claude model
`AUTHORIZED` and the smoke call returns text.

## Phase 1: Native harness, local run, issue to PR (code)

- [ ] `barney/` package skeleton with `pyproject.toml`, `ruff`, `pytest`.
- [ ] `config.py`: per-role config (`RoleConfig` for coder and reviewer), loaded from defaults, target `barney.toml`, env, CLI. Unit tests for precedence.
- [ ] `llm/converse.py`: Converse adapter, tool schema translation, usage
      capture, retry on throttling. Unit tests with recorded fixtures.
- [ ] `tools/fs.py`, `tools/shell.py`, `tools/git.py`: sandboxed to checkout,
      workflow-dir write block, timeouts, output caps. Unit tests.
- [ ] `tools/github.py`: read issue, comment, create PR (REST via `httpx`).
- [ ] `harness/native.py`: the loop, caps, parallel tool execution.
- [ ] `roles/coder.py` + prompt file. `run_record.py`.
- [ ] `cli.py`: `barney models`, `barney code --repo edlovesjava/aiotp1
      --issue N --workdir /path/to/checkout`.
- [ ] Seed `aiotp1` with the target skeleton (Phase 1 of its product spec) so
      the agent has a build to run. Done by hand or as the agent's very first
      issue with a human watching.

**Gate:** from a laptop, `barney code` on a trivial `aiotp1` issue ("add a
`docs/HELLO.md`") opens a PR with a run record. Then a real issue ("OLED
status screen") opens a PR whose body shows `pio run` passing.

## Phase 2: Run in GitHub Actions

- [ ] `infra/iam/github-oidc.yaml`: OIDC provider, role trusting
      `repo:edlovesjava/aiotp1:*`, policy allowing `bedrock:InvokeModel` and
      `bedrock:InvokeModelWithResponseStream` on the chosen profile ARNs.
- [ ] `.github/workflows/agent-code.yml` template: trigger on `issues:
      labeled` with label `agent`; checkout; `aws-actions/configure-aws-
      credentials` with the role; install PlatformIO; `pip install
      git+https://github.com/edlovesjava/barney-bedrock`; run `barney code`;
      upload run record; write job summary. 60 min timeout.
- [ ] Copy workflow into `aiotp1`, set repo variables (`BARNEY_MODEL`,
      `AWS_ROLE_ARN`) and secret (`BARNEY_GITHUB_TOKEN`, or App credentials).
- [ ] Optional now, required later: replace PAT with GitHub App
      `barney-coder` and mint installation tokens in the workflow.

**Gate:** labelling an issue on `aiotp1` produces a PR with no human
involvement. Run record artifact present.

## Phase 3: Reviewer

- [ ] `roles/reviewer.py` + prompt. Tools: read-only fs, shell (for running
      verification), github review submit (pending review, inline comments,
      submit with verdict).
- [ ] `barney review --repo --pr N`.
- [ ] GitHub App `barney-reviewer` (distinct identity is required to review
      the coder's PR meaningfully).
- [ ] `.github/workflows/agent-review.yml`: on `pull_request: opened` where
      `github.event.pull_request.user.login` is the coder identity.

**Gate:** the Phase 2 PR receives an inline review from the reviewer identity.
Success criteria 1 and 2 in the spec are met.

## Phase 4: Model and harness comparison

- [ ] Run the same issue with `BARNEY_MODEL` set to Nova Pro, Llama, and a
      second Claude tier. Collect run records. Small script to tabulate
      outcome, turns, tokens, cost.
- [ ] `harness/claude_code.py`: shell out to Claude Code CLI with
      `CLAUDE_CODE_USE_BEDROCK=1`, parse its JSON output into a run record.
- [ ] `harness/strands.py`: same task on Strands Agents SDK.
- [ ] Comparison doc with the numbers.

**Gate:** success criteria 3 and 4. A table comparing at least three models
and two harnesses on the same three issues.

## Phase 5: Review loop and multi-agent

- [ ] Coder responds to `request_changes` and pushes a revision (bounded
      rounds).
- [ ] Orchestrator role: split an epic issue into sub-issues, run coders in
      parallel on separate branches, integrate.
- [ ] Reviewer specialisations (correctness, embedded constraints, style) as
      parallel reviewers with a merge step.
- [ ] Move compute to ECS Fargate if Actions limits bite.

Not planned in detail yet. Revisit after Phase 4 data.

## Ordering notes

- Phase 0 and the `aiotp1` skeleton can proceed while Phase 1 code is
  written.
- Phase 2 IAM and workflow can be drafted during Phase 1 and tested at the end.
- Nothing in Phases 1 to 3 depends on the target being firmware except the
  PlatformIO install step in the workflow and the verification commands in
  the target's `CLAUDE.md`.
