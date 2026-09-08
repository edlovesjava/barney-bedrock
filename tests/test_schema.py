import pytest

from barney.tools import SchemaError, fs, git, lint_schema, shell


def test_all_builtin_tools_lint():
    for t in [*fs.TOOLS, *shell.TOOLS, *git.TOOLS]:
        lint_schema(t.name, t.schema)


@pytest.mark.parametrize(
    "schema, msg",
    [
        ({"type": "array"}, "top-level type"),
        ({"type": "object", "properties": {}, "required": [], "additionalProperties": False}, "top-level keys"),
        ({"type": "object", "properties": {"a": {"type": "object"}}, "required": []}, "type must be one of"),
        (
            {"type": "object", "properties": {"a": {"type": "string", "default": "x"}}, "required": []},
            "keys not allowed",
        ),
        (
            {"type": "object", "properties": {"a": {"type": "string", "enum": ["x"]}}, "required": []},
            "keys not allowed",
        ),
        ({"type": "object", "properties": {"a": {"type": "string"}}, "required": ["b"]}, "required must list"),
    ],
)
def test_rejects_nova_incompatible(schema, msg):
    with pytest.raises(SchemaError, match=msg):
        lint_schema("t", schema)
