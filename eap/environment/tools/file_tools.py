from __future__ import annotations

# environment/tools/file_tools.py
import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("eap.environment.tools.file_tools")

DEFAULT_MAX_READ_CHARACTERS = 200000
DEFAULT_MAX_LIST_ENTRIES = 200
FILE_TOOL_ROOT_ENV = "EAP_FILE_TOOL_ROOT"


def _validate_non_empty_path(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{field_name}' must be a non-empty string.")


def _sandbox_root(sandbox_root: Optional[str] = None) -> Path:
    raw_root = sandbox_root or os.environ.get(FILE_TOOL_ROOT_ENV) or os.getcwd()
    root = Path(raw_root).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"File tool sandbox root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"File tool sandbox root is not a directory: {root}")
    return root


def _resolve_sandbox_path(path_value: str, *, field_name: str, sandbox_root: Optional[str] = None) -> tuple[Path, Path]:
    _validate_non_empty_path(path_value, field_name)
    root = _sandbox_root(sandbox_root)
    requested = Path(path_value).expanduser()
    candidate = requested if requested.is_absolute() else root / requested
    resolved = candidate.resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        raise PermissionError(
            f"Path '{path_value}' escapes the configured file tool sandbox root '{root}'."
        )
    return root, resolved


def _assert_existing_path_in_sandbox(
    path_value: str,
    *,
    field_name: str,
    sandbox_root: Optional[str] = None,
) -> tuple[Path, Path]:
    root, resolved = _resolve_sandbox_path(path_value, field_name=field_name, sandbox_root=sandbox_root)
    if not resolved.exists():
        raise FileNotFoundError(f"Path '{path_value}' not found inside file tool sandbox '{root}'.")
    # Resolve again with strict semantics so existing symlinks cannot escape after the loose pass.
    strict_resolved = resolved.resolve(strict=True)
    if strict_resolved != root and root not in strict_resolved.parents:
        raise PermissionError(
            f"Path '{path_value}' escapes the configured file tool sandbox root '{root}'."
        )
    return root, strict_resolved


def _assert_write_target_in_sandbox(file_path: str, *, sandbox_root: Optional[str] = None) -> tuple[Path, Path]:
    root, resolved = _resolve_sandbox_path(file_path, field_name="file_path", sandbox_root=sandbox_root)
    parent = resolved.parent
    if parent.exists():
        parent_resolved = parent.resolve(strict=True)
        if parent_resolved != root and root not in parent_resolved.parents:
            raise PermissionError(
                f"Parent directory for '{file_path}' escapes the configured file tool sandbox root '{root}'."
            )
        if resolved.exists():
            target_resolved = resolved.resolve(strict=True)
            if target_resolved != root and root not in target_resolved.parents:
                raise PermissionError(
                    f"Path '{file_path}' escapes the configured file tool sandbox root '{root}'."
                )
    return root, resolved


def _build_entry_record(sandbox_root: Path, base_dir: Path, full_path: Path, is_dir: bool) -> dict:
    resolved = full_path.resolve(strict=True)
    if resolved != sandbox_root and sandbox_root not in resolved.parents:
        raise PermissionError(
            f"Directory entry '{full_path}' escapes the configured file tool sandbox root '{sandbox_root}'."
        )
    relative = os.path.relpath(resolved, base_dir)
    return {
        "path": relative,
        "type": "directory" if is_dir else "file",
        "size_bytes": None if is_dir else resolved.stat().st_size,
    }


def read_local_file(
    file_path: str,
    max_characters: int = DEFAULT_MAX_READ_CHARACTERS,
    sandbox_root: Optional[str] = None,
) -> str:
    """Reads UTF-8 text from a local file with an explicit size guard."""
    logger.info(
        "tool invoked",
        extra={"tool_name": "read_local_file"},
    )
    if max_characters < 1:
        raise ValueError("'max_characters' must be >= 1.")
    root, resolved_path = _assert_existing_path_in_sandbox(
        file_path,
        field_name="file_path",
        sandbox_root=sandbox_root,
    )
    if resolved_path.is_dir():
        raise IsADirectoryError(f"Path '{file_path}' is a directory, not a file.")

    with resolved_path.open("r", encoding="utf-8") as handle:
        content = handle.read(max_characters + 1)

    if len(content) > max_characters:
        raise ValueError(
            f"File '{file_path}' inside sandbox '{root}' exceeds max_characters={max_characters}. "
            "Increase the limit to read this file."
        )
    return content


def write_local_file(
    file_path: str,
    content: str,
    mode: str = "overwrite",
    create_directories: bool = False,
    sandbox_root: Optional[str] = None,
) -> str:
    """Writes or appends UTF-8 text to a local file."""
    logger.info(
        "tool invoked",
        extra={"tool_name": "write_local_file"},
    )
    if mode not in ("overwrite", "append"):
        raise ValueError("'mode' must be one of: overwrite, append.")

    root, absolute_path = _assert_write_target_in_sandbox(file_path, sandbox_root=sandbox_root)
    parent = absolute_path.parent
    if not parent.exists():
        if create_directories:
            parent.mkdir(parents=True, exist_ok=True)
            parent_resolved = parent.resolve(strict=True)
            if parent_resolved != root and root not in parent_resolved.parents:
                raise PermissionError(
                    f"Parent directory for '{file_path}' escapes the configured file tool sandbox root '{root}'."
                )
        else:
            raise FileNotFoundError(
                f"Parent directory '{parent}' not found. Set create_directories=True to create it."
            )
    if absolute_path.exists() and absolute_path.is_dir():
        raise IsADirectoryError(f"Path '{file_path}' is a directory, not a file.")

    file_mode = "w" if mode == "overwrite" else "a"
    with absolute_path.open(file_mode, encoding="utf-8") as handle:
        written = handle.write(content)

    action = "Wrote" if mode == "overwrite" else "Appended"
    return f"{action} {written} characters to '{file_path}' inside sandbox '{root}'."


def list_local_directory(
    directory_path: str,
    recursive: bool = False,
    include_hidden: bool = False,
    max_entries: int = DEFAULT_MAX_LIST_ENTRIES,
    sandbox_root: Optional[str] = None,
) -> str:
    """Lists local directory entries and returns structured JSON output."""
    logger.info(
        "tool invoked",
        extra={"tool_name": "list_local_directory"},
    )
    if max_entries < 1:
        raise ValueError("'max_entries' must be >= 1.")
    sandbox_root_path, base_dir = _assert_existing_path_in_sandbox(
        directory_path,
        field_name="directory_path",
        sandbox_root=sandbox_root,
    )
    if not base_dir.is_dir():
        raise NotADirectoryError(f"Path '{directory_path}' is not a directory.")

    entries = []
    truncated = False

    def _is_visible(name: str) -> bool:
        return include_hidden or not name.startswith(".")

    if recursive:
        for current_root, dirnames, filenames in os.walk(base_dir):
            root_path = Path(current_root)
            if not include_hidden:
                dirnames[:] = [dirname for dirname in dirnames if _is_visible(dirname)]

            for dirname in sorted(dirnames):
                if len(entries) >= max_entries:
                    truncated = True
                    break
                full_path = root_path / dirname
                entries.append(_build_entry_record(sandbox_root_path, base_dir, full_path, is_dir=True))
            if truncated:
                break

            for filename in sorted(filenames):
                if not _is_visible(filename):
                    continue
                if len(entries) >= max_entries:
                    truncated = True
                    break
                full_path = root_path / filename
                entries.append(_build_entry_record(sandbox_root_path, base_dir, full_path, is_dir=False))
            if truncated:
                break
    else:
        with os.scandir(base_dir) as scan_iter:
            visible_items = sorted(
                (entry for entry in scan_iter if _is_visible(entry.name)),
                key=lambda item: item.name,
            )

        for entry in visible_items:
            if len(entries) >= max_entries:
                truncated = True
                break
            entries.append(_build_entry_record(sandbox_root_path, base_dir, Path(entry.path), is_dir=entry.is_dir()))

    payload = {
        "directory_path": str(base_dir),
        "sandbox_root": str(sandbox_root_path),
        "recursive": recursive,
        "include_hidden": include_hidden,
        "max_entries": max_entries,
        "truncated": truncated,
        "entry_count": len(entries),
        "entries": entries,
    }
    return json.dumps(payload)


READ_FILE_SCHEMA = {
    "name": "read_local_file",
    "description": "Reads UTF-8 text content from a local file path.",
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "minLength": 1,
                "description": "The local file path to read.",
            },
            "max_characters": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1000000,
                "description": "Maximum characters to read before failing.",
            },
        },
        "required": ["file_path"],
        "additionalProperties": False,
    },
}

WRITE_FILE_SCHEMA = {
    "name": "write_local_file",
    "description": "Writes or appends UTF-8 text to a local file path.",
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "minLength": 1,
                "description": "The local file path to write.",
            },
            "content": {
                "type": "string",
                "description": "UTF-8 text content to write to the file.",
            },
            "mode": {
                "type": "string",
                "enum": ["overwrite", "append"],
                "description": "Choose overwrite to replace content or append to add to existing content.",
            },
            "create_directories": {
                "type": "boolean",
                "description": "Create missing parent directories before writing.",
            },
        },
        "required": ["file_path", "content"],
        "additionalProperties": False,
    },
}

LIST_DIRECTORY_SCHEMA = {
    "name": "list_local_directory",
    "description": "Lists files/directories from a local directory and returns JSON metadata.",
    "parameters": {
        "type": "object",
        "properties": {
            "directory_path": {
                "type": "string",
                "minLength": 1,
                "description": "The local directory path to list.",
            },
            "recursive": {
                "type": "boolean",
                "description": "Whether to include nested entries recursively.",
            },
            "include_hidden": {
                "type": "boolean",
                "description": "Whether to include hidden entries (names starting with '.').",
            },
            "max_entries": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1000,
                "description": "Maximum number of entries to return.",
            },
        },
        "required": ["directory_path"],
        "additionalProperties": False,
    },
}
