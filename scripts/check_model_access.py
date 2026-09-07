#!/usr/bin/env python3
"""Report which Bedrock models this AWS account can invoke in a region.

Usage:
    python scripts/check_model_access.py --region us-east-1
    python scripts/check_model_access.py --region us-east-1 --smoke
    python scripts/check_model_access.py --region us-east-1 --provider anthropic

For each on-demand text model (optionally filtered by provider prefix) it prints the
authorization / entitlement / region availability reported by
bedrock:GetFoundationModelAvailability, plus the cross-region inference
profile id (us.<model-id>) you should pass to the agent when one exists.

--smoke additionally sends a one-token Converse request through each
available profile so you know the whole path works (IAM, quota, model).

Needs: bedrock:ListFoundationModels, bedrock:ListInferenceProfiles,
bedrock:GetFoundationModelAvailability, and for --smoke bedrock:InvokeModel
on the profiles.
"""
from __future__ import annotations

import argparse
import sys

import boto3
from botocore.exceptions import ClientError

# Model-id prefixes. Default is every provider; filter with --provider (e.g. amazon, qwen, moonshotai, zai, deepseek, minimax).
DEFAULT_PROVIDERS: tuple[str, ...] = ()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--provider", action="append", help="model-id prefix filter, repeatable; default: all providers")
    ap.add_argument("--smoke", action="store_true", help="send a 1-token Converse call to each available model")
    ap.add_argument("--all", action="store_true", help="include models with no cross-region profile and legacy models")
    args = ap.parse_args()
    providers = tuple(p.lower() for p in (args.provider or DEFAULT_PROVIDERS))

    bedrock = boto3.client("bedrock", region_name=args.region)
    runtime = boto3.client("bedrock-runtime", region_name=args.region)

    # Map base model id -> system-defined cross-region profile id (e.g. us.anthropic....)
    profiles: dict[str, str] = {}
    token = None
    while True:
        kw = {"typeEquals": "SYSTEM_DEFINED", "maxResults": 100}
        if token:
            kw["nextToken"] = token
        resp = bedrock.list_inference_profiles(**kw)
        for p in resp.get("inferenceProfileSummaries", []):
            pid = p["inferenceProfileId"]
            for m in p.get("models", []):
                base = m["modelArn"].split("/")[-1]
                # prefer the profile whose geo prefix matches this region (us. for us-east-1)
                if base not in profiles or pid.startswith(args.region.split("-")[0] + "."):
                    profiles[base] = pid
        token = resp.get("nextToken")
        if not token:
            break

    models = bedrock.list_foundation_models(byOutputModality="TEXT", byInferenceType="ON_DEMAND")["modelSummaries"]
    rows = []
    for m in models:
        mid = m["modelId"]
        if providers and mid.split(".")[0].lower() not in providers:
            continue
        if not args.all and m.get("modelLifecycle", {}).get("status") == "LEGACY":
            continue
        profile = profiles.get(mid)
        if not args.all and not profile:
            continue
        try:
            av = bedrock.get_foundation_model_availability(modelId=mid)
            auth = av.get("authorizationStatus", "?")
            ent = av.get("entitlementAvailability", "?")
            reg = av.get("regionAvailability", "?")
            agr = av.get("agreementAvailability", {}).get("status", "?")
        except ClientError as e:
            auth = ent = reg = agr = f"ERR:{e.response['Error']['Code']}"
        rows.append((mid, profile or "-", auth, ent, reg, agr))

    rows.sort()
    w = max(len(r[0]) for r in rows) if rows else 20
    wp = max(len(r[1]) for r in rows) if rows else 20
    print(f"{'model id':<{w}}  {'invoke with':<{wp}}  auth            entitle        region         agreement")
    for mid, profile, auth, ent, reg, agr in rows:
        print(f"{mid:<{w}}  {profile:<{wp}}  {auth:<15} {ent:<14} {reg:<14} {agr}")

    usable = [r for r in rows if r[2] == "AUTHORIZED" and r[3] == "AVAILABLE" and r[4] == "AVAILABLE" and r[1] != "-"]
    blocked = [r for r in rows if r[2] == "NOT_AUTHORIZED"]
    print()
    print(f"{len(usable)} model(s) usable now, {len(blocked)} need an access request or use-case form.")
    if blocked:
        print("For NOT_AUTHORIZED Anthropic models: Bedrock console > Model catalog > pick the model > "
              "Request access (one-time use-case form per account). Non-Anthropic marketplace models: "
              "`aws bedrock list-foundation-model-agreement-offers --model-id <id>` then "
              "`aws bedrock create-foundation-model-agreement --model-id <id> --offer-token <token>`.")

    if args.smoke:
        print("\nSmoke test (1 token each):")
        for mid, profile, *_ in usable:
            try:
                out = runtime.converse(
                    modelId=profile,
                    messages=[{"role": "user", "content": [{"text": "Reply with the single word: ok"}]}],
                    inferenceConfig={"maxTokens": 5},
                )
                text = out["output"]["message"]["content"][0].get("text", "").strip()
                usage = out["usage"]
                print(f"  OK   {profile}  -> {text!r}  in={usage['inputTokens']} out={usage['outputTokens']}")
            except ClientError as e:
                print(f"  FAIL {profile}  {e.response['Error']['Code']}: {e.response['Error']['Message'][:120]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
