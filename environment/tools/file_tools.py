# environment/tools/file_tools.py
import json
import logging
import os

logger = logging.getLogger("eap.environment.tools.file_tools")

DEFAULT_MAX_READ_CHARACTERS = 200000
DEFAULT_MAX_LIST_ENTRIES = 200


def _validate_non_empty_path(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{field_name}' must be a non-empty string.")


def _build_entry_record(base_dir: str, full_path: str, is_dir: bool) -> dict:
    relative = os.path.relpath(full_path, base_dir)
    return {
        "path": relative,
        "type": "directory" if is_dir else "file",
        "size_bytes": None if is_dir else os.path.getsize(full_path),
    }


def read_local_file(file_path: str, max_characters: int = DEFAULT_MAX_READ_CHARACTERS) -> str:
    """Reads UTF-8 text from a local file with an explicit size guard."""
    logger.info(
        "tool invoked",
        extra={"tool_name": "read_local_file"},
    )
    _validate_non_empty_path(file_path, "file_path")
    if max_characters < 1:
        raise ValueError("'max_characters' must be >= 1.")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File '{file_path}' not found.")
    if os.path.isdir(file_path):
        raise IsADirectoryError(f"Path '{file_path}' is a directory, not a file.")

    with open(file_path, "r", encoding="utf-8") as handle:
        content = handle.read(max_characters + 1)

    if len(content) > max_characters:
        raise ValueError(
            f"File '{file_path}' exceeds max_characters={max_characters}. Increase the limit to read this file."
        )
    return content


def write_local_file(
    file_path: str,
    content: str,
    mode: str = "overwrite",
    create_directories: bool = False,
) -> str:
    """Writes or appends UTF-8 text to a local file."""
    logger.info(
        "tool invoked",
        extra={"tool_name": "write_local_file"},
    )
    _validate_non_empty_path(file_path, "file_path")
    if mode not in ("overwrite", "append"):
        raise ValueError("'mode' must be one of: overwrite, append.")

    absolute_path = os.path.abspath(file_path)
    parent = os.path.dirname(absolute_path)
    if parent and not os.path.exists(parent):
        if create_directories:
            os.makedirs(parent, exist_ok=True)
        else:
            raise FileNotFoundError(
                f"Parent directory '{parent}' not found. Set create_directories=True to create it."
            )
    if os.path.isdir(absolute_path):
        raise IsADirectoryError(f"Path '{file_path}' is a directory, not a file.")

    file_mode = "w" if mode == "overwrite" else "a"
    with open(absolute_path, file_mode, encoding="utf-8") as handle:
        written = handle.write(content)

    action = "Wrote" if mode == "overwrite" else "Appended"
    return f"{action} {written} characters to '{file_path}'."


def list_local_directory(
    directory_path: str,
    recursive: bool = False,
    include_hidden: bool = False,
    max_entries: int = DEFAULT_MAX_LIST_ENTRIES,
) -> str:
    """Lists local directory entries and returns structured JSON output."""
    logger.info(
        "tool invoked",
        extra={"tool_name": "list_local_directory"},
    )
    _validate_non_empty_path(directory_path, "directory_path")
    if max_entries < 1:
        raise ValueError("'max_entries' must be >= 1.")
    if not os.path.exists(directory_path):
        raise FileNotFoundError(f"Directory '{directory_path}' not found.")
    if not os.path.isdir(directory_path):
        raise NotADirectoryError(f"Path '{directory_path}' is not a directory.")

    base_dir = os.path.abspath(directory_path)
    entries = []
    truncated = False

    def _is_visible(name: str) -> bool:
        return include_hidden or not name.startswith(".")

    if recursive:
        for root, dirnames, filenames in os.walk(base_dir):
            if not include_hidden:
                dirnames[:] = [dirname for dirname in dirnames if _is_visible(dirname)]

            for dirname in sorted(dirnames):
                if len(entries) >= max_entries:
                    truncated = True
                    break
                full_path = os.path.join(root, dirname)
                entries.append(_build_entry_record(base_dir, full_path, is_dir=True))
            if truncated:
                break

            for filename in sorted(filenames):
                if not _is_visible(filename):
                    continue
                if len(entries) >= max_entries:
                    truncated = True
                    break
                full_path = os.path.join(root, filename)
                entries.append(_build_entry_record(base_dir, full_path, is_dir=False))
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
            entries.append(_build_entry_record(base_dir, entry.path, is_dir=entry.is_dir()))

    payload = {
        "directory_path": base_dir,
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
