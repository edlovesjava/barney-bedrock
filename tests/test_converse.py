from barney.llm import Message, ToolCall, ToolResult, ToolSpec
from barney.llm.converse import ConverseAdapter, provider_of


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def converse(self, **kw):
        self.calls.append(kw)
        return self.response


def test_provider_of():
    assert provider_of("us.amazon.nova-2-lite-v1:0") == "amazon"
    assert provider_of("zai.glm-5") == "zai"
    assert provider_of("global.anthropic.claude-x") == "anthropic"
    assert provider_of("moonshotai.kimi-k2.5") == "moonshotai"


def test_request_shape_and_decode():
    resp = {
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {"reasoningContent": {"reasoningText": {"text": "thinking..."}}},
                    {"text": "I will read the file."},
                    {"toolUse": {"toolUseId": "t1", "name": "read_file", "input": {"path": "a.py"}}},
                ],
            }
        },
        "stopReason": "tool_use",
        "usage": {"inputTokens": 100, "outputTokens": 20},
    }
    client = FakeClient(resp)
    ad = ConverseAdapter("us.amazon.nova-2-lite-v1:0", "us-east-1", client=client)
    tools = [
        ToolSpec(
            "read_file", "read", {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
        )
    ]
    history = [
        Message(role="user", text="do it"),
        Message(role="assistant", text="ok", tool_calls=[ToolCall("t0", "list_files", {})]),
        Message(role="user", tool_results=[ToolResult("t0", "a.py", is_error=False)]),
    ]
    comp = ad.complete("sys", history, tools, 1234)

    kw = client.calls[0]
    assert kw["modelId"] == "us.amazon.nova-2-lite-v1:0"
    assert kw["system"] == [{"text": "sys"}]
    assert kw["inferenceConfig"] == {"maxTokens": 1234}
    assert kw["toolConfig"]["tools"][0]["toolSpec"]["name"] == "read_file"
    assert "additionalModelRequestFields" not in kw
    msgs = kw["messages"]
    assert msgs[1]["content"] == [{"text": "ok"}, {"toolUse": {"toolUseId": "t0", "name": "list_files", "input": {}}}]
    assert msgs[2]["content"][0]["toolResult"]["status"] == "success"

    assert comp.stop_reason == "tool_use"
    assert comp.message.text == "I will read the file."
    assert comp.message.tool_calls == [ToolCall("t1", "read_file", {"path": "a.py"})]
    assert comp.usage.input_tokens == 100 and comp.usage.output_tokens == 20
    # raw content (with reasoning) is what gets replayed next turn
    client2 = FakeClient({**resp, "stopReason": "end_turn"})
    ad2 = ConverseAdapter("x.y", "us-east-1", client=client2)
    ad2.complete("", [Message(role="user", text="a"), comp.message], [], 10)
    replayed = client2.calls[0]["messages"][1]["content"]
    assert replayed[0] == {"reasoningContent": {"reasoningText": {"text": "thinking..."}}}
    assert "system" not in client2.calls[0] and "toolConfig" not in client2.calls[0]
