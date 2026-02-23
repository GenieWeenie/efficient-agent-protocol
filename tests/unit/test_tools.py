import tempfile
import unittest
import json
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
        with tempfile.NamedTemporaryFile(mode="w", delete=True) as handle:
            handle.write("hello")
            handle.flush()
            content = read_local_file(handle.name)
        self.assertEqual(content, "hello")

    def test_read_local_file_missing_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            read_local_file("/tmp/does-not-exist-eap.txt")

    def test_write_local_file_overwrite_and_append(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = f"{tmp_dir}/notes.txt"
            write_result = write_local_file(file_path, "hello")
            append_result = write_local_file(file_path, " world", mode="append")
            content = read_local_file(file_path)

        self.assertIn("Wrote 5 characters", write_result)
        self.assertIn("Appended 6 characters", append_result)
        self.assertEqual(content, "hello world")

    def test_write_local_file_missing_parent_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_parent_path = f"{tmp_dir}/missing/notes.txt"
            with self.assertRaises(FileNotFoundError):
                write_local_file(missing_parent_path, "hello")

    def test_list_local_directory_non_recursive_excludes_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_local_file(f"{tmp_dir}/a.txt", "a")
            write_local_file(f"{tmp_dir}/.hidden.txt", "secret")
            write_local_file(f"{tmp_dir}/sub/b.txt", "b", create_directories=True)

            output_json = list_local_directory(tmp_dir)

        self.assertIn('"path": "a.txt"', output_json)
        self.assertIn('"path": "sub"', output_json)
        self.assertNotIn(".hidden.txt", output_json)
        self.assertNotIn("sub/b.txt", output_json)

    def test_list_local_directory_recursive_and_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            write_local_file(f"{tmp_dir}/a.txt", "a")
            write_local_file(f"{tmp_dir}/sub/b.txt", "b", create_directories=True)
            write_local_file(f"{tmp_dir}/sub/c.txt", "c")

            output_json = list_local_directory(tmp_dir, recursive=True, max_entries=2)

        self.assertIn('"truncated": true', output_json)
        self.assertIn('"entry_count": 2', output_json)

    def test_scrape_url_success(self) -> None:
        response = MagicMock()
        response.content = b"<html><body><h1>Title</h1><p>Body</p></body></html>"
        response.encoding = "utf-8"
        response.raise_for_status.return_value = None
        with patch("environment.tools.web_tools.requests.get", return_value=response):
            text = scrape_url("https://example.com")
        self.assertIn("Title", text)
        self.assertIn("Body", text)

    def test_scrape_url_failure_raises_runtime_error(self) -> None:
        with patch("environment.tools.web_tools.requests.get", side_effect=RuntimeError("network down")):
            with self.assertRaises(RuntimeError):
                scrape_url("https://example.com")

    def test_fetch_json_url_success(self) -> None:
        response = MagicMock()
        response.content = b'{"name":"eap","version":1}'
        response.encoding = "utf-8"
        response.raise_for_status.return_value = None
        with patch("environment.tools.web_tools.requests.get", return_value=response):
            text = fetch_json_url("https://example.com/data.json")
        self.assertIn('"name": "eap"', text)
        self.assertIn('"version": 1', text)

    def test_fetch_json_url_invalid_json_raises_runtime_error(self) -> None:
        response = MagicMock()
        response.content = b"<html>not json</html>"
        response.encoding = "utf-8"
        response.raise_for_status.return_value = None
        with patch("environment.tools.web_tools.requests.get", return_value=response):
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
        with patch("environment.tools.web_tools.requests.get", return_value=response):
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
