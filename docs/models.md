# Model shortlist for us-east-1

Derived from `my-models.json` (output of `aws bedrock list-foundation-models`,
2026-09-07). That listing proves a model is **served in the region**; it does
not prove this account is **authorized**. Marketplace models (everything not
from Amazon) may need a one-click agreement on first use. The first Converse
call, or `scripts/check_model_access.py`, settles that per model.

Invoke ids below are what goes in `BARNEY_MODEL`. Models tagged
`INFERENCE_PROFILE` only must be called through the `us.` cross-region
profile; `ON_DEMAND` models are called by their bare id.

## Tier 0: loop-debugging default

| Invoke id | Why |
|---|---|
| `us.amazon.nova-2-lite-v1:0` | Amazon-owned, no marketplace step, 1M context, reasoning + tool use, cheap, fast. Weakest coder on this list but the best model for finding harness bugs. |

Nova 2 Pro is **not** in the us-east-1 listing. Nova Premier is LEGACY. Nova
Pro / Lite / Micro (gen 1) are present but weaker than Nova 2 Lite.

## Tier 1: primary coder candidates (open weight, on demand)

| Invoke id | Notes |
|---|---|
| `zai.glm-5` | Newest GLM. GLM-5 class scores high-70s on SWE-bench Verified. First choice for the coder role. |
| `moonshotai.kimi-k2.5` | Strong agentic coder, similar tier to GLM-5. Second choice. |
| `qwen.qwen3-coder-next` | Coding-specialised, cheaper, good tool calling. |
| `mistral.devstral-2-123b` | Mistral's agentic-coding model. Worth one run. |
| `deepseek.v3.2` | Strong generalist with tool use. |
| `minimax.minimax-m2.5` | Large output windows, agentic coding focus. |

## Tier 2: also present, for comparison runs

| Invoke id | Notes |
|---|---|
| `zai.glm-4.7`, `zai.glm-4.7-flash` | Previous GLM; flash for cheap reviewer runs |
| `mistral.mistral-large-3-675b-instruct` | Large generalist |
| `us.meta.llama4-maverick-17b-instruct-v1:0` | Llama 4, profile required |
| `qwen.qwen3-coder-30b-a3b-v1:0` | Small fast coder, cheap reviewer candidate |
| `openai.gpt-oss-120b-1:0` | Apache-2 open weights served by AWS, not the OpenAI proprietary line. May or may not be blocked by the same entitlement. |
| `us.deepseek.r1-v1:0` | Reasoning model, slow, profile required |

## Not usable in this account

Anthropic (`anthropic.claude-*`) and OpenAI proprietary (`openai.gpt-5.6-*`)
are listed for the region but blocked at the account level. Left out of the
comparison until that changes.

## Role assignments for v1

| Role | Default | Fallback |
|---|---|---|
| Coder | `zai.glm-5` once the loop works; `us.amazon.nova-2-lite-v1:0` while debugging | `moonshotai.kimi-k2.5` |
| Reviewer | `qwen.qwen3-coder-next` | `zai.glm-4.7-flash` |

## Converse quirks to expect

- Nova: tool schemas must be flat (`type`, `properties`, `required` only).
- Reasoning models (GLM-5, Kimi K2.5, DeepSeek) may return reasoning content
  blocks; the adapter must pass them back unchanged on the next turn or drop
  them consistently, and must not count them as the assistant's text.
- Each provider has its own `additionalModelRequestFields` for thinking
  settings. The adapter keeps a per-provider table and defaults to none.
