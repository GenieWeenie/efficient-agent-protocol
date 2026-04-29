import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from eap.environment.tools.example_tools import analyze_data, fetch_user_data
from eap.environment.tools.file_tools import (
    list_local_directory,
    read_local_file,
    write_local_file,
)
from eap.environment.tools.web_tools import (
    extract_links_from_url,
    fetch_json_url,
    scrape_url,
)


class ToolModuleTest(unittest.TestCase):
    def test_read_local_file_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "notes.txt"
            file_path.write_text("hello", encoding="utf-8")
            content = read_local_file("notes.txt", sandbox_root=tmp_dir)
        self.assertEqual(content, "hello")

    def test_read_local_file_missing_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(FileNotFoundError):
                read_local_file("does-not-exist-eap.txt", sandbox_root=tmp_dir)

    def test_write_local_file_overwrite_and_append(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_result = write_local_file("notes.txt", "hello", sandbox_root=tmp_dir)
            append_result = write_local_file("notes.txt", " world", mode="append", sandbox_root=tmp_dir)
            content = read_local_file("notes.txt", sandbox_root=tmp_dir)

        self.assertIn("Wrote 5 characters", write_result)
        self.assertIn("Appended 6 characters", append_result)
        self.assertEqual(content, "hello world")

    def test_write_local_file_missing_parent_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(FileNotFoundError):
                write_local_file("missing/notes.txt", "hello", sandbox_root=tmp_dir)

    def test_list_local_directory_non_recursive_excludes_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_local_file("a.txt", "a", sandbox_root=tmp_dir)
            write_local_file(".hidden.txt", "secret", sandbox_root=tmp_dir)
            write_local_file("sub/b.txt", "b", create_directories=True, sandbox_root=tmp_dir)

            output_json = list_local_directory(".", sandbox_root=tmp_dir)

        self.assertIn('"path": "a.txt"', output_json)
        self.assertIn('"path": "sub"', output_json)
        self.assertNotIn(".hidden.txt", output_json)
        self.assertNotIn("sub/b.txt", output_json)

    def test_list_local_directory_recursive_and_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_local_file("a.txt", "a", sandbox_root=tmp_dir)
            write_local_file("sub/b.txt", "b", create_directories=True, sandbox_root=tmp_dir)
            write_local_file("sub/c.txt", "c", sandbox_root=tmp_dir)

            output_json = list_local_directory(".", recursive=True, max_entries=2, sandbox_root=tmp_dir)

        self.assertIn('"truncated": true', output_json)
        self.assertIn('"entry_count": 2', output_json)

    def test_file_tools_reject_traversal_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with tempfile.TemporaryDirectory() as outside_dir:
                outside_file = Path(outside_dir) / "secret.txt"
                outside_file.write_text("secret", encoding="utf-8")
                traversal = f"../{Path(outside_dir).name}/secret.txt"
                with self.assertRaises(PermissionError):
                    read_local_file(traversal, sandbox_root=tmp_dir)

    def test_file_tools_reject_absolute_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with tempfile.NamedTemporaryFile(mode="w", delete=True) as handle:
                handle.write("secret")
                handle.flush()
                with self.assertRaises(PermissionError):
                    read_local_file(handle.name, sandbox_root=tmp_dir)
                with self.assertRaises(PermissionError):
                    write_local_file(handle.name, "overwrite", sandbox_root=tmp_dir)

    def test_file_tools_reject_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            with tempfile.NamedTemporaryFile(mode="w", delete=True) as handle:
                handle.write("secret")
                handle.flush()
                link_path = root / "escaped-link.txt"
                link_path.symlink_to(handle.name)
                with self.assertRaises(PermissionError):
                    read_local_file("escaped-link.txt", sandbox_root=tmp_dir)
                with self.assertRaises(PermissionError):
                    list_local_directory(".", sandbox_root=tmp_dir)

    def test_file_tool_root_env_configures_default_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "env-root.txt"
            file_path.write_text("configured", encoding="utf-8")
            with patch.dict("os.environ", {"EAP_FILE_TOOL_ROOT": tmp_dir}):
                self.assertEqual(read_local_file("env-root.txt"), "configured")

    def test_scrape_url_success(self) -> None:
        response = MagicMock()
        response.content = b"<html><body><h1>Title</h1><p>Body</p></body></html>"
        response.encoding = "utf-8"
        response.raise_for_status.return_value = None
        with patch("eap.environment.tools.web_tools.requests.get", return_value=response):
            text = scrape_url("https://example.com")
        self.assertIn("Title", text)
        self.assertIn("Body", text)

    def test_scrape_url_failure_raises_runtime_error(self) -> None:
        with patch("eap.environment.tools.web_tools.requests.get", side_effect=RuntimeError("network down")):
            with self.assertRaises(RuntimeError):
                scrape_url("https://example.com")

    def test_fetch_json_url_success(self) -> None:
        response = MagicMock()
        response.content = b'{"name":"eap","version":1}'
        response.encoding = "utf-8"
        response.raise_for_status.return_value = None
        with patch("eap.environment.tools.web_tools.requests.get", return_value=response):
            text = fetch_json_url("https://example.com/data.json")
        self.assertIn('"name": "eap"', text)
        self.assertIn('"version": 1', text)

    def test_fetch_json_url_invalid_json_raises_runtime_error(self) -> None:
        response = MagicMock()
        response.content = b"<html>not json</html>"
        response.encoding = "utf-8"
        response.raise_for_status.return_value = None
        with patch("eap.environment.tools.web_tools.requests.get", return_value=response):
            with self.assertRaises(RuntimeError):
                fetch_json_url("https://example.com/data.json")

    def test_extract_links_from_url_same_domain_only(self) -> None:
        response = MagicMock()
        response.content = (
            b'<html><body>'
            b'<a href="/a">A</a>'
            b'<a href="https://example.com/b">B</a>'
            b'<a href="https://other.com/c">C</a>'
            b"</body></html>"
        )
        response.encoding = "utf-8"
        response.raise_for_status.return_value = None
        with patch("eap.environment.tools.web_tools.requests.get", return_value=response):
            payload = extract_links_from_url(
                "https://example.com/base",
                same_domain_only=True,
                include_text=True,
            )

        parsed = json.loads(payload)
        self.assertEqual(parsed["link_count"], 2)
        self.assertEqual(parsed["links"][0]["url"], "https://example.com/a")
        self.assertEqual(parsed["links"][0]["text"], "A")

    def test_example_tools(self) -> None:
        raw = fetch_user_data("abc")
        self.assertIn("ABC", raw)
        summary = analyze_data("raw", "focus")
        self.assertIn("focus", summary)


if __name__ == "__main__":
    unittest.main()
