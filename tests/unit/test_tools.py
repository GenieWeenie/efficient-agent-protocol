import tempfile
import unittest
import json
import requests
from pathlib import Path
from unittest.mock import patch

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


class _MockStreamResponse:
    def __init__(
        self,
        chunks: list[bytes],
        *,
        encoding: str = "utf-8",
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._chunks = chunks
        self.encoding = encoding
        self.status_code = status_code
        self.headers = headers or {}
        self.is_redirect = status_code in {301, 302, 303, 307, 308}
        self.is_permanent_redirect = status_code in {301, 308}
        self.closed = False
        self.chunks_read = 0

    def iter_content(self, chunk_size: int = 1) -> object:
        del chunk_size
        for chunk in self._chunks:
            self.chunks_read += 1
            yield chunk

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def close(self) -> None:
        self.closed = True


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
        response = _MockStreamResponse([b"<html><body><h1>Title</h1><p>Body</p></body></html>"])
        with patch("eap.environment.tools.web_tools.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            with patch("eap.environment.tools.web_tools.requests.Session.get", return_value=response):
                text = scrape_url("https://example.com")
        self.assertIn("Title", text)
        self.assertIn("Body", text)

    def test_web_tools_reject_private_and_localhost_targets(self) -> None:
        private_cases = [
            ("http://10.0.0.1", "10.0.0.1"),
            ("http://169.254.169.254/latest/meta-data/", "169.254.169.254"),
            ("http://localhost:11434", "127.0.0.1"),
            ("http://100.64.0.1", "100.64.0.1"),
        ]
        for url, address in private_cases:
            with self.subTest(url=url):
                with patch("eap.environment.tools.web_tools.socket.getaddrinfo", return_value=[(2, 1, 6, "", (address, 80))]):
                    with self.assertRaises(ValueError):
                        scrape_url(url)

    def test_web_tools_allow_explicit_host_allowlist(self) -> None:
        response = _MockStreamResponse([b"<html><body>local page</body></html>"])
        with patch("eap.environment.tools.web_tools.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 80))]):
            with patch("eap.environment.tools.web_tools.requests.Session.get", return_value=response):
                text = scrape_url("http://127.0.0.1:8000", host_allowlist={"127.0.0.1"})
        self.assertIn("local page", text)

    def test_web_tools_allow_env_host_allowlist(self) -> None:
        response = _MockStreamResponse([b'{"ok": true}'])
        with patch.dict("os.environ", {"EAP_WEB_TOOL_HOST_ALLOWLIST": "127.0.0.1"}):
            with patch("eap.environment.tools.web_tools.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 80))]):
                with patch("eap.environment.tools.web_tools.requests.Session.get", return_value=response):
                    text = fetch_json_url("http://127.0.0.1:8000/data.json")
        self.assertIn('"ok": true', text)

    def test_web_tools_recheck_redirect_targets_for_ssrf(self) -> None:
        redirect = _MockStreamResponse([], status_code=302, headers={"Location": "http://127.0.0.1/admin"})
        getaddrinfo_results = [
            [(2, 1, 6, "", ("93.184.216.34", 80))],
            [(2, 1, 6, "", ("127.0.0.1", 80))],
        ]
        with patch("eap.environment.tools.web_tools.socket.getaddrinfo", side_effect=getaddrinfo_results):
            with patch("eap.environment.tools.web_tools.requests.Session.get", return_value=redirect):
                with self.assertRaises(RuntimeError):
                    scrape_url("http://example.com/start")

    def test_web_tools_streaming_byte_cap_stops_early(self) -> None:
        response = _MockStreamResponse([b"12345", b"67890", b"extra"])
        with patch("eap.environment.tools.web_tools.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 80))]):
            with patch("eap.environment.tools.web_tools.requests.Session.get", return_value=response):
                with self.assertRaises(RuntimeError):
                    scrape_url("http://example.com/large", max_bytes=7)
        self.assertEqual(response.chunks_read, 2)

    def test_scrape_url_failure_raises_runtime_error(self) -> None:
        with patch("eap.environment.tools.web_tools.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            with patch("eap.environment.tools.web_tools.requests.Session.get", side_effect=RuntimeError("network down")):
                with self.assertRaises(RuntimeError):
                    scrape_url("https://example.com")

    def test_fetch_json_url_success(self) -> None:
        response = _MockStreamResponse([b'{"name":"eap","version":1}'])
        with patch("eap.environment.tools.web_tools.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            with patch("eap.environment.tools.web_tools.requests.Session.get", return_value=response):
                text = fetch_json_url("https://example.com/data.json")
        self.assertIn('"name": "eap"', text)
        self.assertIn('"version": 1', text)

    def test_fetch_json_url_invalid_json_raises_runtime_error(self) -> None:
        response = _MockStreamResponse([b"<html>not json</html>"])
        with patch("eap.environment.tools.web_tools.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            with patch("eap.environment.tools.web_tools.requests.Session.get", return_value=response):
                with self.assertRaises(RuntimeError):
                    fetch_json_url("https://example.com/data.json")

    def test_extract_links_from_url_same_domain_only(self) -> None:
        response = _MockStreamResponse(
            [
                (
                    b'<html><body>'
                    b'<a href="/a">A</a>'
                    b'<a href="https://example.com/b">B</a>'
                    b'<a href="https://other.com/c">C</a>'
                    b"</body></html>"
                )
            ]
        )
        with patch("eap.environment.tools.web_tools.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            with patch("eap.environment.tools.web_tools.requests.Session.get", return_value=response):
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
