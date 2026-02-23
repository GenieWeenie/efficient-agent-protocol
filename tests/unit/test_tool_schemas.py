import tempfile
import unittest

from eap.environment import InputValidationError, ToolRegistry
from eap.environment.tools import (
    ANALYZE_SCHEMA,
    EXTRACT_LINKS_SCHEMA,
    FETCH_JSON_SCHEMA,
    LIST_DIRECTORY_SCHEMA,
    READ_FILE_SCHEMA,
    SCRAPE_SCHEMA,
    WRITE_FILE_SCHEMA,
    analyze_data,
    extract_links_from_url,
    fetch_json_url,
    list_local_directory,
    read_local_file,
    scrape_url,
    write_local_file,
)


class ToolSchemaValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ToolRegistry()
        self.registry.register("read_local_file", read_local_file, READ_FILE_SCHEMA)
        self.registry.register("write_local_file", write_local_file, WRITE_FILE_SCHEMA)
        self.registry.register("list_local_directory", list_local_directory, LIST_DIRECTORY_SCHEMA)
        self.registry.register("analyze_data", analyze_data, ANALYZE_SCHEMA)
        self.registry.register("scrape_url", scrape_url, SCRAPE_SCHEMA)
        self.registry.register("fetch_json_url", fetch_json_url, FETCH_JSON_SCHEMA)
        self.registry.register("extract_links_from_url", extract_links_from_url, EXTRACT_LINKS_SCHEMA)

    def test_valid_payload_passes_validation(self) -> None:
        self.registry.validate_arguments("analyze_data", {"raw_data": "payload", "focus": "summary"})

    def test_missing_required_field_raises(self) -> None:
        with self.assertRaises(InputValidationError):
            self.registry.validate_arguments("analyze_data", {"raw_data": "payload"})

    def test_invalid_type_raises(self) -> None:
        with self.assertRaises(InputValidationError):
            self.registry.validate_arguments("scrape_url", {"url": 123})

    def test_hashed_tool_name_validation(self) -> None:
        hashed = self.registry.get_hashed_manifest()["read_local_file"]
        with tempfile.NamedTemporaryFile(mode="w", delete=True) as handle:
            handle.write("hello")
            handle.flush()
            self.registry.validate_arguments(hashed, {"file_path": handle.name})

    def test_strict_schema_rejects_unknown_field(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", delete=True) as handle:
            with self.assertRaises(InputValidationError):
                self.registry.validate_arguments(
                    "read_local_file",
                    {"file_path": handle.name, "unexpected": "value"},
                )

    def test_enum_constraint_is_enforced(self) -> None:
        with self.assertRaises(InputValidationError):
            self.registry.validate_arguments(
                "write_local_file",
                {"file_path": "/tmp/x.txt", "content": "x", "mode": "replace"},
            )

    def test_numeric_range_constraint_is_enforced(self) -> None:
        with self.assertRaises(InputValidationError):
            self.registry.validate_arguments(
                "list_local_directory",
                {"directory_path": "/tmp", "max_entries": 0},
            )

    def test_web_schema_string_length_constraint_is_enforced(self) -> None:
        with self.assertRaises(InputValidationError):
            self.registry.validate_arguments("fetch_json_url", {"url": ""})


if __name__ == "__main__":
    unittest.main()
