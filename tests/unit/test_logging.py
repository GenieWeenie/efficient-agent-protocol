import io
import json
import unittest

from eap.protocol.logging_config import configure_logging


class LoggingConfigTest(unittest.TestCase):
    def test_plain_text_logging(self) -> None:
        stream = io.StringIO()
        logger = configure_logging(level="INFO", use_json=False, stream=stream)
        logger.info("plain-text-message")

        output = stream.getvalue()
        self.assertIn("INFO", output)
        self.assertIn("plain-text-message", output)

    def test_json_logging_includes_context_fields(self) -> None:
        stream = io.StringIO()
        logger = configure_logging(level="INFO", use_json=True, stream=stream)
        logger.info("json-message", extra={"step_id": "step-1", "tool_name": "tool-a"})

        line = stream.getvalue().strip()
        payload = json.loads(line)
        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["message"], "json-message")
        self.assertEqual(payload["step_id"], "step-1")
        self.assertEqual(payload["tool_name"], "tool-a")

    def test_redaction_filter_masks_sensitive_tokens(self) -> None:
        stream = io.StringIO()
        logger = configure_logging(level="INFO", use_json=False, stream=stream)
        logger.info("api_key=secret token:abc123 password=hunter2")

        output = stream.getvalue()
        self.assertIn("api_key=[REDACTED]", output)
        self.assertIn("token=[REDACTED]", output)
        self.assertIn("password=[REDACTED]", output)
        self.assertNotIn("secret", output)
        self.assertNotIn("abc123", output)
        self.assertNotIn("hunter2", output)


if __name__ == "__main__":
    unittest.main()
