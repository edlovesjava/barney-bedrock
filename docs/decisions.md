# Decisions

Lightweight ADR log. One entry per decision, newest at the bottom.

| # | Decision | Alternatives | Why |
|---|---|---|---|
| 1 | Custom harness on Bedrock Converse API first | Claude Code on Bedrock first | Model-agnostic from day one; Claude Code becomes a second harness to compare against |
| 2 | GitHub Actions as v1 compute, OIDC to an AWS role | ECS Fargate, CodeBuild, Lambda | Free checkout, sandbox, and test runtime; no AWS infra beyond one IAM role. Fargate when jobs exceed limits |
| 3 | GitHub issue labelled `agent` is the spec input | Spec file in a directory | Natural place for the refined-spec comment and PR linkage |
| 4 | GitHub App identities (coder, reviewer); PAT allowed in Phase 1 | PAT only | Distinct reviewer identity; least privilege; PAT is faster to start |
| 5 | Separate infra repo (`barney-bedrock`) and target repo (`aiotp1`) | Same repo | A bad run cannot corrupt the agent's own code |
| 6 | Python | TypeScript | Bedrock samples and Strands Agents are Python-first |
| 7 | Region us-east-1, cross-region inference profiles (`us.*`) | Direct model ids | Widest model availability and quota |
| 8 | v1 review flow: coder opens PR, reviewer reviews once, human merges | Autonomous fix loop | Smallest thing that exercises both roles; loop is Phase 5 |
| 9 | Verification commands are declared by the target repo's `CLAUDE.md`, not by the agent | Agent infers how to test | Keeps the agent generic and makes "verified" auditable |
| 10 | Target theme: ESP32-S3 voice node with ESP-NOW, based on iotmesh patterns but with a new ESP-NOW transport | Reuse MeshSwarm/painlessMesh | painlessMesh is WiFi-based; ESP-NOW is the stated goal. iotmesh conventions (PlatformIO layout, serial commands, OLED status) carry over |
| 11 | Default model Amazon Nova 2 Lite; open-weight coders (Kimi K2.5, GLM 4.7, Qwen3 Coder Next, DeepSeek V3.2, MiniMax M2.1) as comparison set | Claude Sonnet | Anthropic and OpenAI models are not accessible in this AWS account. Nova 2 Lite is GA, Amazon-owned, cheap, 1M context with tool use. Open-weight coders score far higher on SWE-bench Verified and are served on demand by Bedrock |
| 12 | Tool schemas restricted to flat `type`/`properties`/`required` objects, enforced by a linter | Rich Pydantic schemas | Nova rejects `$defs`, `anyOf`, `default`, nested objects; flat schemas are portable across every Bedrock provider |
