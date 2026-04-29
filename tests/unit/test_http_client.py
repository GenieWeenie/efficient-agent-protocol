import unittest
from unittest.mock import MagicMock

from eap.protocol.http_client import BoundedHTTPClient


class BoundedHTTPClientTest(unittest.TestCase):
    def test_uses_explicit_connect_and_read_timeout(self) -> None:
        session = MagicMock()
        response = MagicMock()
        session.post.return_value = response
        client = BoundedHTTPClient(timeout_seconds=12, session=session)

        result = client.post("https://example.com/v1/test", json={"ok": True})

        self.assertIs(result, response)
        self.assertEqual(session.post.call_args.kwargs["timeout"], (5.0, 12.0))

    def test_configures_pooling_and_bounded_retries(self) -> None:
        client = BoundedHTTPClient(timeout_seconds=30, max_retries=3, pool_connections=4, pool_maxsize=6)
        try:
            adapter = client._session.get_adapter("https://example.com")  # noqa: SLF001
            self.assertEqual(adapter.max_retries.total, 3)
            self.assertEqual(adapter.max_retries.connect, 3)
            self.assertEqual(adapter.max_retries.read, 3)
            self.assertEqual(adapter.max_retries.status, 3)
            self.assertIn(429, adapter.max_retries.status_forcelist)
            self.assertIn("POST", adapter.max_retries.allowed_methods)
            self.assertEqual(adapter._pool_connections, 4)  # noqa: SLF001
            self.assertEqual(adapter._pool_maxsize, 6)  # noqa: SLF001
        finally:
            client.close()

    def test_close_only_closes_owned_sessions(self) -> None:
        injected_session = MagicMock()
        injected = BoundedHTTPClient(timeout_seconds=10, session=injected_session)
        injected.close()
        injected_session.close.assert_not_called()

        owned = BoundedHTTPClient(timeout_seconds=10)
        owned._session.close = MagicMock()  # type: ignore[method-assign] # noqa: SLF001
        owned.close()
        owned._session.close.assert_called_once()  # noqa: SLF001


if __name__ == "__main__":
    unittest.main()
