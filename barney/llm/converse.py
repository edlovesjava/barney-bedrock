"""Amazon Bedrock Converse API adapter (model-agnostic)."""

from __future__ import annotations

import logging
import time
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from . import Completion, Message, ToolCall, ToolSpec, Usage

log = logging.getLogger(__name__)

# Per-provider request extras. Keyed by the provider segment of the model id
# (after an optional geo prefix such as ``us.``). Empty means "send nothing".
PROVIDER_EXTRAS: dict[str, dict[str, Any]] = {
    # e.g. "anthropic": {"thinking": {"type": "adaptive"}},
}


def provider_of(model_id: str) -> str:
    parts = model_id.split(".")
    if len(parts) >= 3 and len(parts[0]) <= 6:  # geo prefix like us., eu., global.
        return parts[1]
    return parts[0]


class ConverseAdapter:
    def __init__(self, model_id: str, region: str, client: Any = None, thinking: str = "off") -> None:
        self.model_id = model_id
        self.region = region
        self.thinking = thinking
        self.client = client or boto3.client(
            "bedrock-runtime",
            region_name=region,
            config=BotoConfig(
                retries={"max_attempts": 8, "mode": "adaptive"},
                read_timeout=600,
                connect_timeout=30,
            ),
        )

    # -- encoding -----------------------------------------------------------

    @staticmethod
    def _encode(messages: list[Message]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "assistant":
                if m.raw is not None:
                    out.append({"role": "assistant", "content": m.raw})
                    continue
                content: list[dict[str, Any]] = []
                if m.text:
                    content.append({"text": m.text})
                for tc in m.tool_calls:
                    content.append({"toolUse": {"toolUseId": tc.id, "name": tc.name, "input": tc.input}})
                out.append({"role": "assistant", "content": content})
            else:
                content = []
                for tr in m.tool_results:
                    content.append(
                        {
                            "toolResult": {
                                "toolUseId": tr.tool_call_id,
                                "content": [{"text": tr.content or "(empty)"}],
                                "status": "error" if tr.is_error else "success",
                            }
                        }
                    )
                if m.text:
                    content.append({"text": m.text})
                out.append({"role": "user", "content": content})
        return out

    @staticmethod
    def _tool_config(tools: list[ToolSpec]) -> dict[str, Any] | None:
        if not tools:
            return None
        return {
            "tools": [
                {"toolSpec": {"name": t.name, "description": t.description, "inputSchema": {"json": t.schema}}}
                for t in tools
            ]
        }

    # -- decoding -----------------------------------------------------------

    @staticmethod
    def _decode(resp: dict[str, Any]) -> tuple[Message, str]:
        content = resp["output"]["message"]["content"]
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for block in content:
            if "text" in block:
                text_parts.append(block["text"])
            elif "toolUse" in block:
                tu = block["toolUse"]
                inp = tu.get("input") or {}
                if not isinstance(inp, dict):
                    inp = {"_raw": inp}
                calls.append(ToolCall(id=tu["toolUseId"], name=tu["name"], input=inp))
            # reasoningContent and anything else: kept in raw, not surfaced.
        msg = Message(role="assistant", text="\n".join(text_parts).strip(), tool_calls=calls, raw=content)
        stop = resp.get("stopReason", "other")
        if stop not in ("end_turn", "tool_use", "max_tokens"):
            stop = "other:" + stop
        return msg, stop

    # -- call ---------------------------------------------------------------

    def complete(self, system: str, messages: list[Message], tools: list[ToolSpec], max_tokens: int) -> Completion:
        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "messages": self._encode(messages),
            "inferenceConfig": {"maxTokens": max_tokens},
        }
        if system:
            kwargs["system"] = [{"text": system}]
        tc = self._tool_config(tools)
        if tc:
            kwargs["toolConfig"] = tc
        extras = PROVIDER_EXTRAS.get(provider_of(self.model_id), {}) if self.thinking != "off" else {}
        if extras:
            kwargs["additionalModelRequestFields"] = extras

        t0 = time.monotonic()
        try:
            resp = self.client.converse(**kwargs)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            msg = e.response.get("Error", {}).get("Message", str(e))
            raise ModelError(f"{code}: {msg}", code=code) from e
        latency = time.monotonic() - t0

        message, stop = self._decode(resp)
        u = resp.get("usage", {})
        usage = Usage(
            input_tokens=u.get("inputTokens", 0),
            output_tokens=u.get("outputTokens", 0),
            cache_read_tokens=u.get("cacheReadInputTokens", 0),
            cache_write_tokens=u.get("cacheWriteInputTokens", 0),
        )
        return Completion(message=message, stop_reason=stop, usage=usage, latency_s=latency)


class ModelError(RuntimeError):
    def __init__(self, msg: str, code: str = "") -> None:
        super().__init__(msg)
        self.code = code

    @property
    def is_access(self) -> bool:
        return self.code in ("AccessDeniedException", "ResourceNotFoundException", "ValidationException")
