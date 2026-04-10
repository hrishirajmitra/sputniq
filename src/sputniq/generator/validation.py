"""Build-time validation helpers for entrypoints and config semantics."""

from __future__ import annotations

import ast
from pathlib import Path

from sputniq.config.errors import BuildValidationError, ValidationError
from sputniq.models.platform import SputniqConfig

_JSON_SCHEMA_TYPES = {"string", "number", "integer", "boolean", "object", "array", "null"}


def validate_runtime_contracts(config: SputniqConfig) -> None:
    """Validate semantic rules required by the runtime."""
    models = {model.id: model for model in config.models}

    for agent in config.agents:
        model = models.get(agent.model)
        if model is None:
            continue
        if agent.tools and "function-calling" not in model.capabilities:
            raise ValidationError(
                f"Agent '{agent.id}' uses tools but model '{agent.model}' "
                "does not declare 'function-calling' capability"
            )

    for tool in config.tools:
        _validate_schema_block(tool.id, tool.schema_def.input, "input")
        _validate_schema_block(tool.id, tool.schema_def.output, "output")


def _validate_schema_block(tool_id: str, schema: object, section: str, path: str = "root") -> None:
    if isinstance(schema, dict):
        schema_type = schema.get("type")
        if isinstance(schema_type, str) and schema_type not in _JSON_SCHEMA_TYPES:
            raise ValidationError(
                f"Tool '{tool_id}' {section} schema at '{path}' declares unsupported type '{schema_type}'"
            )
        if isinstance(schema_type, list):
            invalid = [item for item in schema_type if item not in _JSON_SCHEMA_TYPES]
            if invalid:
                raise ValidationError(
                    f"Tool '{tool_id}' {section} schema at '{path}' declares unsupported types {invalid}"
                )
        for key, value in schema.items():
            _validate_schema_block(tool_id, value, section, f"{path}.{key}")
    elif isinstance(schema, list):
        for index, value in enumerate(schema):
            _validate_schema_block(tool_id, value, section, f"{path}[{index}]")


def validate_source_tree(config: SputniqConfig, source_root: Path) -> None:
    """Validate entrypoint files, syntax, and exported symbols."""
    for agent in config.agents:
        _validate_entrypoint(agent.entrypoint, source_root, kind="agent", entity_id=agent.id)

    for tool in config.tools:
        _validate_entrypoint(tool.entrypoint, source_root, kind="tool", entity_id=tool.id)


def _validate_entrypoint(entrypoint: str, source_root: Path, *, kind: str, entity_id: str) -> None:
    if ":" not in entrypoint:
        raise BuildValidationError(
            f"{kind.title()} '{entity_id}' entrypoint '{entrypoint}' must use file.py:Symbol format"
        )

    file_part, symbol = entrypoint.split(":", 1)
    file_path = source_root / file_part
    if not file_path.exists():
        raise BuildValidationError(
            f"{kind.title()} '{entity_id}' entrypoint file not found: {file_path}"
        )

    try:
        tree = ast.parse(file_path.read_text("utf-8"), filename=str(file_path))
    except SyntaxError as exc:
        raise BuildValidationError(
            f"{kind.title()} '{entity_id}' entrypoint contains invalid Python syntax: {exc.msg}"
        ) from exc

    target = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == symbol
        ),
        None,
    )
    if target is None:
        raise BuildValidationError(
            f"{kind.title()} '{entity_id}' entrypoint symbol '{symbol}' was not found in {file_path}"
        )

    if kind == "agent" and isinstance(target, ast.ClassDef):
        method_names = {
            node.name
            for node in target.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if not {"run", "process"} & method_names:
            raise BuildValidationError(
                f"Agent '{entity_id}' class '{symbol}' must define 'run' or 'process'"
            )
