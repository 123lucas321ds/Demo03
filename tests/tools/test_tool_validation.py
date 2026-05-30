from __future__ import annotations

from typing import Any

import pytest

from sc2_agent.tools.base import Tool


class SampleTool(Tool):
    @property
    def name(self) -> str:
        return "sample"

    @property
    def description(self) -> str:
        return "sample tool"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 2},
                "count": {"type": "integer", "minimum": 1, "maximum": 10},
                "mode": {"type": "string", "enum": ["fast", "full"]},
                "meta": {
                    "type": "object",
                    "properties": {
                        "tag": {"type": "string"},
                        "flags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["tag"],
                },
            },
            "required": ["query", "count"],
        }

    async def execute(self, **kwargs: Any) -> str:
        return "ok"


def test_validate_params_missing_required() -> None:
    errors = SampleTool().validate_params({"query": "hi"})

    assert "missing required count" in "; ".join(errors)


def test_validate_params_type_range_enum_and_length() -> None:
    tool = SampleTool()

    assert any("count must be >= 1" in e for e in tool.validate_params({"query": "hi", "count": 0}))
    assert any("query must be at least 2 chars" in e for e in tool.validate_params({"query": "h", "count": 2}))
    assert any("mode must be one of" in e for e in tool.validate_params({"query": "hi", "count": 2, "mode": "slow"}))


def test_validate_params_nested_object_and_array() -> None:
    errors = SampleTool().validate_params({"query": "hi", "count": 2, "meta": {"flags": [1, "ok"]}})

    assert any("missing required meta.tag" in e for e in errors)
    assert any("meta.flags[0] should be string" in e for e in errors)


@pytest.mark.parametrize(
    ("schema", "params", "expected"),
    [
        ({"type": "object", "properties": {"count": {"type": "integer"}}}, {"count": "42"}, 42),
        ({"type": "object", "properties": {"rate": {"type": "number"}}}, {"rate": "3.14"}, 3.14),
        ({"type": "object", "properties": {"enabled": {"type": "boolean"}}}, {"enabled": "true"}, True),
        ({"type": "object", "properties": {"name": {"type": "string"}}}, {"name": 123}, "123"),
    ],
)
def test_cast_params(schema: dict[str, Any], params: dict[str, Any], expected: Any) -> None:
    class CastTool(SampleTool):
        @property
        def parameters(self) -> dict[str, Any]:
            return schema

    cast = CastTool().cast_params(params)

    assert next(iter(cast.values())) == expected


def test_cast_params_array_items() -> None:
    class CastArrayTool(SampleTool):
        @property
        def parameters(self) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": {"nums": {"type": "array", "items": {"type": "integer"}}},
            }

    assert CastArrayTool().cast_params({"nums": ["1", "2", "3"]})["nums"] == [1, 2, 3]
