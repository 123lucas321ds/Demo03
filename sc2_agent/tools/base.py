"""Base classes for agent tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A normalized tool call emitted by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


class Tool(ABC):
    """Abstract base class for function-calling tools."""

    _TYPE_MAP = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    read_only: bool = True

    @property
    @abstractmethod
    def name(self) -> str:
        """Function name exposed to the model."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Short function description."""

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema object for parameters."""

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        """Execute the tool."""

    @staticmethod
    def _resolve_type(raw_type: Any) -> str | None:
        if isinstance(raw_type, list):
            return next((item for item in raw_type if item != "null"), None)
        return raw_type

    def to_schema(self) -> dict[str, Any]:
        """Return an OpenAI-compatible function schema."""

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def cast_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Safely cast model-provided params according to JSON Schema."""

        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            return params
        return self._cast_object(params, schema)

    def _cast_object(self, value: Any, schema: dict[str, Any]) -> Any:
        if not isinstance(value, dict):
            return value

        result: dict[str, Any] = {}
        properties = schema.get("properties", {})
        for key, item in value.items():
            item_schema = properties.get(key)
            result[key] = self._cast_value(item, item_schema) if item_schema else item
        return result

    def _cast_value(self, value: Any, schema: dict[str, Any] | None) -> Any:
        if not schema:
            return value

        target_type = self._resolve_type(schema.get("type"))
        if value is None:
            return None

        if target_type == "integer" and isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return value
        if target_type == "number" and isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return value
        if target_type == "boolean" and isinstance(value, str):
            lowered = value.lower()
            if lowered in {"true", "1", "yes"}:
                return True
            if lowered in {"false", "0", "no"}:
                return False
            return value
        if target_type == "string":
            return str(value)
        if target_type == "array" and isinstance(value, list):
            item_schema = schema.get("items")
            return [self._cast_value(item, item_schema) for item in value]
        if target_type == "object" and isinstance(value, dict):
            return self._cast_object(value, schema)
        return value

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """Validate params against the tool JSON Schema."""

        if not isinstance(params, dict):
            return [f"parameters must be object, got {type(params).__name__}"]

        schema = self.parameters or {"type": "object"}
        if schema.get("type", "object") != "object":
            return [f"schema for {self.name} must be object"]
        return self._validate(params, {**schema, "type": "object"}, "")

    def _validate(self, value: Any, schema: dict[str, Any], path: str) -> list[str]:
        errors: list[str] = []
        raw_type = schema.get("type")
        target_type = self._resolve_type(raw_type)
        nullable = (isinstance(raw_type, list) and "null" in raw_type) or schema.get("nullable", False)
        label = path or "parameter"

        if value is None and nullable:
            return []

        if target_type in self._TYPE_MAP:
            expected = self._TYPE_MAP[target_type]
            if target_type == "integer":
                if not isinstance(value, int) or isinstance(value, bool):
                    return [f"{label} should be integer"]
            elif target_type == "number":
                if not isinstance(value, expected) or isinstance(value, bool):
                    return [f"{label} should be number"]
            elif not isinstance(value, expected):
                return [f"{label} should be {target_type}"]

        if "enum" in schema and value not in schema["enum"]:
            errors.append(f"{label} must be one of {schema['enum']}")

        if target_type in {"integer", "number"}:
            if "minimum" in schema and value < schema["minimum"]:
                errors.append(f"{label} must be >= {schema['minimum']}")
            if "maximum" in schema and value > schema["maximum"]:
                errors.append(f"{label} must be <= {schema['maximum']}")

        if target_type == "string":
            if "minLength" in schema and len(value) < schema["minLength"]:
                errors.append(f"{label} must be at least {schema['minLength']} chars")
            if "maxLength" in schema and len(value) > schema["maxLength"]:
                errors.append(f"{label} must be at most {schema['maxLength']} chars")

        if target_type == "object":
            properties = schema.get("properties", {})
            for required in schema.get("required", []):
                if required not in value:
                    errors.append(f"missing required {path + '.' if path else ''}{required}")
            for key, item in value.items():
                if key in properties:
                    child_path = f"{path}.{key}" if path else key
                    errors.extend(self._validate(item, properties[key], child_path))

        if target_type == "array" and "items" in schema:
            for index, item in enumerate(value):
                child_path = f"{path}[{index}]" if path else f"[{index}]"
                errors.extend(self._validate(item, schema["items"], child_path))

        return errors
