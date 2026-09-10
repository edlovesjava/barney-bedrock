# Notable runs

A log of runs worth remembering, oldest first. Full run records live in the
`barney-run.json` artifacts; this file keeps the headline numbers and what we
learned. Add a row per interesting run.

| Date | Target | Model | Harness | Turns | Outcome | Learned |
|---|---|---|---|---|---|---|
| 2026-09-10 | aiotp1, `examples/issue-hello.json` (dry run, Codespace) | `us.amazon.nova-2-lite-v1:0` | native | 10 | success | Phase 1 gate passed. Called `post_plan` first, read the spec before writing, ran both verification commands itself, and when `pio` was missing it installed PlatformIO rather than claiming success. Never called `git_commit`; the harness committed the leftovers. Sub-second model latency except when reading the 8 KB spec. Exposed the need for a clean-worktree preflight (an aborted earlier run had left the agent branch dirty). |
